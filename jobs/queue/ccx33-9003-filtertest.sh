#!/usr/bin/env bash
# id: ccx33-9003-filtertest
# description: test routage SOLO — seul le CCX33 doit le prendre (CPX62 doit l'ignorer)
set -uo pipefail
echo "host=$(hostname) nproc=$(nproc)"
sleep 8
echo "FILTERTEST ccx33-9003 OK (attendu host=ubuntu-16gb-hel1-2, rc=0)"
