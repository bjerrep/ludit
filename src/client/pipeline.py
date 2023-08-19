import logging, time, threading
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

from enum import Enum
from common.log import logger as log
from common import util

GObject.threads_init()
Gst.init(None)


class Channel(Enum):
    LEFT = 0
    RIGHT = 1
    STEREO = 2


class Band(Enum):
    LOW = 0
    HIGH = 1


class FilterType(Enum):
    CHEBYCHEV = 0
    WINDOWED_FIR = 1


LOG_FIRST_AUDIO_COUNT = 5
DEFAULT_BUFFERING_COMPLETE_SAMPLES = 50000


class AudioFilter:
    def __init__(self, filter_type):
        self.filter_type = filter_type

    def lowpass(self, poles, cutoff):
        """ Returns a gstreamer pipeline string for a lowpass filter with the given parameters.
            Valid values for poles are 1,2 or 4 which might or might not make
            sense for specific filters. It will however be used for increasing filter slopes
            with increasing values for poles.
        """
        if self.filter_type == FilterType.CHEBYCHEV:
            lowpass_filter = f'audiocheblimit mode=low-pass poles={poles} cutoff={cutoff}'

        else:  # type == FilterType.WINDOWED_FIR:
            if poles == 1:
                length = 2001
            elif poles == 2:
                length = 4001
            else:
                length = 8001

            lowpass_filter = f'audiowsinclimit mode=low-pass length={length} cutoff={cutoff}'

        return lowpass_filter

    def highpass(self, poles, cutoff):
        """ See also lowpass()
        """
        if self.filter_type == FilterType.CHEBYCHEV:
            highpass_filter = f'audiocheblimit mode=high-pass poles={poles} cutoff={cutoff}'

        else:  # type == FilterType.WINDOWED_FIR:
            if poles == 1:
                length = 2001
            elif poles == 2:
                length = 4001
            else:
                length = 8001

            highpass_filter = f'audiowsinclimit mode=high-pass length={length} cutoff={cutoff}'

        return highpass_filter


