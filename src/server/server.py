#!/bin/python

from common import util
from common.log import logger as log
from common import multicast
from common import websocket
from server import group
from server import playsequencer
import time
import signal
import argparse
import os
import sys
import select
import json
import stat
import socket


LOG_FIRST_AUDIO_COUNT = 5

class Server(util.Threadbase):

    def __init__(self, configuration):
        super(Server, self).__init__(name='server    ')
        self.configuration = configuration
        self.play_sequencer = None
        self.play_thread_active = True
        self.cant_play_warning = 5
        self.log_first_audio = LOG_FIRST_AUDIO_COUNT

        self.multicast = multicast.Server(util.multicast_ip, util.multicast_port)
        self.multicast.connect('receive', self.multicast_rx)

        self.ws = websocket.WebSocket(util.local_ip(), util.server_ludit_websocket_port)
        self.ws.connect('message', self.websocket_rx)
        self.start()

    def terminate(self):
        log.debug('server terminate called')
        self.ws.terminate()
        self.multicast.terminate()
        if self.play_sequencer:
            self.play_sequencer.terminate()

        super().terminate()

        # the pipeline might be blocked waiting for a writer to open the fifo. If so, unblock it now.
        try:
            with open('/tmp/audio', 'w') as f:
                f.write("")
        except:
            pass

    def multicast_rx(self, message):
        command = message['command']
        if command == 'get_server_socket':
            device = message['from']
            groupname, devicename = device.split(':')
            endpoint = self.play_sequencer.get_group(groupname).get_device(devicename).start_socket()
            self.multicast.send({'command': 'server_socket',
                                 'from': 'server',
                                 'to': device,
                                 'endpoint': str(endpoint)})

    def websocket_rx(self, message):
        command = message['command']
        group = message['group']

        if command == 'get_configuration':
            log.info('ws: sending current configuration')
            current_config = self.play_sequencer.current_configuration()
            # print(json.dumps(current_config, indent=4, sort_keys=True))
            self.ws.send_message(None,
                                 {'command': 'configuration',
                                  'current_conf': current_config})
        elif command == 'set_volume':
            log.info('ws: setting %s volume to %s' % (group, message['value']))
            self.play_sequencer.get_group(group).set_param('volume', message['value'])
        elif command == 'set_balance':
            log.info('ws: setting %s balance to %s' % (group, message['value']))
            self.play_sequencer.get_group(group).set_param('balance', message['value'])
        elif command == 'set_xoverfreq':
            log.info('ws: setting %s xover to %s' % (group, message['value']))
            self.play_sequencer.get_group(group).set_param('xoverfreq', message['value'])
        elif command == 'set_xoverpoles':
            log.info('ws: setting %s xover poles to %s' % (group, message['value']))
            self.play_sequencer.get_group(group).set_param('xoverpoles', message['value'])
        elif command == 'set_highlowbalance':
            log.info('ws: setting %s high/low balance to %s' % (group, message['value']))
            self.play_sequencer.get_group(group).set_param('highlowbalance', message['value'])
        elif command == 'set_band0':
            log.info('ws: setting %s band0 to %s' % (group, message['value']))
            self.play_sequencer.get_group(group).set_param_array('equalizer', '0', message['value'])
        elif command == 'set_band1':
            log.info('ws: setting %s band1 to %s' % (group, message['value']))
            self.play_sequencer.get_group(group).set_param_array('equalizer', '1', message['value'])
        else:
            log.error('ws: got unknown command %s' % command)

    def broken_socket(self, source):
        log.error('connection lost to %s' % source)
        self.play_thread_active = False

    def slot_message(self, message):
        command = message['command']
        client = message['clientname']
        if command == 'time':
            client_time = float(message['epoch'])
            log.info('[%s] time deviation is %.1f ms' %
                     (client, (time.time() - client_time) * 1000.0))

    def launch_playsequencer(self):
        log.info('launching playsequencer')
        if self.play_sequencer:
            self.play_sequencer.terminate()

        self.play_sequencer = playsequencer.PlaySequencer(self.configuration)
        self.play_sequencer.connect('brokensocket', self.broken_socket)
        self.cant_play_warning = 5

    def run(self):
        try:
            log.info('starting server at %s' % util.local_ip())
            timeout_counter = 40
            self.launch_playsequencer()

            while not self.terminated:

                fifo = os.open('/tmp/audio', os.O_NONBLOCK | os.O_RDONLY)
                if fifo <= 0:
                    log.critical('no fifo /tmp/audio, bailing out')
                    self.terminate()
                    continue

                log.info('opened /tmp/audio fifo')

                self.play_thread_active = True
                running = False
                data = bytearray()

                try:
                    while self.play_thread_active and not self.terminated:
                        try:
                            inputready, outputready, exceptready = \
                                select.select([fifo], [], [], 0.1)
                        except socket.timeout:
                            log.critical('got timeout 123')
                            self.play_thread_active = False
                            continue

                        if inputready:
                            timeout_counter = 40
                            data += os.read(fifo, 100000)

                            if not data and not self.terminated:
                                log.info('restarting fifo')
                                self.play_thread_active = False
                                continue

                            running = True

                            if data.startswith(b'::'):
                                end = data.find(b'::', 2)
                                if end == -1:
                                    continue
                                end_of_data = end + 2

                                key, value = data[2:end].decode('utf-8').split('=')

                                if key == 'audio':
                                    end_of_data += int(value)
                                    if end_of_data > len(data):
                                        log.info('got partial packet')
                                        continue
                                    if self.log_first_audio:
                                        self.log_first_audio -= 1
                                        log.debug('audio %s bytes' % value)
                                    self.play_sequencer.new_audio(data[end + 2:end_of_data])

                                elif key == 'codec':
                                    log.info('codec is %s' % value)
                                    self.play_sequencer.set_codec(value)

                                elif key == 'volume':
                                    log.info('volume %s' % value)
                                    self.play_sequencer.set_volume(value)

                                elif key == 'state':
                                    log.info('state=%s' % value)
                                    if value == 'stop':
                                        self.play_sequencer.state_changed(group.State.STOPPED)
                                        self.play_thread_active = False
                                        self.log_first_audio = LOG_FIRST_AUDIO_COUNT
                                        time.sleep(0.2)

                                else:
                                    log.critical("got unknown inband message '%s=%s'" %
                                                 (str(key), str(value)))

                                data = data[end_of_data:]
                            else:
                                if not self.terminated:
                                    log.critical('missing header, %i bytes' % len(data))
                                    time.sleep(0.05)

                        else:
                            if running:
                                if timeout_counter:
                                    timeout_counter -= 1
                                    if not timeout_counter:
                                        log.debug('timeout reading fifo, no data for 4 seconds')
                                        self.play_sequencer.state_changed(group.State.STOPPED)
                                        self.play_thread_active = False

                    os.close(fifo)

                except TimeoutError:
                    log.critical('ignoring a Timeout error...')
                except socket.timeout:
                    log.critical('****** got a socket timeout, warmstarting ******')
                    time.sleep(1)
                    self.launch_playsequencer()
                except BrokenPipeError:
                    log.critical('****** got a broken pipe exception, warmstarting ******')
                    time.sleep(1)
                    self.launch_playsequencer()

        except Exception as e:
            log.critical("server thread exception '%s'" % str(e))
            self.terminate()

        log.debug('main thread terminated')


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
        'active': True,
        'volume': '100.0',
        'balance': '0.0',
        'highlowbalance': '-0.41',
        'xoverfreq': '1200',
        'xoverpoles': '4',
        'devices': devices,
        'equalizer': {'0': '12.0', '1': '6.5'}
    }

    stereo = {
        'name': 'stereo',
        'enabled': False,
        'active': False,
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


"""
Use the run_server.py script in ./src
"""
def start():
    try:
        parser = argparse.ArgumentParser('Ludit client')
        parser.add_argument('--newcfg', action='store_true', dest='newcfg',
                            help='dump template (ludit.cfg) configuration file')
        parser.add_argument('--cfg', dest='cfg',
                            help='configuration file to use')
        results = parser.parse_args()

        if results.newcfg:
            config = json.dumps(generate_config(), indent=4, sort_keys=True)
            print(config)
            exit(0)

        if results.cfg:
            with open(results.cfg) as f:
                config = f.read()
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

        _server = Server(config)
        _server.join()
        log.info('server exiting')

    except Exception as e:
        log.critical('server exception: %s' % str(e))
