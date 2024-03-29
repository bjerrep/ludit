.. _software_installations:

######################
Software installations
######################

The package lists below are at least a starting point for installing the Ludit dependencies. On a computer never used for development before the lists will most likely not be exhaustive. Hopefully things will later crash and fail in a way that indicates what could be missing.


​Common installs
****************

These installs are common for both server and clients

Arch::

    python-pip libfdk-aac faad2 faac kate git subversion openssh rsync gstreamer gst-python gst-plugins-good gst-plugins-bad gst-plugins-ugly gst-libav python-pybluez python-websockets

On a fresh install this will end up as nearly 1GB of storage used.

Ubuntu::

    gstreamer1.0-libav gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly python-gst-1.0 ubuntu-restricted-extras aac-enc libfdk-aac-dev autoconf libtool libasound2 libasound2-dev bluez libbluetooth-dev glib-2.0-dev libgtk2.0-dev libsbc-dev libsbc1 python3-pip python3-websockets


Others
-------

connectable installable via pip::

    pip3 install connectable --upgrade



Client software installs
*************************

The client attempts to interact with gpio on a raspberrypi, to keep it from complaining on a raspberrypi install rpi-gpio python bindings. If rpi-gpio are unavailable (which they will always be on a non-rpi) then gpio will just be disabled.

Server software installs
*************************

simple-websocket-server can be installed via pip::

    sudo pip install git+https://github.com/dpallot/simple-websocket-server.git



Known problems
***************

Bluez exception using python 3.10 (seen on arch)
 - SystemError: PY_SSIZE_T_CLEAN macro must be defined for '#' formats
 - UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 4: invalid start byte

Install pybluez from Blaok fork (after uninstalling whatever pybluez might already be installed)::

    $ git clone https://github.com/Blaok/pybluez.git && cd pybluez
    # python setup.py install

