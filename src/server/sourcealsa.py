from common.log import logger as log
from common import util
import time
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst


class SourceAlsa(util.Threadbase):
    """
    Source for raw Alsa input. Since there is no out of band control channel
    issuing e.g. start and stop events the pipeline uses a cutter element
    as gate.
    Notice that at least for the python binding the first thing comming from
    a gated non leaky cutter is not the 'above' event but the first audio packet,
    then followed by the 'above' event.
    The state is 'experimental'
    """
    signals = 'event'

    def __init__(self, alsa_src_config):
        super(SourceAlsa, self).__init__(name='alsa')
        self.config = alsa_src_config
        self.client_buffer = self.config['client_buffer']
        log.debug('starting alsasource')
        self.is_playing = False
        self.start()

    def start_playing(self):
        self.is_playing = True
        log.debug('[%s] audio started, start playing' % self.name)
        self.send_event('codec', 'aac_adts')

    def stop_playing(self):
        self.is_playing = False
        log.debug('[%s] audio cut, stop playing' % self.name)
        self.send_event('state', 'stop')

    def bus_message(self, bus, message):
        try:
            if message.type == Gst.MessageType.EOS:
                log.debug('EOS')
            elif message.type == Gst.MessageType.ERROR:
                err, deb = message.parse_error()
                log.critical("pipeline error: %s '%s'" % (err, deb))
                self.send_event('status', 'pipeline_error')
            elif message.type == Gst.MessageType.STATE_CHANGED:
                old_state, new_state, pending_state = message.parse_state_changed()
                if message.src == self.pipeline:
                    log.debug('pipeline state changed to %s' % Gst.Element.state_get_name(new_state))

        except Exception as e:
            log.critical('[%s] parsing bus message gave "%s"' % (self.name, str(e)))

    def cutter_message(self, bus, message):
        try:
            if message.has_name("cutter"):
                above = message.get_structure().get_value('above')
                if not above and self.is_playing:
                    self.stop_playing()
                elif above and not self.is_playing:
                    self.start_playing()

        except Exception as e:
            log.critical('[%s] parsing cutter message gave "%s"' % (self.name, str(e)))

    def new_sample(self, sink):
        if not self.is_playing:
            self.start_playing()
        sample = sink.emit("pull-sample")
        buffer = sample.get_buffer()
        data = buffer.extract_dup(0, buffer.get_size())
        self.send_event('audio', data)
        return Gst.FlowReturn.OK

    def construct_pipeline(self):
        try:
            if self.config['device']:
                device = 'device=%s' % self.config['device']
            else:
                device = ''

            pipeline = 'alsasrc %s ! '\
                       'cutter name=cutter leaky=false run-length=%i threshold-dB=%f ! '\
                       'faac ! aacparse ! avmux_adts ! appsink name=appsink' % \
                        (device,
                         int(float(self.config['timeout']) * util.NS_IN_SEC),
                         float(self.config['threshold_dB']))

            log.info('launching pipeline listening to alsa %s' % device)
            self.pipeline = Gst.parse_launch(pipeline)

            appsink = self.pipeline.get_by_name('appsink')
            appsink.set_property('emit-signals', True)
            appsink.connect('new-sample', self.new_sample)

            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.enable_sync_message_emission()
            bus.connect('message', self.bus_message)
            bus.connect('message::element', self.cutter_message)

            self.pipeline.set_state(Gst.State.PLAYING)

        except Exception as e:
            log.critical("[%s] couldn't construct pipeline, %s" % (self.name, str(e)))

    def send_event(self, key, value):
        self.emit('event', {'name': self.name, 'key': key, 'value': value})

    def run(self):
        self.construct_pipeline()

        while not self.terminated:
            time.sleep(0.1)

        self.pipeline.set_state(Gst.State.NULL)
        log.debug('sourcealsa exits')
