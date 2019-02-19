#!/bin/python

from common import util
from common.log import logger as log
from common import multicast
from common import websocket
from monitor import metrics
from monitor import bluetooth_metrics
import time
import signal
import sys


monitor_websocket_port = 45659


class Monitor(util.Threadbase):

    SERVER_PING_SECONDS = 4
    server_ping_time = 0

    def __init__(self):
        super(Monitor, self).__init__()
        self.multicast = multicast.Server(util.remote_multicast_ip, util.remote_multicast_port)
        self.multicast.connect('server_receive', self.multicast_rx)
        self.ws = websocket.WebSocket(util.local_ip(), monitor_websocket_port)
        self.ws.connect('message', self.websocket_rx)
        self.start()
        self.bt = bluetooth_metrics.BTDiscoverer()
        self.bt.connect('bt_client', self.bt_slot)

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

        log.debug('%s returns %s = %s' % (client, command, result))
        websocket.WebSocket.send_message(None,
                                         {'command': 'get_' + command,
                                          'from': client,
                                          'result': result})

    def computer(self, command):
        if command == 'reboot':
            log.info('rebooting...')
            util.execute("/usr/bin/reboot")
        elif command == 'restart_all':
            self.service('restart', 'bluealsa')
            self.service('restart', 'ludit_server')
            self.service('restart', 'twitse_server')
            self.service('restart', 'ludit_monitor')  # this one
        elif command == 'restart_ludit':
            self.service('restart', 'ludit_server')
        else:
            log.warning('got unknown command %s' % command)

    def bt_slot(self, _json):
        self.send_websocket_result('get_bluetooth_clients', _json)
        self.bt = None

    @staticmethod
    def send_websocket_result(command, result):
        log.debug('server returns %s = %s' % (command, result))
        websocket.WebSocket.send_message(None,
                                         {'command': command,
                                          'from': 'server',
                                          'result': result})

    def websocket_rx(self, message):
        ip = message['ip']
        command = message['command']
        log.debug('got websocket command %s from %s' % (command, ip))
        result = None

        if command == 'restart_all':
            self.multicast.send({'command': 'restart_all', 'to': '*'})
            self.computer(command)
        elif command == 'restart_ludit':
            self.multicast.send({'command': 'restart_ludit', 'to': '*'})
            self.computer(command)
        elif command == 'reboot':
            self.multicast.send({'command': 'reboot', 'to': '*'})
            self.computer(command)
        elif command == 'get_cputemperature':
            self.multicast.send({'command': 'cputemperature', 'to': '*'})
            result = metrics.get_cputemperature()
        elif command == 'get_uptime':
            self.multicast.send({'command': 'uptime', 'to': '*'})
            result = metrics.get_uptime()
        elif command == 'get_loadaverages':
            self.multicast.send({'command': 'loadaverages', 'to': '*'})
            result = metrics.get_loadaverages()
        elif command == 'get_cpuload':
            self.multicast.send({'command': 'cpuload', 'to': '*'})
            result = metrics.get_cpu_load()
        elif command == "get_wifi_stats":
            self.multicast.send({'command': 'wifi_stats', 'to': '*'})
        elif command == "get_bluetooth_clients":
            if not self.bt:
                self.bt = bluetooth_metrics.BTDiscoverer()
                self.bt.connect('bt_client', self.bt_slot)
            else:
                log.info('bluetooth request ignored, already active')
        elif command == 'get_ip':
            self.multicast.send({'command': 'ip', 'to': '*'})
            result = util.local_ip()

        if result:
            self.send_websocket_result(command, result)

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

    _monitor = None
    _monitor = Monitor()
    _monitor.join()

    log.info('monitor exits')
