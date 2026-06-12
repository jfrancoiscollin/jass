#!/usr/bin/env bash
# id: cpx62-9002-filtertest
# description: confirme que le CPX62 (filtre cpx62-) prend SES jobs (pas de course)
set -uo pipefail
echo "host  = $(hostname)"
echo "nproc = $(nproc)"
echo "cpu   = $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | sed 's/^ *//')"
echo "FILTERTEST cpx62 OK (attendu host=ubuntu-32gb-hel1-1, 16 cores Genoa)"
