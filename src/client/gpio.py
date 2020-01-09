from common.log import logger as log
from enum import Enum
import json


try:
    import RPi.GPIO as GPIO
except Exception as e:
    log.critical("import RPi.GPIO error: " + str(e) + " - running without hardware support")
    GPIO = None


class LedColor(Enum):
    OFF = 0
    RED = 1
    GREEN = 2
    ORANGE = 3


GPIO_SPEAKER = 15
GPIO_SPEAKER_ACTIVE_HIGH = True
GPIO_PAPOWER = 14
GPIO_PAPOWER_ACTIVE_HIGH = False
GPIO_LED_A = 23
GPIO_LED_A_ACTIVE_HIGH = True
GPIO_LED_B = 22
GPIO_LED_B_ACTIVE_HIGH = True
GPIO_GPIO = 17


def init():
    global GPIO_PAPOWER, GPIO_SPEAKER, GPIO_PAPOWER_ACTIVE_HIGH, GPIO_SPEAKER_ACTIVE_HIGH
    global GPIO_LED_A, GPIO_LED_A_ACTIVE_HIGH, GPIO_LED_B, GPIO_LED_B_ACTIVE_HIGH
    if GPIO:
        try:
            with open('client_hw_setup.cfg') as f:
                config = json.loads(f.read())
                try:
                    GPIO_PAPOWER = config['papower']['pin']
                    GPIO_PAPOWER_ACTIVE_HIGH = config['papower']['active']
                except:
                    pass
                try:
                    GPIO_SPEAKER = config['speaker']['pin']
                    GPIO_SPEAKER_ACTIVE_HIGH = config['speaker']['active']
                except:
                    pass
                try:
                    GPIO_LED_A = config['ledA']['pin']
                    GPIO_LED_A_ACTIVE_HIGH = config['ledA']['active']
                except:
                    pass
                try:
                    GPIO_LED_B = config['ledB']['pin']
                    GPIO_LED_B_ACTIVE_HIGH = config['ledB']['active']
                except:
                    pass

                log.debug(f'speaker on gpio={GPIO_SPEAKER} polarity={GPIO_SPEAKER_ACTIVE_HIGH}')
                log.debug(f'papower on gpio={GPIO_PAPOWER} polarity={GPIO_PAPOWER_ACTIVE_HIGH}')
        except:
            log.info('using default i/o mappings')

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(GPIO_SPEAKER, GPIO.OUT)
        GPIO.setup(GPIO_PAPOWER, GPIO.OUT)
        GPIO.setup(GPIO_LED_A, GPIO.OUT)
        GPIO.setup(GPIO_LED_B, GPIO.OUT)
        GPIO.setup(GPIO_GPIO, GPIO.OUT)


def close():
    if not GPIO:
        return
    GPIO.cleanup()


def speaker(on):
    # Off the shelf class-D amplifiers often have a 'enable' input which can bring
    # the amplifier to sleep before cutting the power. Alternatively the speaker
    # signal can be used to control standard relays. All this is done to avoid
    # the risk of bangs and pops when power comes and goes.
    if not GPIO:
        return
    GPIO.output(GPIO_SPEAKER, on if GPIO_SPEAKER_ACTIVE_HIGH else not on)


def power(on):
    # Power on/off the amplifier power supply, typically done with a solid state relay.
    if not GPIO:
        return
    log.debug(f'setting pa power {on}')
    GPIO.output(GPIO_PAPOWER, on if GPIO_PAPOWER_ACTIVE_HIGH else not on)


def LED(color):
    if not GPIO:
        return
    if color == LedColor.OFF:
        GPIO.output(GPIO_LED_A, not GPIO_LED_A_ACTIVE_HIGH)
        GPIO.output(GPIO_LED_B, not GPIO_LED_B_ACTIVE_HIGH)
    elif color == LedColor.RED:
        GPIO.output(GPIO_LED_A, GPIO_LED_A_ACTIVE_HIGH)
        GPIO.output(GPIO_LED_B, not GPIO_LED_B_ACTIVE_HIGH)
    elif color == LedColor.GREEN:
        GPIO.output(GPIO_LED_A, not GPIO_LED_A_ACTIVE_HIGH)
        GPIO.output(GPIO_LED_B, GPIO_LED_B_ACTIVE_HIGH)
    else:
        GPIO.output(GPIO_LED_A, GPIO_LED_A_ACTIVE_HIGH)
        GPIO.output(GPIO_LED_B, GPIO_LED_B_ACTIVE_HIGH)


def GPIO_PIN(on):
    if not GPIO:
        return
    GPIO.output(GPIO_GPIO, on)


def reset():
    if not GPIO:
        return
    state = False
    GPIO.output(GPIO_SPEAKER, state)
    GPIO.output(GPIO_PAPOWER, state)
    GPIO.output(GPIO_LED_A, state)
    GPIO.output(GPIO_LED_B, state)
    GPIO.output(GPIO_GPIO, state)
