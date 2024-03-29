import time

from common.log import logger as log
import socket
import threading
import subprocess
import sys
import os
from connectable import Connectable
from enum import Enum

NS_IN_SEC = 1000000000

LUDIT_VERSION = "0.1"
CONFIG_VERSION = "0.4"

multicast_ip = '225.168.1.102'
multicast_port = 45655

remote_multicast_ip = multicast_ip
remote_multicast_port = multicast_port + 1


class LowBufferHandler(Enum):
    starved = 0
    silence = 1


class Base(Connectable):
    pass


class Threadbase(threading.Thread, Connectable):
    def __init__(self, name='default'):
        super(Threadbase, self).__init__()
        self.name = name
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def is_terminated(self):
        return self.terminated


def die(message, exit_code=1, hard_exit=False):
    log.critical(message)
    if hard_exit:
        os.kill(os.getpid(), os.WNOHANG)
    else:
        sys.exit(exit_code)


def make_id(groupname, devicename):
    return "%s:%s" % (groupname, devicename)


def get_group_and_device_from_id(id):
    try:
        return id.split(':')
    except Exception as e:
        log.critical(f'get_group_and_device_from_id from "{id}" failed with {e}')
        raise e


def split_tcp(tcp):
    """
    Converts an ipv4 udp/tcp ip endpoint string 'x.x.x.x:p' to a ('x.x.x.x', p) tuple
    used for e.g. socket.bind() and socket.connect()
    """
    return tcp.split(':')[0], int(tcp.split(':')[1])


def tcp2str(tcp):
    """
    Converts an ipv4 tupple ('x.x.x.x', p) to the string 'x.x.x.x:p'
    """
    return '%s:%s' % (tcp[0], str(tcp[1]))


# https://stackoverflow.com/a/23822431
def local_ip():
    """ raises exception on failure to get local ip address """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.connect(('<broadcast>', 0))
    return s.getsockname()[0]


def wait_for_network(timeout=60):
    """ wait for a local ip to be defined and return it.
        Return None if this doesn't happen before the timeout
    """
    seconds_waited = 0
    while True:
        try:
            ip = local_ip()
            if seconds_waited:
                log.debug(f'network acquired after {seconds_waited} seconds')
            return ip
        except:
            pass
        time.sleep(1)
        seconds_waited += 1
        timeout -= 1
        if not timeout:
            log.warning(f'network timeout, waited {seconds_waited} seconds. Giving up')
            return None


def execute(command):
    # log.debug('NOT executing "%s"' % command)
    # return 0

    ret = subprocess.run(command, shell=True)
    if ret.returncode:
        log.critical('command failed with exitcode %i' % ret.returncode)
    return ret.returncode


def execute_get_output(command):
    try:
        output = subprocess.check_output(command, shell=True)
        return output.decode()
    except subprocess.CalledProcessError:
        return None


def get_pid_lock(process_name):
    # https://stackoverflow.com/a/7758075
    get_pid_lock._lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        get_pid_lock._lock_socket.bind('\0' + process_name)
    except socket.error:
        die('pid lock "%s" already exists, exiting now' % process_name, 1, True)


class MalformedPacketException(Exception):
    pass


class TimeoutException(Exception):
    pass


class ExpectedException(Exception):
    pass


class ClosedException(Exception):
    pass


class IsOpenException(Exception):
    pass


class TerminatedException(Exception):
    pass


class ColdstartException(Exception):
    pass


class AudioClosedException(Exception):
    pass


class DeviceException(Exception):
    pass
