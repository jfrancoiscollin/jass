#!/usr/bin/env bash
# id: home-0978-l3-pure-turnover1to1-independent-eval-v1
# Publish only after completed 0977 and after pinning its model/result prefix.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
: "${EXPECTED_CANDIDATE_MODEL_SHA256:?set after completed 0977}"
: "${M2_PREFIX:?set exact completed 0977 result prefix}"
export EXPECTED_CANDIDATE_CORPUS_SHA256="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0978-l3-pure-turnover1to1-independent-eval-v1"
export EXPECTED_CANDIDATE_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export EVAL_VARIANT="TURNOVER"
export OPENING_SEED_OVERRIDE=732051
export EXPECTED_OPENING_SHA256="6ebd2a5ecd79d5e11fc35100c00babb33c98c47843a7b9aadbed7eaef2b6930d"
export D8_M2_PREFIX="r2:jass-data/runs/home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1/20260725T164714Z-012b9c71"
export EXPECTED_M2_D8_JOB="home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1"
export EXPECTED_M2_D8_CODE_SHA="012b9c716dadf2c3df668c23a7dd9d5ece423b8c"
export M2_EVAL_PREFIX="r2:jass-data/runs/home-0970bis-l3-pure-m2-independent-eval-v3/20260725T214024Z-f9ee6be0"
export EXPECTED_M2_EVAL_JOB="home-0970bis-l3-pure-m2-independent-eval-v3"
export D12_EVAL_PREFIX="r2:jass-data/runs/home-0974bis-l3-pure-d12-causal-independent-eval-v1/20260726T054944Z-4d10d40d"
export EXPECTED_D12_EVAL_JOB="home-0974bis-l3-pure-d12-causal-independent-eval-v1"
export EXPECTED_D12_OPENING_SHA256="0f7af083406063719717190cab7f983bee6d0f49b552f42ca4d05d81dce7cf7f"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export CHAMPION_PREFIX="r2:jass-data/runs/home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1/20260725T154956Z-0c1e04a9"
export GAUGE_PREFIX="r2:jass-data/runs/home-0954-l3-pure-m1-abextras-validation-v5/20260724T234944Z-8efd1c45"
export MATRIX_PREFIX="r2:jass-data/runs/home-0962-l3-pure-m1-repaired-engine-matrix-v1/20260725T134639Z-eacd90ab"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 21600s bash jobs/templates/l3-pure-m2-eval-v1.sh
