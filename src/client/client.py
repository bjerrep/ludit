from client import client_socket
from client import player
from common import util
from common import multicast
from common.log import logger as log
import logging
import sys
import time
import signal
import argparse
import threading
import json
from enum import Enum


class RTState(Enum):
    RT_IDLE = 0
    RT_LOCAL = 1
    RT_AAC = 2


class Client(util.Threadbase):
    def __init__(self, configuration):
        super(Client, self).__init__(name='client')
        self.groupname = configuration['group']
        self.devicename = configuration['device']

        try:
            realtime = configuration['realtime'] == 'true'
        except:
            realtime = False

        self.id = '%s:%s' % (self.groupname, self.devicename)
        log.info('starting client %s' % self.id)
        self.server_endpoint = None
        self.terminate_socket = False
        self.player = player.Player(realtime)
        self.player.connect('status', self.slot_player_status)

        self.socket = None
        self.server_offline_counter = 10
        self.socket_lock = threading.Lock()

        self.multicast = multicast.Client(
            self.id,
            configuration['multicast']['ip'],
            int(configuration['multicast']['port']))

        self.multicast.connect('client_receive', self.multicast_rx)

        server_connector_thread = threading.Thread(target=self.server_connector, args=())
        server_connector_thread.daemon
        server_connector_thread.start()

        self.start()

    def terminate(self):
        self.multicast.terminate()
        if self.socket:
            self.socket.terminate()
            self.socket.join()
        self.player.terminate()
        if self.player.isAlive():
            self.player.join()
        super().terminate()

    def connected(self):
        return self.socket is not None

    def setup_realtime(self):
        self.rt_state = RTState.RT_IDLE
        self.setup_local_monitor_pipeline()

    def setup_local_monitor_pipeline(self):
        self.rt_pipeline = 'alsasrc ! cutter'

    def rt_new_state(self, state):
        if state == RTState.RT_IDLE:
            self.setup_local_monitor_pipeline()

    def multicast_rx(self, message):
        command = message['command']
        if command == 'server_socket':
            if not self.socket:
                endpoint = message['endpoint']
                if endpoint == "None":
                    log.critical("server refused the connection (check the group and device name)")
                    time.sleep(1)
                    util.die('exiting..', 1, True)
                log.info('server found, connecting to %s' % endpoint)
                self.server_endpoint = util.split_tcp(endpoint)
                self.start_socket()

    def slot_player_status(self, message):
        if message in ('buffered', 'starved'):
            if self.socket:
                self.socket.send({'command': 'status',
                                  'clientname': self.devicename,
                                  'state': message})
        elif message in ('rt_stop', 'rt_play'):
            log.info(f'realtime status: {message}')
        else:
            log.error(f'got unknown message {str(message)}')

    def slot_new_message(self, message):
        try:
            self.player.process_server_message(message)
        except Exception as e:
            log.critical('client slot_new_message "%s" caught "%s"' % (str(message), str(e)))

    def slot_socket(self, state):
        self.socket_lock.acquire()
        if state == 'open':
            if self.socket:
                self.socket.send({'command': 'time',
                                  'clientname': self.devicename,
                                  'epoch': str(time.time())})
        elif state == 'closed':
            # this is running in the socket thread, move the work to this thread
            log.info('got socket close message')
            self.terminate_socket = True
        self.socket_lock.release()

    def start_socket(self):
        self.socket_lock.acquire()
        if self.socket:
            raise util.IsOpenException
        self.socket = client_socket.ClientSocket(self.server_endpoint)
        self.socket.connect('audio', self.player.new_audio)
        self.socket.connect('message', self.slot_new_message)
        self.socket.connect('socket', self.slot_socket)
        self.socket_lock.release()

    def server_connector(self):
        delay = 0.1
        while not self.terminated:
            if self.terminate_socket:
                self.socket_lock.acquire()
                self.terminate_socket = False
                if self.socket:
                    self.socket.join()
                    self.socket = None
                self.server_endpoint = None
                self.player.process_message({'command': 'stopping'})
                log.info('waiting for server connection')
                self.server_offline_counter = 10
                self.socket_lock.release()

            if not self.server_endpoint:
                if self.server_offline_counter:
                    self.server_offline_counter -= 1
                    if not self.server_offline_counter:
                        log.critical('server seems to be offline')
                try:
                    self.multicast.send({'command': 'get_server_socket',
                                         'to': 'server',
                                         'from': self.id})
                except OSError:
                    log.warning('got a multicast send exception. Bummer.')

                if delay < 5.0:
                    delay += 0.1
            else:
                delay = 0.1

            _delay = delay
            while _delay > 0.0 and not self.terminated:
                time.sleep(0.1)
                _delay -= 0.1

        log.debug('server connector exits')
        return False

    def run(self):
        self.player.mainloop.run()
        log.debug('client exits')


def generate_config():
    configuration = {
        'version': util.CONFIG_VERSION,
        'multicast': {
            'ip': util.multicast_ip,
            'port': str(util.multicast_port)
        },
        'realtime': {
            'enabled': 'false'
        }
    }
    return configuration


def load_configuration(configuration_file):
    try:
        with open(configuration_file) as f:
            configuration = json.loads(f.read())
            version = configuration.get('version')
            log.info('loaded configuration %s' % configuration_file)
            if version != util.CONFIG_VERSION:
                util.die('expected configuration version %s but found version %s' % (util.CONFIG_VERSION, version))
    except Exception:
        log.warning('no configuration file specified (--cfg), using defaults')
        configuration = generate_config()
    return configuration


def start():
    """
    Use the run_client.py script in ./src
    """
    try:
        parser = argparse.ArgumentParser('Ludit client')
        parser.add_argument('--id', action='store', dest='id',
                            help='required identifier in the form groupname:devicename')
        parser.add_argument('--newcfg', action='store_true', dest='newcfg',
                            help='dump template configuration file to stdout')
        parser.add_argument('--cfg', dest='cfg',
                            help='configuration file to use (optional)')
        parser.add_argument('--verbose', action='store_true',
                            help='enable more logging')
        parser.add_argument('--nocheck', action='store_true',
                            help='don\'t check for multiple client instances')

        results = parser.parse_args()

        if results.newcfg:
            configuration = generate_config()
            configuration['group'] = 'stereo'
            configuration['device'] = 'stereo'
            config = json.dumps(configuration, indent=4, sort_keys=True)
            print(config)
            exit(0)

        if not results.nocheck:
            util.get_pid_lock('ludit_client')

        if results.verbose:
            log.setLevel(logging.DEBUG)

        try:
            configuration = load_configuration(results.cfg)
        except:
            configuration = generate_config()

        try:
            groupname, devicename = results.id.split(':')
            configuration['group'] = groupname
            configuration['device'] = devicename
        except:
            if not configuration.get('group'):
                raise Exception('need a group:device name pair from arguments or configuration file')

        def ctrl_c_handler(_, __):
            try:
                print(' ctrl-c handler')
                if _client:
                    log.info('terminating by user')
                    _client.terminate()
                    _client.join()
                sys.exit(1)
            except Exception as e:
                log.critical('ctrl-c handler got ' + str(e))

        signal.signal(signal.SIGINT, ctrl_c_handler)

        _client = None
        _client = Client(configuration)
        _client.join()

        log.info('client exiting')

    except Exception as e:
        log.critical('client exception: %s' % str(e))
