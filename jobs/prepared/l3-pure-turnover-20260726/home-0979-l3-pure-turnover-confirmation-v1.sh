#!/usr/bin/env bash
# id: home-0979-l3-pure-turnover-confirmation-v1
# Independent confirmation only: same immutable model, fresh disjoint match pool.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0979-l3-pure-turnover-confirmation-v1"
export TURNOVER_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_TURNOVER_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export TURNOVER_EVAL_PREFIX="r2:jass-data/runs/home-0978-l3-pure-turnover1to1-independent-eval-v1/20260726T075220Z-336bb984"
export EXPECTED_TURNOVER_EVAL_JOB="home-0978-l3-pure-turnover1to1-independent-eval-v1"
export M2_PREFIX="r2:jass-data/runs/home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1/20260725T164714Z-012b9c71"
export EXPECTED_M2_JOB="home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1"
export F2M_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_F2M_JOB="home-0944-l3-pure-m1-train-resume-v3"
export EXPECTED_OPENING_SHA256="c34f25f0dddf8865e90a4f149bcca0f4b40ccb32d0b5e1aff5fde6a604e92251"
export EXPECTED_CANDIDATE_OPENING_SHA256="c440f5a6818aee4b226ceb968fa2753b2d2d71b6257d9a335c1f2e96efb5a51a"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 21600s \
  bash jobs/templates/l3-pure-turnover-confirmation-v1.sh
