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

Spotifyd enables Ludit as an 'Spotify Connect' audio player in e.g. the Spotify list called 'Connect to device'.
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


Audio source : gstreamer
*************************

An example of a gstreamer audio source can be found in :ref:`quick_start`.


