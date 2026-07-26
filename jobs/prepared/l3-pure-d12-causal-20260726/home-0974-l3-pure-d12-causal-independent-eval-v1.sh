#!/usr/bin/env bash
# id: home-0974-l3-pure-d12-causal-independent-eval-v1
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
: "${EXPECTED_CANDIDATE_MODEL_SHA256:?set after completed 0973}"
: "${EXPECTED_CANDIDATE_CORPUS_SHA256:?set after completed 0973}"
: "${EXPECTED_OPENING_SHA256:?set after independent-pool preflight}"
: "${M2_PREFIX:?set exact completed 0973 result prefix}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0974-l3-pure-d12-causal-independent-eval-v1"
export EXPECTED_CANDIDATE_JOB="home-0973-l3-pure-d12-causal-fresh2m-train-v1"
export EVAL_VARIANT="D12_CAUSAL"
export OPENING_SEED_OVERRIDE=424243
export D10_TRAIN_PREFIX="r2:jass-data/runs/home-0971-l3-pure-d10-causal-fresh2m-train-v1/20260725T222217Z-abb1aaa0"
export EXPECTED_D10_TRAIN_JOB="home-0971-l3-pure-d10-causal-fresh2m-train-v1"
export D10_EVAL_PREFIX="r2:jass-data/runs/home-0972-l3-pure-d10-causal-independent-eval-v1/20260725T233713Z-5e08d0c5"
export EXPECTED_D10_EVAL_JOB="home-0972-l3-pure-d10-causal-independent-eval-v1"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export CHAMPION_PREFIX="r2:jass-data/runs/home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1/20260725T154956Z-0c1e04a9"
export GAUGE_PREFIX="r2:jass-data/runs/home-0954-l3-pure-m1-abextras-validation-v5/20260724T234944Z-8efd1c45"
export MATRIX_PREFIX="r2:jass-data/runs/home-0962-l3-pure-m1-repaired-engine-matrix-v1/20260725T134639Z-eacd90ab"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 43200s bash jobs/templates/l3-pure-m2-eval-v1.sh
