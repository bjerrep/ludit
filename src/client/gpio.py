from common.log import logger as log
from enum import Enum


try:
    import RPi.GPIO as GPIO
except Exception as e:
    log.critical("import RPi.GPIO error: " + str(e) + " running without hardware support")
    GPIO = None


class LedColor(Enum):
    OFF = 0
    RED = 1
    GREEN = 2
    ORANGE = 3


if GPIO:
    GPIO.setmode(GPIO.BCM)

    GPIO_SPEAKER = 15
    GPIO_PAPOWER = 14
    GPIO_LED_A = 23
    GPIO_LED_B = 22
    GPIO_GPIO = 17

    GPIO.setup(GPIO_SPEAKER, GPIO.OUT)
    GPIO.setup(GPIO_PAPOWER, GPIO.OUT)
    GPIO.setup(GPIO_LED_A, GPIO.OUT)
    GPIO.setup(GPIO_LED_B, GPIO.OUT)
    GPIO.setup(GPIO_GPIO, GPIO.OUT)


def close():
    if not GPIO:
        return
    GPIO.cleanup()


def speaker_relay(on):
    if not GPIO:
        return
    GPIO.output(GPIO_SPEAKER, on)


def Power(on):
    if not GPIO:
        return
    GPIO.output(GPIO_PAPOWER, not on)


def LED(color):
    if not GPIO:
        return
    if color == LedColor.OFF:
        GPIO.output(GPIO_LED_A, False)
        GPIO.output(GPIO_LED_B, False)
    elif color == LedColor.RED:
        GPIO.output(GPIO_LED_A, True)
        GPIO.output(GPIO_LED_B, False)
    elif color == LedColor.GREEN:
        GPIO.output(GPIO_LED_A, False)
        GPIO.output(GPIO_LED_B, True)
    else:
        GPIO.output(GPIO_LED_A, True)
        GPIO.output(GPIO_LED_B, True)


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
