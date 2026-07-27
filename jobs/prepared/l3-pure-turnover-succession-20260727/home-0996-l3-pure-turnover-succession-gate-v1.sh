#!/usr/bin/env bash
# id: home-0996-l3-pure-turnover-succession-gate-v1
# Champion-succession gate: TURNOVER vs F2M, Gen2 guard, P3/P4 conversion.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0996-l3-pure-turnover-succession-gate-v1"
export PREFLIGHT_PREFIX="r2:jass-data/runs/home-0995-l3-pure-turnover-succession-preflight-v2/20260727T054246Z-f20e59d0"
export EXPECTED_PREFLIGHT_JOB="home-0995-l3-pure-turnover-succession-preflight-v2"
export EXPECTED_OPENING_SHA256="eb129db1dd304ff3b47cae894f8f8d919d74fdf6b1c8a901e443b23920e4c203"
export DOSE_READOUT_PREFIX="r2:jass-data/runs/home-0993-l3-pure-replay75-readout-v1/20260726T232409Z-64829307"
export EXPECTED_DOSE_READOUT_JOB="home-0993-l3-pure-replay75-readout-v1"
export TURNOVER_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_TURNOVER_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export CHAMPION_PREFIX="r2:jass-data/runs/home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1/20260725T154956Z-0c1e04a9"
export EXPECTED_CHAMPION_JOB="home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1"
export GAUGE_PREFIX="r2:jass-data/runs/home-0954-l3-pure-m1-abextras-validation-v5/20260724T234944Z-8efd1c45"
export MATRIX_PREFIX="r2:jass-data/runs/home-0962-l3-pure-m1-repaired-engine-matrix-v1/20260725T134639Z-eacd90ab"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 28800s \
  bash jobs/templates/l3-pure-turnover-succession-gate-v1.sh
