#!/bin/python

from common import util
from common.log import logger as log
from common import multicast
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
        self.multicast.connect('receive', self.multicast_rx)
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
            self.service('restart', 'ludit_remote')
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
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                result = "%.1f" % (int(f.read()) / 1000)
        elif command == 'ip':
            result = util.local_ip()
        elif command == 'message':
            log.info('message: %s' % message['message'])
        elif command == 'ping':
            pass # fixit
        else:
            result = str(-1)

        if result:
            log.info('%s returns %s = %s' % (self.id, command, result))
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
    parser = argparse.ArgumentParser('remote - monitor client')
    parser.add_argument('--id', action='store', dest='id',
                        help='unique identifier', required=True)
    results = parser.parse_args()

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
