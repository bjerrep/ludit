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
        super(HwCtl, self).__init__(name='hwctl     ')
        self.target = HardwareState.BOOT
        gpio.reset()
        self.start()

    def terminate(self):
        super().terminate()
        self.target = HardwareState.POWEROFF

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
                # immediately power on and in next pass energize the relays
                if poweroff_counter != 300:
                    poweroff_counter = 300
                    gpio.Power(True)
                    gpio.LED(gpio.LedColor.ORANGE)
                elif poweroff_counter == 300:
                    gpio.speaker_relay(True)
                    gpio.LED(gpio.LedColor.GREEN)
                    state = HardwareState.PLAYING

            if self.target == HardwareState.POWEROFF and state != HardwareState.POWEROFF:
                # a long count towards 1 and 0 for speaker relays off and then power off respectively
                if poweroff_counter > 0:
                    poweroff_counter -= 1
                    if poweroff_counter == 1:
                        gpio.speaker_relay(False)
                        gpio.LED(gpio.LedColor.ORANGE)
                    elif poweroff_counter == 0:
                        gpio.Power(False)
                        gpio.LED(gpio.LedColor.RED)
                        state = HardwareState.POWEROFF

        gpio.close()
        log.debug('hwctrl thread terminated')
