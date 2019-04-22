from common.log import logger as log
from common import util
from client.pipeline import Pipeline
import time
from enum import Enum
import threading
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

LOG_FIRST_AUDIO_COUNT = 5


class State(Enum):
    STOPPED = 1
    BUFFERING = 2
    PLAYING = 3


class BufferState(Enum):
    MONITOR_STARTING = 1
    MONITOR_STARVATION = 2
    MONITOR_BUFFERED = 3


class Channel(Enum):
    LEFT = 0
    RIGHT = 1
    STEREO = 2


class Player(util.Threadbase):
    signals = 'status'

    log_first_audio = LOG_FIRST_AUDIO_COUNT
    buffer_state = BufferState.MONITOR_STARTING
    last_status_time = None
    monitor_lock = threading.Lock()  # experimental
    NOF_STARVATION_ALERTS = 25
    starvation_alerts = NOF_STARVATION_ALERTS
    message_inhibit_time = time.time()
    realtime_operation = False

    def __init__(self, realtime):
        super(Player, self).__init__('player')
        self._pipeline = Pipeline(realtime)
        self.realtime_operation = realtime
        self.start()

    def terminate(self):
        self._pipeline.terminate()
        super().terminate()

    def process_server_message(self, message):
        command = message['command']

        if command == 'buffering':
            self.log_first_audio = LOG_FIRST_AUDIO_COUNT
            self.m_state = State.BUFFERING
            self.buffer_state = BufferState.MONITOR_STARTING
            if self.realtime_operation:
                self.realtime = False
                self._pipeline.construct_pipeline()

        elif command == 'playing':
            log.info('---- playing ----')

            """
            gstreamer has 3 time concepts:
            running-time = absolute-time - base-time

            running-time
                the real time spent in playing state. Running from 0 for a non-live source as here.
            absolute-time
                the current value of the gst clock. It is always running (hardware based)
            base-time
                normally selected so that the running-time statement above is true
                here the base time is set into the future since playing starts
                when the running time >= 0
            """

            if self.realtime:
                self.realtime = False
                return

            play_time = float(message['playtime'])
            play_time_ns = play_time * 1000000000

            # here the time precision is about to go out the window in the call to set_base_time. If and when we
            # are preempted then the timing can be off in the millisecond range which is by any standards super awful.
            # The loop is an attempt to get some kind of deterministic execution time.
            target_time_us = 37  # found empirically on an overclocked rpi 3B+
            target_window_us = 0.2

            for i in range(151):
                gst_setup_start = time.time()

                self._pipeline.pipeline.set_base_time( #  fixit messing around
                    self._pipeline.pipeline.get_pipeline_clock().get_time()
                    + play_time_ns
                    - time.time() * 1000000000)

                gst_setup_elapsed_us = (time.time() - gst_setup_start) * 1000000

                if (gst_setup_elapsed_us > target_time_us - i * target_window_us and
                    gst_setup_elapsed_us < target_time_us + i * target_window_us):
                    break

            setup_message = 'time setup took %.3f us in %i tries' % (gst_setup_elapsed_us, i)
            if i != 150:
                log.info(setup_message)
            else:
                log.error(setup_message)

            play_delay_ns = play_time_ns - time.time() * 1000000000

            self._pipeline.pipeline.set_start_time(Gst.CLOCK_TIME_NONE)

            self._pipeline.pipeline.set_state(Gst.State.PLAYING)

            self.m_state = State.PLAYING

            play_delay_secs = play_delay_ns / util.NS_IN_SEC
            self.playing_start_time = time.time() + play_delay_secs

            log.info('playing will start in %.9f sec' % play_delay_secs)

            self.last_status_time = time.time()

        elif command == 'stopping':
            log.info('---- stopping ----')
            if self.realtime_operation:
                self.realtime = True
                self._pipeline.construct_pipeline()
            else:
                self._pipeline.stop_pipeline()

            self.m_state = State.STOPPED
            self.playing_start_time = None
            self.buffer_state = BufferState.MONITOR_STARTING
            self.last_status_time = None

        else:
            self._pipeline.process_message(message)

    def print_stats(self):
        try:
            position, duration = self._pipeline.pipeline.query_position(Gst.Format.TIME)  # fixit messing around
            buffer_size = int(self._pipeline.last_queue.get_property('current-level-bytes'))
            duration_secs = int(duration) / util.NS_IN_SEC
            playtime_skew = (time.time() - self.playing_start_time) - duration_secs
            log.info("playing time %.3f sec, buffered %i bytes. Skew %.6f" %
                     (duration_secs, buffer_size, playtime_skew))
        except NameError:
            return True
        except Exception as e:
            log.error('internal error %s' % str(e))
            return True
        return playtime_skew > 1.0

    """
    For now playing is brutally restarted if the pipeline buffer suddenly dries out.
    In the current implementation this would be if the codec is trashing data which
    in turn should be investigated since it happens. If the audio is moved from tcp
    to a more elegant multicast then it makes more sense to be prepared for lost data
    and perhaps a strategy like this.
    """
    def pipeline_monitor(self):
        self.monitor_lock.acquire()

        buffer_size, currently_buffered = self._pipeline.get_buffer_values()

        if self.buffer_state == BufferState.MONITOR_STARTING:
            if currently_buffered > buffer_size:
                self.starvation_alerts = self.NOF_STARVATION_ALERTS
                self.buffer_state = BufferState.MONITOR_STARVATION
                log.info('monitor: initial buffering complete, sending buffered')
                self.emit('status', 'buffered')

        elif self.buffer_state == BufferState.MONITOR_STARVATION:
            if currently_buffered < 40000:
                self.starvation_alerts -= 1
                in_trouble = self.print_stats()
                if not self.starvation_alerts or in_trouble:
                    self.buffer_state = BufferState.MONITOR_BUFFERED
                    if in_trouble:
                        log.warning('monitor: pipeline is stalled, sending starvation')
                    else:
                        log.warning('monitor: low buffer size, sending starvation')
                    self.starvation_alerts = self.NOF_STARVATION_ALERTS
                    self.emit('status', 'starved')
            else:
                self.starvation_alerts = self.NOF_STARVATION_ALERTS

        else:
            if currently_buffered > buffer_size:
                self.buffer_state = BufferState.MONITOR_STARVATION
                log.info('monitor: buffer ready again, sending buffered')
                self.emit('status', 'buffered')

        self.monitor_lock.release()

    def new_audio(self, audio):
        self._pipeline.new_audio(audio)
        if audio:
            self.pipeline_monitor()

    def run(self):
        try:
            log.debug('player starting')

            while not self.terminated:
                time.sleep(0.1)

                self.pipeline_monitor()

                if (self._pipeline.is_playing() and
                    self.last_status_time and
                    (time.time() - self.last_status_time > 2)):
                    self.last_status_time = time.time()
                    self.print_stats()

        except Exception as e:
            log.critical('player thread exception %s' % str(e))

        log.debug('player exits')
