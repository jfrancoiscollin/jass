#!/usr/bin/env bash
# id: home-0986-l3-pure-turnover-l2-independent-eval-v1
# Staged independent readout of the completed home-0985 L2 screen fits.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0986-l3-pure-turnover-l2-independent-eval-v1"
export TRAIN_PREFIX="r2:jass-data/runs/home-0985-l3-pure-turnover-l2-train-v1/20260726T123823Z-ad067a4b"
export EXPECTED_TRAIN_JOB="home-0985-l3-pure-turnover-l2-train-v1"
export EXPECTED_L2_1E5_MODEL_SHA256="27cf9bedf20d00bbcc106a52ad183990f8df131362c4590fc319cc708464ff49"
export EXPECTED_L2_1E4_MODEL_SHA256="0b710b80ab11fbcdcf4904adaeeb48166f0449c8c0c0fbf063a12c182372884b"
export PREFLIGHT_PREFIX="r2:jass-data/runs/home-0984bis-l3-pure-turnover-l2-preflight-v2/20260726T122615Z-5ef14ffe"
export EXPECTED_PREFLIGHT_JOB="home-0984bis-l3-pure-turnover-l2-preflight-v2"
export EXPECTED_OPENING_SHA256="e7b89a5e3feade8919c8a498f424084deb0a2128c1712c9ca0a9547cf22b6df2"
export TURNOVER_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_TURNOVER_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export TURNOVER_EVAL_PREFIX="r2:jass-data/runs/home-0978-l3-pure-turnover1to1-independent-eval-v1/20260726T075220Z-336bb984"
export EXPECTED_TURNOVER_EVAL_JOB="home-0978-l3-pure-turnover1to1-independent-eval-v1"
export TURNOVER_CONFIRM_PREFIX="r2:jass-data/runs/home-0980-l3-pure-turnover-confirmation-v2/20260726T085020Z-aef92679"
export EXPECTED_TURNOVER_CONFIRM_JOB="home-0980-l3-pure-turnover-confirmation-v2"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export CHAMPION_PREFIX="r2:jass-data/runs/home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1/20260725T154956Z-0c1e04a9"
export EXPECTED_CHAMPION_JOB="home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1"
export GAUGE_PREFIX="r2:jass-data/runs/home-0954-l3-pure-m1-abextras-validation-v5/20260724T234944Z-8efd1c45"
export MATRIX_PREFIX="r2:jass-data/runs/home-0962-l3-pure-m1-repaired-engine-matrix-v1/20260725T134639Z-eacd90ab"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 21600s \
  bash jobs/templates/l3-pure-turnover-l2-eval-v1.sh
