import json
import SimpleWebSocketServer
from common import util
from common.log import logger as log

clients = []
emitter = None


class WebsocketInterface(SimpleWebSocketServer.WebSocket):
    emitter = None
    def handleMessage(self):
        try:
            data = self.data
            log.debug('websocket message: %s' % data)
            message = json.loads(data)
            message['ip'] = self.address[0]
            emitter.emit('message', message)
        except Exception as e:
            log.critical('exception in handleMessage: %s' % str(e))

    def handleConnected(self):
        try:
            log.info(f'new websocket connection from {self.address[0]}')
            clients.append(self)
            emitter.send_message(self, {'command': 'connected'})
        except Exception as e:
            log.critical('exception in handleConnected: {str(e)}')

    def handleClose(self):
        clients.remove(self)
        log.debug('websocket connection from {self.address[0]} closed')


class WebSocketServer(util.Threadbase):
    signals = 'message'

    def __init__(self, ip, port, description):
        global emitter
        super(WebSocketServer, self).__init__()
        emitter = self
        port = port
        log.info(f'starting websocket server {description} on {ip}:{port}')
        self.server = SimpleWebSocketServer.SimpleWebSocketServer(ip, port, WebsocketInterface)
        self.start()

    def terminate(self):
        log.debug('terminating websocket')
        super().terminate()

    @staticmethod
    def send_message(client, message_dict):
        _json = json.dumps(message_dict)
        for _client in clients:
            if not client or _client.address[0] == client.address[0]:
                _client.sendMessage(_json)

    def run(self):
        try:
            while not self.terminated:
                self.server.serveonce()
            self.server.close()
        except Exception as e:
            log.error(f'failed to start websocket: {str(e)}')
        log.debug('websocket exits')
