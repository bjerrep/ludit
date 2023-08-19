import socket, time
from common.log import logger as log
from common import util


class SourceBlueALSA(util.Threadbase):
    """
    Starts an UDP server written to by the BlueALSA direct audio fork. It expects the inband ascii
    framing so it supports e.g. volume events which will be forwarded to the clients together with
    the unmodified a2dp encoded audio.
    """
    signals = 'event'
    sync = False
    sock = None

    def __init__(self, server_endpoint=('localhost', 5678)):
        super(SourceBlueALSA, self).__init__(name='bluealsa')
        self.startUDPServer(server_endpoint)
        self.start()

    @staticmethod
    def source_name():
        return 'bluealsa'

    def send_event(self, key, value):
        self.emit('event', {'name': self.name, 'key': key, 'value': value})

    def startUDPServer(self, server_endpoint):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(server_endpoint)
        self.sock.settimeout(0.1)
        log.info(f'source bluealsa udp server listening at {server_endpoint}')

    def run(self):
        data = bytearray()
        running = False

        while not self.terminated:

            try:
                rx, _client_address = self.sock.recvfrom(10000)
            except socket.timeout:
                time.sleep(0.1)
                continue

            if rx:
                data += rx
            else:
                continue

            if data.startswith(b'::'):
                end = data.find(b'::', 2)
                if end == -1:
                    continue
                end_of_data = end + 2
            else:
                data = bytearray()
                continue

            key, value = data[2:end].decode('utf-8').split('=')

            if key != 'audio':
                log.info(f'inband "{key}={value}"')

            if key == 'codec':
                running = True
                self.send_event('codec', value)
                data = data[end_of_data:]
                continue

            if not running:
                data = bytearray()
                continue

            if key == 'samplerate':
                self.send_event('samplerate', value)
                data = data[end_of_data:]
                continue

            if key == 'audio':
                end_of_data += int(value)
                if end_of_data > len(data):
                    log.info('got partial packet')
                    continue
                self.send_event('audio', data[end + 2:end_of_data])

            elif key == 'volume':
                self.send_event('volume', value)

            elif key == 'state':
                if value == 'stop':
                    running = False
                    self.send_event('state', value)
                    time.sleep(0.2)

            else:
                log.critical(f"got unknown inband message '{str(key)}={str(value)}'")
                self.sync = False

            data = data[end_of_data:]

        #except Exception as e:
        #    log.critical("source %s exception '%s'" % (self.source_name(), str(e)))
        #    self.terminate()

        log.debug('source bluealsa exits')
