#!/usr/bin/env bash
# id: home-0974-l3-pure-d12-causal-independent-eval-v1
set -Eeuo pipefail
export EXPECTED_CODE_SHA="199b02f95496e2b9ba378f953251c02948536f19"
export EXPECTED_CANDIDATE_MODEL_SHA256="2541774af6ecdb832e4cb99723cc95880b7d940c042da32e7d4b270ac2464263"
export EXPECTED_CANDIDATE_CORPUS_SHA256="45cc916a0d398efd48aadb322c7e1be86db49b6d18d7626edf5f3f3d493ea802"
export EXPECTED_OPENING_SHA256="0f7af083406063719717190cab7f983bee6d0f49b552f42ca4d05d81dce7cf7f"
export M2_PREFIX="r2:jass-data/runs/home-0973-l3-pure-d12-causal-fresh2m-train-v1/20260726T001956Z-d4896990"
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
