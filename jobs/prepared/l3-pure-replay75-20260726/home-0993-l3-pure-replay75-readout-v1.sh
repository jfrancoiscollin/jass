#!/usr/bin/env bash
# id: home-0993-l3-pure-replay75-readout-v1
# Powered dose readout, views summed: n=5000 per matchup, ~1.4 pp resolution.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0993-l3-pure-replay75-readout-v1"
export PREFLIGHT_PREFIX="r2:jass-data/runs/home-0991-l3-pure-replay75-preflight-v2/20260726T225845Z-38456455"
export EXPECTED_PREFLIGHT_JOB="home-0991-l3-pure-replay75-preflight-v2"
export EXPECTED_OPENING_SHA256="17544078f6e32ec714302dc71aa68c97b34f572fd3205a376b2c868a40095148"
export TRAIN_PREFIX="r2:jass-data/runs/home-0992-l3-pure-replay75-train-v1/20260726T230907Z-25cd278c"
export EXPECTED_TRAIN_JOB="home-0992-l3-pure-replay75-train-v1"
export EXPECTED_CANDIDATE_MODEL_SHA256="9b9b26d59504546ed14ee7daa722cc4c1ec44373c9e3d074a6d6cd3cd1116e32"
export TURNOVER_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_TURNOVER_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 21600s \
  bash jobs/templates/l3-pure-replay75-readout-v1.sh
