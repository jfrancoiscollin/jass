#!/usr/bin/env bash
# id: home-0984-l3-pure-turnover-l2-preflight-v1
# Exact preflight authorized only by the completed REPLAY25 dose-closure result.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0984-l3-pure-turnover-l2-preflight-v1"
export REPLAY25_EVAL_PREFIX="r2:jass-data/runs/home-0983-l3-pure-replay25-independent-eval-v1/20260726T112309Z-42b9af7e"
export EXPECTED_REPLAY25_EVAL_JOB="home-0983-l3-pure-replay25-independent-eval-v1"
export REPLAY25_PREFLIGHT_PREFIX="r2:jass-data/runs/home-0981ter-l3-pure-replay25-preflight-v1/20260726T104130Z-01873c15"
export EXPECTED_REPLAY25_PREFLIGHT_JOB="home-0981ter-l3-pure-replay25-preflight-v1"
export TURNOVER_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_TURNOVER_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export TURNOVER_CONFIRM_PREFIX="r2:jass-data/runs/home-0980-l3-pure-turnover-confirmation-v2/20260726T085020Z-aef92679"
export EXPECTED_TURNOVER_CONFIRM_JOB="home-0980-l3-pure-turnover-confirmation-v2"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 14400s \
  bash jobs/templates/l3-pure-turnover-l2-preflight-v1.sh
