#!/bin/python

from common import util
from common.log import logger as log
import json
from SimpleWebSocketServer import WebSocket, SimpleWebSocketServer

clients = []
emitter = None


class WebsocketClient(WebSocket):
    def handleMessage(self):
        global emitter
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
            log.info('new websocket connection from %s' % self.address[0])
            clients.append(self)
            emitter.send_message(self, {'command': 'connected'})
        except Exception as e:
            log.critical('exception in handleConnected: %s' % str(e))

    def handleClose(self):
        clients.remove(self)
        log.debug('websocket connection from %s closed' % self.address[0])


class WebSocket(util.Threadbase):
    signals = 'message'

    def __init__(self, ip, port):
        global emitter
        super(WebSocket, self).__init__()
        emitter = self
        log.info('starting websocket on %s:%i' % (ip, port))
        self.server = SimpleWebSocketServer(ip, port, WebsocketClient)
        self.start()

    def terminate(self):
        log.debug('terminating websocket')
        super().terminate()
        self.server.close()

    @staticmethod
    def send_message(client, message_dict):
        _json = json.dumps(message_dict)
        for _client in clients:
            if not client or _client.address[0] == client.address[0]:
                _client.sendMessage(_json)

    def run(self):
        while not self.terminated:
            self.server.serveonce()
        log.debug('websocket exits')
