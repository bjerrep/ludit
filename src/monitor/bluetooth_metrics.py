import bluetooth
import select
import json
from common.log import logger as log
from common import util


class BTDiscoverer(util.Threadbase, bluetooth.DeviceDiscoverer):
    signals = 'bt_client'

    def __init__(self):
        util.Threadbase.__init__(self)
        bluetooth.DeviceDiscoverer.__init__(self)
        self.success = False
        self.start()

    def device_discovered(self, address, device_class, rssi, name):
        metrics = {'name': name.decode('utf-8'), 'address': address, 'rssi': str(rssi)}
        self.emit('bt_client', json.dumps(metrics))
        self.success = True
        self.terminate()

    def inquiry_complete(self):
        self.terminate()

    def run(self):
        self.find_devices(lookup_names=True)

        readfiles = [self, ]

        while not self.terminated:
            rfds = select.select(readfiles, [], [])[0]

            if self in rfds:
                self.process_event()

        if not self.success:
            metrics = {'name': '', 'address': '', 'rssi': ''}
            self.emit('bt_client', json.dumps(metrics))

        log.debug('BTDiscoverer exits')
