.. _system_overview:

#########################
System overview
#########################

Ludit is both the name of the audio player project on github but it is also more generally used to encompass the entire audio player system.
The current complete Ludit audio system as it looks today is shown in the following image. The two main components are the server and the client dealing with routing and playing audio. There is a web page which connects to the server and is used for e.g. audio adjustments and selecting which groups are playing and which is not.

.. image:: images/ludit_system_diagram.png

Server:
-------

Pending...

Client:
-------

The client shown in the yellowish square to the right in the image is a mono player so there will be two of these in a stereo group. Stuff running on the raspberry pi is shown to the left of the vertical line, and stuff on the right is located on the carrier board called Luhab which is part of the Twitse project. Besides a DAC + VCTCXO for controlling the clock to the raspberry pi the Luhab carrier also features a PCM5102A audio DAC.

Web:
----

Pending...