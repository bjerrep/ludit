from common import util
from common.log import logger as log
from common import datapacket
from server import group
import time


class PlaySequencer(util.Base):
    signals = ('brokensocket',)
    m_state = group.State.STOPPED
    m_buffer_count = 0
    groups = {}

    def __init__(self, jsn):
        for group_jsn in jsn['groups']:
            if not group_jsn['enabled']:
                log.info('group %s is disabled' % group_jsn['name'])
                continue
            group_jsn['playdelay'] = jsn['playdelay']
            group_jsn['buffersize'] = jsn['buffersize']

            group_name = group_jsn['name']
            log.debug('playsequencer, adding group "%s"' % group_name)
            self.audio_timeout = float(jsn['audiotimeout'])
            _group = group.Group(group_jsn)
            _group.connect('brokensocket', self.broken_socket)
            _group.connect('status', self.status)
            self.groups.update({group_name: _group})

        self.starvation_pause = False
        self.client_buffering_ready = False

    def ready(self):
        try:
            for group in self.enabled_groups():
                if not group.ready_to_play():
                    return False
            return True
        except:
            return False

    def terminate(self):
        for _group in self.groups.values():
            _group.terminate()

    def broken_socket(self, source):
        self.emit('brokensocket', source)

    def status(self, state):
        if state in ('buffered', 'starved'):
            if self.m_state == group.State.BUFFERING and state == 'buffered':
                log.info('------ playing -------')
                self.state_changed(group.State.PLAYING)
            elif self.m_state == group.State.PLAYING and state == 'starved':
                log.info('------ pause ---------')
                self.state_changed(group.State.STOPPED)

    def current_configuration(self):
        config = []
        for group in self.groups.values():
            config.append(group.get_configuration())
        return {'groups' : config}

    def send_to_groups(self, packet):
        for _group in self.enabled_groups():
            _group.send_all(packet)

    def set_codec(self, codec):
        self.send_to_groups({'command': 'setcodec', 'codec': codec})

    def set_volume(self, volume):
        self.send_to_groups({'command': 'setvolume', 'volume': volume})

    def get_group(self, groupname):
        return self.groups[groupname]

    def state_changed(self, new_state):
        global AudioQueue
        if self.m_state != new_state:
            now = time.time()
            for _group in self.enabled_groups():
                if new_state == group.State.BUFFERING:
                    _group.send_all({'command': 'buffering'})
                elif new_state == group.State.STOPPED:
                    _group.send_all({'command': 'stopping'})
                elif new_state == group.State.PLAYING:
                    _group.start_playing(now)
                else:
                    log.critical('internal error #0082')
            self.m_state = new_state

    def enabled_groups(self):
        return [group for group in self.groups.values() if group.active()]

    def new_audio(self, audio):

        new_state = self.m_state

        if self.m_state == group.State.STOPPED:
            self.m_buffer_count = 0
            new_state = group.State.BUFFERING
            self.client_buffering_ready = False

        if new_state != self.m_state:
            self.state_changed(new_state)

        self.send_to_groups(datapacket.pack_audio(audio))
