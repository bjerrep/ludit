from enum import Enum
from common.log import logger as log


try:
    import RPi.GPIO as GPIO
except Exception as e:
    log.critical("import RPi.GPIO error: " + str(e) + " - running without hardware support")
    GPIO = None


class LedDrive(Enum):
    DIM = 0
    OFF = 1
    ON = 2


# Default gpio mappings (BCM style). Use a "client_hw_setup.cfg" to customize the mappings.
#  pin  wpi  bcm
#  10   16   15     RxD
#  22   6    25     GPIO.6
#  15   3    22     GPIO.3
#  16   4    23     GPIO.4
#
Setup = {
    "papower" : {
        "bcm":  25,
        "active": "high",
        "enabled": True
    },
    "speakerrelay" : {
        "bcm":  15,
        "active": "high",
        "enabled": True
    },
    "led_red" : {
        "bcm":  22,
        "active": "high",
        "enabled": True
    },
    "led_green" : {
        "bcm":  23,
        "active": "high",
        "enabled": True
    }
}

PAPOWER = 'papower'
SPRELAY = 'speakerrelay'
LEDGRN = 'led_green'
LEDRED = 'led_red'
ENABLED = 'enabled'
ACTIVE = 'active'
BCM = 'bcm'

GPIO_SPEAKER = 15
GPIO_SPEAKER_ACTIVE_HIGH = True
GPIO_PAPOWER = 14
GPIO_PAPOWER_ACTIVE_HIGH = False
GPIO_LED_A = 23
GPIO_LED_A_ACTIVE_HIGH = True
GPIO_LED_B = 22
GPIO_LED_B_ACTIVE_HIGH = True
GPIO_GPIO = 17


def init(hardware_config):
    global Setup
    if GPIO:
        if hardware_config:
            Setup = hardware_config

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        # Set the power and speaker outputs right away
        if Setup[PAPOWER][ENABLED]:
            GPIO.setup(Setup[PAPOWER][BCM], GPIO.OUT)
            power(False)
        if Setup[SPRELAY][ENABLED]:
            GPIO.setup(Setup[SPRELAY][BCM], GPIO.OUT)
            speaker(False)

def close():
    if not GPIO:
        return
    GPIO.cleanup()


def has_gpio():
    return GPIO


def speaker(on):
    # Off the shelf class-D amplifiers often have a 'enable' input which can bring
    # the amplifier to sleep before cutting the power or enabling the amplifier
    # after power is applied. Alternatively the speaker signal can be used to
    # control standard speaker relays.
    # All this is done to avoid the risk of bangs and pops when power comes and goes.
    # It might or might not be needed depending on the electronics used.
    if not GPIO:
        return
    if Setup[SPRELAY][ENABLED]:
        GPIO.output(Setup[SPRELAY][BCM], on if Setup[SPRELAY][ACTIVE] == 'high' else not on)


def power(on):
    # Power on/off the amplifier power supply, typically done with a solid state relay
    # for a standard mains PSU.
    if not GPIO:
        return
    log.debug(f'setting pa power {on}')
    if Setup[PAPOWER][ENABLED]:
        GPIO.output(Setup[PAPOWER][BCM], on if Setup[PAPOWER][ACTIVE] == 'high' else not on)


def green(drive):
    if not GPIO:
        return
    if Setup[LEDGRN][ENABLED]:
        if drive == LedDrive.ON:
            GPIO.setup(Setup[LEDGRN][BCM], GPIO.OUT)
            GPIO.output(Setup[LEDGRN][BCM], True if Setup[LEDGRN][ACTIVE] == 'high' else False)
        elif drive == LedDrive.OFF:
            GPIO.setup(Setup[LEDGRN][BCM], GPIO.OUT)
            GPIO.output(Setup[LEDGRN][BCM], False if Setup[LEDGRN][ACTIVE] == 'high' else True)
        else:
            GPIO.setup(Setup[LEDGRN][BCM], GPIO.IN)


def red(drive):
    if not GPIO:
        return
    if Setup[LEDRED][ENABLED]:
        if drive == LedDrive.ON:
            GPIO.setup(Setup[LEDRED][BCM], GPIO.OUT)
            GPIO.output(Setup[LEDRED][BCM], True if Setup[LEDRED][ACTIVE] == 'high' else False)
        elif drive == LedDrive.OFF:
            GPIO.setup(Setup[LEDRED][BCM], GPIO.OUT)
            GPIO.output(Setup[LEDRED][BCM], False if Setup[LEDRED][ACTIVE] == 'high' else True)
        else:
            GPIO.setup(Setup[LEDRED][BCM], GPIO.IN)


def reset():
    if not GPIO:
        return

def execute_gpio_command(command):
    if not GPIO:
        print('no gpio installed/available on this computer ?!')
        exit(1)
    elif command == 'paon':
        power(True)
    elif command == 'paoff':
        power(False)
    elif command == 'speakeron':
        speaker(True)
    elif command == 'speakeroff':
        speaker(False)
    else:
        print(f'don\'t recognize gpio action {command}')
        exit(1)
