from client import hwctl
from common.log import logger as log
from common import util
import time
from enum import Enum
import threading
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, GObject, Gst
GObject.threads_init()
Gst.init(None)

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


class Player(util.Threadbase):
    signals = 'status'

    pipeline = None
    last_queue = None
    m_state = State.STOPPED
    log_first_audio = LOG_FIRST_AUDIO_COUNT
    channel = None
    buffer_state = BufferState.MONITOR_STARTING
    monitor_lock = threading.Lock()  # experimental
    NOF_STARVATION_ALERTS = 25
    playing_start_time = None
    starvation_alerts = NOF_STARVATION_ALERTS
    buffer_size = 100000
    mainloop = GLib.MainLoop()
    gain = 1.0

    codec = 'pcm'
    volume = 0.01
    balance = 1.0
    highlowbalance = 0.0
    xoverfreq = 1000
    xoverpoles = 4
    band0 = 0.0
    band1 = 0.0
    user_volume = 0.3

    message_inhibit_time = time.time()

    def __init__(self):
        super(Player, self).__init__(name='playseq   ')
        self.hwctl = hwctl.HwCtl()
        self.start()

    def terminate(self):
        self.mainloop.quit()
        self.hwctl.play(False)
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        self.hwctl.terminate()
        super().terminate()

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

    def construct_pipeline(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)

        if self.codec == 'sbc':
            decoding = 'sbcparse ! sbcdec !'
            buffer_size = self.buffer_size
            self.gain = 3.0
        elif self.codec == 'aac':
            decoding = 'aacparse ! avdec_aac !'
            buffer_size = self.buffer_size
            self.gain = 0.5
        elif self.codec == 'pcm':
            buffer_size = 200000
            decoding = 'decodebin !'
            self.gain = 1.0
        else:
            log.critical("unknown codec '%s'" % self.codec)

        try:
            master_volume = max(0.0005, self.user_volume * self.gain * self.balance)

            lo, hi = self.calculate_highlowbalance(self.highlowbalance)

            pipeline = (
                'appsrc name=audiosource emit-signals=true max-bytes=%i ! %s '
                'audioconvert ! audio/x-raw,format=F32LE,channels=2 ! queue ! deinterleave name=d '
                'd.src_%s ! tee name=t '
                'interleave name=i ! capssetter caps = audio/x-raw,channels=2,channel-mask=0x3 ! '
                'audioconvert ! audioresample ! queue name=lastqueue max-size-time=20000000000 ! '
                'volume name=vol volume=%f ! autoaudiosink name=audiosink sync=false '
                't.src_0 ! queue ! audiocheblimit poles=%i name=lowpass mode=low-pass cutoff=%f ! '
                'equalizer-10bands name=equalizer band0=%f band1=%f ! volume name=lowvol volume=%f ! i.sink_0 '
                't.src_1 ! queue ! audiocheblimit poles=%i name=highpass mode=high-pass cutoff=%f ! '
                'volume name=highvol volume=%f ! i.sink_1 ' %
                (buffer_size, decoding,
                 self.channel,
                 master_volume,
                 self.xoverpoles, self.xoverfreq, self.band0, self.band1, lo,
                 self.xoverpoles, self.xoverfreq, hi))

            # print(pipeline)

            log.info('launching pipeline ...')
            self.pipeline = Gst.parse_launch(pipeline)

        except Exception as e:
            log.critical("couldn't launch pipeline, %s" % str(e))

        self.source = self.pipeline.get_by_name('audiosource')

        self.last_queue = self.pipeline.get_by_name('lastqueue')

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        bus.connect('message', self.bus_message)

        self.pipeline.set_state(Gst.State.PAUSED)

    def set_volume(self, volume = None):
        if volume:
            self.user_volume = volume
        # the pipeline stops if the volume is zero ?
        _master_volume = max(0.0005, self.user_volume * self.gain * self.balance)
        if volume:
            log.debug('setting pipeline volume %f (user volume %f)' %
                      (_master_volume, self.user_volume))

        if self.pipeline:
            master_volume = self.pipeline.get_by_name('vol')
            master_volume.set_property('volume', _master_volume)

    # fixit, should be constant power
    def set_balance(self, balance):
        self.balance = 1.0
        if self.channel == Channel.LEFT.value and balance > 0.0:
            self.balance = 1.0 - balance
        elif self.channel == Channel.RIGHT.value and balance < 0.0:
            self.balance = 1.0 + balance

        log.debug('setting balance %.2f' % self.balance)

        self.set_volume()

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
            self.set_volume(int(message['volume']) / 127.0)

        elif command == 'buffering':
            self.log_first_audio = LOG_FIRST_AUDIO_COUNT
            self.m_state = State.BUFFERING
            self.buffer_state = BufferState.MONITOR_STARTING
            self.hwctl.play(True)

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

            play_time = float(message['playtime'])
            # here the time precision goes out the window
            play_delay_ns = (play_time - time.time()) * 1000000000
            self.pipeline.set_base_time(self.pipeline.get_pipeline_clock().get_time() + play_delay_ns)

            self.pipeline.set_start_time(Gst.CLOCK_TIME_NONE)

            self.pipeline.set_state(Gst.State.PLAYING)

            self.m_state = State.PLAYING

            play_delay_secs = play_delay_ns / util.NS_IN_SEC
            self.playing_start_time = time.time() + play_delay_secs

            log.info('playing will start in %.9f sec' % play_delay_secs)

        elif command == 'stopping':
            log.info('---- stopping ----')
            self.hwctl.play(False)
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline = None
            self.m_state = State.STOPPED
            self.playing_start_time = None
            self.buffer_state = BufferState.MONITOR_STARTING

        elif command == 'configuration':
            self.configure_pipeline(message)

        else:
            log.critical("got unknown command '%s'" % command)

    def configure_pipeline(self, message):
        channel = message.get('channel')
        if channel:
            self.channel = int(channel)
            log.info("processing setup '%s'. Channel=%i" % (message.get('name'), self.channel))

        volume = message.get('volume')
        if volume:
            self.set_volume(float(volume) / 100.0)

        balance = message.get('balance')
        if balance:
            self.set_balance(float(balance) / 100.0)

        highlowbalance = message.get('highlowbalance')
        if highlowbalance:
            highlowbalance = float(highlowbalance)
            lo, hi = self.calculate_highlowbalance(highlowbalance)
            log.debug('setting high/low balance %.1f (low %.5f high %.5f)' %
                      (highlowbalance, lo, hi))
            if self.pipeline:
                self.pipeline.get_by_name('highvol').set_property('volume', hi)
                self.pipeline.get_by_name('lowvol').set_property('volume', lo)

        xoverfreq = message.get('xoverfreq')
        if xoverfreq:
            log.debug('setting xover frequency %s' % xoverfreq)
            self.xoverfreq = float(xoverfreq)
            if self.pipeline:
                xlow = self.pipeline.get_by_name('lowpass')
                xlow.set_property('cutoff', self.xoverfreq)
                xhigh = self.pipeline.get_by_name('highpass')
                xhigh.set_property('cutoff', self.xoverfreq)

        xoverpoles = message.get('xoverpoles')
        if xoverpoles:
            log.debug('setting xover poles %s' % xoverpoles)
            self.xoverpoles = int(xoverpoles)
            if self.pipeline:
                xlow = self.pipeline.get_by_name('lowpass')
                xlow.set_property('poles', self.xoverpoles)
                xhigh = self.pipeline.get_by_name('highpass')
                xhigh.set_property('poles', self.xoverpoles)

        """
        band 0 : 29Hz
        band 1 : 59Hz
        """
        equalizer = message.get('equalizer')
        if equalizer:
            att = equalizer.get('0')
            if att:
                self.band0 = float(att)
                log.debug('setting eqband0 %f' % self.band0)
                if self.pipeline:
                    eq = self.pipeline.get_by_name('equalizer')
                    eq.set_property('band0', self.band0)

            att = equalizer.get('1')
            if att:
                self.band1 = float(att)
                log.debug('setting eqband1 %f' % self.band1)
                if self.pipeline:
                    eq = self.pipeline.get_by_name('equalizer')
                    eq.set_property('band1', self.band1)

        buffersize = message.get('buffersize')
        if buffersize:
            self.buffer_size = int(buffersize)
            log.debug('setting buffersize %i' % self.buffer_size)

    def print_stats(self):
        try:
            position, duration = self.pipeline.query_position(Gst.Format.TIME)
            buffer_size = int(self.last_queue.get_property('current-level-bytes'))
            duration_secs = int(duration) / util.NS_IN_SEC
            playtime_skew = (time.time() - self.playing_start_time) - duration_secs
            log.info("playing time %.3f sec, buffered %i bytes. Skew %.6f" %
                     (duration_secs, buffer_size, playtime_skew))
        except:
            return 999
        return playtime_skew > 1.0

    """
    For now playing is brutally restarted if the pipeline buffer suddenly dries out.
    In the current implementation this would be if the codec is trashing data which
    in turn should be investigated since it happens. If the audio is moved from tcp
    to a more elegant multicast then it makes more sense to be prepared for lost data 
    and perhaps a strategy like this.
    """
    def pipeline_monitor(self):
        if not self.pipeline:
            return

        self.monitor_lock.acquire()

        buffer_size = int(self.last_queue.get_property('current-level-bytes'))

        if self.buffer_state == BufferState.MONITOR_STARTING:
            if buffer_size > self.buffer_size:
                self.starvation_alerts = self.NOF_STARVATION_ALERTS
                self.buffer_state = BufferState.MONITOR_STARVATION
                log.info('monitor: initial buffering complete, sending buffered')
                self.emit('status', 'buffered')

        elif self.buffer_state == BufferState.MONITOR_STARVATION:
            if buffer_size < 40000:
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
            if buffer_size > self.buffer_size:
                self.buffer_state = BufferState.MONITOR_STARVATION
                log.info('monitor: buffer ready again, sending buffered')
                self.emit('status', 'buffered')

        self.monitor_lock.release()

    def new_audio(self, audio):
        # if the server issued a stop due to a starvation restart then this is a good
        # time to construct a new pipeline
        if not self.pipeline:
            self.construct_pipeline()

        if self.log_first_audio:
            self.log_first_audio -= 1
            log.debug('received %i bytes audio (%i)' % (len(audio), self.log_first_audio))

        if audio:
            buf = Gst.Buffer.new_allocate(None, len(audio), None)
            buf.fill(0, audio)
            self.source.emit('push-buffer', buf)
            self.pipeline_monitor()

    def run(self):
        try:
            log.debug('play sequenser starting')
            last_status_time = time.time()

            while not self.terminated:
                time.sleep(0.1)

                self.pipeline_monitor()

                if (self.m_state != State.STOPPED) and (time.time() - last_status_time > 2):
                    last_status_time = time.time()
                    self.print_stats()

        except Exception as e:
            log.critical('player thread exception %s' % str(e))

        log.debug('player thread terminated')
