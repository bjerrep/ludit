[![readthedocs](https://readthedocs.org/projects/ludit/badge/?version=latest)](https://ludit.readthedocs.io/en/latest/?badge=latest)

<p align="center"><img src="artwork/title.png"></p>

Ludit is the audio player for an audio system consisting of a wired raspberry pi server and wireless raspberry pi powered active stereo (as in two separate) speakers running with hard time synchronization.

You probably don't want to know what that is all about. If all you are looking for a nice multi-room audio player with a proven track record and a lot of happy users then you should head over to e.g. [snapcast](https://github.com/badaix/snapcast). 

The initial reason for the Ludit project was to see if it was possible to go wireless and replace normal speaker cables with either local short mains cables, or just thin uncritical power supply cables rather than speaker cables as with a normal power amplifier setup. 

The expectation is that nobody else will actually construct a audio system like this. It requires a lot of work to get going, both with hardware and software, and there is no guarantee that it will be possible to  reproduce a system like this in good working order.

## Hard time synchronization
The 2 wireless raspberry pi computers are located in 2 separate right and left speakers in a stereo setup. Both rpi's are hardware modified and have their normal 19.2 MHz X1 xtal replaced with a VCTCXO, a voltage controlled crystal oscillator. These VCTCXO's are controlled with the [twitse](https://github.com/bjerrep/twitse) client/server software. With this running both wireless rpi's are synchronized to each other typically within some +/- 20-30 microseconds. And synchronized means exactly that since the processors, buses and what not on the rpi's are now running at the same speed and are continuously tracking each other. This is a non-compromise solution to the problem of crystal drift over time between two separate computers if they should be in sync down to the actual hardware. As a consequence this audio player therefore have no concept of sample skipping, package dropping, re-sampling or anything that would be needed for correcting drift between speakers. Which in turn is why this player is useless to most for playing wireless stereo.

## Bluetooth A2DP
Ludit is intended to be invisible and out of the way for normal users. It can currently play one thing only, bluetooth A2DP. Most likely driven by e.g. Spotify on a mobile. (It does a lot of buffering and can not be used for realtime audio). The server hosts a bluetooth dongle and a [BlueALSA](https://github.com/Arkq/bluez-alsa) -> [fork](https://github.com/bjerrep/bluez-alsa) delivers encoded audio (sbc/aac) for the ludit server.

## Processes

Here is a list of the Ludit specific processes running on the server and on the two clients in the ludit system. First the server:

### Server

**BlueALSA** ([BlueALSA fork](https://github.com/bjerrep/bluez-alsa))
If it wasn't for bluealsa this page would probably have looked quite different. Makes it a breeze to get a A2DP audio sink running (once Bluetooth is running that is).

**Ludit server** (python, this repository)
The server loads audio from BlueALSA and forwards it to the speaker clients over WiFi. It maintains the overall system configuration which it sends to the clients and can exchange with the system configuration webpage. The server is designed to be multi-room capable but so far Ludit have only seen a single group of speakers. 
Also its not completely true that the server only plays bluetooth, it now listens on a gstreamer tcp socket and a [spotifyd](https://github.com/Spotifyd/spotifyd) daemon (spotify connect via wifi) as well.

**Monitor** (python, this repository)
A system aware process that allows restarting e.g. Ludit and Twitse processes and rebooting the server and/or clients. Used by the webpage to get computer related metrics for server and clients.

**webpage** (jQuery, this repository)
A homepage that allows fine-tuning of the loudspeaker internals. The following image is for configuring a group (containing 2 stereo speakers). The source files are pure prototype implementations, don't go there. For anyone that has calculated and constructed a passive crossover and then thought it could be funny to move the crossover frequency 200 Hz then a slider probably sounds attractive. The webpage is client side only and connects to the Ludit server, Monitor server and the Twitse server via websockets.

<p align="center"><img src="artwork/web_group_setup.png"></p>

### Clients

**Ludit client** (python, this repository)
Receives the raw stereo encoded A2DP audio, picks a channel to play and decodes it to a 2-way woofer and tweeter signal with gstreamer. The client is hardcoded to drive a 2-way speaker only. Audio is sent via ALSA to a DAC and finally a class D power amplifier where right channel is driving the woofer and left channel the tweeter. Or perhaps it is the other way around.

**Remote** (python, this repository)
Allows the Monitor to restart processes on the client and to get useless but geeky related information like cpu-temperature and such.


**Twitse** ([github](https://github.com/bjerrep/twitse))
Runs on both server and client to get their time in true sync.

### Status

Ludit is playing and have done so for a while. This does not mean that it isn't buggy, only that it works in a stationary setup with exactly two clients always available. A test with a single client, where two where expected from the configuration, only showed that this remains to be implemented properly. So there is one way to make Ludit work, and most likely infinitely many ways to make it fail.
Also something like volume control are left in a state where it is possible to turn it up and down but where the absolute resulting volume is useless until some magic values are inserted here and there in the source files. Consider yourself warned.

For more words there is a half-started documentation attempt [here](https://ludit.readthedocs.io/en/latest/). Its rather incoherent but it features e.g. a 'quick start' page in case the software for some reason should be tried out.

### Requirements

Some of the requirements for the whole enterprise are python 3, the python libs [connectable](https://github.com/timothycrosley/connectable) & [simple-websocket-server](https://github.com/dpallot/simple-websocket-server) and last but not least, gstreamer. 



