#!/usr/bin/env bash
# id: home-0988-l3-pure-turnover-l2-confirm-preflight-v1
# Certify a fresh independent pool for the L2_1E5 confirmation. No fit, no games.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0988-l3-pure-turnover-l2-confirm-preflight-v1"
export SCREEN_EVAL_PREFIX="r2:jass-data/runs/home-0987-l3-pure-turnover-l2-independent-eval-v2/20260726T164809Z-fa8cd0b1"
export EXPECTED_SCREEN_EVAL_JOB="home-0987-l3-pure-turnover-l2-independent-eval-v2"
export SCREEN_PREFLIGHT_PREFIX="r2:jass-data/runs/home-0984bis-l3-pure-turnover-l2-preflight-v2/20260726T122615Z-5ef14ffe"
export EXPECTED_SCREEN_PREFLIGHT_JOB="home-0984bis-l3-pure-turnover-l2-preflight-v2"
export TRAIN_PREFIX="r2:jass-data/runs/home-0985-l3-pure-turnover-l2-train-v1/20260726T123823Z-ad067a4b"
export EXPECTED_TRAIN_JOB="home-0985-l3-pure-turnover-l2-train-v1"
export TURNOVER_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_TURNOVER_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export TURNOVER_CONFIRM_PREFIX="r2:jass-data/runs/home-0980-l3-pure-turnover-confirmation-v2/20260726T085020Z-aef92679"
export EXPECTED_TURNOVER_CONFIRM_JOB="home-0980-l3-pure-turnover-confirmation-v2"
export REPLAY25_PREFLIGHT_PREFIX="r2:jass-data/runs/home-0981ter-l3-pure-replay25-preflight-v1/20260726T104130Z-01873c15"
export EXPECTED_REPLAY25_PREFLIGHT_JOB="home-0981ter-l3-pure-replay25-preflight-v1"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 5400s \
  bash jobs/templates/l3-pure-turnover-l2-confirm-preflight-v1.sh
