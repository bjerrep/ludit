.. _server_audio_source_setup:

#########################
Server audio source setup
#########################

The currently supported audio sources are

- spotifyd - Spotify over LAN/Wifi
- bluealsa - A2DP bluetooth sink
- gstreamer - Used for testing


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


Audio source: Mopidy
*********************
It would be kind of rude not to add Mopidy as an audio source since Mopidy uses gstreamer and exposes its playing pipeline directly in its configurationfile. Mopidy plays just about everything but for development it has only been tested with a standard MPD client. So the state of the Mopidy audio source in this project will realisticly be something like 'under development'.

The Mopidy playing pipeline in ~/.config/mopidy/mopidy.conf should be changed to::
    
    output = audioconvert ! audio/x-raw, channels=2 ! faac ! aacparse ! avmux_adts ! tcpclientsink host=<server> port=4666 sync=true

Mopidy sends general play state events on a websocket that Ludit needs to subscribe to. There are 4 configuration values in the Ludit configurationfile that needs to get adjusted::

    mopidy_ws_enabled': 'true'
    mopidy_ws_address': ip where Mopidy is running
    mopidy_ws_port': the http port in the Mopidy configuration file
    mopidy_gst_port': the tcpclientsink port in the Mopidy playing pipeline above


Audio source : gstreamer
*************************

An example of a gstreamer audio source can be found in :ref:`quick_start`.


