.. _client_types:

############
Client types
############

There are two types of clients, single channel and stereo. 

Single channel
**************

Single channel clients are straightforward and simple. They come in pair of twos in order to play a stereo signal. They will play either the left or right channel and thus each client will need to know which channel to pick. A server group for two single channel clients could look like this:

*Server configuration:*

.. code-block:: json 
   
    "devices": [
        {
            "channel": "left",
            "name": "leftdevicename"
        },
        {
            "channel": "right",
            "name": "rightdevicename"
        }
      ],
      "name": "groupname"


This is a part of the default json configuration that the server will print out with --newcfg. 

The two clients in a group like this will call in with their names and the server will inform them about which channel to play. The straight forward way for each standard single channel client to identify itself is to supply a '--id group:name' on the command line which will use default settings for everything else. Alternatively they can specify a client configuration file instead in case the defaults won't do, see client configuration.


Stereo
******

It is possible to make a stereo speaker as well. The usecase will be a speaker that both runs as a low latency soundbar for a tv as well as being a normal streaming playing group. Channel will now be 'stereo'.

*Server configuration:*

.. code-block:: json

    "devices": [
        {
          "channel": "stereo",
          "name": "devicename"
        }
      ],
      "name": "groupname"

As for the single channel a stereo client can be started with --id or by specifying a local configuration file with --cfg.


Client configuration
********************

This is a template configuration for a client printed by a client with --newcfg:

.. code-block:: json

    "alsa": {
        "devices": [
            "hw:0",
            "hw:1"
        ]
    },
    "device": "devicename",
    "group": "groupname",
    "multicast": {
        "ip": "225.168.1.102",
        "port": "45655"
    },
    "version": "0.3"


The "alsa" part is optional, it can be used to override the system default alsa device if needed. The only case where it is required to be present and contain exactly two entries is for a stereo device using two separate soundcards. For a single channel device or a stereo device using e.g. a 5.1 surround soundcard it should only contain a single 'devices' entry if the default should be overwritten.

