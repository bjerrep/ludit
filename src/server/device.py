from common.log import logger as log
from common import util
from server import server_socket


class Device(util.Base):
    signals = ('clientconnected', 'message')

    def __init__(self, devicename, groupname):
        self.jsn = {}
        self.clientname = devicename
        self.id = util.make_id(groupname, self.clientname)
        self.socket = server_socket.ServerSocket(self.id)
        self._state = None

    def terminate(self):
        self.socket.terminate()
        # don't leave before the socket is gone in order to avoid stray messages
        self.socket.join()

    def get_clientname(self):
        return self.clientname

    def state(self):
        return self._state

    def message(self, msg):
        msg['clientname'] = self.clientname
        if msg['command'] == 'status':
            state = msg['state']
            if state in ('buffered', 'starved'):
                self._state = state
        self.emit('message', msg)

    def client_connected(self):
        log.info('[%s] sending configuration' % self.id)
        _ = self.jsn
        _['command'] = 'configuration'
        self.socket.send(_)
        self.emit('clientconnected')

    def start_socket(self):
        self.socket.connect('clientconnected', self.client_connected)
        self.socket.connect('message', self.message)
        return self.socket.get_endpoint()

    def set_param(self, param):
        self.jsn.update(param)
        self.socket.send(param)
