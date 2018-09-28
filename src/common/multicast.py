from common import util
from common.log import logger as log
import socket
import struct
import json


class Server(util.Threadbase):
    signals = 'receive'

    def __init__(self, ip, port):
        super(Server, self).__init__(name='server mc ')
        self.multicast_ip = ip
        self.multicast_port = port
        self.multicast_group = (ip, port)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(0.2)
        ttl = struct.pack('b', 100)
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 20)
        self.socket.bind(self.multicast_group)
        self.start()

    def send(self, message_dict):
        _json = json.dumps(message_dict).encode()
        self.socket.sendto(_json, self.multicast_group)

    def run(self):
        try:
            while not self.terminated:
                try:
                    data = self.socket.recv(1024)
                except socket.timeout:
                    continue

                message = json.loads(data)
                try:
                    if message['to'] == 'server':
                        try:
                            self.emit('receive', message)
                        except Exception as e:
                            log.critical('emit message failed with %s' % str(e))
                except Exception as e:
                    log.critical('got malformed message %s - %s' % (str(message), str(e)))

        except Exception as e:
            log.critical('server multicast got ' + str(e))

        self.socket.close()
        log.debug('server multicast terminated')


class Client(util.Threadbase):
    signals = 'receive'

    def __init__(self, id, ip, port):
        super(Client, self).__init__(name='client mc ')
        self.id = id
        self.multicast_ip = ip
        self.multicast_group = (ip, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.multicast_group)
        self.socket.settimeout(0.2)
        mreq = struct.pack('4sl', socket.inet_aton(self.multicast_ip), socket.INADDR_ANY)
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self.start()

    def send(self, message):
        _json = json.dumps(message).encode()
        self.socket.sendto(_json, self.multicast_group)

    def run(self):
        try:
            while not self.terminated:
                try:
                    data = self.socket.recv(1024)
                except socket.timeout:
                    continue
                else:
                    message = json.loads(data)
                    try:
                        if message['to'] in (self.id, '*') or self.id == '*':
                            try:
                                self.emit('receive', message)
                            except Exception as e:
                                log.critical('emit message failed with %s' % str(e))
                    except Exception as e:
                        log.critical('got malformed message %s - %s' % (str(message), str(e)))

        except Exception as e:
            log.critical('client multicast got ' + str(e))

        self.socket.close()
        log.debug('client multicast terminated')
