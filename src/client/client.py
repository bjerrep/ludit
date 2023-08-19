import logging, traceback, sys, time, signal, argparse, threading, json
from client import client_socket
from client import player
from client import hwctl, gpio
from common import util, multicast
from common.log import logger as log

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib


class Client(util.Threadbase):
    def __init__(self, configuration, hardware_config):
        super(Client, self).__init__(name='client')

        self.groupname = configuration['group']
        self.devicename = configuration['device']
        self.id = f'{self.groupname}:{self.devicename}'
        log.info(f'starting client {self.id}')

        self.mainloop = GLib.MainLoop()
        self.server_endpoint = None
        self.terminate_socket = False
        self.hw_ctrl = hwctl.HwCtl(hardware_config)
        self.player = player.Player(configuration, self.hw_ctrl)
        self.player.connect('status', self.slot_player_status)
        self.player.connect('message', self.slot_player_message)
        self.player.connect('device_lock_quality', self.slot_device_lock_quality)

        self.socket = None
        self.server_offline_counter = 10
        self.socket_lock = threading.Lock()
        self.server_connected = False

        self.multicast = multicast.Client(
            self.id,
            configuration['multicast']['ip'],
            int(configuration['multicast']['port']))

        self.multicast.connect('client_receive', self.multicast_rx)

        server_connector_thread = threading.Thread(target=self.server_connector_run, args=())
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
        self.hw_ctrl.terminate()
        super().terminate()

    def connected(self):
        return self.server_connected

    def update_connected(self, connected):
        if self.server_connected and not connected:
            self.hw_ctrl.server_connection(False)
            self.server_connected = False
        elif not self.server_connected and connected:
            self.hw_ctrl.server_connection(True)
            self.server_connected = True

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
        else:
            log.warning(f'multicast got unknown message {message}')

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

    def slot_device_lock_quality(self, message):
        log.debug(f'twitse lock report: {message}')
        try:
            locked = message['lockstate'] in ('locked', 'high lock')
            self.hw_ctrl.time_sync(locked)
        except:
            pass

    def slot_new_message(self, message):
        try:
            if not self.server_connected:
                log.warning(f'got server message but server not connected ? {str(message)}')
                return
            self.player.process_server_message(message)
        except Exception as e:
            log.critical(traceback.format_exc())
            log.critical(f'client slot_new_message "{str(message)}" caught "{str(e)}"')

    def slot_socket(self, state):
        with self.socket_lock:
            if state == 'open':
                if self.socket:
                    self.socket.send({'command': 'time',
                                      'clientname': self.devicename,
                                      'epoch': str(time.time())})
            elif state == 'closed':
                # this is running in the socket thread, move the work to this thread
                log.info('got socket close message')
                self.terminate_socket = True

    def start_socket(self):
        self.socket_lock.acquire()
        self.update_connected(True)
        if self.socket:
            raise util.IsOpenException
        self.socket = client_socket.ClientSocket(self.server_endpoint)
        self.socket.connect('audio', self.player.new_audio)
        self.socket.connect('message', self.slot_new_message)
        self.socket.connect('socket', self.slot_socket)
        self.socket_lock.release()

    def server_connector_run(self):
        delay = 0.1

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
                self.update_connected(False)

            if not self.server_endpoint:
                self.update_connected(False)

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
                self.update_connected(True)

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
            'device': 'devicename'
        }
        configuration.update(extra)

    return configuration


def load_configuration(configuration_file, human_name):
    try:
        with open(configuration_file) as f:
            configuration = json.loads(f.read())
            version = configuration.get('version')
            log.info(f'loaded {human_name} {configuration_file}')
            if version != util.CONFIG_VERSION:
                util.die(f'expected {human_name} version {util.CONFIG_VERSION} but found version {version} in {configuration_file}')
    except json.JSONDecodeError as e:
        util.die(f'got fatal error loading {human_name} file "{e}"')
    except Exception:
        return None
    return configuration


def start():
    """
    Use the run_client.py script in ./src
    """

    # wait for the network to -really- get working
    ip = util.wait_for_network()
    if not ip:
        log.critical('no network connection, exiting')
        exit(1)
    log.info(f'ludit client starting at {ip}')

    try:
        parser = argparse.ArgumentParser('Ludit client')
        parser.add_argument('--id', action='store', dest='id',
                            help='required identifier in the form groupname:devicename')
        parser.add_argument('--cfg', dest='cfg',
                            help='configuration file to use (required for stereo clients)')
        parser.add_argument('--hwsetup', dest='hwsetup',
                            help='load hardware gpio setup file')
        parser.add_argument('--verbose', action='store_true',
                            help='enable more logging')
        parser.add_argument('--nocheck', action='store_true',
                            help='don\'t check for multiple client instances')
        parser.add_argument('--dumpcfg', action='store_true', dest='dumpcfg',
                            help='dump template configuration file to stdout')
        parser.add_argument('--gpio', action='store', dest='gpio',
                            help='bringup, set gpio and exit: [paon|paoff|speakeron|speakeroff]')
        args = parser.parse_args()

        if args.gpio:
            gpio.execute_gpio_command(args.gpio)
            exit(0)

        if args.dumpcfg:
            configuration = generate_config(template=True)
            config = json.dumps(configuration, indent=4, sort_keys=True)
            print(config)
            exit(0)

        if not args.nocheck:
            util.get_pid_lock('ludit_client')

        if args.verbose:
            log.setLevel(logging.DEBUG)

        configuration = None
        if args.cfg:
            configuration = load_configuration(args.cfg, 'configuration')
            log.warning('no configuration file specified (--cfg), using defaults')
        if not configuration:
            log.info('no configuration file specified, using defaults')
            configuration = generate_config(template=False)

        hardware_config = None
        if args.hwsetup:
            hardware_config = load_configuration(args.hwsetup, 'hardware configuration')
        if not hardware_config:
            log.warning('no hardware configuration file specified (--hwsetup), using defaults')

        try:
            groupname, devicename = args.id.split(':')
            configuration['group'] = groupname
            configuration['device'] = devicename
        except:
            log.debug(configuration)
            if not configuration.get('group'):
                raise Exception('need a group:device name from --id argument or "group" in configuration file')

        def ctrl_c_handler(_, __):
            try:
                print(' ctrl-c handler')
                if _client:
                    log.info('terminating by user')
                    _client.terminate()
                    _client.join()
                sys.exit(1)
            except Exception as e:
                log.critical(f'ctrl-c handler got {str(e)}')

        signal.signal(signal.SIGINT, ctrl_c_handler)

        _client = None
        _client = Client(configuration, hardware_config)
        _client.join()

        log.info('client exiting')

    except Exception as e:
        if args.verbose:
            print(traceback.format_exc())
        log.critical(f'client exception: {str(e)}')
