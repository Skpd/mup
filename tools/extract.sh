#!/bin/bash
# Extracts the packet handling of a 0.97 client (main.exe) with Ghidra headless.
#
# usage: tools/extract.sh <main.exe> <output dir> [head switch jmp] [receive loop]
#   head switch jmp / receive loop: addresses in the receive dispatcher, defaults are for
#   the 0.97b Chs main (0.97.04) in ~/projects/client/mu, see docs/protocol-097.md
#
# GHIDRA - Ghidra install dir, JAVA_HOME - jdk 21
#
# output:
#   receive.txt         server -> client head / sub codes and the functions handling them
#   receive_fields.txt  packet offsets each handler reads
#   send.txt            client -> server packets found in the senders (heuristic, see extract_senders.py)
#   dispatcher.c, handlers.c, senders.c   decompiled code

set -e

GHIDRA="${GHIDRA:-/opt/ghidra_12.1.4_PUBLIC}"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"

EXE="$(realpath "$1")"
OUT="$(realpath -m "$2")"
SWITCH_JMP="${3:-0x4213f4}"
RECEIVE_LOOP="${4:-0x420c93}"
TOOLS="$(cd "$(dirname "$0")" && pwd)"
HEADLESS="$GHIDRA/support/analyzeHeadless"
PROGRAM="$(basename "$EXE")"

# helpers called from the dispatcher that aren't packet handlers: object lookup, chat log, sounds, etc.
NOT_HANDLERS='^(00403390|004035b0|004037c0|00403940|004043d0|004239b0|0045e860|00423fe0|004e7c6c|0040e1d0|004234a0|00408f70)$'

mkdir -p "$OUT/project"

echo "importing and analyzing $EXE"
"$HEADLESS" "$OUT/project" mu -import "$EXE" -overwrite > "$OUT/import.log" 2>&1

echo "mapping the receive dispatcher, dumping senders"
"$HEADLESS" "$OUT/project" mu -process "$PROGRAM" -noanalysis -readOnly -scriptPath "$TOOLS/ghidra" \
  -postScript ReceiveDispatch.java "$OUT/receive.txt" "$SWITCH_JMP" "$RECEIVE_LOOP" \
  -postScript DumpDecompiled.java "$OUT/dispatcher.c" "$SWITCH_JMP" \
  -postScript DumpSenders.java "$OUT/senders.c" > "$OUT/scripts.log" 2>&1

grep -oE 'FUN_[0-9a-f]+@[0-9a-f]+' "$OUT/receive.txt" | cut -d@ -f2 | sort -u | grep -vE "$NOT_HANDLERS" > "$OUT/handlers.txt"

echo "decompiling $(wc -l < "$OUT/handlers.txt") handlers"
"$HEADLESS" "$OUT/project" mu -process "$PROGRAM" -noanalysis -readOnly -scriptPath "$TOOLS/ghidra" \
  -postScript DumpDecompiled.java "$OUT/handlers.c" "@$OUT/handlers.txt" >> "$OUT/scripts.log" 2>&1

python3 "$TOOLS/extract_handlers.py" "$OUT/receive.txt" "$OUT/handlers.c" > "$OUT/receive_fields.txt"
python3 "$TOOLS/extract_senders.py" "$OUT/senders.c" > "$OUT/send.txt"

echo "done: $OUT"
