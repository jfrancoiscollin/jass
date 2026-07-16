#!/usr/bin/env bash
# id: ccx33-0741-t1bis-adj-g1-v3
# Relance de T1-bis sur ccx33 après correction strictement technique du launcher.
# Paramètres scientifiques inchangés par rapport à cpx62-0729.
# Seuls les plafonds de parallélisme/cache sont adaptés au serveur 16 Go.
set -euo pipefail

EXPECTED_HOST="ubuntu-16gb-hel1-2"
[ "$(hostname)" = "$EXPECTED_HOST" ] || { echo "wrong host" >&2; exit 2; }

NCPU="$(nproc)"
cap(){ local value="$1" max="$2"; [ "$value" -lt "$max" ] && echo "$value" || echo "$max"; }

export JOB_ID=ccx33-0741-t1bis-adj-g1-v3
export TOUR=T1-bis
export PARENT_PJTW_GZ=jobs/results/cpx62-0707-b4-bootstrap-gate/artefacts/bootstrap-build-matched.pjtw.gz
export FIXED_PJTW_GZ=jobs/results/cpx62-0707-b4-bootstrap-gate/artefacts/bootstrap-build-matched.pjtw.gz
export GYM_MIN_POS=150
export MIN_PROTECTED_TIP_RATE=0.0
export ALLOW_MTC_SKIP=1

# Technical resource caps only; games, depths, quotas, anchor and gates are unchanged.
export NSH_GEN="$(cap "$NCPU" 8)"
export NSH_RELABEL="$(cap "$NCPU" 8)"
export NSH_CONV="$(cap "$NCPU" 4)"
export NSH_GATE="$(cap "$NCPU" 4)"
export CACHE_MB_RELABEL=384
export CACHE_MB_CONV=192

exec bash jobs/templates/t1bis-adj-g1-v3-launch.sh
