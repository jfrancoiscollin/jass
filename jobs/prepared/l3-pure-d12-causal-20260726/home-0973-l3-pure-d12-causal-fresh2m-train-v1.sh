#!/usr/bin/env bash
# id: home-0973-l3-pure-d12-causal-fresh2m-train-v1
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0973-l3-pure-d12-causal-fresh2m-train-v1"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export CHAMPION_PREFIX="r2:jass-data/runs/home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1/20260725T154956Z-0c1e04a9"
export EXPECTED_CHAMPION_JOB="home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1"
export EXPECTED_PARENT_MODEL_SHA256="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
export D10_EVAL_PREFIX="r2:jass-data/runs/home-0972-l3-pure-d10-causal-independent-eval-v1/20260725T233713Z-5e08d0c5"
export EXPECTED_D10_EVAL_JOB="home-0972-l3-pure-d10-causal-independent-eval-v1"
export EXPECTED_D10_MODEL_SHA256="18930613234b4a1a6a933393151a05dd68f71d1af749f058f37c5778bd77960f"
export EXPERIMENT_VARIANT="D12_CAUSAL_FRESH2M"
export PLAY_DEPTH_OVERRIDE=12
export D12_CAUSAL_APPROVED=1
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 43200s bash jobs/templates/l3-pure-m2-train-v1.sh
