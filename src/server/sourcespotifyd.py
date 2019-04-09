from common.log import logger as log
from common import util
import select
import time
import re
import os
import stat
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst


class SourceSpotifyd(util.Threadbase):
    """
    spotifyd is configured to send audio to a alsa loopback which this source then reads with a gstreamer
    pipeline and encodes to aac. This is an unfortunate transcoding which seem unavoidable. Using flac or the
    like would be the obvious thing to try to use rather than aac. The alsa loopback requres the snd-aloop
    kernel module to be loaded.
    Spotifyd sends play state events via the script config/write_spotifyd_fifo.sh which via a named pipe is
    picked up below. Nothing can possibly go wrong when using this source. Meh.
    """
    signals = 'event'

    def __init__(self):
        super(SourceSpotifyd, self).__init__(name='spotifyd')
        self.pipeline = None
        self.start()

    def start_playing(self):
        self.send_event('codec', 'aac_adts')
        self.construct_pipeline()
        self.pipeline.set_state(Gst.State.PLAYING)

    def stop_playing(self):
        self.send_event('state', 'stop')
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

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
            pipeline = 'alsasrc device=hw:1,1 ! faac ! aacparse ! avmux_adts ! appsink name=appsink'

            log.info('launching pipeline listening to alsa loopback')
            self.pipeline = Gst.parse_launch(pipeline)

            appsink = self.pipeline.get_by_name('appsink')
            appsink.set_property('emit-signals', True)
            appsink.connect('new-sample', self.new_sample)

            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.enable_sync_message_emission()
            bus.connect('message', self.bus_message)

        except Exception as e:
            log.critical("couldn't construct pipeline, %s" % str(e))

    def send_event(self, key, value):
        self.emit('event', {'name': self.name, 'key': key, 'value': value})

    def run(self):
        while not self.terminated:

            try:
                fifo = os.open('/tmp/spotifyd', os.O_NONBLOCK | os.O_RDONLY)
            except FileNotFoundError:
                log.critical('fifo /tmp/spotifyd does not exist, source "%s" disabled' % self.name)
                self.terminate()
                continue

            if fifo <= 0:
                log.critical('could not open /tmp/spotifyd, source "%s" disabled' % self.name)
                self.terminate()
                continue

            if not stat.S_ISFIFO(os.stat('/tmp/spotifyd').st_mode):
                log.critical('fifo /tmp/spotifyd is there but its not a fifo, source "%s" disabled' % self.name)
                self.terminate()
                continue

            log.info('opened /tmp/spotifyd fifo')

            try:
                while not self.terminated:
                    try:
                        inputready, _, __ = select.select([fifo], [], [], 0.2)
                    except Exception as e:
                        log.critical('select gave exception ' + str(e))
                        continue

                    fifo_data = os.read(fifo, 1000)

                    if inputready and fifo_data:
                        commands = fifo_data.decode('utf-8').split('\n')
                        commands = [x for x in commands if x]

                        for cmd in commands:
                            command, track_id = re.sub(' +', ' ', cmd).split(' ')
                            log.debug('spotifyd sent %s %s' % (command, track_id))
                            if command == 'start':
                                self.start_playing()
                            elif command == 'stop':
                                self.stop_playing()
                            elif command == 'change':
                                pass
                            else:
                                log.warning('received unknown command from spotifyd')
                    else:
                        # the select returns immediately, probably for a good but unknown reason
                        time.sleep(0.1)

            except Exception as e:
                log.critical('reading spotifyd gave "%s"' % str(e))

        log.debug('sourcespotifyd exits')
