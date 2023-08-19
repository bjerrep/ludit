from common.log import logger as log
from common import util
from server import sourcebase
import time
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst


class SourceTCP(sourcebase.SourceBase):
    """
    Hosts a gstreamer tcp server originally made for speaker testing with audio generated
    by gstreamer pipelines on the command line. It also opens up for the possibility
    for ludit to be the player backend for other audio systems/player frameworks but that
    haven't been tried yet. Currently it hardcodes the codec type to be aac and the samplerate
    to 44.1 kHz although the  payloads simply are forwarded as-is, there are no audio
    processing going on here.
    """
    signals = 'event'
    def __init__(self, codec, samplerate, port, name='tcp'):
        """
        codec: 'pcm', 'aac_adts'
        """
        super(SourceTCP, self).__init__(name=name)
        log.info(f'starting gstreamer tcp at port {port}')
        self.codec = codec
        self.samplerate = samplerate
        self.port = port
        self.pipeline = None
        self.eos = False
        self.start()

    def terminate(self):
        super().terminate()
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)

    def source_name(self):
        return self.name

    def bus_message(self, bus, message):
        try:
            if message.type == Gst.MessageType.EOS:
                log.debug('EOS')
                self.eos = True
            elif message.type == Gst.MessageType.ERROR:
                err, deb = message.parse_error()
                log.critical("pipeline error: %s '%s'" % (err, deb))
                self.emit('status', 'pipeline_error')
            elif message.type == Gst.MessageType.STATE_CHANGED:
                old_state, new_state, pending_state = message.parse_state_changed()
                if message.src == self.pipeline:
                    log.debug('pipeline state changed to %s' % Gst.Element.state_get_name(new_state))
                    if new_state == Gst.State.PLAYING:
                        self.send_event('codec', self.codec)
                        self.send_event('samplerate', '44100')
        except Exception as e:
            log.critical('[%s] parsing bus message gave %s' % (self.source_name(), str(e)))

    def new_sample(self, sink):
        sample = sink.emit("pull-sample")
        buffer = sample.get_buffer()
        data = buffer.extract_dup(0, buffer.get_size())
        self.send_event('audio', data)
        return Gst.FlowReturn.OK

    def construct_pipeline(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)

        try:
            # playing a sine wave through this source (always remember the volume or be prepared for a wakeup call):
            # gst-launch-1.0 audiotestsrc freq=1000 volume=0.004 is-live=true ! audioconvert ! audio/x-raw, channels=2 !
            # faac ! aacparse ! avmux_adts ! tcpclientsink host=<hostname> port=4666
            #
            # for playing the pipeline above directly on a second command line (without the server running):
            # gst-launch-1.0 tcpserversrc host=<hostname> port=4666 ! decodebin ! audioconvert ! alsasink
            #
            ip = util.local_ip()
            pipeline = 'tcpserversrc host=%s port=%i ! appsink name=appsink emit-signals=true sync=false' % \
                       (ip, self.port)

            log.info('launching %s pipeline listening at %s:%i' % (self.name, ip, self.port))
            self.pipeline = Gst.parse_launch(pipeline)

            appsink = self.pipeline.get_by_name('appsink')
            appsink.connect('new-sample', self.new_sample)

            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.enable_sync_message_emission()
            bus.connect('message', self.bus_message)

            self.pipeline.set_state(Gst.State.PLAYING)

        except Exception as e:
            log.critical("couldn't construct pipeline, %s" % str(e))

    def run(self):
        try:
            while not self.terminated:
                self.construct_pipeline()

                while not self.eos and not self.terminated:
                    time.sleep(0.1)

                if self.eos:
                    self.send_event('state', 'stop')
                    self.eos = False

        except Exception as e:
            log.critical("source %s exception '%s'" % (self.source_name(), str(e)))
            self.terminate()

        log.debug('sourcetcp exits')
