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
import os
import queue
import sys
import json
import stat
import threading


class Server(util.Threadbase):

    def __init__(self, configuration):
        super(Server, self).__init__(name='server    ')
        self.configuration = configuration
        self.play_sequencer = None
        self.play_thread_active = True
        self.cant_play_warning = 5
        self.delayed_broadcast = None

        self.input_mux = inputmux.InputMux()

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

    def client_disconnected(self, source):
        log.error('connection lost to %s' % source)
        self.play_thread_active = False

    def multicast_rx(self, message):
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

    def websocket_rx(self, message):
        command = message['command']
        group = message['group']

        if command == 'get_configuration':
            self.broadcast_new_configuration()
            return

        value = message['value']

        if command == 'set_on':
            log.info('ws: setting %s on/off to %s' % (group, value))
            self.play_sequencer.get_group(group).set_param('on', value)
        elif command == 'set_volume':
            log.info('ws: setting %s volume to %s' % (group, value))
            self.play_sequencer.get_group(group).set_param('volume', value)
        elif command == 'set_balance':
            log.info('ws: setting %s balance to %s' % (group, value))
            self.play_sequencer.get_group(group).set_param('balance', value)
        elif command == 'set_xoverfreq':
            log.info('ws: setting %s xover to %s' % (group, value))
            self.play_sequencer.get_group(group).set_param('xoverfreq', value)
        elif command == 'set_xoverpoles':
            log.info('ws: setting %s xover poles to %s' % (group, value))
            self.play_sequencer.get_group(group).set_param('xoverpoles', value)
        elif command == 'set_highlowbalance':
            log.info('ws: setting %s high/low balance to %s' % (group, value))
            self.play_sequencer.get_group(group).set_param('highlowbalance', value)
        elif command == 'set_band0':
            log.info('ws: setting %s band0 to %s' % (group, value))
            self.play_sequencer.get_group(group).set_param_array('equalizer', '0', value)
        elif command == 'set_band1':
            log.info('ws: setting %s band1 to %s' % (group, value))
            self.play_sequencer.get_group(group).set_param_array('equalizer', '1', value)
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
            self.play_sequencer.connect('clientdisconnected', self.client_disconnected)
            self.cant_play_warning = 5
        except Exception as e:
            log.critical('playsequencer failed with %s' % str(e))

    def run(self):
        try:
            log.info('starting server at %s' % util.local_ip())
            self.launch_playsequencer()

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

        except:
            self.terminate()

        log.debug('server exits')


def generate_config():
    device_left = {
        'name': 'left',
        'channel': '0'
    }
    device_right = {
        'name': 'right',
        'channel': '1'
    }
    devices = [device_left, device_right]

    kitchen = {
        'name': 'kitchen',
        'enabled': True,
        'on': True,
        'volume': '100.0',
        'balance': '0.0',
        'highlowbalance': '-0.45',
        'xoverfreq': '1300',
        'xoverpoles': '4',
        'devices': devices,
        'equalizer': {'0': '12.0', '1': '10'}
    }

    stereo = {
        'name': 'stereo',
        'enabled': False,
        'on': False,
        'volume': '100.0',
        'balance': '0.0',
        'highlowbalance': '0.0',
        'xoverfreq': '1200',
        'xoverpoles': '4',
        'devices': devices,
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
        results = parser.parse_args()

        if results.newcfg:
            config = json.dumps(generate_config(), indent=4, sort_keys=True)
            print(config)
            exit(0)

        if results.cfg:
            with open(results.cfg) as f:
                config = json.loads(f.read())
            log.info('loaded configuration %s' % results.cfg)
        else:
            log.warning('no configuration file specified (--cfg), using template configuration')
            config = generate_config()

        if not stat.S_ISFIFO(os.stat('/tmp/audio').st_mode):
            log.critical('/tmp/audio is not a fifo')
            exit(1)

        def ctrl_c_handler(_, __):
            try:
                print(' ctrl-c handler')
                if _server:
                    log.info('terminating by user')
                    _server.terminate()
                    _server.join()
                sys.exit(1)
            except Exception as e:
                log.critical('ctrl-c handler got ' + str(e))

        def ignore(_, __):
            pass

        signal.signal(signal.SIGINT, ctrl_c_handler)
        signal.signal(signal.SIGPIPE, ignore)

        _server = None
        _server = Server(config)
        _server.join()
        log.info('server exiting')

    except Exception as e:
        log.critical('server exception: %s' % str(e))
