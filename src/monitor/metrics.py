from common import util
import datetime
import os
import re


def get_uptime():
    with open('/proc/uptime', 'r') as f:
        seconds = float(f.readline().split()[0])
        return str(datetime.timedelta(seconds=seconds))


def get_cputemperature():
    with open('/sys/class/thermal/thermal_zone0/temp') as f:
        return "%.1f" % (int(f.read()) / 1000)


def get_loadaverages():
    return "%.2f %.2f %.2f" % os.getloadavg()


def get_wifi_stats():
    result = util.execute_get_output("/usr/bin/iw wlan0 link")
    rssi = re.search(r'signal: (.*)', result).group(1)
    tx_rate = re.search(r'tx bitrate: (.*)', result).group(1)
    return "%s (%s)" % (rssi, tx_rate)


def get_cpu_load():
    result = util.execute_get_output(
        "grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage }' ")

    return "%.1f %%" % float(result)
