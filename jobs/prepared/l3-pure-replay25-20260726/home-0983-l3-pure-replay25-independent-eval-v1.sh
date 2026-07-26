#!/usr/bin/env bash
# id: home-0983-l3-pure-replay25-independent-eval-v1
# Exact independent readout of the completed home-0982 REPLAY25 fit.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0983-l3-pure-replay25-independent-eval-v1"
export TRAIN_PREFIX="r2:jass-data/runs/home-0982-l3-pure-replay25-train-v1/20260726T104933Z-87012934"
export EXPECTED_TRAIN_JOB="home-0982-l3-pure-replay25-train-v1"
export EXPECTED_CANDIDATE_MODEL_SHA256="289047ff33c93f518ec8c853fb1c1ac8f7e3a4e52299277b314f0ac712022950"
export EXPECTED_CANDIDATE_CORPUS_SHA256="29c5b99d15da160132c6ede388065844b53503aebf8e44cac6d76f99ffdde56e"
export PREFLIGHT_PREFIX="r2:jass-data/runs/home-0981ter-l3-pure-replay25-preflight-v1/20260726T104130Z-01873c15"
export EXPECTED_PREFLIGHT_JOB="home-0981ter-l3-pure-replay25-preflight-v1"
export TURNOVER_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_TURNOVER_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export TURNOVER_EVAL_PREFIX="r2:jass-data/runs/home-0978-l3-pure-turnover1to1-independent-eval-v1/20260726T075220Z-336bb984"
export EXPECTED_TURNOVER_EVAL_JOB="home-0978-l3-pure-turnover1to1-independent-eval-v1"
export TURNOVER_CONFIRM_PREFIX="r2:jass-data/runs/home-0980-l3-pure-turnover-confirmation-v2/20260726T085020Z-aef92679"
export EXPECTED_TURNOVER_CONFIRM_JOB="home-0980-l3-pure-turnover-confirmation-v2"
export M2_PREFIX="r2:jass-data/runs/home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1/20260725T164714Z-012b9c71"
export EXPECTED_M2_JOB="home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1"
export M2_EVAL_PREFIX="r2:jass-data/runs/home-0970bis-l3-pure-m2-independent-eval-v3/20260725T214024Z-f9ee6be0"
export EXPECTED_M2_EVAL_JOB="home-0970bis-l3-pure-m2-independent-eval-v3"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export CHAMPION_PREFIX="r2:jass-data/runs/home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1/20260725T154956Z-0c1e04a9"
export EXPECTED_CHAMPION_JOB="home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1"
export GAUGE_PREFIX="r2:jass-data/runs/home-0954-l3-pure-m1-abextras-validation-v5/20260724T234944Z-8efd1c45"
export MATRIX_PREFIX="r2:jass-data/runs/home-0962-l3-pure-m1-repaired-engine-matrix-v1/20260725T134639Z-eacd90ab"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 21600s \
  bash jobs/templates/l3-pure-replay25-eval-v1.sh
