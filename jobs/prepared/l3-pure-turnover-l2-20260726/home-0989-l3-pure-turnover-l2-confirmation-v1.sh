#!/usr/bin/env bash
# id: home-0989-l3-pure-turnover-l2-confirmation-v1
# Independent high-N confirmation of L2_1E5 on the pool certified by home-0988.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0989-l3-pure-turnover-l2-confirmation-v1"
export PREFLIGHT_PREFIX="r2:jass-data/runs/home-0988-l3-pure-turnover-l2-confirm-preflight-v1/20260726T195948Z-8ca7f37a"
export EXPECTED_PREFLIGHT_JOB="home-0988-l3-pure-turnover-l2-confirm-preflight-v1"
export EXPECTED_OPENING_SHA256="71dc575eb6930718b1f2762c4adcd1db479b2c41abbbf00b417772e7d6f53043"
export EXPECTED_CANDIDATE_OPENING_SHA256="b3aefba94ad60a913554859f3ff07b46e5b1a39d157a7fb68652d41ef6994e12"
export SCREEN_EVAL_PREFIX="r2:jass-data/runs/home-0987-l3-pure-turnover-l2-independent-eval-v2/20260726T164809Z-fa8cd0b1"
export EXPECTED_SCREEN_EVAL_JOB="home-0987-l3-pure-turnover-l2-independent-eval-v2"
export TRAIN_PREFIX="r2:jass-data/runs/home-0985-l3-pure-turnover-l2-train-v1/20260726T123823Z-ad067a4b"
export EXPECTED_TRAIN_JOB="home-0985-l3-pure-turnover-l2-train-v1"
export TURNOVER_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_TURNOVER_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 21600s \
  bash jobs/templates/l3-pure-turnover-l2-confirmation-v1.sh
