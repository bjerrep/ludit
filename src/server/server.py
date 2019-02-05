#!/bin/python

from common import util
from common.log import logger as log
from common import multicast
from common import websocket
from server import playsequencer
from server import inputmux
import time
import signal
import argparse
import queue
import logging
import sys
import json
import threading


class Server(util.Threadbase):

    def __init__(self, configuration_file):
        super(Server, self).__init__(name='server    ')

        self.configuration_file = configuration_file
        self.configuration = None
        self.load_configuration()

        self.play_sequencer = None
        self.play_thread_active = True
        self.cant_play_warning = 5
        self.delayed_broadcast = None

        self.input_mux = inputmux.InputMux()

        log.info('starting server at %s' % util.local_ip())
        self.launch_playsequencer()

        self.multicast = multicast.Server(util.multicast_ip, util.multicast_port)
        self.multicast.connect('server_receive', self.multicast_rx)

        self.ws = websocket.WebSocket(util.local_ip(), util.server_ludit_websocket_port)
        self.ws.connect('message', self.websocket_rx)

        self.start()

    def terminate(self):
        log.debug('server terminate called')
        self.ws.terminate()
        self.multicast.terminate()
        self.input_mux.terminate()
        if self.play_sequencer:
            self.play_sequencer.terminate()

        super().terminate()
        log.debug('server terminated')

    def load_configuration(self):
        try:
            with open(self.configuration_file) as f:
                self.configuration = json.loads(f.read())
            log.info('loaded configuration %s' % self.configuration_file)
        except:
            log.warning('no configuration file specified (--cfg), using template configuration')
            self.configuration = generate_config()

    def save_configuration(self):
        try:
            with open(self.configuration_file, 'w') as f:
                f.write(json.dumps(self.play_sequencer.current_configuration(), indent=4, default=lambda x : str(x)))
            log.info('saved configuration in %s' % self.configuration_file)
        except Exception as e:
            log.warning('save configuration failed (see --cfg) - %s' % str(e))

    def all_groups_disconnected(self):
        log.error('playsequenser reports that all groups (and devices) have disconnected')
        self.play_thread_active = False

    def multicast_rx(self, message):
        device = "unknown"
        try:
            command = message['command']
            if command == 'get_server_socket':
                device = message['from']
                groupname, devicename = device.split(':')
                endpoint = self.play_sequencer.get_group(groupname).get_device(devicename).get_endpoint()
                log.debug('sending tcp socket endpoint %s to device %s' % (str(endpoint), device))
                self.multicast.send({'command': 'server_socket',
                                     'from': 'server',
                                     'to': device,
                                     'endpoint': str(endpoint)})
        except Exception as e:
            log.error('connection failed from unknown device %s (%s)' % (device, str(e)))
            self.multicast.send({'command': 'server_socket',
                                 'from': 'server',
                                 'to': device,
                                 'endpoint': "None"})

    def websocket_rx(self, message):
        command = message['command']

        if command == 'get_configuration':
            self.broadcast_new_configuration()
            return
        elif command == 'save_current_configuration':
            self.save_configuration()
            return

        group = message['group']
        value = message['value']

        if command in ('set_on', 'set_enabled', 'set_volume', 'set_balance',
                       'set_xoverfreq', 'set_xoverpoles', 'set_highlowbalance'):

            raw_cmd = command.replace('set_', '')
            log.info('ws: setting %s %s to %s' % (group, raw_cmd, value))
            self.play_sequencer.get_group(group).set_param(raw_cmd, value)

        elif command.startswith('set_band'):
            band = command[8:]
            log.info('ws: setting %s band %s to %s' % (group, band, value))
            self.play_sequencer.get_group(group).set_param_array('equalizer', band, value)

        else:
            log.error('ws: got unknown command %s' % command)

        if not self.delayed_broadcast:
            self.delayed_broadcast = threading.Timer(0.05, self.send_broadcast)
            self.delayed_broadcast.start()

    def send_broadcast(self):
        self.broadcast_new_configuration()
        self.delayed_broadcast = None

    def broadcast_new_configuration(self):
        log.debug('ws: sending current configuration')
        current_config = self.play_sequencer.current_configuration()
        self.ws.send_message(None,
                             {'command': 'configuration',
                              'current_conf': current_config})

    def slot_message(self, message):
        command = message['command']
        client = message['clientname']
        if command == 'time':
            client_time = float(message['epoch'])
            log.info('[%s] time deviation is %.1f ms' %
                     (client, (time.time() - client_time) * 1000.0))

    def launch_playsequencer(self):
        try:
            log.info('launching playsequencer')
            if self.play_sequencer:
                self.play_sequencer.terminate()

            self.play_sequencer = playsequencer.PlaySequencer(self.configuration)
            self.play_sequencer.connect('allgroupsdisconnected', self.all_groups_disconnected)
            self.cant_play_warning = 5
        except Exception as e:
            log.critical('playsequencer failed with %s' % str(e))

    def run(self):
        try:
            while not self.terminated:
                try:
                    key, value = self.input_mux.queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if key == 'audio':
                    self.play_sequencer.new_audio(value)
                elif key == 'codec':
                    self.play_sequencer.set_codec(value)
                elif key == 'state':
                    self.play_sequencer.set_state(value)
                elif key == 'volume':
                    self.play_sequencer.set_volume(value)
                else:
                    log.critical('got an unknown key %s' % key)

        except Exception as e:
            log.critical("server loop caught exception '%s'" % str(e))
            self.terminate()

        log.debug('server exits')


