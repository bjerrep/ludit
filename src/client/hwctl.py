from client import gpio
from common import util
from common.log import logger as log
import time
from enum import Enum


class HardwareState(Enum):
    BOOT = 1
    POWERON = 2
    PLAYING = 3
    MUTED = 4
    POWEROFF = 5


class HwCtl(util.Threadbase):
    def __init__(self):
        super(HwCtl, self).__init__(name='hwctl')
        self.target = HardwareState.BOOT
        self.connected = False
        gpio.reset()
        self.start()

    def terminate(self):
        super().terminate()

    def connected_to_server(self, connected):
        self.connected = connected

    def play(self, on):
        if on:
            self.target = HardwareState.PLAYING
        else:
            self.target = HardwareState.POWEROFF

    def run(self):
        poweroff_counter = 0
        state = HardwareState.BOOT

        while not self.terminated:
            time.sleep(0.1)

            if self.target == HardwareState.PLAYING and state != HardwareState.PLAYING:
                # immediately power on and in next pass enable speakers
                if poweroff_counter != 300:
                    poweroff_counter = 300
                    gpio.power(True)
                elif poweroff_counter == 300:
                    gpio.speaker(True)
                    state = HardwareState.PLAYING

            if self.target == HardwareState.POWEROFF and state != HardwareState.POWEROFF:
                # a long count towards 1 and 0 for speakers off and then power off respectively
                if poweroff_counter > 0:
                    poweroff_counter -= 1
                    if poweroff_counter == 1:
                        gpio.speaker(False)
                    elif poweroff_counter == 0:
                        gpio.power(False)
                        state = HardwareState.POWEROFF

            if self.connected:
                if self.target == HardwareState.PLAYING:
                    gpio.LED(gpio.LedColor.ORANGE)
                else:
                    gpio.LED(gpio.LedColor.GREEN)
            else:
                gpio.LED(gpio.LedColor.RED)

        if state != HardwareState.POWEROFF:
            gpio.speaker(False)
            time.sleep(0.5)
            gpio.power(False)

        gpio.close()
        log.debug('hwctrl exits')
