import time
from enum import Enum
from client import gpio
from common import util
from common.log import logger as log

class ClientState(Enum):
    #
    CLIENT_STARTING = 1                # red dimmed

    # connected to the ludit server
    LUDIT_SERVER_CONNECTED = 2         # red bright

    # twitse not in sync. This hides the NOT_PLAYING and PLAYING led states
    # but does not prevent the playing part (see playing_state).
    TWITSE_TIME_NOT_SYNC = 3           # red/green flash

    TWITSE_TIME_SYNC = 4               # green dimmed

    # And finally the led goes bright green if playing_state == True


class PowerAndSpeakers(Enum):
    BOTH_OFF = 1
    POWER_ON = 2
    BOTH_ON = 3

class HwCtl(util.Threadbase):
    def __init__(self, hardware_setup):
        super(HwCtl, self).__init__(name='hwctl')
        self.state = ClientState.CLIENT_STARTING
        self.power_and_speakers = PowerAndSpeakers.BOTH_OFF
        self.power_delay = 0
        self.playing_state = False
        gpio.init(hardware_setup)
        self.start()

    def terminate(self):
        super().terminate()

    def server_connection(self, connected):
        if connected and self.state == ClientState.CLIENT_STARTING:
            self.state = ClientState.LUDIT_SERVER_CONNECTED
        elif not connected:
            self.state = ClientState.CLIENT_STARTING
        log.debug(f'got server connected={connected}, state is now {self.state}')

    def time_sync(self, locked):
        if locked and self.state in (ClientState.TWITSE_TIME_NOT_SYNC, ClientState.LUDIT_SERVER_CONNECTED):
            self.state = ClientState.TWITSE_TIME_SYNC
        elif not locked and self.state in (ClientState.TWITSE_TIME_SYNC, ClientState.LUDIT_SERVER_CONNECTED):
            self.state = ClientState.TWITSE_TIME_NOT_SYNC
        log.debug(f'got time sync locked={locked}, state is now {self.state}')

    def play(self, on):
        self.playing_state = on

    def run(self):
        FLASHING_PERIOD = 50
        period_red = 0
        period_green = 0
        last_state = None
        last_playing_state = None

        while not self.terminated:
            time.sleep(0.01)

            if last_state != self.state or last_playing_state != self.playing_state:
                log.info(f'state changed from {last_state} to {self.state}')
                red_flashing = False
                green_flashing = False
                period_red = 0
                period_green = 0

                if self.state == ClientState.CLIENT_STARTING:
                    gpio.red(gpio.LedDrive.DIM)
                    gpio.green(gpio.LedDrive.OFF)
                elif self.state == ClientState.LUDIT_SERVER_CONNECTED:
                    gpio.red(gpio.LedDrive.ON)
                    gpio.green(gpio.LedDrive.OFF)
                elif not self.playing_state:
                    if self.state == ClientState.TWITSE_TIME_NOT_SYNC:
                        gpio.red(gpio.LedDrive.ON)
                        gpio.green(gpio.LedDrive.OFF)
                        red_flashing = True
                        green_flashing = True
                        period_red = FLASHING_PERIOD
                    else:
                        gpio.red(gpio.LedDrive.OFF)
                        gpio.green(gpio.LedDrive.DIM)
                else:
                    # playing
                    gpio.red(gpio.LedDrive.OFF)
                    gpio.green(gpio.LedDrive.ON)

                last_state = self.state
                last_playing_state = self.playing_state

            if period_red:
                period_green = 0
                period_red -= 1
                if not period_red:
                    period_green = FLASHING_PERIOD * 1.5
                    gpio.red(gpio.LedDrive.OFF)
                    if green_flashing:
                        gpio.green(gpio.LedDrive.ON)

            if period_green:
                period_red = 0
                period_green -= 1
                if not period_green:
                    period_red = FLASHING_PERIOD * 0.5
                    gpio.green(gpio.LedDrive.OFF)
                    if red_flashing:
                        gpio.red(gpio.LedDrive.ON)

            if self.power_delay:
                self.power_delay -= 1
            else:
                if self.playing_state:
                    if self.power_and_speakers != PowerAndSpeakers.BOTH_ON:
                        if self.playing_state and self.power_and_speakers == PowerAndSpeakers.BOTH_OFF:
                            self.power_and_speakers = PowerAndSpeakers.POWER_ON
                            gpio.power(True)
                            self.power_delay = 50
                        else:
                            self.power_and_speakers = PowerAndSpeakers.BOTH_ON
                            gpio.speaker(True)
                else:
                    if self.power_and_speakers != PowerAndSpeakers.BOTH_OFF:
                        if self.playing_state and self.power_and_speakers == PowerAndSpeakers.BOTH_ON:
                            self.power_and_speakers = PowerAndSpeakers.POWER_ON
                            gpio.speaker(False)
                            self.power_delay = 10
                        else:
                            self.power_and_speakers = PowerAndSpeakers.BOTH_OFF
                            gpio.power(False)

        gpio.close()
        log.debug('hwctrl exits')
