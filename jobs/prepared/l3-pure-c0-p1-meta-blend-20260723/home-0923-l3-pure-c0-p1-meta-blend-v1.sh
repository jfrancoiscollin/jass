#!/usr/bin/env bash
# id: home-0923-l3-pure-c0-p1-meta-blend-v1
# description: home runner replication of the convex C0/P1 blend screen and independent confirmation
# expected_duration: 55-70 min on home nproc=16; hard cap 90 min
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed develop SHA in jass-control}"
export C0_PREFIX="r2:jass-data/runs/ccx33-0790-l3-pure-c0-a-v1/20260718T104245Z-8fc4eacb"
export EXPECTED_C0_JOB="ccx33-0790-l3-pure-c0-a-v1"
export P1_PREFIX="r2:jass-data/runs/cpx62-0842-l3-p1-frozen-v1/20260719T175711Z-337ccbdc"
export EXPECTED_P1_JOB="cpx62-0842-l3-p1-frozen-v1"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1
export SCREEN_NOPEN=128 CONFIRM_NOPEN=256 SCREEN_DEPTH=8 CONFIRM_DEPTH=9 MOVETIME=0.3
export PAR_GATE=12 GAME_TIMEOUT=100 JASS_BUILD_JOBS=4
export SHARD_TIMEOUT=1800 GATE_TIMEOUT=2700
exec timeout --signal=TERM --kill-after=30 5400 \
  bash jobs/templates/l3-pure-c0-p1-meta-blend-v1.sh
