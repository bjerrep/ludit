import socket, struct, json

from common import util
from common.log import logger as log

# mtools at https://github.com/troglobit/mtools is handy for testing multicast from the cmd line
# (add a "-1" to the handler_par.len argument in line 290 to avoid a trailing "\x00")

class MulticastSocket(util.Threadbase):
    signals = 'socket_receive'

    def __init__(self, ip, port, name):
        super(MulticastSocket, self).__init__(name)
        self.multicast_ip = ip
        self.multicast_port = port
        self.multicast_group = (ip, port)
        log.info('starting multicast socket at %s:%i' % (ip, port))

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

        while not self.terminated:
            try:
                data = self.socket.recv(1024)
            except socket.timeout:
                continue
            try:
                message = json.loads(data.decode())
            except json.JSONDecodeError as e:
                log.critical(f'multicast rx got malformed json exception "{e}"')
                continue
            except Exception as e:
                log.critical(f'multicast rx got exception "{e}"')
                continue
            try:
                # note that what is sent is also received. Nothing is done to filter out that.
                self.emit('socket_receive', message)
            except Exception as e:
                log.critical('emit message failed with %s' % str(e))

        self.socket.close()
        log.debug('multicast exits')


class Server(MulticastSocket):
    signals = 'server_receive'

    def __init__(self, ip, port):
        super(Server, self).__init__(ip, port, 'server mc ')
        super().connect('socket_receive', self.receive)

    def receive(self, message):
        try:
            if message['to'] == 'server':
                self.emit('server_receive', message)
        except Exception as e:
            log.error('multicast server rx gave %s' % str(e))


class Client(MulticastSocket):
    signals = 'client_receive'

    def __init__(self, id, ip, port):
        super(Client, self).__init__(ip, port, 'client mc  ')
        self.id = id
        super().connect('socket_receive', self.receive)

    def receive(self, message):
        try:
            if message['to'] in (self.id, '*') or self.id == '*':
                self.emit('client_receive', message)
        except KeyError as e:
            log.error(f'multicast client rx message invalid, missing {e} field')
        except Exception as e:
            log.error(f'multicast client rx gave exception {e}')
