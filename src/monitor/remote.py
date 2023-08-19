#!/bin/python

from common import util
from common.log import logger as log
from common import multicast
from monitor import metrics
import time
import signal
import argparse
import sys


class Remote(util.Threadbase):

    SERVER_LOST_SECONDS = 10
    server_lost_time = time.time() + SERVER_LOST_SECONDS

    def __init__(self, id):
        super(Remote, self).__init__()
        self.id = id
        self.multicast = multicast.Client(id, util.remote_multicast_ip, util.remote_multicast_port)
        self.multicast.connect('client_receive', self.multicast_rx)
        log.info('remote is starting with id "%s" on multicast %s:%i' %
                 (id, util.remote_multicast_ip, util.remote_multicast_port))
        self.start()

    def terminate(self):
        self.multicast.terminate()
        self.multicast.join()
        super().terminate()

    def service(self, action, name):
        log.info('%s %s' % (action, name))
        util.execute("/usr/bin/systemctl %s %s" % (action, name))

    def computer(self, command):
        if command == 'reboot':
            log.info('rebooting...')
            util.execute("/usr/bin/reboot")
        elif command == 'restart_all':
            self.service('restart', 'ludit_client')
            self.service('restart', 'twitse_client')
            self.service('restart', 'ludit_remote')  # this one
        elif command == 'restart_ludit':
            self.service('restart', 'ludit_client')
        else:
            log.warning('got unknown command %s' % command)

    def multicast_rx(self, message):
        self.server_lost_time = time.time() + self.SERVER_LOST_SECONDS
        command = message['command']
        log.debug('processing command %s' % command)
        result = None
        if command in ('start', 'stop'):
            result = self.service(command, message['service'])
        elif command in ('reboot', 'restart_all'):
            result = self.computer(command)
        elif command == 'cputemperature':
            result = metrics.get_cputemperature()
        elif command == 'ip':
            result = util.local_ip()
        elif command == 'uptime':
            result = metrics.get_uptime()
        elif command == 'loadaverages':
            result = metrics.get_loadaverages()
        elif command == 'cpuload':
            result = metrics.get_cpu_load()
        elif command == 'wifi_stats':
            result = metrics.get_wifi_stats()
        elif command == 'message':
            log.info('message: %s' % message['message'])
        elif command == 'ping':
            pass
        else:
            result = str(-1)

        if result:
            log.debug('%s returns %s = %s' % (self.id, command, result))
            self.multicast.send({
                'command': command,
                'to': 'server',
                'from': self.id,
                'result': result})

    def run(self):
        while not self.terminated:
            time.sleep(0.1)

            if self.server_lost_time < time.time():
                log.critical('server lost')
                self.server_lost_time = time.time() + self.SERVER_LOST_SECONDS


def start():

    # wait for the network to -really- get working
    ip = util.wait_for_network()
    if not ip:
        log.critical('no network connection, exiting')
        exit(1)
    log.info(f'ludit remote starting at {ip}')

    parser = argparse.ArgumentParser('remote - monitor client')
    parser.add_argument('--id', action='store', dest='id',
                        help='unique identifier', required=True)
    results = parser.parse_args()

    util.get_pid_lock('ludit_remote')

    def ctrl_c_handler(_, __):
        try:
            print(' ctrl-c handler')
            if _remote:
                log.info('terminating by user')
                _remote.terminate()
                _remote.join()
            sys.exit(1)
        except Exception as e:
            log.critical('ctrl-c handler got ' + str(e))

    signal.signal(signal.SIGINT, ctrl_c_handler)

    _remote = Remote(results.id)
    _remote.join()

    log.info('remote exits')
