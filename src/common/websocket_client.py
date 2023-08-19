import time, json
from websocket import WebSocket
from websocket._exceptions import WebSocketConnectionClosedException

from common import util
from common.log import logger as log

clients = []
emitter = None


class WebSocketClient(util.Threadbase):
    signals = 'message'

    def __init__(self, ip, port, description):
        super(WebSocketClient, self).__init__()
        port = port
        self.description = description
        log.info(f'starting websocket {description} client on {ip}:{port}')
        self.ws = WebSocket()
        self.server = f'ws://{ip}:{port}'
        self.connected = False
        self.start()

    def terminate(self):
        log.debug(f'terminating websocket {self.description}')
        super().terminate()
        self.ws.close()

    def run(self):
        while not self.terminated:
            try:
                message = json.loads(self.ws.recv())
                self.emit('message', message)
            except WebSocketConnectionClosedException:
                if self.terminated:
                    continue
                if self.connected:
                    log.error(f'websocket {self.description} server connection lost')
                    self.connected = False
                    self.emit('connected', False)
                time.sleep(1)
                try:
                    self.ws.connect(self.server)
                    log.info(f'connected to {self.description} websocket server at {self.server}')
                    self.connected = True
                    self.emit('connected', True)
                except ConnectionRefusedError:
                    pass
            except json.JSONDecodeError:
                continue

        log.debug(f'{self.description} websocket exits')
