#!/usr/bin/env bash
# Fidelity oracle for the add_sacs port : clone + build Scan with a dump program
# that prints Scan's REAL add_sacs output (FMJD notation) per position, so the jass
# port can be validated bit-for-bit against it. Input on stdin = Scan hub pos strings
# (side char + 50 squares e/w/W/b/B). Output : "SACS <n> <from-to>...".
set -euo pipefail
SCAN=/tmp/scan-src
[ -d "$SCAN" ] || git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN"
cp "$(dirname "$0")/dump_sacs.cpp" "$SCAN/src/dump_sacs.cpp"
( cd "$SCAN/src" && make >/dev/null 2>&1 )
g++ -std=c++14 -fno-rtti -O2 -mpopcnt -pthread -I"$SCAN/src" "$SCAN/src/dump_sacs.cpp" \
   $(ls "$SCAN"/src/*.o | grep -v '/main.o') -o /tmp/scan_dump_sacs -pthread
echo "/tmp/scan_dump_sacs ready" >&2
exec /tmp/scan_dump_sacs
