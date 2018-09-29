#!/bin/python

from common import util
from common.log import logger as log
from common import multicast
from common import websocket
import time
import signal
import sys


class Monitor(util.Threadbase):

    SERVER_PING_SECONDS = 4
    server_ping_time = 0

    def __init__(self):
        super(Monitor, self).__init__()
        self.multicast = multicast.Server(util.remote_multicast_ip, util.remote_multicast_port)
        self.multicast.connect('server_receive', self.multicast_rx)
        self.ws = websocket.WebSocket(util.local_ip(), util.server_monitor_websocket_port)
        self.ws.connect('message', self.websocket_rx)
        self.start()

    def terminate(self):
        self.ws.terminate()
        self.multicast.terminate()
        self.multicast.join()
        super().terminate()

    def service(self, action, name):
        log.info('%s %s' % (action, name))
        util.execute("/usr/bin/systemctl %s %s" % (action, name))

    def multicast_rx(self, message):
        command = message['command']
        result = message['result']
        client = message['from']

        log.info('%s returns %s = %s' % (client, command, result))
        websocket.WebSocket.send_message(None,
                                        {'command': 'get_' + command,
                                         'from': client,
                                         'result': result})

    def websocket_rx(self, message):
        ip = message['ip']
        command = message['command']
        log.info('got websocket command %s from %s' % (command, ip))
        result = None

        if command == 'restart_all':
            self.multicast.send({'command': 'restart_all', 'to': '*'})
            self.service('restart', 'ludit_server')
            self.service('restart', 'twitse_server')
            self.service('restart', 'ludit_monitor')
        elif command == 'get_cputemperature':
            self.multicast.send({'command': 'cputemperature', 'to': '*'})
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                result = "%.1f" % (int(f.read()) / 1000)
        elif command == 'get_ip':
            self.multicast.send({'command': 'ip', 'to': '*'})
            result = util.local_ip()

        if result:
            log.info('server returns %s = %s' % (command, result))
            websocket.WebSocket.send_message(None,
                                            {'command': command,
                                             'from': 'server',
                                             'result': result})

    def run(self):
        while not self.terminated:
            time.sleep(0.1)

            if time.time() > self.server_ping_time + self.SERVER_PING_SECONDS:
                self.server_ping_time = time.time()
                self.multicast.send({'command': 'ping', 'to': '*'})


def start():
    def ctrl_c_handler(_, __):
        try:
            print(' ctrl-c handler')
            if _monitor:
                log.info('terminating by user')
                _monitor.terminate()
                _monitor.join()
            sys.exit(1)
        except Exception as e:
            log.critical('ctrl-c handler got ' + str(e))

    signal.signal(signal.SIGINT, ctrl_c_handler)

    _monitor = Monitor()
    _monitor.join()

    log.info('monitor exits')