class Pipeline(util.Base):
    signals = ('status', 'buffered', 'device_lock_quality')

    samplerate = None
    input_pipeline = None
    output_pipeline = None
    alsa_appsrc_first = None
    alsa_appsrc_second = None
    output_pipeline_launcher = None
    alsa_sink = None

    filter_buffer_size = DEFAULT_BUFFERING_COMPLETE_SAMPLES  # can be overruled from server via configuration file
    filter_alsa_buffer_ms = 20                               # Default. Overruled from server config
    filter = AudioFilter(FilterType.WINDOWED_FIR)
    buffering = 20000
    input_pipeline_appsrc = None

    source_gain = 1.0
    codec = 'pcm'
    remote_streaming_volumes = [0.0, 0.0]           # will incorporate any balance offsets

    player_volume = 0.3
    external_volume = 0.1

    balance = 0.0
    highlowbalance = 0.0
    xoverfreq = 1000.0
    xoverpoles = 4
    eq_bands = 10
    eq_band_gain = [0.0] * eq_bands
    channel_list = []
    alsa_hw_device = {'0': '', '1': ''}             # The default empty will be using default alsa device
                                                    # Overruled from local config.
    channel = False                                 # class Channel
    silence_bytes_added = 0                         # used by the Player class
    realtime = False
    enough_data_handle = None
    stereo = False
    stereo_enhance_depth = 0.0
    stereo_enhance_enabled = False
    noise_gate_level_db = None
    noise_gate_duration_secs = None

    log_first_audio = LOG_FIRST_AUDIO_COUNT
    silence_lock = threading.Lock()

    def __init__(self):
        pass

    def terminate(self):
        self.stop()

    def get_buffer_values(self):
        try:
            # self.alsa_sink.get_property('current-level-bytes')
            return self.filter_buffer_size, int(self.alsa_sink.get_property('buffer-time'))
        except:
            return self.filter_buffer_size, 0

    def realtime_enabled(self):
        return self.realtime

    def set_play_time(self, play_time_ns):
        log.debug(f'server setting play start time to {int(play_time_ns)} ns')

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

        # here the time precision is about to go out the window in the call to set_base_time in set_play_time().
        # If and when we are preempted then the timing can be off in the millisecond range which is by any
        # standards super awful.
        # The loop is an attempt to get some kind of deterministic execution time.

        target_time_us = 37.0  # found empirically on an overclocked rpi 3B+
        target_window_us = 0.2

        try:
            for i in range(151):
                gst_setup_start = time.time()

                self.output_pipeline.set_base_time(
                    self.output_pipeline.get_pipeline_clock().get_time()
                    + play_time_ns
                    - time.time() * util.NS_IN_SEC)

                gst_setup_elapsed_us = (time.time() - gst_setup_start) * 1000000

                if target_time_us - i * target_window_us < gst_setup_elapsed_us < target_time_us + i * target_window_us:
                    break
        except Exception as e:
            log.error(f'got fatal exception {e}')
            log.error(f'{self.output_pipeline.get_pipeline_clock().get_time()} + {play_time_ns} - {time.time() * util.NS_IN_SEC}')
            raise e

        setup_message = 'time setup took %.3f us in %i tries' % (gst_setup_elapsed_us, i)
        if i != 150:
            log.info(setup_message)
        else:
            log.error(setup_message)

        self.output_pipeline.set_start_time(Gst.CLOCK_TIME_NONE)
        self.output_pipeline.set_state(Gst.State.PLAYING)

    def print_pipeline(self, title, pipeline):
        if log.level <= logging.DEBUG:
            print()
            print(f'------ {title} ------')
            print(pipeline)
            print()

    def bus_message_warning(self, _bus, _message):
        log.info('warning')
        return True

    def bus_message(self, _bus, message, _loop):
        if message.type == Gst.MessageType.EOS:
            log.debug('EOS')
        elif message.type == Gst.MessageType.ERROR:
            err, deb = message.parse_error()
            log.critical(f'{message.src.name}: pipeline error: {err} {deb}')
            self.emit('status', 'pipeline_error')
        elif message.type == Gst.MessageType.WARNING:
            err, deb = message.parse_warning()
            log.critical(f'{message.src.name}: pipeline warning: {err} {deb}')
        elif message.type == Gst.MessageType.STATE_CHANGED:
            #old_state, new_state, pending_state = message.parse_state_changed()
            #log.debug(f'* pipeline [{message.src.name}] state changed to {Gst.Element.state_get_name(new_state)}')

            if message.src in (self.appsink, self.alsa_sink):
                _old_state, new_state, pending_state = message.parse_state_changed()
                log.debug(f'* pipeline [{message.src.name}] state changed to {Gst.Element.state_get_name(new_state)}')
            elif message.src == self.input_decoder:
                _old_state, new_state, pending_state = message.parse_state_changed()
                if new_state == Gst.State.PLAYING:
                    # All this is just to print interesting caps from the decoder.
                    # The values are not currently sanity checked
                    decoder = self.input_pipeline.get_by_name('decoder')
                    caps = decoder.sinkpads[0].get_current_caps()
                    params = caps.get_structure(0)
                    rate = params.get_value('rate')
                    channels = params.get_value('channels')
                    log.debug(f'got caps on decoder: {rate}Hz {channels} channels')

        elif message.type == Gst.MessageType.BUFFERING:
            pct = message.parse_buffering()
            log.info(f'buffering {pct}')
        return True

    def cutter_message(self, bus, message):
        try:
            if message.has_name("cutter"):
                above = message.get_structure().get_value('above')
                if above:
                    self.emit('status', 'rt_play')
                else:
                    self.emit('status', 'rt_stop')
        except Exception as e:
            log.critical('[%s] parsing cutter message gave "%s"' % (self.name, str(e)))

    def add_silence(self, audio_bytes):
        log.info(f'adding {audio_bytes} bytes silence')
        audio = bytes(audio_bytes)

        with self.silence_lock:
            buf = Gst.Buffer.new_allocate(None, len(audio), None)
            buf.fill(0, audio)
            self.alsa_appsrc_first.emit('push-buffer', buf)
            self.silence_bytes_added += audio_bytes

    def get_pipeline_volume(self, channel):
        return self.remote_streaming_volumes[int(channel)]

    def get_channel_mask(self, band: Band, channel: int):
        """
        If playing stereo on a single soundcard then the 4 output channels
        needs to know where they should be located 'on the soundcard'. This
        is done by setting a gstreamer 'channel-mask' on each of the 4 channels.
        """
        if self.channel == Channel.STEREO and self.alsa_hw_device[0] == self.alsa_hw_device[1]:
            bitmasks = (0x01, 0x02, 0x10, 0x20)
            mask = bitmasks[channel * 2 + band.value]
            return 'audioconvert ! audio/x-raw,channels=1,channel-mask=(bitmask)%02x ! ' % mask
        return ''

    def new_audio(self, audio):
        # if the server issued a stop due to a starvation restart then this is a good
        # time to construct a new pipeline
        if not self.input_pipeline or not self.input_pipeline_appsrc:
            self.realtime = False
            self.construct_pipelines()

        if self.log_first_audio:
            self.log_first_audio -= 1
            log.debug('received %i bytes audio (%i)' % (len(audio), self.log_first_audio))

        if audio:
            with self.silence_lock:
                buf = Gst.Buffer.new_allocate(None, len(audio), None)
                buf.fill(0, audio)
                self.input_pipeline_appsrc.emit('push-buffer', buf)

        if self.buffering > 0:
            self.buffering -= len(audio)
            if self.buffering <= 0:
                self.emit('buffered')

    def decoder_new_sample_first_channel(self, sink):
        if self.alsa_appsrc_first:
            sample = sink.emit("pull-sample")
            buffer = sample.get_buffer()
            self.alsa_appsrc_first.emit('push-buffer', buffer)
        return Gst.FlowReturn.OK

    def decoder_new_sample_second_channel(self, sink):
        if self.alsa_appsrc_second:
            sample = sink.emit("pull-sample")
            buffer = sample.get_buffer()
            self.alsa_appsrc_second.emit('push-buffer', buffer)
        return Gst.FlowReturn.OK

    def construct_input_decoding_pipeline(self):
        """
        Construct the textual pipeline for playing either from alsa (realtime mode)
        or for playing encoded data from server.
        Used by construct_and_launch_input_pipeline() below.
        It will always output 2 channels / stereo.
        """

        try:
            if self.realtime:
                pipeline = (
                    'alsasrc device=hw:0 ! '
                    'cutter name=cutter leaky=false '
                    f'run-length={self.noise_gate_duration_secs * util.NS_IN_SEC} '
                    f'threshold-dB={self.noise_gate_level_db} ! '
                    'audioconvert ! audio/x-raw,format=F32LE,channels=2 ! queue ')

                log.info('constructing pipeline playing local alsa (realtime)')
            else:
                if self.codec == 'sbc':
                    decoder = 'sbcparse ! sbcdec name=decoder '
                    self.source_gain = 3.0
                elif self.codec == 'aac':
                    decoder = 'aacparse ! faad name=decoder'
                    self.source_gain = 0.5
                elif self.codec == 'aac_adts':
                    # e.g. audio generated with gstreamer "faac ! aacparse ! avmux_adts"
                    decoder = 'decodebin name=decoder'
                    self.source_gain = 0.5
                elif self.codec == 'pcm':
                    decoder = 'wavpackparse name=decoder ! wavpackdec'
                    self.source_gain = 1.0
                else:
                    log.critical("unknown codec '%s'" % self.codec)

                log.info(f'using gstreamer decoder "{decoder}"')

                pipeline = (
                    f'appsrc name=input_appsrc ! {decoder} ! '
                     'audioconvert ! audio/x-raw,format=F32LE,channels=2,layout=interleaved ! queue ! ')

            return pipeline

        except Exception as e:
            log.critical("couldn't construct decoding pipeline, %s" % str(e))
            raise e

    def construct_and_launch_input_pipeline(self):
        """
        Convert one of the channels left or right to a 'stereo' signal containing
        treble and bass for a normal single channel standalone two way speaker.
        Alternatively if the client is configured as a stereo speaker both input
        channels will be used and a total of two 'stereo' channels will be output
        with treble and bass for two speakers.
        The 'stereo' output for a speaker will be sent to an appsink. This will be
        configured to feed an appsrc in construct_and_launch_output_pipeline() below.
        """

        self.silence_bytes_added = 0

        try:
            lo, hi = self.calculate_highlowbalance(self.highlowbalance)
            self.update_pipeline_balance_and_volume()

            pipeline = self.construct_input_decoding_pipeline()

            pipeline += 'deinterleave name=d '

            for index, channel in enumerate(self.channel_list):

                channel_pipeline = f'd.src_{channel} ! '

                lo_mask = self.get_channel_mask(Band.LOW, int(channel))
                hi_mask = self.get_channel_mask(Band.HIGH, int(channel))

                try:
                    eq_band_gains = ''.join(
                        ['band%i=%f ' % (band, self.eq_band_gain[band]) for band in range(self.eq_bands)])
                    eq_setup = 'equalizer-10bands name=equalizer%s %s' % (channel, eq_band_gains)
                except Exception as e:
                    log.critical('equalizer setup failed with %s' % str(e))

                channel_pipeline += (
                    f'tee name=tee_{channel} '

                    f'interleave name=interleave_{channel} ! queue ! '
                    'capssetter caps = audio/x-raw,channels=2,channel-mask=0x3 ! '
                    'audioconvert ! queue max-size-bytes=1024 ! '
                    
                    f'appsink name=filtersrc_{channel} emit-signals=true sync=false '

                    f'tee_{channel}.src_0 ! queue ! '
                    f'{self.filter.lowpass(self.xoverpoles, self.xoverfreq)} name=lowpass{channel} ! '
                    f'{eq_setup} ! volume name=lowvol{channel} volume={lo} ! {lo_mask}interleave_{channel}.sink_0 '

                    f'tee_{channel}.src_1 ! queue ! '
                    f'{self.filter.highpass(self.xoverpoles, self.xoverfreq)} name=highpass{channel} ! '
                    f'volume name=highvol{channel} volume={hi} ! {hi_mask}interleave_{channel}.sink_1 ')

                self.print_pipeline(f'filter pipeline {channel}:', channel_pipeline)

                pipeline += channel_pipeline

            if self.realtime:
                log.info('constructing filter pipeline (local realtime)')
            else:
                log.info('constructing filter pipeline (server stream)')

            self.print_pipeline(f'filter pipeline', pipeline)

            self.input_pipeline = Gst.parse_launch(pipeline)
            self.input_pipeline.set_name('input_pipeline')

            for index, channel in enumerate(self.channel_list):
                self.appsink = self.input_pipeline.get_by_name(f'filtersrc_{channel}')
                if index == 0:
                    self.appsink.connect('new-sample', self.decoder_new_sample_first_channel)
                else:
                    self.appsink.connect('new-sample', self.decoder_new_sample_second_channel)

            self.input_pipeline_appsrc = self.input_pipeline.get_by_name('input_appsrc')
            self.input_decoder = self.input_pipeline.get_by_name('decoder')

            bus = self.input_pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect('message', self.bus_message, None)
            self.input_pipeline.set_state(Gst.State.PLAYING)
            self.buffering = 20000

        except Exception as e:
            log.critical("couldn't construct pipeline, %s" % str(e))
            raise e

    def construct_and_launch_output_pipeline(self):
        pipeline = ''

        for channel in self.channel_list:

            if self.channel == Channel.STEREO and self.alsa_hw_device['0'] != self.alsa_hw_device['1']:
                alsa_device = self.alsa_hw_device[channel]
            else:
                # left, right and single soundcard stereo will only use the first single alsa device.
                alsa_device = self.alsa_hw_device['0']

            log.debug(f'pipeline channel {channel} playing in alsa device "{alsa_device}"')
            if 0:
                channel_pipeline = (f'appsrc name=output_appsrc_{channel} ! '
                                    f'audio/x-raw,format=F32LE,channels=2,rate={self.samplerate},'
                                     'layout=interleaved,channel-mask=0x3 ! '
                                    f'audioconvert ! queue name=alsasinkqueue_{channel} ! '
                                    f'alsasink name=alsasink_{channel} sync=true {alsa_device}')
            else:
                channel_pipeline = (
                    f'appsrc name=output_appsrc_{channel} is-live=true format=time ! '
                    f'audio/x-raw,format=F32LE,channels=2,rate={self.samplerate},layout=interleaved ! audioconvert ! queue ! '
                    f'volume name=vol{channel} volume={self.get_pipeline_volume(int(channel))} ! '
                    f'alsasink name=alsasink_{channel} sync=true {alsa_device}')

            self.print_pipeline(f'alsa pipeline {channel}:', channel_pipeline)

            pipeline += channel_pipeline

        self.output_pipeline = Gst.parse_launch(pipeline)
        self.output_pipeline.set_name('output_pipeline')

        for index, channel in enumerate(self.channel_list):
            appsrc = self.output_pipeline.get_by_name(f'output_appsrc_{channel}')
            if index == 0:
                self.alsa_appsrc_first = appsrc
                self.alsa_sink = self.output_pipeline.get_by_name(f'alsasink_{channel}')
            else:
                self.alsa_appsrc_second = appsrc

        bus = self.output_pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.bus_message, None)

        self.output_pipeline.set_state(Gst.State.PAUSED)

    def construct_pipelines(self):
        if self.input_pipeline:
            log.error('internal error, stop old pipeline before launching a new')
            self.stop()
        self.construct_and_launch_input_pipeline()
        self.construct_and_launch_output_pipeline()

    def stop(self):
        if self.input_pipeline:
            # log.warning('writing pipeline dot file')
            # Gst.debug_bin_to_dot_file(self.pipeline, Gst.DebugGraphDetails.ALL, 'ludit_client')
            self.input_pipeline.set_state(Gst.State.NULL)
            self.input_pipeline = None

        if self.output_pipeline:
            self.output_pipeline.set_state(Gst.State.NULL)
            self.output_pipeline = None

    def update_pipeline_balance_and_volume(self):
        """
        Set the volume on the volume elements in the output pipeline for each channel.
        The volume depends on the 'player volume' which may come from the player
        (if from bluealsa always present on iphone, optionally on android) and the socalled
        'external volume' which is currently the volume setting on the ludit webpage.
        The two channel volumes implements balance as well and finally there is a correction
        for each codec type used which probably tries to normalize the volume from different
        players which is pretty rubbish.
        """
        for channel in self.channel_list:
            channel_int = int(channel)
            balance = 1.0
            if channel_int == 0 and self.balance > 0.0:
                balance = 1.0 - self.balance
            elif channel_int == 1 and self.balance < 0.0:
                balance = 1.0 + self.balance

            channel_vol = max(0.0005, self.player_volume * self.external_volume * self.source_gain * balance)
            self.remote_streaming_volumes[channel_int] = channel_vol
            if self.output_pipeline:
                log.debug('channel %s volume %.3f' % (channel, channel_vol))
                volume_element = self.output_pipeline.get_by_name('vol%s' % channel)
                volume_element.set_property('volume', channel_vol)

    def set_player_volume(self, player_volume):
        self.player_volume = player_volume
        self.update_pipeline_balance_and_volume()

    def set_external_volume(self, external_volume):
        self.external_volume = external_volume
        self.update_pipeline_balance_and_volume()

    def set_balance(self, balance):
        self.balance = balance
        log.debug('setting balance %.2f' % self.balance)
        self.update_pipeline_balance_and_volume()

    def calculate_highlowbalance(self, highlowbalance):
        self.highlowbalance = highlowbalance
        lowvol = 1.0
        highvol = 1.0
        if self.highlowbalance > 0.0:
            lowvol -= self.highlowbalance
        elif self.highlowbalance < 0.0:
            highvol += self.highlowbalance
        return lowvol, highvol

    def process_message(self, message):
        command = message['command']

        if command == 'setcodec':
            self.codec = message['codec']
            log.info("setting codec to '%s'" % self.codec)
            self.realtime = False

        elif command == 'setsamplerate':
            self.samplerate = message['samplerate']
            log.info("setting samplerate to '%s'" % self.samplerate)
            self.construct_pipelines()

        elif command == 'setvolume':
            volume = int(message['volume']) / 127.0
            log.debug('setting player volume %.5f' % volume)
            self.set_player_volume(volume)

        elif command == 'configure' or command == 'setparam':
            param = message['param']
            self.set_pipeline_parameter(param)

        elif command == 'device_lock_quality':
            self.emit('device_lock_quality', message)

        else:
            log.critical("got unknown server command '%s'" % command)

    def set_pipeline_parameter(self, param: dict):
        """
        Parameters will initially be set in two passes, first from reading
        the local client configuration and later from parameters sent by
        the server. Both these passes will predate the construction of the
        first pipeline.
        Later calls (e.g. volume) will see the value stored and also applied
        on any running pipeline immediately.
        """
        try:
            # the channel identifier from the server configuration, right, left or stereo
            channel_name = param['channel']
            self.channel = Channel[channel_name.upper()]
            if self.channel:
                log.info('device is configuring as "%s"' % self.channel)
                self.channel_list = []
                if self.channel == Channel.LEFT or self.channel == Channel.STEREO:
                    self.channel_list.append('0')
                if self.channel == Channel.RIGHT or self.channel == Channel.STEREO:
                    self.channel_list.append('1')
        except:
            pass

        alsa = param.get('alsa')
        if alsa:
            alsa_device = alsa['devices'][0]
            self.alsa_hw_device['0'] = 'device=%s' % alsa_device
            log.debug('first alsa device is %s' % alsa_device)

            try:
                alsa_device = alsa['devices'][1]
                self.alsa_hw_device['1'] = 'device=%s' % alsa_device
                log.debug('second alsa device is %s' % alsa_device)
            except:
                log.info('no second alsa device found, using alsa device "%s" for all outputs' % self.alsa_hw_device['0'])

        levels = param.get('levels')
        if levels:
            external_volume = levels.get('volume')
            if external_volume is not None:
                external_volume = float(external_volume) / 30.0
                log.debug('setting external volume %.5f' % external_volume)
                self.set_external_volume(external_volume)

            balance = levels.get('balance')
            if balance is not None:
                self.set_balance(float(balance) / 100.0)

            equalizer = levels.get('equalizer')
            if equalizer is not None:
                # Center frequencies 29 59 119 237 474 947 1889 3770 7523 15011
                for band in range(self.eq_bands):
                    att = equalizer.get('%i' % band)
                    if att:
                        self.eq_band_gain[band] = float(att)
                        log.debug('setting equalizer band %i to %f' % (band, self.eq_band_gain[band]))
                        if self.input_pipeline:
                            for channel in self.channel_list:
                                eq = self.input_pipeline.get_by_name('equalizer' + channel)
                                eq.set_property('band%i' % band, self.eq_band_gain[band])

        stereo_enhance = param.get('stereoenhance')
        if stereo_enhance:
            stereo_enhance_depth = stereo_enhance.get('depth')
            if stereo_enhance_depth:
                log.debug('setting stereoenhance depth %s' % stereo_enhance_depth)
                self.stereo_enhance_depth = float(stereo_enhance_depth)

            stereo_enhance_enabled = stereo_enhance.get('enabled')
            if stereo_enhance_enabled:
                log.debug('setting stereoenhance enable %s' % stereo_enhance_enabled)
                self.stereo_enhance_enabled = stereo_enhance_enabled == 'true'

        xover = param.get('xover')
        if xover:
            highlowbalance = xover.get('highlowbalance')
            if highlowbalance is not None:
                highlowbalance = float(highlowbalance)
                lo, hi = self.calculate_highlowbalance(highlowbalance)
                log.debug('setting high/low balance %.2f (low %.5f high %.5f)' %
                          (highlowbalance, lo, hi))
                if self.input_pipeline:
                    for channel in self.channel_list:
                        self.input_pipeline.get_by_name('highvol' + channel).set_property('volume', hi)
                        self.input_pipeline.get_by_name('lowvol' + channel).set_property('volume', lo)

            xoverfreq = xover.get('freq')
            if xoverfreq is not None:
                log.debug('setting xover frequency %s' % xoverfreq)
                self.xoverfreq = float(xoverfreq)
                if self.input_pipeline:
                    for channel in self.channel_list:
                        xlow = self.input_pipeline.get_by_name('lowpass' + channel)
                        xlow.set_property('cutoff', self.xoverfreq)
                        xhigh = self.input_pipeline.get_by_name('highpass' + channel)
                        xhigh.set_property('cutoff', self.xoverfreq)

            xoverpoles = xover.get('poles')
            if xoverpoles:
                log.debug('setting xover poles %s' % xoverpoles)
                self.xoverpoles = int(xoverpoles)
                if self.input_pipeline:
                    for channel in self.channel_list:
                        xlow = self.input_pipeline.get_by_name('lowpass' + channel)
                        xlow.set_property('poles', self.xoverpoles)
                        xhigh = self.input_pipeline.get_by_name('highpass' + channel)
                        xhigh.set_property('poles', self.xoverpoles)

        streaming = param.get('streaming')
        if streaming:
            encoded_buffersize = streaming.get('buffersize')
            if encoded_buffersize is not None:
                self.filter_buffer_size = encoded_buffersize
                log.debug('setting buffersize ready threshold %i' % self.filter_buffer_size)

            alsa_buffer_time = streaming.get('alsabuffertime_ms')
            if alsa_buffer_time is not None:
                self.filter_alsa_buffer_ms = alsa_buffer_time
                log.debug(f'setting alsa buffer time to {self.filter_alsa_buffer_ms}ms')

        realtime = param.get('realtime')
        if realtime is not None and realtime.get('enabled') == 'true':
            self.noise_gate_level_db = float(realtime.get('level_db'))
            self.noise_gate_duration_secs = int(float(realtime.get('duration_sec')))
            log.info('realtime mode enabled, threshold %.1f dB, duration %i secs' %
                     (self.noise_gate_level_db, self.noise_gate_duration_secs))
