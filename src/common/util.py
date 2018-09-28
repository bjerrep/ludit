from common.log import logger as log
import socket
import threading
import subprocess
from connectable import Connectable

NS_IN_SEC = 1000000000

multicast_ip = '225.168.1.102'
multicast_port = 45655

remote_multicast_ip = multicast_ip
remote_multicast_port = multicast_port + 1

server_ludit_websocket_port = 45658
server_monitor_websocket_port = 45659


class Threadbase(threading.Thread, Connectable):
    def __init__(self, name=None):
        super(Threadbase, self).__init__()
        if name:
            self.setName(name)
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def is_terminated(self):
        return self.terminated


def make_id(groupname, devicename):
    return "%s:%s" % (groupname, devicename)


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
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.connect(('<broadcast>', 0))
    return s.getsockname()[0]


def execute(command):
    log.debug('NOT executing "%s"' % command)
    return 0

    ret = subprocess.run(command, shell=True)
    if ret.returncode:
        log.critical('command failed with exitcode %i' % ret.returncode)
    return ret.returncode


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


class Base(Connectable):
    pass
