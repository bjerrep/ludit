from common.log import logger as log
from common import util
from client.pipeline import Pipeline, LOG_FIRST_AUDIO_COUNT
import time
from enum import Enum
import threading
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst


class ServerAudioState(Enum):
    STOPPED = 1
    BUFFERING = 2
    PLAYING = 3


class BufferState(Enum):
    MONITOR_STARTING = 1
    MONITOR_STARVATION = 2
    MONITOR_BUFFERED = 3


class Player(util.Threadbase):
    signals = 'status'

    buffer_state = BufferState.MONITOR_STARTING
    last_status_time = None
    monitor_lock = threading.Lock()  # experimental
    NOF_STARVATION_ALERTS = 25
    starvation_alerts = NOF_STARVATION_ALERTS
    message_inhibit_time = time.time()
    server_audio_state = ServerAudioState.STOPPED
    playing_start_time = None
    playing = False

    def __init__(self, configuration, hwctrl):
        super(Player, self).__init__('player')
        self.hwctrl = hwctrl
        use_cec = configuration.get('cec') == 'true'
        self.pipeline = Pipeline(use_cec)
        self.pipeline.connect('status', self.pipeline_event)
        self.pipeline.set_pipeline_parameter(configuration)
        self.start()

    def terminate(self):
        self.pipeline.terminate()
        super().terminate()

    def is_playing(self):
        return self.server_audio_state != ServerAudioState.STOPPED

    def realtime_autostart(self):
        return self.pipeline.realtime_enabled() and self.playing

    def process_runtime_message(self, runtime):
        command = runtime['command']

        if command == 'buffering':
            self.pipeline.log_first_audio = LOG_FIRST_AUDIO_COUNT
            self.server_audio_state = ServerAudioState.BUFFERING
            self.buffer_state = BufferState.MONITOR_STARTING
            if self.realtime_autostart():
                self.pipeline.construct_and_start_local_pipeline()
            self.hwctrl.play(True)

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

            play_time = float(runtime['playtime'])
            play_time_ns = play_time * util.NS_IN_SEC

            # here the time precision is about to go out the window in the call to set_base_time in set_play_time().
            # If and when we are preempted then the timing can be off in the millisecond range which is by any
            # standards super awful.
            # The loop is an attempt to get some kind of deterministic execution time.

            target_time_us = 37  # found empirically on an overclocked rpi 3B+
            target_window_us = 0.2

            for i in range(151):
                gst_setup_start = time.time()

                self.pipeline.set_play_time(play_time_ns)

                gst_setup_elapsed_us = (time.time() - gst_setup_start) * 1000000

                if target_time_us - i * target_window_us < gst_setup_elapsed_us < target_time_us + i * target_window_us:
                    break

            setup_message = 'time setup took %.3f us in %i tries' % (gst_setup_elapsed_us, i)
            if i != 150:
                log.info(setup_message)
            else:
                log.error(setup_message)

            play_delay_ns = play_time_ns - time.time() * util.NS_IN_SEC

            self.pipeline.delayed_start()

            self.server_audio_state = ServerAudioState.PLAYING

            play_delay_secs = play_delay_ns / util.NS_IN_SEC
            self.playing_start_time = time.time() + play_delay_secs

            log.info('playing will start in %.9f sec' % play_delay_secs)

            self.last_status_time = time.time()

        elif command == 'stopping':
            log.info('---- stopping ----')
            self.hwctrl.play(False)
            self.server_audio_state = ServerAudioState.STOPPED

            if self.realtime_autostart():
                self.pipeline.construct_and_start_local_pipeline()
            else:
                self.pipeline.stop_pipeline()
            self.playing_start_time = None
            self.buffer_state = BufferState.MONITOR_STARTING
            self.last_status_time = None

    def process_server_message(self, message):
        """
        A message example (originating from webpage):
        {'command': 'setparam', 'name': 'stereo', 'param': {'general': {'playing': 'true'}}, 'ip': '192.168.1.126'}
        """
        runtime = message.get('runtime')
        if runtime:
            self.process_runtime_message(runtime)
        else:
            before = self.realtime_autostart()

            try:
                self.playing = message['param']['general']['playing'] == 'true'
                log.info('group currently selected for playing: %s' % self.playing)
                if not self.playing:
                    self.pipeline.stop_pipeline()
            except:
                pass

            # pipeline will be started if message contains 'setcodec'
            self.pipeline.process_message(message)

            if not before and self.realtime_autostart():
                self.pipeline.construct_and_start_local_pipeline()

    def print_stats(self):
        try:
            position, duration = self.pipeline.pipeline.query_position(Gst.Format.TIME)
            buffer_target, currently_buffered = self.pipeline.get_buffer_values()
            duration_secs = int(duration) / util.NS_IN_SEC
            playtime_skew = (time.time() - self.playing_start_time) - duration_secs
            log.info("playing time %.3f sec, buffered %i bytes. Skew %.6f" %
                     (duration_secs, currently_buffered, playtime_skew))
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
    def buffer_level_monitor(self):
        self.monitor_lock.acquire()

        buffer_target, currently_buffered = self.pipeline.get_buffer_values()

        if self.buffer_state == BufferState.MONITOR_STARTING:
            if currently_buffered > buffer_target:
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
            if currently_buffered > buffer_target:
                self.buffer_state = BufferState.MONITOR_STARVATION
                log.info('monitor: buffer ready again, sending buffered')
                self.emit('status', 'buffered')

        self.monitor_lock.release()

    def pipeline_event(self, message):
        log.info(f'pipeline event: {message}')
        if message == 'rt_play':
            self.hwctrl.play(True)
        elif message == 'rt_stop':
            self.hwctrl.play(False)

    def new_audio(self, audio):
        self.pipeline.new_audio(audio)
        if audio:
            self.buffer_level_monitor()

    def run(self):
        try:
            log.debug('player starting')

            while not self.terminated:
                time.sleep(0.1)

                if self.server_audio_state != ServerAudioState.STOPPED:
                    # normally there will be a gstreamer pipeline to query but things are not always normal..
                    if self.pipeline.has_pipeline():
                        self.buffer_level_monitor()

                    if (self.is_playing() and self.last_status_time and (time.time() - self.last_status_time > 2)):
                        self.last_status_time = time.time()
                        self.print_stats()

        except Exception as e:
            log.critical('player thread exception %s' % str(e))

        log.debug('player exits')
