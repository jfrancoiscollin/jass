#!/usr/bin/env bash
# id: home-0967-l3-pure-m2-independent-eval-v1
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0967-l3-pure-m2-independent-eval-v1"
export M2_PREFIX="r2:jass-data/runs/home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1/20260725T164714Z-012b9c71"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export CHAMPION_PREFIX="r2:jass-data/runs/home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1/20260725T154956Z-0c1e04a9"
export GAUGE_PREFIX="r2:jass-data/runs/home-0954-l3-pure-m1-abextras-validation-v5/20260724T234944Z-8efd1c45"
export MATRIX_PREFIX="r2:jass-data/runs/home-0962-l3-pure-m1-repaired-engine-matrix-v1/20260725T134639Z-eacd90ab"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 43200s bash jobs/templates/l3-pure-m2-eval-v1.sh
