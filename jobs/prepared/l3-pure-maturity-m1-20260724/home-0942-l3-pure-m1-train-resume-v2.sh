#!/usr/bin/env bash
# id: home-0942-l3-pure-m1-train-resume-v2
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0942-l3-pure-m1-train-resume-v2"
export PARENT_PREFIX="r2:jass-data/runs/ccx33-0790-l3-pure-c0-a-v1/20260718T104245Z-8fc4eacb"
export EXPECTED_PARENT_JOB="ccx33-0790-l3-pure-c0-a-v1"
export RESUME_SOURCE_PREFIX="r2:jass-data/runs/home-0937-l3-pure-m1-train-v1/20260724T030013Z-aefecfb1"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 72000s bash jobs/templates/l3-pure-m1-train-v1.sh
