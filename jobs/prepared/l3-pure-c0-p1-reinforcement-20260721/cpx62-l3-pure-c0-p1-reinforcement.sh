#!/usr/bin/env bash
# id: cpx62-l3-pure-c0-p1-reinforcement
# description: strengthened direct C0 A-G3 vs P1-0842 G4 comparison on independent openings
set -Eeuo pipefail

: "${EXPECTED_CODE_SHA:?set reviewed merged jass SHA}"
export C0_PREFIX="r2:jass-data/runs/ccx33-0790-l3-pure-c0-a-v1/20260718T104245Z-8fc4eacb"
export EXPECTED_C0_JOB="ccx33-0790-l3-pure-c0-a-v1"
export P1_PREFIX="r2:jass-data/runs/cpx62-0842-l3-p1-frozen-v1/20260719T175711Z-337ccbdc"
export EXPECTED_P1_JOB="cpx62-0842-l3-p1-frozen-v1"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1
export NOPEN=768 NSH_GATE=16 PAR_GATE=12 DEPTH=9 MOVETIME=0.3
export JASS_BUILD_JOBS=8
exec bash jobs/templates/l3-pure-c0-p1-reinforcement-v1.sh
