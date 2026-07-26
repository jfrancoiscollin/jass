#!/usr/bin/env bash
# id: home-0985-l3-pure-turnover-l2-train-v1
# Fit only the two preregistered L2 arms from the completed 0984bis certificate.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0985-l3-pure-turnover-l2-train-v1"
export PREFLIGHT_PREFIX="r2:jass-data/runs/home-0984bis-l3-pure-turnover-l2-preflight-v2/20260726T122615Z-5ef14ffe"
export EXPECTED_PREFLIGHT_JOB="home-0984bis-l3-pure-turnover-l2-preflight-v2"
export TURNOVER_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_TURNOVER_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 14400s \
  bash jobs/templates/l3-pure-turnover-l2-train-v1.sh
