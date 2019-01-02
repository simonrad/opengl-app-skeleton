#!/usr/bin/env bash

set -e
cd "$(dirname "$0")" # cd to directory of this script.

./build_deps.sh && ./build.sh && DYLD_LIBRARY_PATH=sigil/build-linux-gcc bin/simple_sigil_example
