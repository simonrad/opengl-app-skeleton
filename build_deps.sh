#!/usr/bin/env bash

set -e
cd "$(dirname "$0")" # cd to directory of this script

# TODO: If brew does not exist, print "please install homebrew"

brew tap homebrew/versions
brew install portaudio cmake glew glfw3

# TODO: If sigil does not exist, clone it from simonrad github

cd sigil

# Build sigil
mkdir -p build-linux-gcc
cd build-linux-gcc
cmake ../
make

echo "All done!"
