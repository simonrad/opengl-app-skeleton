#!/usr/bin/env bash

set -e
cd "$(dirname "$0")" # cd to directory of this script.

command -v brew >/dev/null 2>&1 || {
    # Homebrew is not installed.
    echo >&2 "Please install homebrew and then re-run build_deps.sh. Aborting."
    exit 1
}

brew install portaudio cmake glew glfw freetype

if [ ! -d "sigil" ]; then
    # Directory sigil does not exist, clone it.
    git clone git@github.com:simonrad/sigil.git
fi

cd sigil

# Build sigil
mkdir -p build-linux-gcc
cd build-linux-gcc
cmake ../
make

echo "All done!"
