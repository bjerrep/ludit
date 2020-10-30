from common.log import logger as log
from common import util
import select
import socket
import os
import time
import stat


class SourceFifo(util.Threadbase):
    """
    Reads from the /tmp/audio fifo written to by the BlueALSA codec fork. It expects the added ascii
    framing so it supports e.g. volume events which will be forwarded to the clients together with
    the unmodified a2dp encoded audio.
    """
    signals = 'event'
    sync = False

    def __init__(self):
        super(SourceFifo, self).__init__(name='fifo')
        self.start()

    @staticmethod
    def source_name():
        return 'fifo'

    def send_event(self, key, value):
        self.emit('event', {'name': self.name, 'key': key, 'value': value})

    def run(self):
        try:
            while not self.terminated:

                try:
                    fifo = os.open('/tmp/audio', os.O_NONBLOCK | os.O_RDONLY)
                except FileNotFoundError:
                    log.critical('fifo /tmp/audio does not exist, source "%s" disabled' % self.name)
                    self.terminate()
                    continue

                if fifo <= 0:
                    log.critical('could not open /tmp/audio, source "%s" disabled' % self.name)
                    self.terminate()
                    continue

                if not stat.S_ISFIFO(os.stat('/tmp/audio').st_mode):
                    log.critical('fifo /tmp/audio is there but its not a fifo, source "%s" disabled' % self.name)
                    self.terminate()
                    continue

                log.info('opened /tmp/audio fifo')

                self.play_thread_active = True
                data = bytearray()

                try:
                    while self.play_thread_active and not self.terminated:
                        try:
                            inputready, outputready, exceptready = \
                                select.select([fifo], [], [], 0.1)
                        except socket.timeout:
                            log.critical('got timeout 123')
                            self.play_thread_active = False
                            continue

                        if inputready:
                            data += os.read(fifo, 100000)

                            if not data and not self.terminated:
                                log.info('restarting fifo')
                                self.play_thread_active = False
                                continue

                            if data.startswith(b'::'):
                                end = data.find(b'::', 2)
                                if end == -1:
                                    self.sync = False
                                    continue
                                end_of_data = end + 2

                                key, value = data[2:end].decode('utf-8').split('=')

                                if not self.sync:
                                    log.info('sourcefifo running')
                                    self.sync = True

                                if key == 'audio':
                                    end_of_data += int(value)
                                    if end_of_data > len(data):
                                        log.info('got partial packet')
                                        continue
                                    self.send_event('audio', data[end + 2:end_of_data])

                                elif key == 'codec':
                                    self.send_event('codec', value)

                                elif key == 'volume':
                                    log.info('volume %s' % value)
                                    self.send_event('volume', value)

                                elif key == 'state':
                                    log.info('state=%s' % value)
                                    if value == 'stop':
                                        self.send_event('state', value)
                                        self.play_thread_active = False
                                        time.sleep(0.2)

                                else:
                                    log.critical("got unknown inband message '%s=%s'" %
                                                 (str(key), str(value)))
                                    self.sync = False

                                data = data[end_of_data:]
                            else:
                                if not self.terminated:
                                    if self.sync:
                                        self.sync = False
                                    log.critical('in-band missing header, %i bytes' % len(data))
                                    self.play_thread_active = False
                                    time.sleep(0.5)

                    os.close(fifo)

                except TimeoutError:
                    log.critical('ignoring a Timeout error...')
                except socket.timeout:
                    log.critical('got a socket timeout, warmstarting')
                    time.sleep(1)
                except BrokenPipeError:
                    log.critical('got a broken pipe exception, warmstarting')
                    time.sleep(1)

        except Exception as e:
            log.critical("source %s exception '%s'" % (self.source_name(), str(e)))
            self.terminate()

        log.debug('sourcefifo exits')
