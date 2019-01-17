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


class Client(util.Threadbase):
    def __init__(self, groupname, devicename):
        super(Client, self).__init__(name='client    ')
        self.groupname = groupname
        self.devicename = devicename
        self.id = '%s:%s' % (self.groupname, self.devicename)
        log.info('starting client %s' % self.id)
        self.server_endpoint = None
        self.terminate_socket = False
        self.player = player.Player()
        self.player.connect('status', self.slot_player_status)

        self.socket = None
        self.server_offline_counter = 10
        self.socket_lock = threading.Lock()

        self.multicast = multicast.Client(self.id, util.multicast_ip, util.multicast_port)
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

    def multicast_rx(self, message):
        command = message['command']
        if command == 'server_socket':
            if not self.socket:
                endpoint = message['endpoint']
                if endpoint == "None":
                    log.critical("server refused the connection (check the --id)")
                    time.sleep(1)
                    exit(1)
                log.info('server found, connecting to %s' % endpoint)
                self.server_endpoint = util.split_tcp(endpoint)
                self.start_socket()

    def slot_player_status(self, message):
        if message in ('buffered', 'starved'):
            if self.socket:
                self.socket.send({'command': 'status',
                                  'clientname': self.devicename,
                                  'state': message})
        else:
            log.error('got unknown message %s' % str(message))

    def slot_new_message(self, message):
        try:
            self.player.process_message(message)
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

                self.multicast.send({'command': 'get_server_socket',
                                     'to': 'server',
                                     'from': self.id})
                if delay < 5.0:
                    delay += 0.1
            else:
                delay = 0.1

            time.sleep(delay)

        log.debug('server connector exits')
        return False

    def run(self):
        self.player.mainloop.run()
        log.debug('client exits')


def start():
    """
    Use the run_client.py script in ./src
    """
    try:
        parser = argparse.ArgumentParser('Ludit client')
        parser.add_argument('--id', action='store', dest='id',
                            help='required identifier in the form groupname:devicename', required=True)
        parser.add_argument('--verbose', action='store_true',
                            help='enable more logging')

        results = parser.parse_args()

        if results.verbose:
            log.setLevel(logging.DEBUG)

        try:
            groupname, devicename = results.id.split(':')
        except:
            raise Exception('need a group:device name pair')

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
        _client = Client(groupname, devicename)
        _client.join()

        log.info('client exiting')

    except Exception as e:
        log.critical('client exception: %s' % str(e))
