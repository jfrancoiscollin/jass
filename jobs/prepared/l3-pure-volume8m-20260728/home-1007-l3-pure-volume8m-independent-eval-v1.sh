#!/usr/bin/env bash
# id: home-1007-l3-pure-volume8m-independent-eval-v1
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-1007-l3-pure-volume8m-independent-eval-v1"
export TRAIN_PREFIX="r2:jass-data/runs/home-1006-l3-pure-volume8m-train-v2/20260728T024741Z-a5a7301f"
export EXPECTED_TRAIN_JOB="home-1006-l3-pure-volume8m-train-v2"
export EXPECTED_TRAIN_CODE_SHA="a5a7301f9dddcffa03251edde74a96c6f6018e6a"
export PREFLIGHT_PREFIX="r2:jass-data/runs/home-1004-l3-pure-volume8m-preflight-v2/20260727T211936Z-90d3aad1"
export EXPECTED_PREFLIGHT_JOB="home-1004-l3-pure-volume8m-preflight-v2"
export EXPECTED_PREFLIGHT_CODE_SHA="90d3aad1ae4f9bcfccab00ef6b1492e7644bd7b4"
export TURNOVER_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_TURNOVER_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export TURNOVER_EVAL_PREFIX="r2:jass-data/runs/home-0978-l3-pure-turnover1to1-independent-eval-v1/20260726T075220Z-336bb984"
export EXPECTED_TURNOVER_EVAL_JOB="home-0978-l3-pure-turnover1to1-independent-eval-v1"
export M2_PREFIX="r2:jass-data/runs/home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1/20260725T164714Z-012b9c71"
export EXPECTED_M2_JOB="home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export GAUGE_PREFIX="r2:jass-data/runs/home-0954-l3-pure-m1-abextras-validation-v5/20260724T234944Z-8efd1c45"
export MATRIX_PREFIX="r2:jass-data/runs/home-0962-l3-pure-m1-repaired-engine-matrix-v1/20260725T134639Z-eacd90ab"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 28800s bash jobs/templates/l3-pure-volume8m-eval-v1.sh
