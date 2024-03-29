from server import sourcebluealsa
from server import sourcetcp
from server import sourcespotifyd
from server import sourcemopidy
from server import sourcealsa
from common.log import logger as log
from common import util
import queue
import threading
import time
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, GObject, Gst
GObject.threads_init()
Gst.init(None)

LOG_FIRST_AUDIO_COUNT = 5


class InputMux(util.Threadbase):
    """
    Hosts the sources (currently sourcebluealsa, sourcetcp and sourcespotifyd), listens to their events
    and makes sure that the events passed on are sane. Implements the policy on what to do when
    multiple sources are playing at once.
    """
    def __init__(self, source_config, streaming_config):
        super(InputMux, self).__init__(name='inputmux')
        log.info('inputmux is starting sources')
        self.queue = queue.Queue()
        self.source_event_lock = threading.Lock()
        self.mainloop = None

        self.log_first_audio = LOG_FIRST_AUDIO_COUNT
        self.now_playing = None
        self.timeout_counter = None
        self.timeout_preset_ticks = int(streaming_config['audiotimeout']) * 10
        self.audio_buffer = bytearray()

        self.sources = []

        # udp server for encoded audio and signals from bluealsa (typ adts framed aac)
        _sourcebluealsa = sourcebluealsa.SourceBlueALSA()
        _sourcebluealsa.connect('event', self.source_event)
        self.sources.append(_sourcebluealsa)

        # gstreamer tcp source(s)
        for gst_source in source_config['gstreamer']:
            if gst_source['enabled']:
                _sourcetcp = sourcetcp.SourceTCP(
                    gst_source['format'],
                    gst_source['samplerate'],
                    gst_source['port'])
                _sourcetcp.connect('event', self.source_event)
                self.sources.append(_sourcetcp)

        # mopidy tcp source
        _sourcespotifyd = sourcespotifyd.SourceSpotifyd()
        _sourcespotifyd.connect('event', self.source_event)
        self.sources.append(_sourcespotifyd)

        if source_config['mopidy_ws_enabled'] == 'on':
            _source_mopidy = sourcemopidy.SourceMopidy(source_config['mopidy_ws_address'],
                                                           source_config['mopidy_ws_port'],
                                                           source_config['mopidy_gst_port'])
            _source_mopidy.connect('event', self.source_event)
            self.sources.append(_source_mopidy)

        try:
            if source_config['alsasource']['enabled']:
                _alsasrc = sourcealsa.SourceAlsa(source_config['alsasource'])
                _alsasrc.connect('event', self.source_event)
                self.sources.append(_alsasrc)
        except Exception as e:
            log.warning(f'unable to start alsasource, "{e}"')

        self.audiominblocksize = source_config['audiominblocksize']

        threading.Thread(target=self.gst_mainloop_thread).start()
        self.start()

    def terminate(self):
        super().terminate()
        for source in self.sources:
            source.terminate()
        self.mainloop.quit()

    @staticmethod
    def source_name():
        return 'inputmux'

    def gst_mainloop_thread(self):
        try:
            self.mainloop = GLib.MainLoop()
            self.mainloop.run()
            log.debug('gst mainloop exits')
        except:
            util.die('caught a gst mainloop exception, exiting..', 1, True)

    def event_poll(self):
        return self.queue.get(timeout=0.1)

    def new_event(self, key, value):
        self.queue.put_nowait({'key': key, 'value': value})

    def stop_playing(self):
        self.now_playing = None
        self.timeout_counter = None
        self.new_event('state', 'stop')

    def source_event(self, event):
        """
        Recieves events from all sources and implements a policy on how to deal with one
        or more simultaneously active sources. Currently the winner is always the latest source
        that started playing (implicitly done by the source by sending a 'codec' event).
        Once playing it buffers audio to sane package sizes. Outdata (messages and audio) are
        placed in a queue for others to pick up (currently picked by the server itself)
        """
        with self.source_event_lock:
            source = event['name']
            key = event['key']
            value = event['value']

            if key == 'codec':
                if self.now_playing:
                    log.info(f'inputmux ditching current source "{self.now_playing}", new codec={value}')
                    self.stop_playing()
                self.now_playing = source
                self.log_first_audio = LOG_FIRST_AUDIO_COUNT
                log.info(f'inputmux starts playing source "{source}"')
                self.audio_buffer = bytearray()

            if not self.now_playing or self.now_playing != source:
                return

            if key == 'audio':
                if self.log_first_audio:
                    self.log_first_audio -= 1
                    log.debug(f'audio {len(value)} bytes')
                self.timeout_counter = self.timeout_preset_ticks
                self.audio_buffer += value
                if len(self.audio_buffer) < self.audiominblocksize:
                    return
                value = self.audio_buffer
                self.audio_buffer = bytearray()

            if key == 'state':
                if value == 'stop':
                    log.info(f'inputmux received stop from source "{source}"')
                    self.stop_playing()
                else:
                    log.warning(f'inputmux received unknown state "{value}" from source "{source}"')
            elif key == 'flush':
                pass
            else:
                self.new_event(key, value)

    def run(self):
        while not self.terminated:
            try:
                time.sleep(0.1)
                if self.timeout_counter:
                    self.timeout_counter -= 1
                    if not self.timeout_counter:
                        log.warning('timeout from source "%s", no data for 4 seconds' % self.now_playing)
                        self.stop_playing()

            except Exception as e:
                log.critical('exception in inputmux, %s' % str(e))

        log.debug('inputmux exits')
