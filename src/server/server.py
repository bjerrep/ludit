#!/usr/bin/env python3

from common import util
from common.log import logger as log
from common import multicast
from common import websocket_server, websocket_client
from server import playsequencer
from server import inputmux
import traceback
import signal
import argparse
import queue
import logging
import sys
import json
import threading


class Server(util.Threadbase):

    def __init__(self, configuration_file):
        super(Server, self).__init__(name='server')

        log.info('starting server at %s' % util.local_ip())

        self.configuration_file = configuration_file
        self.configuration = None
        self.load_configuration()

        self.play_sequencer = None
        self.cant_play_warning = 5
        self.delayed_broadcast = None

        self.launch_playsequencer()

        source_config = self.configuration['sources']
        streaming_config = self.configuration['streaming']
        self.input_mux = inputmux.InputMux(source_config, streaming_config)

        self.multicast = multicast.Server(
            self.configuration['multicast']['ip'],
            int(self.configuration['multicast']['port']))

        self.multicast.connect('server_receive', self.multicast_rx)

        ws_port = source_config['ludit_websocket_port']
        self.ws = websocket_server.WebSocketServer(util.local_ip(), ws_port, 'ludit_ws')
        self.ws.connect('message', self.websocket_rx)

        try:
            twitse_port = self.configuration["interfaces"]["twitse_websocket_port"]
            self.twitse_ws_client = websocket_client.WebSocketClient(util.local_ip(), twitse_port, 'twitse')
            self.twitse_ws_client.connect('message', self.websocket_twitse_rx)
        except:
            self.twitse_ws_client = None
            log.debug('not connecting to twitse websocket')

        self.start()

    def terminate(self):
        log.debug('server terminate called')
        super().terminate()
        self.ws.terminate()
        if self.twitse_ws_client:
            self.twitse_ws_client.terminate()
        self.multicast.terminate()
        self.input_mux.terminate()
        if self.play_sequencer:
            self.play_sequencer.terminate()
        log.debug('server terminated')

    def load_configuration(self):
        try:
            with open(self.configuration_file) as f:
                self.configuration = json.loads(f.read())
                version = self.configuration.get('version')
                log.info('loaded configuration %s' % self.configuration_file)
                if version != util.CONFIG_VERSION:
                    util.die('expected configuration version %s but found version %s' % (util.CONFIG_VERSION, version))
        except json.JSONDecodeError as e:
            util.die(f'got fatal error loading configuration file "{e}"')
        except Exception as e:
            log.warning('no configuration file specified (--cfg), using template configuration')
            self.configuration = generate_config()

    def save_configuration(self):
        try:
            with open(self.configuration_file, 'w') as f:
                config = self.play_sequencer.current_configuration()
                config.update({'sources': self.configuration['sources']})
                config.update({'multicast': self.configuration['multicast']})
                f.write(json.dumps(config, indent=4, default=lambda x: str(x)))
            log.info('saved configuration in %s' % self.configuration_file)
        except Exception as e:
            log.warning('save configuration failed (see --cfg) - %s' % str(e))

    def all_groups_disconnected(self):
        log.error('playsequenser reports that all groups (and devices) have disconnected')

    def multicast_tx(self, command, device_id, key=None, value=None):
        msg = {'command': command,
               'from': 'server',
               'to': device_id}
        if key:
            msg.update({key: value})
        self.multicast.send(msg)

    def multicast_rx(self, message):
        """
        Multicast receive is used for the initial communication with a client. The client
        will send 'get_server_socket' and will in return get a 'server_socket' containing
        the address of the tcp socket it should connect to and use from now on.
        """
        if self.terminated:
            return
        device_id = 'unknown'
        try:
            command = message['command']
            if command == 'get_server_socket':
                if message['version'] != util.LUDIT_VERSION:
                    raise Exception('server version is %s but client version is %s' %
                                    (util.LUDIT_VERSION, message['version']))
                device_id = message['from']
                groupname, devicename = device_id.split(':')
                device = self.play_sequencer.get_group(groupname).get_device(devicename)
                if device.connected:
                    log.warning(f'ignoring second connection request from {device_id}, already have a device with that id')
                    self.multicast_tx('server_socket', device_id, 'endpoint', 'None')
                    return
                endpoint = device.get_endpoint()
                log.info('[%s] connecting, sending tcp socket endpoint %s' % (device_id, str(endpoint)))
                self.multicast_tx('server_socket', device_id, 'endpoint', str(endpoint))
        except Exception as e:
            log.error('connection failed from unknown device %s (%s)' % (device_id, str(e)))
            self.multicast_tx('server_socket', device_id, 'endpoint', 'None')

    def websocket_rx(self, message):
        if self.terminated:
            return

        command = message['command']

        if command == 'get_configuration':
            self.broadcast_new_configuration()
            return
        elif command == 'save_current_configuration':
            self.save_configuration()
            return

        groupname = message['name']

        self.play_sequencer.get_group(groupname).set_param(message)

        if not self.delayed_broadcast:
            self.delayed_broadcast = threading.Timer(0.05, self.send_broadcast)
            self.delayed_broadcast.start()

    def websocket_twitse_rx(self, message):
        if self.terminated:
            return
        try:
            command = message['command']

            if command == 'device_lock_quality':
                group, client = util.get_group_and_device_from_id(message['from'])
                lock = message['lockstate']
                quality = message['quality']

                log.info(f'twitse client {group}:{client} quality:{quality}, lock:"{lock}"')
                g = self.play_sequencer.get_group(group)
                c = g.get_device(client)
                c.send(message)
        except Exception as e:
            log.error(message)
            raise e

    def send_broadcast(self):
        self.broadcast_new_configuration()
        self.delayed_broadcast = None

    def broadcast_new_configuration(self):
        log.debug('ws: sending current configuration')
        current_config = self.play_sequencer.current_configuration()
        _ = json.dumps(current_config, indent=4, sort_keys=True)
        self.ws.send_message(None,
                             {'command': 'configuration',
                              'current_conf': current_config})

    def slot_message(self, message):
        command = message['command']
        client_name = message['clientname']

        # Here all client 'time' messages are harvested but so far the only output is a log
        # message. What is missing is how the server should convey general status like e.g.
        # one or more clients having a wall clock too far off to make a playing system.
        if command == 'time':
            here_time = message['local_time']
            client_time = float(message['epoch'])
            diff = abs(here_time - client_time)
            # Make a rough check of the apparent time difference between client and server.
            # It contains the delays from two python scripts and the IP transit time so
            # it makes no sense to be too picky.
            txt = f'[{client_name}] epoch is {message["epoch"]} (offset {diff:.3f} sec)'
            if diff < 0.1:
                log.debug(txt)
            else:
                log.warning(txt)
        else:
            log.warning(f'unexpected command {command} from {client_name}')

    def launch_playsequencer(self):
        try:
            log.info('launching playsequencer')
            if self.play_sequencer:
                self.play_sequencer.terminate()

            self.play_sequencer = playsequencer.PlaySequencer(self.configuration)
            self.play_sequencer.connect('allgroupsdisconnected', self.all_groups_disconnected)
            self.play_sequencer.connect('message', self.slot_message)
            self.cant_play_warning = 5
        except Exception as e:
            log.critical('playsequencer failed with %s' % str(e))

    def run(self):
        try:
            while not self.terminated:
                try:
                    event = self.input_mux.event_poll()
                except queue.Empty:
                    continue

                key = event['key']
                value = event['value']

                if key == 'audio':
                    self.play_sequencer.new_audio(value)
                elif key == 'codec':
                    self.play_sequencer.set_codec(value)
                elif key == 'samplerate':
                    self.play_sequencer.set_samplerate(value)
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

    kitchen_group = {
        'general': {
            'legend': 'Kitchen',
            'name': 'kitchen',
            'enabled': "true",
            'playing': "true",
            'devices': [kitchen_device_left, kitchen_device_right],
        },
        'levels': {
            'volume': '10.0',
            'balance': '0.0',
            'equalizer': {'0': '12.0', '1': '10.0', '2': '3.0'}
        },
        'xover': {
            'highlowbalance': '-0.1',
            'freq': '1500',
            'poles': '4',
        },
        'stereoenhance': {
            'visible': 'false',
            'depth': '0.0',
            'enabled': "false",
        }
    }

    stereo_device = {
        'name': 'stereo',
        'channel': 'stereo'
    }

    stereo_group = {
        'general': {
            'legend': 'Stereo',
            'name': 'stereo',
            'enabled': "true",
            'playing': "false",
            'devices': [stereo_device],
        },
        'levels': {
            'volume': '10.0',
            'balance': '0.0',
            'equalizer': {'0': '12.0', '1': '10.0', '2': '0.0'}
        },
        'xover': {
            'highlowbalance': '-0.1',
            'freq': '1500',
            'poles': '4',
        },
        'stereoenhance': {
            'visible': 'false',
            'depth': '0.0',
            'enabled': "false",
        },
        'realtime': {
            'enabled': 'false',
            'level_db': '-40.0',
            'duration_sec': '15'
        }
    }

    configuration = {
        'version': util.CONFIG_VERSION,
        'groups': [kitchen_group, stereo_group],
        'streaming': {
            'audiotimeout': '5',
            'playdelay': 0.5,
            'buffersize': 50000,
            'low_buffer_handler': util.LowBufferHandler.starved.name,
            'alsabuffertime_ms': 20
        },
        'sources': {
            'mopidy_ws_enabled': 'false',
            'mopidy_ws_address': util.local_ip(),
            'mopidy_ws_port': '6680',
            'mopidy_gst_port': '4666',
            'ludit_websocket_port': 45658,
            'audiominblocksize': 3000,
            'alsasource': {
                'enabled': False,
                'device': 'hw:1',
                'timeout': 5.0,
                'threshold_dB': -40.0
            },
            'gstreamer': [
                {
                    'format': 'pcm',
                    'enabled': True,
                    'port': 4666,
                    'samplerate': 48000
                }
            ]
        },
        'multicast': {
            'ip': util.multicast_ip,
            'port': util.multicast_port
        },
        "interfaces": {
            "twitse_websocket_port": 12343
        }
    }
    return configuration


def start():
    """
    Use the run_server.py script in ./src
    """
    try:
        parser = argparse.ArgumentParser('Ludit client')
        parser.add_argument('--dumpcfg', action='store_true', dest='dumpcfg',
                            help='dump template configuration file to stdout')
        parser.add_argument('--cfg', dest='cfg',
                            help='configuration file to use')
        parser.add_argument('--verbose', action='store_true',
                            help='enable more logging')

        args = parser.parse_args()

        util.get_pid_lock('ludit_server')

        if args.verbose:
            log.setLevel(logging.DEBUG)

        if args.dumpcfg:
            config = json.dumps(generate_config(), indent=4, sort_keys=True)
            print(config)
            exit(0)

        def ctrl_c_handler(_, __):
            try:
                print(' ctrl-c handler')
                if _server:
                    log.info('terminated by user')
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
        _server = Server(args.cfg)
        _server.join()
        log.info('server exiting')

    except Exception as e:
        if args.verbose:
            print(traceback.format_exc())
        util.die('server exception: %s' % str(e))
