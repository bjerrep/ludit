from common import util
from common.log import logger as log
import socket
import struct
import json


class MulticastSocket(util.Threadbase):
    signals = 'socket_receive'

    def __init__(self, ip, port, name):
        super(MulticastSocket, self).__init__(name)
        self.multicast_ip = ip
        self.multicast_port = port
        self.multicast_group = (ip, port)
        log.debug('starting multicast socket at %s:%i' % (ip, port))

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.multicast_group)
        self.socket.settimeout(0.2)
        mreq = struct.pack('4sl', socket.inet_aton(self.multicast_ip), socket.INADDR_ANY)
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
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
                    self.emit('socket_receive', message)
                except Exception as e:
                    log.critical('emit message failed with %s' % str(e))

        except Exception as e:
            log.critical('server multicast got ' + str(e))

        self.socket.close()
        log.debug('server multicast terminated')


class Server(MulticastSocket):
    signals = 'server_receive'

    def __init__(self, ip, port):
        super(Server, self).__init__(ip, port, 'server mc ')
        super().connect('socket_receive', self.receive)

    def receive(self, message):
        if message['to'] == 'server':
            self.emit('server_receive', message)


class Client(MulticastSocket):
    signals = 'client_receive'

    def __init__(self, id, ip, port):
        super(Client, self).__init__(ip, port, 'client mc  ')
        self.id = id
        super().connect('socket_receive', self.receive)

    def receive(self, message):
        if message['to'] in (self.id, '*') or self.id == '*':
            self.emit('client_receive', message)
