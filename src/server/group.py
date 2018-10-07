from common import util
from server import device
from common.log import logger as log
from enum import Enum
import threading
import json


class State(Enum):
    STOPPED = 1
    BUFFERING = 2
    PLAYING = 3


class Group(util.Base):
    signals = ('clientdisconnected', 'status')

    def __init__(self, jsn):
        self.devices = []
        self.jsn = jsn
        self.play_delay = float(jsn['playdelay'])
        self.groupname = jsn["name"]
        log.info('[%s] group is configuring' % self.groupname)
        self.lock = threading.Lock()

        for device_json in jsn['devices']:
            _device = device.Device(device_json['name'], self.groupname)
            if not _device.socket.is_alive():
                raise util.ColdstartException
            _device.connect('clientdisconnected', self.client_disconnected)
            _device.connect('message', self.client_message)
            complete_json = device_json.copy()
            complete_json.update(jsn)
            _device.set_param(complete_json)
            self.devices.append(_device)

    def get_device(self, devicename):
        for _device in self.devices:
            if _device.get_clientname() == devicename:
                return _device

    def ready_to_play(self):
        for _device in self.devices:
            if not _device.is_connected():
                return False
        return True

    def on(self):
        return self.jsn['on']

    def start_playing(self, now):
        play_time = now + self.play_delay
        self.send_all({'command': 'playing', 'playtime': str(play_time)})

    def stop_playing(self):
        self.send_all({'command': 'stopping'})

    def terminate(self):
        for _device in self.devices:
            _device.terminate()

    def client_disconnected(self, source):
        self.emit('clientdisconnected', source)

    def get_configuration(self):
        config = self.jsn.copy()
        config.pop('devices', None)
        return config

    def set_param(self, key, value):
        if key == 'on':
            self.jsn[key] = value
            if not value:
                self.stop_playing()
        else:
            self.jsn[key] = float(value)
            self.send_all({'command': 'configuration', key: value})

    def set_param_array(self, name, key, value):
        self.jsn[name][key] = float(value)
        self.send_all({'command': 'configuration', name: {key: value}})
        print(json.dumps(self.jsn, indent=4, sort_keys=True))

    def client_message(self, msg):
        self.lock.acquire()
        command = msg['command']
        clientname = msg['clientname']
        id = util.make_id(self.groupname, clientname)
        if command == 'time':
            log.debug("[%s] epoch is %s" %
                      (id, msg['epoch']))
        elif command == 'status':
            state = msg['state']
            for _device in self.devices:
                if _device.state() != state:
                    self.lock.release()
                    return
            self.emit('status', state)
        else:
            log.debug('[%s] got %s ?' % (id, command))
        self.lock.release()

    def send_all(self, packet):
        for _device in self.devices:
            _device.socket.send(packet)
