#!/usr/bin/env bash
# id: home-0948-l3-pure-m1-readout-v2
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?}"
export EXPECTED_JOB_ID="home-0948-l3-pure-m1-readout-v2"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export M1_EVAL_PREFIX="r2:jass-data/runs/home-0945-l3-pure-m1-eval-v1/20260724T072619Z-7879cea3"
export NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 30s 900s bash jobs/templates/l3-pure-m1-readout-v1.sh
