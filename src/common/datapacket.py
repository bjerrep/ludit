import struct
import json
from common import util
from common.log import logger as log
from enum import Enum


class Payload(Enum):
    JSON = 1
    AUDIO = 2
    FLUSHING = 3


header_length = 4
serial = 0
trace_packets = False


def parse(data):
    _json = None
    _audio = None
    if len(data) < header_length:
        return data, _json, _audio

    length = struct.unpack('!H', data[0:2])[0]
    type = struct.unpack_from('!B', data, 2)[0]
    _serial = struct.unpack_from('!B', data, 3)[0]

    data_length = len(data)

    if data_length >= length + header_length:
        payload = data[header_length:header_length + length]

        if type == Payload.AUDIO.value:
            if trace_packets:
                log.info('rx audio serial %i - %i bytes' % (_serial, data_length - header_length))
            _audio = payload
        elif type == Payload.JSON.value:
            if trace_packets:
                log.info('rx json serial %i - %i bytes' % (_serial, data_length - header_length))
            _json = json.loads(payload.decode())
        elif type == Payload.FLUSHING.value:
            if trace_packets:
                log.info('rx flushing serial %i - %i bytes' % (_serial, data_length - header_length))
            pass
        else:
            log.critical('got malformed data, %i bytes' % len(data))
            log.critical(' '.join(format(x, '02x') for x in data[:min(500, len(data))]))
            raise util.MalformedPacketException
        data = data[header_length + length:]

    return data, _json, _audio


def inc_serial():
    global serial
    serial += 1
    if serial > 255:
        serial = 0


def pack_audio(data):
    global serial
    if trace_packets:
        log.info('tx audio serial %i - %i bytes' % (serial, len(data)))
    header = struct.pack('>HBB', *[len(data), Payload.AUDIO.value, serial])
    inc_serial()
    return header + data


def generate_flushing_packet():
    global serial
    data = bytearray(4096)
    if trace_packets:
        log.info('tx flushing serial %i - %i bytes' % (serial, len(data)))
    header = struct.pack('>HBB', *[len(data), Payload.FLUSHING.value, serial])
    inc_serial()
    return header + data


def pack_json(dictionary):
    global serial
    if type(dictionary) is str:
        _json = dictionary.encode()
    else:
        _json = json.dumps(dictionary).encode()

    if trace_packets:
        log.info('tx json serial %i - %i bytes' % (serial, len(_json)))
    header = struct.pack('>HBB', *[len(_json), Payload.JSON.value, serial])
    inc_serial()
    return header + _json


if __name__ == '__main__':
    try:
        packet = pack_audio(b'\x10\x11\x12')
        data, _json, _audio = parse(packet)
        print(str(data) + ' ' + str(_json) + ' ' + str(_audio))

        packet = pack_json({'command': 'test', 'command2': 'test2'})
        data, _json, _audio = parse(packet)
        print(str(data) + ' ' + str(_json) + ' ' + str(_audio))
        if _json:
            print(_json['command'])

        packet = pack_json('{"command": "test", "command2": "test2"}')
        data, _json, _audio = parse(packet)
        print(str(data) + ' ' + str(_json) + ' ' + str(_audio))
        if _json:
            print(_json['command'])

        packet = pack_json('{"command": "test1", "command2": "test2"}') + \
            pack_json('{"command": "test2", "command2": "test2"}')
        packet, _json, _audio = parse(packet)
        print(str(packet) + ' ' + str(_json) + ' ' + str(_audio))
        if _json:
            print(_json['command'])
        packet, _json, _audio = parse(packet)
        print(str(packet) + ' ' + str(_json) + ' ' + str(_audio))
        if _json:
            print(_json['command'])
        print('expecting zero bytes left: ' + str(len(packet)))

    except Exception as e:
        log.critical(str(e))
