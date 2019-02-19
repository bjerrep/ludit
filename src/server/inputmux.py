from server import sourcefifo
from server import sourcetcp
from server import sourcespotifyd
from server import sourcemopidy
from common.log import logger as log
from common import util
import queue
import threading
import time
import gi
import os
gi.require_version('Gst', '1.0')
from gi.repository import GLib, GObject, Gst
GObject.threads_init()
Gst.init(None)

LOG_FIRST_AUDIO_COUNT = 5


class InputMux(util.Threadbase):
    """
    Hosts the sources (currently sourcefifo, sourcetcp and sourcespotifyd), listens to their events
    and makes sure that the events passed on are sane.
    """
    def __init__(self, source_config):
        super(InputMux, self).__init__(name='inputmux  ')
        self.queue = queue.Queue()
        self.source_event_lock = threading.Lock()

        self.log_first_audio = LOG_FIRST_AUDIO_COUNT
        self.now_playing = None
        self.timeout_counter = None
        self.audio_buffer = bytearray()

        self.sourcefifo = sourcefifo.SourceFifo()
        self.sourcefifo.connect("event", self.input_event)
        self.sourcetcp = sourcetcp.SourceTCP(source_config['gstreamer_port'])
        self.sourcetcp.connect("event", self.input_event)
        self.sourcespotifyd = sourcespotifyd.SourceSpotifyd()
        self.sourcespotifyd.connect("event", self.input_event)
        if source_config['mopidy_ws_enabled'] == 'on':
            self.source_mopidy = sourcemopidy.SourceMopidy(source_config['mopidy_ws_address'],
                                                           source_config['mopidy_ws_port'],
                                                           source_config['mopidy_gst_port'])
            self.source_mopidy.connect("event", self.input_event)
        else:
            self.source_mopidy = None

        threading.Thread(target=self.gst_mainloop_thread).start()
        self.start()

    def terminate(self):
        super().terminate()
        self.sourcefifo.terminate()
        self.sourcetcp.terminate()
        self.sourcespotifyd.terminate()
        if self.source_mopidy:
            self.source_mopidy.terminate()
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
            os.kill(os.getpid(), os.WNOHANG)

    def stop_playing(self):
        self.now_playing = None
        self.timeout_counter = None
        self.queue.put_nowait(['state', 'stop'])

    def input_event(self, skv):
        """
        Recieves events from all sources and implements a policy on how to deal with one
        or more simultaneously active sources. Currently the winner is always the latest source
        that started playing (implicitly done by the source by sending a 'codec' event).
        Once playing it buffers audio to sane package sizes. Outdata (messages and audio) are
        placed in a queue for others to pick up (currently picked by the server itself)
        """
        with self.source_event_lock:
            source, key, value = skv

            if key == 'codec':
                if self.now_playing:
                    log.info('inputmux ditching current source "%s", new codec=%s' % (self.now_playing, value))
                    self.stop_playing()
                self.now_playing = source
                self.log_first_audio = LOG_FIRST_AUDIO_COUNT
                log.info('inputmux starts playing source "%s"' % source)
                self.audio_buffer = bytearray()

            if not self.now_playing or self.now_playing != source:
                return

            if key == 'audio':
                if self.log_first_audio:
                    self.log_first_audio -= 1
                    log.debug('audio %s bytes' % len(value))
                self.timeout_counter = 40
                self.audio_buffer += value
                if len(self.audio_buffer) < 3000:
                    return
                value = self.audio_buffer
                self.audio_buffer = bytearray()

            self.queue.put_nowait([key, value])

            if key == 'state' and value == 'stop':
                log.info('inputmux received stop from source "%s"' % source)
                self.stop_playing()

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
