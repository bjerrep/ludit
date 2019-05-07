from common.log import logger as log
from common import util
from server import server_socket


class Device(util.Base):
    """
    A device in the server maintain the connection to a remote client. Its called device in the server rather than
    client in an attempt to minimize confusion when working in the source files.
    """
    signals = ('deviceconnected', 'devicedisconnected', 'message')

    def __init__(self, devicename, groupname):
        self.jsn = {}
        self.devicename = devicename
        self.connected = False
        self.id = util.make_id(groupname, self.devicename)
        self._state = None
        self.start_socket()

    def __hash__(self):
        return hash(self.id)

    def terminate(self):
        self.socket.terminate()
        # don't leave before the socket is gone in order to avoid stray messages
        self.socket.join()

    def name(self):
        return self.devicename

    def state(self):
        return self._state

    def slot_message(self, msg):
        msg['clientname'] = self.devicename
        if msg['command'] == 'status':
            state = msg['state']
            if state in ('buffered', 'starved'):
                self._state = state
        self.emit('message', msg)

    def slot_connected(self):
        log.info('[%s] sending configuration' % self.id)
        _configuration = {'param': self.jsn}
        _configuration['command'] = 'configure'
        self.socket.send(_configuration)
        self.connected = True
        self.emit('deviceconnected', self)

    def slot_disconnected(self):
        self.connected = False
        self.emit('devicedisconnected', self)

    def start_socket(self):
        self.socket = server_socket.ServerSocket(self.id)
        self.socket.connect('deviceconnected', self.slot_connected)
        self.socket.connect('devicedisconnected', self.slot_disconnected)
        self.socket.connect('message', self.slot_message)

    def get_endpoint(self):
        return self.socket.get_endpoint()

    def set_param(self, param):
        self.jsn.update(param)
        if self.connected:
            self.socket.send(param)
