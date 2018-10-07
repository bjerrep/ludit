from common import util
from common.log import logger as log
from common import datapacket
import socket
import time


class ClientSocket(util.Threadbase):
    signals = ('socket', 'audio', 'message')

    def __init__(self, endpoint):
        super(ClientSocket, self).__init__(name='clientsoc ')
        self.socket = None
        self.endpoint = endpoint
        self.connected = False
        self.start()

    def send(self, packet):
        if self.connected:
            if type(packet) == dict:
                packet = datapacket.pack_json(packet)
            self.socket.sendall(packet)

    def run(self):
        log.debug('starting clientsocket at %s' % util.tcp2str(self.endpoint))
        log_waiting = True
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except Exception as e:
            log.critical(self.name + str(e))

        while not self.terminated:
            try:
                if not self.connected:
                    try:
                        rxdata = bytearray()
                        self.socket.settimeout(5.0)
                        self.socket.connect(self.endpoint)
                        self.socket.settimeout(1.0)
                        self.connected = True
                        log_waiting = True
                        log.info('connected to server at %s' % util.tcp2str(self.endpoint))
                        self.emit('socket', 'open')
                    except (TimeoutError, socket.timeout):
                        if log_waiting:
                            log.info("waiting for server")
                            log_waiting = False
                        self.connected = False
                        time.sleep(1)
                        raise util.ExpectedException

                try:
                    blob = self.socket.recv(4096)
                    rxdata = rxdata + blob

                except ConnectionResetError:
                    raise util.ClosedException
                except socket.timeout:
                    time.sleep(0.05)
                    raise util.ExpectedException

                if not rxdata:
                    raise util.ClosedException

                while True:
                    rxdata, _json, _audio = datapacket.parse(rxdata)
                    if _json:
                        self.emit('message', _json)
                    elif _audio:
                        self.emit('audio', _audio)
                    else:
                        break

            except util.ExpectedException:
                pass
            except util.TerminatedException:
                break
            except ConnectionAbortedError:
                log.critical("internal error #0080")
            except util.ClosedException:
                if self.connected:
                    self.connected = False
                    log.error('server connection lost')
                    self.emit('socket', 'closed')
                    self.terminate()
                time.sleep(0.1)
            except util.MalformedPacketException:
                self.connected = False
                log.error('got malformed data, restarting')
                self.emit('socket', 'closed')
                self.terminate()
                time.sleep(0.1)

        if self.socket:
            self.socket.close()
        log.debug(self.name + ' exits')
