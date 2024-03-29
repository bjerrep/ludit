from common import util
from server import device
from common.log import logger as log
from enum import Enum
import threading, time


class State(Enum):
    STOPPED = 1
    BUFFERING = 2
    PLAYING = 3


class Group(util.Base):
    signals = ('groupconnected', 'groupdisconnected', 'status', 'message')

    def __init__(self, jsn):
        self.devices = []
        self.connected_devices = []
        self.jsn = jsn

        self.groupname = jsn['general']['name']
        log.info(f'[{self.groupname}] group is configuring (play enabled={self.play_enabled()})')
        self.lock = threading.Lock()

        for device_json in jsn['general']['devices']:
            _device = device.Device(device_json['name'], self.groupname)
            if not _device.socket.is_alive():
                raise util.ColdstartException
            _device.connect('devicedisconnected', self.slot_device_disconnected)
            _device.connect('deviceconnected', self.slot_device_connected)
            _device.connect('message', self.slot_device_message)
            complete_json = device_json.copy()
            complete_json.update(jsn)
            _device.set_param(complete_json)
            self.devices.append(_device)

    def name(self):
        return self.groupname

    def get_device(self, devicename):
        for _device in self.devices:
            if _device.name() == devicename:
                return _device
        log.info("group failed to find device %s", devicename)
        raise util.DeviceException

    def play_enabled(self):
        return self.jsn['general']['playing'] == 'true'

    def ready_to_play(self):
        # group can play as long as just a single client is connected
        return self.connected_devices and self.play_enabled()

    def get_devices(self):
        return self.devices

    def start_playing(self, play_time):
        self.send({'runtime': {'command': 'playing', 'playtime': str(play_time)}})

    def stop_playing(self):
        log.debug('%s send stop playing' % self.groupname)
        self.send({'runtime': {'command': 'stopping'}})

    def terminate(self):
        for _device in self.devices:
            _device.terminate()

    def slot_device_connected(self, device):
        if device not in self.connected_devices:
            self.connected_devices.append(device)
            log.info(f'connected to {self.groupname}:{device.name()}')
            if len(self.connected_devices) == 1:
                self.emit('groupconnected', self)
        else:
            log.error('%s already registered as connected' % device.name())

    def slot_device_disconnected(self, device):
        if device in self.connected_devices:
            self.connected_devices.remove(device)
            log.info(f'disconnected from {self.groupname}:{device.name()}')
            if not self.connected_devices:
                self.emit('groupdisconnected', self)
        else:
            log.error('%s disconnected while not connected' % device.name())

    def slot_device_message(self, msg):
        with self.lock:
            command = msg['command']
            clientname = msg['clientname']
            id = util.make_id(self.groupname, clientname)
            if command == 'time' or command == 'message':
                msg['clientname'] = id
                self.emit('message', msg)
            elif command == 'status':
                state = msg['state']
                for _device in self.connected_devices:
                    if _device.state() != state:
                        return
                self.emit('status', state)
            else:
                log.debug('[%s] got %s ?' % (id, command))

    def get_configuration(self):
        config = self.jsn.copy()
        return config

    def set_param(self, message):
        try:
            param = message['param']
            key = list(param.keys())[0]
            tpe = list(param[key].keys())[0]
            value = list(param[key].values())[0]

            if key == 'levelsequalizer':
                message.update({'param': {'levels': {'equalizer': {tpe: value}}}})
                self.jsn['levels']['equalizer'][tpe] = value
            else:
                self.jsn[key][tpe] = value

            log.info('[%s] setting %s:%s to %s' % (self.groupname, key, tpe, value))

            if key == 'general' and tpe == 'playing':
                if value == 'false':
                    self.stop_playing()

            self.send(message)

        except Exception as e:
            log.exception('unable to parse parameter %s' % str(e))

    def set_param_array(self, name, key, value):
        self.jsn[name][key] = float(value)
        self.send({'command': 'configuration', name: {key: value}})

    def send(self, packet):
        for _device in self.connected_devices:
            _device.socket.send(packet)
