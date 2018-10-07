import logging

logger = logging.getLogger()
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s %(levelname)s (%(module)-10.10s) %(message)s\033[0m')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

RESET = '\033[0m'
GREY = '\033[0;37m'
WHITE = '\033[1;37m'
LIGHT_GREEN = '\033[1;32m'
LIGHT_RED = '\033[1;31m'
LIGHT_RED2 = '\033[1;37;41m'

_GREY = GREY + '%3.3s'
_WHITE = WHITE + '%3.3s'
_LIGHT_GREEN = LIGHT_GREEN + '%3.3s'
_LIGHT_RED = LIGHT_RED + '%3.3s'
_LIGHT_RED2 = LIGHT_RED2 + '%3.3s'

logging.addLevelName(logging.DEBUG, _GREY % logging.getLevelName(logging.DEBUG))
logging.addLevelName(logging.INFO, _LIGHT_GREEN % logging.getLevelName(logging.INFO))
logging.addLevelName(logging.WARNING, _LIGHT_RED % logging.getLevelName(logging.WARNING))
logging.addLevelName(logging.ERROR, _LIGHT_RED2 % logging.getLevelName(logging.ERROR))
logging.addLevelName(logging.CRITICAL, _LIGHT_RED2 % logging.getLevelName(logging.CRITICAL))
