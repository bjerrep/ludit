from common.log import logger as log
from common import util
from server import server_socket


class Device(util.Base):
    signals = ('clientconnected', 'clientdisconnected', 'message')

    def __init__(self, devicename, groupname):
        self.jsn = {}
        self.devicename = devicename
        self.connected = False
        self.id = util.make_id(groupname, self.devicename)
        self.socket = server_socket.ServerSocket(self.id)
        self.socket.connect('clientconnected', self.client_connected)
        self.socket.connect('brokensocket', self.broken_socket)
        self.socket.connect('message', self.message)
        self._state = None

    def terminate(self):
        self.socket.terminate()
        # don't leave before the socket is gone in order to avoid stray messages
        self.socket.join()

    def get_clientname(self):
        return self.devicename

    def state(self):
        return self._state

    def message(self, msg):
        msg['clientname'] = self.devicename
        if msg['command'] == 'status':
            state = msg['state']
            if state in ('buffered', 'starved'):
                self._state = state
        self.emit('message', msg)

    def client_connected(self):
        log.info('[%s] sending configuration' % self.id)
        _configuration = dict(self.jsn)
        _configuration['command'] = 'configuration'
        self.socket.send(_configuration)
        self.connected = True
        self.emit('clientconnected')

    def broken_socket(self):
        self.connected = False
        self.emit('clientdisconnected', self.id)

    def is_connected(self):
        return self.connected

    def get_endpoint(self):
        return self.socket.get_endpoint()

    def set_param(self, param):
        self.jsn.update(param)
        self.socket.send(param)
