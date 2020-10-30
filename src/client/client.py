from client import client_socket
from client import player
from common import util, multicast
from common.log import logger as log
from client import hwctl, gpio
import logging, traceback
import sys
import time
import signal
import argparse
import threading
import json
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib


class Client(util.Threadbase):
    def __init__(self, configuration):
        super(Client, self).__init__(name='client')

        self.groupname = configuration['group']
        self.devicename = configuration['device']
        self.id = '%s:%s' % (self.groupname, self.devicename)
        log.info('starting client %s' % self.id)

        self.mainloop = GLib.MainLoop()
        self.server_endpoint = None
        self.terminate_socket = False
        self.hwctrl = hwctl.HwCtl()
        self.player = player.Player(configuration, self.hwctrl)
        self.player.connect('status', self.slot_player_status)
        self.player.connect('message', self.slot_player_message)

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
        self.mainloop.quit()
        self.multicast.terminate()
        if self.socket:
            self.socket.terminate()
            self.socket.join()
        self.player.terminate()
        if self.player.is_alive():
            self.player.join()
        self.hwctrl.terminate()
        super().terminate()

    def connected(self):
        return self.socket is not None

    def multicast_rx(self, message):
        command = message['command']
        if command == 'server_socket':
            if not self.socket:
                endpoint = message['endpoint']
                if endpoint == "None":
                    log.critical("server refused the connection (check the group and device name)")
                    time.sleep(1)
                    util.die('exiting..', 1, True)
                log.info(f'server found, connecting to {endpoint}')
                self.server_endpoint = util.split_tcp(endpoint)
                self.start_socket()

    def slot_player_status(self, status):
        if status in ('buffered', 'starved'):
            if self.socket:
                self.socket.send({'command': 'status',
                                  'clientname': self.devicename,
                                  'state': status})
        elif status in ('rt_stop', 'rt_play'):
            log.info(f'realtime status: {status}')
        else:
            log.error(f'got unknown status {str(status)}')

    def slot_player_message(self, message):
        if self.socket:
            header = {'command': 'message',
                      'clientname': self.devicename}
            header.update(message)
            self.socket.send(header)

    def slot_new_message(self, message):
        try:
            self.player.process_server_message(message)
        except Exception as e:
            log.critical(traceback.format_exc())
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
        connected = False
        while not self.terminated:
            if self.terminate_socket:
                self.socket_lock.acquire()
                self.terminate_socket = False
                if self.socket:
                    self.socket.join()
                    self.socket = None
                self.server_endpoint = None
                self.player.process_server_message({'runtime': {'command': 'stopping'}})
                log.info('waiting for server connection')
                self.server_offline_counter = 10
                self.socket_lock.release()
                if connected:
                    self.hwctrl.connected_to_server(False)
                    connected = False

            if not self.server_endpoint:
                if connected:
                    self.hwctrl.connected_to_server(False)
                    connected = False

                if self.server_offline_counter:
                    self.server_offline_counter -= 1
                    if not self.server_offline_counter:
                        log.critical('server seems to be offline')
                try:
                    self.multicast.send({'command': 'get_server_socket',
                                         'to': 'server',
                                         'from': self.id,
                                         'version': util.LUDIT_VERSION})
                except OSError:
                    log.warning('got a multicast send exception. Bummer.')

                if delay < 5.0:
                    delay += 0.1
            else:
                if not connected:
                    self.hwctrl.connected_to_server(True)
                    connected = True

                delay = 0.1

            _delay = delay
            while _delay > 0.0 and not self.terminated:
                time.sleep(0.1)
                _delay -= 0.1

        log.debug('server connector exits')
        return False

    def run(self):
        self.mainloop.run()
        log.debug('client exits')


def generate_config(template):
    configuration = {
        'version': util.CONFIG_VERSION,
        'multicast': {
            'ip': util.multicast_ip,
            'port': str(util.multicast_port)
        }
    }

    if template:
        # Omit the 'alsa' block below for single channel clients which will usually be happy with the
        # 'default' alsa playback device. If used for single channel clients then the left channel will
        # use the first entry, the right channel the second. That will definitely be confusing.
        # Stereo clients will have to deal with two different playback devices.
        extra = {
            'alsa': {
                'devices': ['hw:0', 'hw:1']
            },
            'group': 'groupname',
            'device': 'devicename',
            'cec': 'false'
        }
        configuration.update(extra)

    return configuration


def load_configuration(configuration_file):
    try:
        with open(configuration_file) as f:
            configuration = json.loads(f.read())
            version = configuration.get('version')
            log.info('loaded configuration %s' % configuration_file)
            if version != util.CONFIG_VERSION:
                util.die('expected configuration version %s but found version %s' % (util.CONFIG_VERSION, version))
    except json.JSONDecodeError as e:
        util.die(f'got fatal error loading configuration file "{e}"')
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
                            help='configuration file to use (only required for stereo clients)')
        parser.add_argument('--verbose', action='store_true',
                            help='enable more logging')
        parser.add_argument('--nocheck', action='store_true',
                            help='don\'t check for multiple client instances')

        args = parser.parse_args()

        if args.newcfg:
            configuration = generate_config(template=True)
            config = json.dumps(configuration, indent=4, sort_keys=True)
            print(config)
            exit(0)

        if not args.nocheck:
            util.get_pid_lock('ludit_client')

        if args.verbose:
            log.setLevel(logging.DEBUG)

        if args.cfg:
            configuration = load_configuration(args.cfg)
        else:
            log.info('no configuration file, using defaults')
            configuration = generate_config(template=False)

        try:
            groupname, devicename = args.id.split(':')
            configuration['group'] = groupname
            configuration['device'] = devicename
        except:
            log.debug(configuration)
            if not configuration.get('group'):
                raise Exception('need a group:device name from --id argument or configuration file')

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

        gpio.init()

        _client = None
        _client = Client(configuration)
        _client.join()

        log.info('client exiting')

    except Exception as e:
        if args.verbose:
            print(traceback.format_exc())
        log.critical('client exception: %s' % str(e))
