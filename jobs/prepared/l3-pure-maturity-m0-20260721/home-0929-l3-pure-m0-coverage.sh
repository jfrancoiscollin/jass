#!/usr/bin/env bash
# id: home-0929-l3-pure-m0-coverage
# description: HOME L3-PURE M0 bucket-coverage audit for C0 A and P1-0842
set -Eeuo pipefail

: "${EXPECTED_CODE_SHA:?set the reviewed merged jass SHA}"
export C0_PREFIX="r2:jass-data/runs/ccx33-0790-l3-pure-c0-a-v1/20260718T104245Z-8fc4eacb"
export EXPECTED_C0_JOB="ccx33-0790-l3-pure-c0-a-v1"
export P1_PREFIX="r2:jass-data/runs/cpx62-0842-l3-p1-frozen-v1/20260719T175711Z-337ccbdc"
export EXPECTED_P1_JOB="cpx62-0842-l3-p1-frozen-v1"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1

exec timeout -k 60s 5400s bash jobs/templates/l3-pure-m0-coverage-v1.sh
