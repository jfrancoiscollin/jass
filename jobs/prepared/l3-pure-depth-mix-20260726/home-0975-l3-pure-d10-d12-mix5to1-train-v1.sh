#!/usr/bin/env bash
# id: home-0975-l3-pure-d10-d12-mix5to1-train-v1
# Draft only: publish after a valid flat 0974 verdict and exact mix preflight.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
: "${D12_TRAIN_PREFIX:?set exact completed 0973 result prefix}"
: "${EXPECTED_D12_MODEL_SHA256:?set after completed 0973}"
: "${EXPECTED_D12_CORPUS_SHA256:?set after completed 0973}"
: "${EXPECTED_D12_META_SHA256:?set after completed 0973}"
: "${D12_EVAL_PREFIX:?set exact completed flat 0974 result prefix}"
: "${EXPECTED_MIX_CORPUS_SHA256:?set after deterministic mix preflight}"
: "${EXPECTED_MIX_META_SHA256:?set after deterministic mix preflight}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0975-l3-pure-d10-d12-mix5to1-train-v1"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export CHAMPION_PREFIX="r2:jass-data/runs/home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1/20260725T154956Z-0c1e04a9"
export EXPECTED_CHAMPION_JOB="home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1"
export EXPECTED_PARENT_MODEL_SHA256="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
export D10_TRAIN_PREFIX="r2:jass-data/runs/home-0971-l3-pure-d10-causal-fresh2m-train-v1/20260725T222217Z-abb1aaa0"
export EXPECTED_D10_TRAIN_JOB="home-0971-l3-pure-d10-causal-fresh2m-train-v1"
export EXPECTED_D10_MODEL_SHA256="18930613234b4a1a6a933393151a05dd68f71d1af749f058f37c5778bd77960f"
export EXPECTED_D10_CORPUS_SHA256="3351cb8aebd33c417de179d72f4483193ae67f05f723c520190ed2a118fc9297"
export EXPECTED_D10_META_SHA256="f14bab1eca1988fa9fae9bd69f718d434d5e808cfb68b11e12a47fa211aa65a6"
export EXPECTED_D12_TRAIN_JOB="home-0973-l3-pure-d12-causal-fresh2m-train-v1"
export EXPECTED_D12_EVAL_JOB="home-0974-l3-pure-d12-causal-independent-eval-v1"
export EXPERIMENT_VARIANT="D10_D12_MIX_5_1"
export PLAY_DEPTH_OVERRIDE=0
export DEPTH_MIX_APPROVED=1
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 43200s bash jobs/templates/l3-pure-m2-train-v1.sh
