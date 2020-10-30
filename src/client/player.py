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
    MONITOR_IDLE = 1
    MONITOR_SILENCE = 2
    MONITOR_BUFFERED = 3


class Player(util.Threadbase):
    signals = ('status', 'message')

    buffer_state = BufferState.MONITOR_IDLE
    monitor_lock = threading.Lock()  # experimental
    last_status_time = 0
    NOF_STARVATION_ALERTS = 25
    starvation_alerts = NOF_STARVATION_ALERTS
    message_inhibit_time = time.time()
    server_audio_state = ServerAudioState.STOPPED
    playing_start_time = None
    playing = False
    low_buffer_handler = util.LowBufferHandler.starved
    bytes_per_sec = 0
    nof_bps_messages = 0
    silence_bytes = 0

    def __init__(self, configuration, hwctrl):
        super(Player, self).__init__('player')
        self.hwctrl = hwctrl
        use_cec = configuration.get('cec') == 'true'
        self.pipeline = Pipeline(use_cec)
        self.pipeline.connect('status', self.slot_pipeline_event)
        self.pipeline.connect('buffered', self.slot_pipeline_buffered)
        self.pipeline.set_pipeline_parameter(configuration)
        self.start()

    def terminate(self):
        self.pipeline.terminate()
        super().terminate()

    def is_playing(self):
        return self.server_audio_state != ServerAudioState.STOPPED

    def realtime_autostart(self):
        return self.pipeline.realtime_enabled() and self.playing

    def process_server_runtime_message(self, runtime):
        command = runtime['command']

        if command == 'buffering':
            self.pipeline.log_first_audio = LOG_FIRST_AUDIO_COUNT
            self.server_audio_state = ServerAudioState.BUFFERING
            self.buffer_state = BufferState.MONITOR_IDLE
            self.silence_bytes = 0
            if self.realtime_autostart():
                self.pipeline.construct_and_start_local_pipeline()
            self.hwctrl.play(True)

        elif command == 'playing':
            log.info(f'---- playing {self.pipeline.codec} '
                     f'({self.pipeline.decoder_sample_rate}Hz '
                     f'Channels:{self.pipeline.decoder_channels}) ----')

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

            target_time_us = 37.0  # found empirically on an overclocked rpi 3B+
            target_window_us = 0.2

            for i in range(151):
                gst_setup_start = time.time()

                if not self.pipeline.set_play_time(play_time_ns):
                    return

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

            if play_delay_secs > 0.02:
                log.info('playing will start in %.9f sec' % play_delay_secs)
            elif play_delay_secs > 0.0:
                log.warning('playing will start in %.9f sec (thats too close for comfort)' % play_delay_secs)
            else:
                log.error('playing will start in %.9f sec (thats a failed start)' % play_delay_secs)

        elif command == 'stopping':
            log.info('---- stopping ----')
            self.hwctrl.play(False)
            self.server_audio_state = ServerAudioState.STOPPED

            if self.realtime_autostart():
                self.pipeline.construct_and_start_local_pipeline()
            else:
                self.pipeline.stop_pipeline()
            self.playing_start_time = None
            self.buffer_state = BufferState.MONITOR_IDLE

    def process_server_message(self, message):
        """
        A message example (originating from webpage):
        {'command': 'setparam', 'name': 'stereo', 'param': {'general': {'playing': 'true'}}, 'ip': '192.168.1.126'}
        """
        runtime = message.get('runtime')
        if runtime:
            self.process_server_runtime_message(runtime)
            return

        command = message['command']
        if command == 'silence':
            samples = message["samples"]
            missing = samples - self.silence_bytes
            if missing > 0:
                log.warning(f'got new silence total {samples}, adjusting with {missing} samples')
                self.pipeline.add_silence(missing)
            elif missing < 0:
                log.warning(f'got new silence total {samples}, server lags behind, ignored')
            else:
                log.warning(f'got new silence total {samples}, in sync')

        else:
            before = self.realtime_autostart()

            try:
                self.playing = message['param']['general']['playing'] == 'true'
                log.info('group currently selected for playing: %s' % self.playing)
                if not self.playing:
                    self.pipeline.stop_pipeline()
                else:
                    self.nof_bps_messages = 10
                    self.last_status_time = time.time()
            except:
                pass

            # pipeline will be started if message contains 'setcodec'
            self.pipeline.process_message(message)

            if not before and self.realtime_autostart():
                self.pipeline.construct_and_start_local_pipeline()

    def print_stats(self):
        try:
            position, duration = self.pipeline.filter_pipeline.query_position(Gst.Format.TIME)
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

    def slot_pipeline_event(self, message):
        log.info(f'pipeline event: {message}')
        if message == 'rt_play':
            self.hwctrl.play(True)
        elif message == 'rt_stop':
            self.hwctrl.play(False)

    def slot_pipeline_buffered(self):
        """
        Triggered by the first 'enough-data' signal emitted by the filter pipeline. Inform the server.
        """
        self.buffer_state = BufferState.MONITOR_SILENCE
        log.info('pipeline is buffered')
        self.emit('status', 'buffered')

    def new_audio(self, audio):
        self.pipeline.new_audio(audio)
        self.bytes_per_sec += len(audio)

    def pipeline_silence_monitor(self):
        try:
            with self.monitor_lock:
                if self.buffer_state == BufferState.MONITOR_SILENCE:
                    action = False
                    with self.pipeline.silence_lock:
                        if self.silence_bytes != self.pipeline.silence_bytes_added:
                            # the pipeline inserted silence, inform the server about the new local grand total.
                            bytes_added = self.pipeline.silence_bytes_added - self.silence_bytes
                            self.silence_bytes = self.pipeline.silence_bytes_added
                            action = True
                    if action:
                        log.warning(f'silence monitor, {bytes_added} bytes added, '
                                    f'broadcast total {self.silence_bytes}')
                        self.emit('message', {'silence': self.silence_bytes})

                    # This is where a failing and apparently unrecoverable audio playback could be detected due
                    # to excessive silence insertions.
                    # Playback can be restarted with "self.emit('status', 'starved')"
        except:
            pass

    def run(self):
        try:
            log.debug('player starting')

            while not self.terminated:
                time.sleep(0.1)

                if self.server_audio_state != ServerAudioState.STOPPED:
                    self.pipeline_silence_monitor()

                if self.last_status_time and (time.time() - self.last_status_time > 2.0):
                    if self.playing_start_time and self.is_playing():
                        self.print_stats()

                    if self.bytes_per_sec and self.nof_bps_messages:
                        self.nof_bps_messages -= 1
                        log.debug('receiving %i bytes/sec%s' % (
                            int(self.bytes_per_sec / 2.0),
                            '' if self.nof_bps_messages else ' (automute)'))
                        self.bytes_per_sec = 0

                    self.last_status_time += 2.0

        except Exception as e:
            log.critical('player thread exception %s' % str(e))

        log.debug('player exits')
