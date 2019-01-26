.. _software_installations:

######################
Software installations
######################

The package names on this page does not follow any specific distribution so a little detective work will be required to find the actual packages to install. On a computer never used for development before the lists below will be far from exhaustive. 

****************
​Common installs
****************

These installs are common for both server and clients::

    git python3 gstreamer gst-libav gst-plugins-bad gst-plugins-base gst-plugins-good gst-plugins-ugly gst-python

Installable via pip::

    connectable

*************************
Client software installs
*************************

The client attempts to interact with gpio on a raspberrypi, to keep it from complaining on a raspberrypi install rpi-gpio python bindings. If rpi-gpio are unavailable (which they will always be on a non-rpi) then gpio will just be disabled.

*************************
Server software installs
*************************

Installable via pip::

    simple-websocket-server

sudo pip install git+https://github.com/dpallot/simple-websocket-server.git

Audio source: spotifyd
======================

Spotifyd enables Ludit as an 'Spotify Connect' audio player in e.g. the Spotify list called 'Connect to device'.
There are ready made binaries for RPI, on x86 follow the upstream `spotifyd <https://github.com/Spotifyd/spotifyd>`_ for build instructions.

PCM audio from spotifyd is recorded with an Alsa loopback device. Install ./config/modules-load.d/raspberrypi.conf from the repository in /etc/modules.d on the server. This will make the snd-aloop kernel module load at boot which configures the loopback device. Check that the loopback device is card 1 and the onboard bcm2835 is card 0. The loopback setup is just to avoid touching the spotifyd sources as they are written in Rust which apparently is some kind of programming language.

aplay -l::

    card 0: ALSA [bcm2835 ALSA], device 0: bcm2835 ALSA [bcm2835 ALSA]
        Subdevices: 7/7
        Subdevice #0: subdevice #0
        Subdevice #1: subdevice #1
        .. etc
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


Audio source: BlueALSA
======================

Prerequisites are::

    a standard gcc and autotools build toolchain.
    sbc aac bluez

Use the fork `here <https://github.com/bjerrep/bluez-alsa/>`_. Building instructions can be found on `upstream <https://github.com/Arkq/bluez-alsa>`_.







