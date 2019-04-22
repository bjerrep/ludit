from common.log import logger as log
from common import util
from enum import Enum
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, GObject, Gst
GObject.threads_init()
Gst.init(None)

LOG_FIRST_AUDIO_COUNT = 5


# HwCtrl

class State(Enum):
    STOPPED = 1
    BUFFERING = 2
    PLAYING = 3


class Channel(Enum):
    LEFT = 0
    RIGHT = 1
    STEREO = 2


class Pipeline:
    signals = 'status'

    pipeline = None
    appsrc_element = None
    last_queue = None
    m_state = State.STOPPED

    playing_start_time = None

    buffer_size = 100000

    mainloop = GLib.MainLoop()

    gain = 1.0
    codec = 'pcm'
    master_channel_volumes = [0.0, 0.0]
    balance = 0.0
    stereo_enhance_depth = 0.0
    stereo_enhance_enabled = False
    highlowbalance = 0.0
    xoverfreq = 1000
    xoverpoles = 4
    eq_bands = 10
    eq_band_gain = [0.0] * eq_bands
    user_volume = 0.3
    channel_list = []
    alsa_hw_device = {}
    realtime = False

    def __init__(self, realtime):
        self.realtime = realtime

    def terminate(self):
        self.mainloop.quit()
        self.stop_pipeline()

    def stop_pipeline(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

    def get_buffer_values(self):
        return self.buffer_size, int(self.last_queue.get_property('current-level-bytes'))

    def is_playing(self):
        return self.m_state != State.STOPPED

    def bus_message(self, bus, message):
        if message.type == Gst.MessageType.EOS:
            log.debug('EOS')
        elif message.type == Gst.MessageType.ERROR:
            err, deb = message.parse_error()
            log.critical("pipeline error: %s '%s'" % (err, deb))
            self.emit('status', 'pipeline_error')
        elif message.type == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            if message.src == self.pipeline:
                log.debug('* pipeline state changed to %s' % Gst.Element.state_get_name(new_state))

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

    def construct_pipeline(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)

        if self.codec == 'sbc':
            decoding = 'sbcparse ! sbcdec !'
            buffer_size = self.buffer_size
            self.gain = 3.0
        elif self.codec == 'aac':
            # decoding = 'aacparse ! avdec_aac !'
            decoding = 'decodebin !'
            buffer_size = self.buffer_size
            self.gain = 0.5
        elif self.codec == 'aac_adts':
            # audio generated with gstreamer "faac ! aacparse ! avmux_adts"
            decoding = 'decodebin !'
            buffer_size = self.buffer_size
            self.gain = 0.5
        elif self.codec == 'pcm':
            buffer_size = 200000
            decoding = 'decodebin !'
            self.gain = 1.0
        else:
            log.critical("unknown codec '%s'" % self.codec)

        try:
            lo, hi = self.calculate_highlowbalance(self.highlowbalance)
            self.set_volume(None)

            stereo_enhance_element = ''
            if self.stereo_enhance_enabled:
                stereo_enhance_element = 'audioconvert ! stereo stereo=%f ! ' % self.stereo_enhance_depth

            if self.realtime:
                pipeline = (
                    'alsasrc ! '
                    'cutter name=cutter leaky=false run-length=%i threshold-dB=%f ! '
                    'audioconvert ! audio/x-raw,format=F32LE,channels=2 ! queue ! deinterleave name=d ' %
                    (5 * util.NS_IN_SEC, -30.0))
                buffer_time = 100
            else:
                pipeline = (
                    'appsrc name=audiosource emit-signals=true max-bytes=%i ! %s %s '
                    'audioconvert ! audio/x-raw,format=F32LE,channels=2 ! queue ! deinterleave name=d ' %
                    (buffer_size, decoding, stereo_enhance_element))
                buffer_time = 200000

            for channel in self.channel_list:
                try:
                    eq_band_gains = ''.join(
                        ['band%i=%f ' % (band, self.eq_band_gain[band]) for band in range(self.eq_bands)])
                    eq_setup = 'equalizer-10bands name=equalizer%s %s ' % (channel, eq_band_gains)
                except Exception as e:
                    log.info('equalizer setup failed with %s' % str(e))
                    eq_setup = ''

                pipeline += (
                    'd.src_%s ! tee name=t%s '
                    'interleave name=i%s ! capssetter caps = audio/x-raw,channels=2,channel-mask=0x3 ! '
                    'audioconvert ! audioresample ! queue name=lastqueue%s max-size-time=20000000000 ! '
                    'volume name=vol%s volume=%f ! alsasink sync=true %s buffer-time=%d '
                    't%s.src_0 ! queue ! audiocheblimit poles=%i name=lowpass%s mode=low-pass cutoff=%f ! '
                    '%s ! volume name=lowvol%s volume=%f ! i%s.sink_0 '
                    't%s.src_1 ! queue ! audiocheblimit poles=%i name=highpass%s mode=high-pass cutoff=%f ! '
                    'volume name=highvol%s volume=%f ! i%s.sink_1 ' %
                    (channel, channel, channel, channel,
                     channel, self.master_channel_volumes[int(channel)], self.alsa_hw_device[channel], buffer_time,
                     channel, self.xoverpoles, channel, self.xoverfreq, eq_setup, channel, lo, channel,
                     channel, self.xoverpoles, channel, self.xoverfreq, channel, hi, channel))

            # print(pipeline)

            log.info('launching pipeline ...')
            self.pipeline = Gst.parse_launch(pipeline)
            if not self.realtime:
                self.appsrc_element = self.pipeline.get_by_name('audiosource')
            else:
                self.appsrc_element = None
            self.last_queue = self.pipeline.get_by_name('lastqueue' + self.channel_list[0])

            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.enable_sync_message_emission()
            bus.connect('message', self.bus_message)

            self.pipeline.set_state(Gst.State.PAUSED)
            if self.realtime:
                bus.connect('message::element', self.cutter_message)
                self.pipeline.set_state(Gst.State.PLAYING)

        except Exception as e:
            log.critical("couldn't construct pipeline, %s" % str(e))

    def set_volume(self, volume):
        if volume:
            self.user_volume = volume

        for channel in self.channel_list:
            channel_int = int(channel)
            balance = 1.0
            if channel_int == 0 and self.balance > 0.0:
                balance = 1.0 - self.balance
            elif channel_int == 1 and self.balance < 0.0:
                balance = 1.0 + self.balance

            channel_vol = max(0.0005, self.user_volume * self.gain * balance)
            self.master_channel_volumes[channel_int] = channel_vol
            if self.pipeline:
                volume_element = self.pipeline.get_by_name('vol%s' % channel)
                volume_element.set_property('volume', channel_vol)

    def set_balance(self, balance):
        self.balance = balance
        log.debug('setting balance %.2f' % self.balance)
        self.set_volume(None)

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
            self.construct_pipeline()

        elif command == 'setvolume':
            volume = int(message['volume']) / 127.0
            log.debug('setting volume %.4f' % volume)
            self.set_volume(volume)

        elif command == 'initialize':
            try:
                self.setup_alsa_rt(message['param']['alsasource'])
            except:
                pass
            self.configure_pipeline(message['param'])

        else:
            log.critical("got unknown command '%s'" % command)

    def setup_alsa_rt(self, configuration):
        if not configuration['enabled']:
            return

    def configure_pipeline(self, message):
        try:
            channel_name = message['channel']
            channel = Channel[channel_name.upper()]
            if channel:
                self.channel_list = []
                for device in message['general']['devices']:
                    if device['name'] == channel_name:
                        break

                log.info("processing setup '%s'. %s" % (message.get('name'), channel))
                if channel == Channel.LEFT or channel == Channel.STEREO:
                    self.channel_list.append('0')
                    try:
                        alsa_device = device['left_alsa_device']
                        self.alsa_hw_device['0'] = 'device=%s' % alsa_device
                        log.debug('left alsa device is %s' % alsa_device)
                    except:
                        self.alsa_hw_device['0'] = ''

                if channel == Channel.RIGHT or channel == Channel.STEREO:
                    self.channel_list.append('1')
                    try:
                        alsa_device = device['right_alsa_device']
                        self.alsa_hw_device['1'] = 'device=%s' % alsa_device
                        log.debug('right alsa device is %s' % alsa_device)
                    except:
                        self.alsa_hw_device['1'] = ''
        except:
            pass

        levels = message.get('levels')
        if levels:
            volume = levels.get('volume')
            if volume:
                volume = float(volume) / 100.0
                log.debug('setting volume %.4f' % volume)
                self.set_volume(volume)

            balance = levels.get('balance')
            if balance:
                self.set_balance(float(balance) / 100.0)

            equalizer = levels.get('equalizer')
            if equalizer:
                """
                Center frequencies 29 59 119 237 474 947 1889 3770 7523 15011
                """
                for band in range(self.eq_bands):
                    att = equalizer.get('%i' % band)
                    if att:
                        self.eq_band_gain[band] = float(att)
                        log.debug('setting equalizer band %i to %f' % (band, self.eq_band_gain[band]))
                        if self.pipeline:
                            for channel in self.channel_list:
                                eq = self.pipeline.get_by_name('equalizer' + channel)
                                eq.set_property('band%i' % band, self.eq_band_gain[band])

        stereo_enhance = message.get('stereoenhance')
        if stereo_enhance:
            stereo_enhance_depth = stereo_enhance.get('depth')
            if stereo_enhance_depth:
                log.debug('setting stereoenhance depth %s' % stereo_enhance_depth)
                self.stereo_enhance_depth = float(stereo_enhance_depth)

            stereo_enhance_enabled = stereo_enhance.get('enabled')
            if stereo_enhance_enabled:
                log.debug('setting stereoenhance enable %s' % stereo_enhance_enabled)
                self.stereo_enhance_enabled = stereo_enhance_enabled == 'true'

        xover = message.get('xover')
        if xover:
            highlowbalance = xover.get('highlowbalance')
            if highlowbalance:
                highlowbalance = float(highlowbalance)
                lo, hi = self.calculate_highlowbalance(highlowbalance)
                log.debug('setting high/low balance %.1f (low %.5f high %.5f)' %
                          (highlowbalance, lo, hi))
                if self.pipeline:
                    for channel in self.channel_list:
                        self.pipeline.get_by_name('highvol' + channel).set_property('volume', hi)
                        self.pipeline.get_by_name('lowvol' + channel).set_property('volume', lo)

            xoverfreq = xover.get('freq')
            if xoverfreq:
                log.debug('setting xover frequency %s' % xoverfreq)
                self.xoverfreq = float(xoverfreq)
                if self.pipeline:
                    for channel in self.channel_list:
                        xlow = self.pipeline.get_by_name('lowpass' + channel)
                        xlow.set_property('cutoff', self.xoverfreq)
                        xhigh = self.pipeline.get_by_name('highpass' + channel)
                        xhigh.set_property('cutoff', self.xoverfreq)

            xoverpoles = xover.get('poles')
            if xoverpoles:
                log.debug('setting xover poles %s' % xoverpoles)
                self.xoverpoles = int(xoverpoles)
                if self.pipeline:
                    for channel in self.channel_list:
                        xlow = self.pipeline.get_by_name('lowpass' + channel)
                        xlow.set_property('poles', self.xoverpoles)
                        xhigh = self.pipeline.get_by_name('highpass' + channel)
                        xhigh.set_property('poles', self.xoverpoles)

        buffersize = message.get('buffersize')
        if buffersize:
            self.buffer_size = int(buffersize)
            log.debug('setting buffersize %i' % self.buffer_size)

        if not self.pipeline and self.realtime:
            self.construct_pipeline()

    def new_audio(self, audio):
        # if the server issued a stop due to a starvation restart then this is a good
        # time to construct a new pipeline
        if not self.pipeline or not self.appsrc_element:
            self.construct_pipeline()

        if self.log_first_audio:
            self.log_first_audio -= 1
            log.debug('received %i bytes audio (%i)' % (len(audio), self.log_first_audio))

        if audio:
            buf = Gst.Buffer.new_allocate(None, len(audio), None)
            buf.fill(0, audio)
            self.appsrc_element.emit('push-buffer', buf)

