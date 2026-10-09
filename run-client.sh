#!/bin/bash
# Runs a client with native wine inside a virtual desktop window, so the game's
# fullscreen switch stays inside the window instead of changing the display mode.
#
# usage: ./run-client.sh [client dir] [desktop size] [desktop name]
#   desktop size should match the client resolution set in the wine registry
#   (HKCU\Software\Webzen\Mu\Config\Resolution: 0 - 640x480, 1 - 800x600, 2 - 1024x768, 3 - 1280x1024;
#   4 - 1600x1200 has no font size in the client, its text is unreadable)
#   Text is crisp with font smoothing off in the prefix (HKCU\Control Panel\Desktop FontSmoothing "0") and the
#   fixed client data files (tools/fix_client.py).
#   desktop name defaults to a unique one per run, so several clients can run side by side.
#   Clients started with the same name share one desktop and fight over its resolution.
#
# The patched 0.97 main connects to mu.skpd.dev:44405, which resolves to 127.0.0.1.

CLIENT_PATH="${1:-$HOME/projects/client/mu}"
DESKTOP_SIZE="${2:-1280x1024}"
DESKTOP_NAME="${3:-mu-$$}"

export WINEPREFIX="${WINEPREFIX:-$HOME/projects/client}"
export WINEDEBUG="${WINEDEBUG:--all}"

if [ ! -f "$CLIENT_PATH/main.exe" ]; then
  echo "no main.exe in $CLIENT_PATH"
  exit 1
fi

cd "$CLIENT_PATH" || exit 1
wine explorer /desktop="$DESKTOP_NAME","$DESKTOP_SIZE" main.exe
