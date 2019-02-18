from common import util
from server import device
from common.log import logger as log
from enum import Enum
import threading


class State(Enum):
    STOPPED = 1
    BUFFERING = 2
    PLAYING = 3


class Group(util.Base):
    signals = ('groupconnected', 'groupdisconnected', 'status')

    def __init__(self, jsn):
        self.devices = []
        self.connected_devices = []
        self.jsn = jsn
        self.play_delay = float(jsn['playdelay'])
        self.groupname = jsn['general']['name']
        log.info('[%s] group is configuring' % self.groupname)
        self.lock = threading.Lock()

        for device_json in jsn['general']['devices']:
            _device = device.Device(device_json['name'], self.groupname)
            if not _device.socket.is_alive():
                raise util.ColdstartException
            _device.connect('devicedisconnected', self.slot_device_disconnected)
            _device.connect('deviceconnected', self.slot_device_connected)
            _device.connect('message', self.slot_message)
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

    def ready_to_play(self):
        # group can play as long as just a single client is connected
        return self.connected_devices and self.jsn['general']['playing'] == 'true'

    def get_devices(self):
        return self.devices

    def start_playing(self, now):
        play_time = now + self.play_delay
        self.send({'command': 'playing', 'playtime': str(play_time)})

    def stop_playing(self):
        self.send({'command': 'stopping'})

    def terminate(self):
        for _device in self.devices:
            _device.terminate()

    def slot_device_connected(self, device):
        if device not in self.connected_devices:
            self.connected_devices.append(device)
            log.info('connected to %s:%s' % (self.groupname, device.name()))
            if len(self.connected_devices) == 1:
                self.emit('groupconnected', self)
        else:
            log.error('%s already registered as connected' % device.name())

    def slot_device_disconnected(self, device):
        if device in self.connected_devices:
            self.connected_devices.remove(device)
            log.info('disconnected from %s' % device.name())
            if not self.ready_to_play():
                self.emit('groupdisconnected', self)
        else:
            log.error('%s disconnected while not connected' % device.name())

    def slot_message(self, msg):
        with self.lock:
            command = msg['command']
            clientname = msg['clientname']
            id = util.make_id(self.groupname, clientname)
            if command == 'time':
                log.debug("[%s] epoch is %s" % (id, msg['epoch']))
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
            value = message['param']['general']['playing']
            self.jsn['general']['playing'] = value
            if value == 'false':
                self.stop_playing()
            log.info('[%s] setting %s:%s to %s' % (self.groupname, 'general', 'playing', value))
        except:
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

            self.send(message)

    def set_param_array(self, name, key, value):
        self.jsn[name][key] = float(value)
        self.send({'command': 'configuration', name: {key: value}})

    def send(self, packet):
        for _device in self.connected_devices:
            _device.socket.send(packet)
