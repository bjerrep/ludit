.. _client_types:

############
Client types
############

There are two types of clients, single channel and stereo. 

Single channel
**************

Single channel clients are straightforward and simple. They come in pair of twos in order to play a stereo signal. They will play either the left or right channel and thus each client will need to know which channel to pick. A server group for two single channel clients could look like this:

.. code-block:: json

    "devices": [
        {
            "channel": "left",
            "name": "left"
        },
        {
            "channel": "right",
            "name": "right"
        }
    ]

This is a part of the default json configuration that the server will print out with --newcfg. The two clients in a group like this will call in with their names and the server will inform them about which channel to play.


Stereo
******

It should be possible to make stereo speakers as well. This will require two stereo outputs for a total of 4 outputs.

.. code-block:: json

    "general": {
        "devices": [
            {
                "channel": "stereo",
                "left_alsa_device": "hw:0",
                "name": "stereo",
                "right_alsa_device": "hw:1"
            }
        ]
    }





amixer sget 'PCM Capture Source'
amixer cset name='PCM Capture Source', 'Line'
alsactl store
