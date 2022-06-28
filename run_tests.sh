#!/usr/bin/bash

CURDIR="$(dirname -- "$(which -- "$0" 2>/dev/null || realpath -- "./$0")")"
pushd $CURDIR
export PYTHONPATH=$PYTHONPATH:$CURDIR/src
python3 -m unittest discover -s tests
popd
