#!/bin/python3
import gi, sys, re, time, signal
gi.require_version('Gst', '1.0')
from gi.repository import GLib, GObject, Gst
Gst.init(None)


def sigint_handler(sig, frame):
    if sig == signal.SIGINT:
        __mainloop.quit()
    else:
        raise ValueError("Undefined handler for '{}'".format(sig))

signal.signal(signal.SIGINT, sigint_handler)


sink = None

def bus_message(_bus, message):
    if message.type == Gst.MessageType.ERROR:
        err, deb = message.parse_error()
        print(f'{message.src.name}: pipeline error: {err} {deb}')
    elif message.type == Gst.MessageType.WARNING:
        err, deb = message.parse_warning()
        print(f'{message.src.name}: pipeline warning: {err} {deb}')
    elif message.type == Gst.MessageType.STATE_CHANGED:
        if message.src == sink:
            old_state, new_state, pending_state = message.parse_state_changed()
            print(f'* pipeline [{message.src.name}] state changed to {Gst.Element.state_get_name(new_state)}')
    else:
        print(message.type)
    return True


if len(sys.argv) != 2:
    print('add tx or rx')
    exit(1)

# How to get error messages from python Gst.Bus
# https://stackoverflow.com/q/49244142

p = re.compile(r'Unexpected discontinuity in audio timestamps of \+0:00:(\d{2}.\d{9}), resyncing')

t = p.match('Unexpected discontinuity in audio timestamps of +0:00:00.711904761, resyncing')
disc1 = 0.0
disc2 = 0.0

"""
def on_debug(category, level, dfile, dfctn, dline, source, message, user_data):
    if a != 1:
        print("oups")
    if level == Gst.DebugLevel.WARNING:
        if message.get().startswith('Unexpected discontinuity'):
            r = p.match(message.get())
            disc1 = float(r.group(1))
            disc2 = disc1
            print(disc1)

Gst.debug_remove_log_function(None)
Gst.debug_add_log_function(on_debug, None)
"""
if Gst.debug_get_default_threshold() < Gst.DebugLevel.WARNING:
    Gst.debug_set_default_threshold(Gst.DebugLevel.WARNING)
Gst.debug_set_active(True)

if sys.argv[1] == 'tx':
    tx = 'audiotestsrc ! audioconvert ! audioresample ! audio/x-raw, rate=44100, channels=2, format=S32LE ! audiomixer ! udpsink port=5555 host=127.0.0.1 name=sink'
    pipeline = Gst.parse_launch(tx)
elif sys.argv[1] == 'rx':
    rx = 'udpsrc address=127.0.0.1 port=5555 ! rawaudioparse use-sink-caps=false format=pcm pcm-format=s32le sample-rate=44100 num-channels=2 ! queue ! audioconvert ! audioresample ! alsasink name=sink'
    pipeline = Gst.parse_launch(rx)

sink = pipeline.get_by_name('sink')

bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect('message', bus_message)
pipeline.set_state(Gst.State.PLAYING)

__running = False
__mainloop = GLib.MainLoop()

context = __mainloop.get_context()
try:
    while not __running:
        msg = bus.timed_pop_filtered(
            Gst.CLOCK_TIME_NONE,
            Gst.MessageType.WARNING
        )

        if msg:
            print("asdf")
            print(msg)
            # if level == Gst.DebugLevel.WARNING:
            #     if message.get().startswith('Unexpected discontinuity'):
            #         r = p.match(message.get())
            #         disc1 = float(r.group(1))
            #         disc2 = disc1
            #         print(disc1)

        if context.pending():
            context.iteration(True)
        else:
            time.sleep(0.01)
except:
    pass

__mainloop.quit()
#GLib.MainLoop().run()



