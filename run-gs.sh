#!/bin/bash

trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

./venv/bin/python ./bin/gs.py &
./run.sh ~/projects/client > /dev/null
