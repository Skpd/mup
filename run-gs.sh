#!/bin/bash
# Starts connect + game server, then the client. Closing the client stops the servers.
# Arguments are passed to run-client.sh.

cd "$(dirname "$0")" || exit 1

trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

./venv/bin/python ./bin/cs.py &
./venv/bin/python ./bin/gs.py &
./run-client.sh "$@"
