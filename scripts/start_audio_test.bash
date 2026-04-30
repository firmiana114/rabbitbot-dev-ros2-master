#!/bin/bash

aplay -l

pactl list short sinks

pactl get-sink-volume 0
pactl set-sink-volume 0 80%

arecord -D hw:3,0 --dump-hw-params -d 1 /dev/null
arecord -D hw:3,0 -d 5 -f S16_LE -r 48000 -c 1 test.wav
