#!/usr/bin/env bash
# id: cpx62-0001-verify
# description: Verifie que le runner CPX62 tourne et pousse ses resultats
# (test de la deploy key end-to-end). Trivial, ~secondes.
set -uo pipefail
echo "=== CPX62 verify ==="
echo "host  : $(hostname)"
echo "nproc : $(nproc)"
echo "mem   : $(free -h 2>/dev/null | awk '/^Mem:/{print $2}')"
echo "cpu   : $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | sed 's/^ *//')"
echo "date  : $(date -u)"
echo "VERIFY OK"
