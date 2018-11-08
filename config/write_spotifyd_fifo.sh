#!/bin/bash
# this is a broker between spotifyd (executing a command as the script here) and
# ludit listening to the fifo
echo $PLAYER_EVENT " " $TRACK_ID > /tmp/spotifyd
