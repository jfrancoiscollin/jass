#!/usr/bin/env bash
# id: home-0930-l3-pure-m0-triangle
# description: HOME L3-PURE M0 C0-A-G3 / P1-0842-G4 / gen2-mmto benchmark
set -Eeuo pipefail

: "${EXPECTED_CODE_SHA:?set the reviewed merged jass SHA}"
export C0_PREFIX="r2:jass-data/runs/ccx33-0790-l3-pure-c0-a-v1/20260718T104245Z-8fc4eacb"
export EXPECTED_C0_JOB="ccx33-0790-l3-pure-c0-a-v1"
export P1_PREFIX="r2:jass-data/runs/cpx62-0842-l3-p1-frozen-v1/20260719T175711Z-337ccbdc"
export EXPECTED_P1_JOB="cpx62-0842-l3-p1-frozen-v1"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1
export NOPEN=300 NSH_GATE=12 PAR_GATE=2 DEPTH=9 NATIVE_MOVETIME=0.3
export JASS_BUILD_JOBS=4 SHARD_TIMEOUT=10800

exec timeout -k 60s 28800s bash jobs/templates/l3-pure-m0-triangle-v1.sh
