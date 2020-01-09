.. _server_audio_source_setup:

#########################
Server audio source setup
#########################

The currently supported audio sources are

- spotifyd - Spotify over LAN/Wifi
- bluealsa - A2DP bluetooth sink
- gstreamer - Used for testing
- alsa - Alsa input on the server
- realtime - Local client in soundbar mode

Audio source: spotifyd
***********************

Spotifyd enables Ludit as an 'Spotify Connect' audio player in e.g. the Spotify list called 'Connect to device' seen by selecting 'Devices Available' during playing.
There are ready made binaries for RPI, on x86 follow the upstream `spotifyd <https://github.com/Spotifyd/spotifyd>`_ instructions.

PCM audio from spotifyd is recorded with an Alsa loopback device. Install ./config/modules-load.d/raspberrypi.conf from the repository in /etc/modules.d on the server. This will make the snd-aloop kernel module load at boot which setups the loopback device. Check that the loopback device is device 1 and the onboard bcm2835 is device 0.


aplay -l::

    card 0: ALSA [bcm2835 ALSA], device 0: bcm2835 ALSA [bcm2835 ALSA]
        Subdevices: 7/7
        Subdevice #0: subdevice #0
        Subdevice #1: subdevice #1
        .. etc
    card 0: ALSA [bcm2835 ALSA], device 1: bcm2835 ALSA [bcm2835 IEC958/HDMI]
        Subdevices: 1/1
        Subdevice #0: subdevice #0
    card 1: Loopback [Loopback], device 0: Loopback PCM [Loopback PCM]
        Subdevices: 8/8
        Subdevice #0: subdevice #0
        Subdevice #1: subdevice #1
        Subdevice #2: subdevice #2
        .. etc
    card 1: Loopback [Loopback], device 1: Loopback PCM [Loopback PCM]
        Subdevices: 8/8
        Subdevice #0: subdevice #0
        Subdevice #1: subdevice #1
        Subdevice #2: subdevice #2
        .. etc

For starting spotifyd manually have a look at the systemd file in ./systemd/ludit_spotifyd.service.template. It shows how to create a /tmp/spotifyd fifo and an example spotifyd launch line.


Audio source: BlueALSA
***********************

Use the fork `here <https://github.com/bjerrep/bluez-alsa/>`_. Building instructions can be found on `upstream <https://github.com/Arkq/bluez-alsa>`_.

Get bluetooth running as the first thing, including pairing and trusting the source devices.

For starting bluealsa manually have a look at the systemd file in ./systemd/bluealsa.service.template (in the bluealsa fork repository !). Like for spotifyd it shows how to create a /tmp/audio fifo and a typical spotifyd launch line.

If anonymous users should be able to play over bluetooth without any trusting or pairing then use a bluetooth autoconnect script like this one: (not tried this specific one but it looks nice)
https://gist.github.com/oleq/24e09112b07464acbda1#file-a2dp-autoconnect

Audio source: Mopidy
*********************
It would be kind of rude not to add Mopidy as an audio source since Mopidy uses gstreamer and exposes its playing pipeline directly in its configurationfile. Mopidy plays just about everything but for Ludit integration it has only been tested with a standard MPD client. So the state of the Mopidy audio source in this project will realisticly be something like 'under development'.

The Mopidy playing pipeline in ~/.config/mopidy/mopidy.conf should be changed to::

    output = audioconvert ! audio/x-raw, channels=2 ! faac ! aacparse ! avmux_adts ! tcpclientsink host=<server> port=4666 sync=true

Mopidy sends general play state events on a websocket that Ludit needs to subscribe to. There are 4 configuration values in the Ludit configurationfile that needs to get adjusted::

    mopidy_ws_enabled': 'true'
    mopidy_ws_address': ip where Mopidy is running
    mopidy_ws_port': the http port in the Mopidy configuration file
    mopidy_gst_port': the tcpclientsink port in the Mopidy playing pipeline above

While developing Mopidy refused the webconnection from the Ludit server. A quick hack is to edit 'handlers.py' in the Mopidy sources. Edit the check_origin function to end with

    #if parsed_origin and parsed_origin not in allowed_origins:
    #   logger.warn('HTTP request denied for Origin "%s"', origin)
    #    return False
    return True

For reference see https://github.com/mopidy/mopidy/pull/1712/commits/6e9ed9e8a9d4734671756ceeebf2059657ea2ab5. What the real fix is remains to be figured out.


Audio source : gstreamer
*************************

An example of a gstreamer audio source can be found in :ref:`quick_start`.

Audio source : alsa
*******************

Listens to an alsa input device on the server and uses a noise gate to automatically start and stop playing whenever there is a signal. This source is experimental.

Tip: To quickly check that there is indeed audio present on a given device (when nothing works), then arecord can act as a commandline vu meter:

arecord -f cd -d 0 -D hw:0 -vv /dev/null


Audio source : realtime
***********************

This is a rather convoluted audio source. The aim is to allow a client to run with minimal latency from a local input source and play it back locally as well. As such it is running against the spirit of Ludit as it for a start isn't really a Ludit audio source as it doesn't run on the server. It only plays locally on a single client and it is not broadcast over the network to other clients. The only usecase would be a stereo or a soundbar that should be able to both operate as a normal Ludit client with audio streamed from the server, but also play audio from a local video source in realtime. And even then it only makes sense if the audio processing in Ludit is truly needed due to e.g. preserve the workings of the crossover filter and/or any equalization filters. For playing a local realtime stereo signal the client should be configured as a stereo device which requires it to have two stereo alsa devices for 4 channel playback matching two two-way crossovers.

If a client is running in realtime mode its idle state is to listen for local audio and start playing if there is any. If the server starts streaming this will always have priority over the local audio and the local audio will only be able to resume when the server stops streaming. This is the simplest possible setup since it does not require the server to even know that there is a realtime client present.

If a client should run in realtime mode it has to be started with a local configuration file. The server can't help with setting up a realtime client.

As for what the latency actually is then its okay for watching video. Purists requiring near zero latency (or better..) will most likely have left reading about Ludit by now anyway.

The automatic starting and stopping of local audio is done the same way as for the normal alsa audio source described above.
