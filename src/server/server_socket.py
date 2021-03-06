from common import datapacket
from common.log import logger as log
from common import util
import socket
import struct
import select
import time


class ServerSocket(util.Threadbase):
    signals = ('message', 'devicedisconnected', 'deviceconnected')

    def __init__(self, id):
        super(ServerSocket, self).__init__(name='serversoc ')
        self.connection = None
        self.id = id
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # close gracefully from this end
            l_onoff = 1
            l_linger = 0
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', l_onoff, l_linger))
            # and detect peers that didn't close gracefully with a reset
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 2)
            self.socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 2)
            self.socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 2)
            self.socket.bind((util.local_ip(), 0))
            self.socket.listen(1)
        except socket.error as e:
            if e.errno == 98:  # Address already in use
                log.critical(str(e) + ' - cant start')
                raise e
        except Exception as e:
            log.critical('serversocket %s caught %s' % (self.id, str(e)))

        self.start()

    def get_endpoint(self):
        return self.socket.getsockname()[0] + ':' + str(self.socket.getsockname()[1])

    def send(self, packet):
        if self.connection:
            try:
                if type(packet) == dict:
                    packet = datapacket.pack_json(packet)
                self.connection.sendall(packet)
            except Exception as e:
                log.warning('serversocket %s send caught %s' % (self.id, str(e)))

    def run(self):
        log.debug('starting serversocket at %s for %s' %
                  (str(self.get_endpoint()),
                   self.id))

        rxdata = bytearray()
        connected = False

        self.connection = None

        while not self.terminated:
            try:
                if not connected:
                    try:
                        rxdata = bytearray()
                        self.socket.settimeout(0.1)
                        self.connection, addr = self.socket.accept()
                        log.info('>>> client connected from ' + str(addr))
                        self.connection.settimeout(1.0)
                        connected = True
                        self.emit('deviceconnected')
                    except socket.timeout:
                        time.sleep(0.1)
                        raise util.ExpectedException
                    except Exception as e:
                        time.sleep(0.1)
                        log.critical('exception in socket thread: %s' % str(e))
                        raise e

                timeoutsecs = 0.1

                while True:
                    result = select.select([self.connection], [], [], timeoutsecs)
                    if result and result[0]:
                        break
                    if self.terminated:
                        raise util.TerminatedException

                try:
                    newdata = self.connection.recv(1024)
                except Exception:
                    raise util.TimeoutException

                if not newdata:
                    raise util.ClosedException

                rxdata = rxdata + newdata

                while True:
                    rxdata, _json, _audio = datapacket.parse(rxdata)
                    if _json:
                        self.emit('message', _json)
                    else:
                        break

            except util.ExpectedException:
                pass
            except util.TerminatedException:
                break
            except (BrokenPipeError, util.ClosedException):
                connected = False
                self.emit('devicedisconnected', self.id)
            except Exception as e:
                if connected:
                    log.error('>>> client connection lost "%s"' % str(e))
                    connected = False
                    self.emit('devicedisconnected', self.id)
                else:
                    log.error('exception: ' + str(e))

        if self.connection:
            self.connection.close()
        if self.socket:
            self.socket.close()
        log.debug('server socket exits')
