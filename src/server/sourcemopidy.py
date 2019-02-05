from server.sourcetcp import SourceTCP
from common.log import logger as log
from common import util
import asyncio
import websockets
import json
import time

# https://techtutorialsx.com/2018/02/11/python-websocket-client/


class SourceMopidy(util.Threadbase):

    signals = 'event'

    def __init__(self, mopidy_address, tcp_port, name='mopidy'):
        super(SourceMopidy, self).__init__(name=name)
        self.mopidy_address = mopidy_address
        self.tcp = SourceTCP(tcp_port)
        self.tcp.connect("event", self.input_event)
        self.volume = -1
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.start()

    def terminate(self):
        print(dir(self.ws))
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.tcp.terminate()
        super().terminate()
        log.debug('sourcemopidy terminated')

    def input_event(self, skv):
        self.emit('event', skv)

    async def ws_listen(self):

        async with websockets.connect('ws://%s:6680/mopidy/ws' % self.mopidy_address) as self.ws:
            try:
                log.info('connected to mopidy websocket')
                while 1:
                    response = await self.ws.recv()
                    message = json.loads(response)
                    event = message['event']

                    try:
                        uri = message['tl_track']['track']['uri']
                    except KeyError:
                        uri = ''

                    if event == 'track_playback_paused':
                        log.info('mopidy paused ' + uri)
                    elif event == 'track_playback_resumed':
                        log.info('mopidy resumes ' + uri)
                    elif event == 'playback_state_changed':
                        old_state = message['old_state']
                        new_state = message['new_state']
                        log.info('mopidy state change from %s to %s' % (old_state, new_state))
                    elif event == 'volume_changed':
                        volume = message['volume']
                        if volume != self.volume:
                            self.volume = volume
                            log.info('mopidy volume %i' % volume)
                    elif event == 'track_playback_started':
                        log.info('mopidy started ' + uri)
                    elif event == 'track_playback_ended':
                        log.info('mopidy stopped ' + uri)
                    elif event == 'tracklist_changed':
                        pass
                    else:
                        log.info('mopidy event not recognized: %s' % message)
            except Exception as e:
                print('fixit')
                raise e

    def run(self):
        while not self.terminated:
            try:
                self.loop.run_until_complete(self.ws_listen())
            except ConnectionRefusedError:
                pass
            except websockets.ConnectionClosed:
                log.info('mopidy websocket was closed')
            except Exception as e:
                print(str(e))

            time.sleep(1)

        log.debug('sourcemopidy exits')
