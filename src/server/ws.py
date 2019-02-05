
import asyncio
import websockets
import json
 
async def test():
 
    async with websockets.connect('ws://192.168.1.126:6680/mopidy/ws') as websocket:
 
        print("connected")
        while 1:
            response = await websocket.recv()
            print(response)
            message = json.loads(response)
            event = message['event']
            if event == 'track_playback_paused':
                pass
            elif event == 'playback_state_changed':
                pass
            elif event == 'volume_changed':
                pass
            elif event == 'track_playback_started':
                pass
            elif event == 'track_playback_ended':
                pass
            elif event == 'tracklist_changed':
                pass
            
 
asyncio.get_event_loop().run_until_complete(test())