def generate_config():
    kitchen_device_left = {
        'name': 'left',
        'channel': 'left'
    }
    kitchen_device_right = {
        'name': 'right',
        'channel': 'right'
    }

    kitchen = {
        'legend': 'Kitchen',
        'name': 'kitchen',
        'enabled': "on",
        'on': "on",
        'volume': '100.0',
        'balance': '0.0',
        'highlowbalance': '-0.45',
        'xoverfreq': '1300',
        'xoverpoles': '4',
        'devices': [kitchen_device_left, kitchen_device_right],
        'equalizer': {'0': '12.0', '1': '10.0', '2': '0.0'}
    }

    stereo_device = {
        'name': 'stereo',
        'channel': 'stereo',
        'left_device': 'hw:0',
        'right_device': 'hw:1'
    }

    stereo = {
        'legend': 'Stereo',
        'name': 'stereo',
        'enabled': "off",
        'on': "off",
        'volume': '100.0',
        'balance': '0.0',
        'highlowbalance': '0.0',
        'xoverfreq': '1200',
        'xoverpoles': '4',
        'devices': [stereo_device],
        'equalizer': {'0': '8.0', '1': '4.0'}
    }

    configuration = {
        'groups': [kitchen, stereo],
        'audiotimeout': '5',
        'playdelay': '0.5',
        'buffersize': '200000'
    }
    return configuration


def start():
    """
    Use the run_server.py script in ./src
    """
    try:
        parser = argparse.ArgumentParser('Ludit client')
        parser.add_argument('--newcfg', action='store_true', dest='newcfg',
                            help='dump template configuration file to stdout')
        parser.add_argument('--cfg', dest='cfg',
                            help='configuration file to use')
        parser.add_argument('--verbose', action='store_true',
                            help='enable more logging')

        results = parser.parse_args()

        if results.verbose:
            log.setLevel(logging.DEBUG)

        if results.newcfg:
            config = json.dumps(generate_config(), indent=4, sort_keys=True)
            print(config)
            exit(0)

        def ctrl_c_handler(_, __):
            try:
                print(' ctrl-c handler')
                if _server:
                    log.info('terminating by user')
                    _server.terminate()
                    log.debug('terminate done, waiting..')
                    _server.join()
                sys.exit(1)
            except Exception as e:
                log.critical('ctrl-c handler got ' + str(e))

        def ignore(_, __):
            pass

        signal.signal(signal.SIGINT, ctrl_c_handler)
        signal.signal(signal.SIGPIPE, ignore)

        _server = None
        _server = Server(results.cfg)
        _server.join()
        log.info('server exiting')

    except Exception as e:
        log.critical('server exception: %s' % str(e))
