#!/usr/bin/env bash

set -e
cd "$(dirname "$0")" # cd to directory of this script

OPTIONS='
    -Isigil/include
    -Lsigil/build-linux-gcc
    -framework CoreServices
    -framework CoreFoundation
    -framework AudioUnit
    -framework AudioToolbox
    -framework CoreAudio
    -lportaudio
    -lsigil
'

rm -rf bin
mkdir -p bin

gcc $OPTIONS src/examples/portaudio_sine_example.c -o bin/portaudio_sine_example
gcc $OPTIONS src/examples/simple_sigil_example.cpp -o bin/simple_sigil_example


# Run with:
# DYLD_LIBRARY_PATH=sigil/build-linux-gcc bin/simple_sigil_example
