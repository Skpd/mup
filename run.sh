#!/bin/bash
#set -x
vhome="${HOME}/tmp/.winestorage"
# SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
CLIENT_PATH=$1

if [ ! -d "$vhome" ]; then
  echo "creating $vhome"
  mkdir -p $vhome
fi

if [ ! -d "$CLIENT_PATH" ]; then
  echo "client path required."
  exit 1
fi

docker run --rm \
  -e DISPLAY \
  -e WINEPREFIX=/wine/game \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -e PULSE_SERVER=unix:/pulse \
  -e HOME=/wine \
  -v "$HOME"/.Xauthority:/wine/.Xauthority \
  -v /run/user/$(id -u)/pulse/native:/pulse \
  --device /dev/nvidia0:/dev/nvidia0 \
  --device /dev/nvidiactl:/dev/nvidiactl \
  --device /dev/nvidia-uvm:/dev/nvidia-uvm \
  --device /dev/nvidia-uvm-tools:/dev/nvidia-uvm-tools \
  --device /dev/nvidia-modeset:/dev/nvidia-modeset \
  -v "${vhome}":/wine \
  -v "${CLIENT_PATH}":/wine/game \
  -ti \
  wine:latest -c "cd /wine/game/client_wip && wine main.exe"