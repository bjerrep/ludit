import socket, time
from common import util
from common.log import logger as log
from common import datapacket


class ClientSocket(util.Threadbase):
    signals = ('socket', 'audio', 'message')

    def __init__(self, endpoint, buffer_size=4096):
        super(ClientSocket, self).__init__(name='clientsoc ')
        self.socket = None
        self.endpoint = endpoint
        self.buffer_size = buffer_size
        self.connected = False
        self.start()

    def send(self, packet):
        if self.connected:
            if isinstance(packet, dict):
                packet = datapacket.pack_json(packet)
            self.socket.sendall(packet)

    def run(self):
        log.debug(f'starting clientsocket for server at {util.tcp2str(self.endpoint)}')
        log_waiting = True
        while not self.terminated:
            try:
                if not self.connected:
                    try:
                        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                        rxdata = bytearray()
                        self.socket.settimeout(5.0)
                        self.socket.connect(self.endpoint)
                        self.socket.settimeout(1.0)
                        self.connected = True
                        log_waiting = True
                        log.info(f'connected to server at {util.tcp2str(self.endpoint)}')
                        self.emit('socket', 'open')

                    except (TimeoutError, socket.timeout) as e:
                        if log_waiting:
                            log.info("waiting for server")
                            log_waiting = False
                        self.connected = False
                        time.sleep(1)
                        raise util.ExpectedException from e
                    except OSError as e:
                        if e.errno == 113:
                            log.error('got no route to host at ip broadcast by server. Has network changed ?')
                        raise e
                    except Exception as e:
                        log.critical(self.name + str(e))
                        raise e

                try:
                    blob = self.socket.recv(self.buffer_size)
                    rxdata = rxdata + blob

                except ConnectionResetError as e:
                    raise util.ClosedException from e
                except socket.timeout as e:
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
            except ConnectionRefusedError:
                # the server needs to get flipped. Reason unknown.
                if self.connected:
                    self.connected = False
                    log.error('server refused the connection')
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
