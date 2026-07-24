#!/usr/bin/env bash
# id: home-0945-l3-pure-m1-eval-v1
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?}"
export EXPECTED_JOB_ID="home-0945-l3-pure-m1-eval-v1"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export C0_PREFIX="r2:jass-data/runs/ccx33-0790-l3-pure-c0-a-v1/20260718T104245Z-8fc4eacb"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 36000s bash jobs/templates/l3-pure-m1-eval-v1.sh
