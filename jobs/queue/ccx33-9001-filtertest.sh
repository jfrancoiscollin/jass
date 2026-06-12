#!/usr/bin/env bash
# id: ccx33-9001-filtertest
# description: confirme que le CCX33 (filtre ccx33-) prend SES jobs (pas de course)
set -uo pipefail
echo "host  = $(hostname)"
echo "nproc = $(nproc)"
echo "FILTERTEST ccx33 OK (attendu host=ubuntu-16gb-hel1-2)"
