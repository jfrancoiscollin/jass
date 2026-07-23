#!/usr/bin/env bash
# id: home-0928quater-resume-cap-discovery-v1
# description: resume the partial HOME matrix and inventory every deterministic cap
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed develop SHA containing discovery resume}"
: "${EXPECTED_SCAN_SHA256:?set pinned Scan executable SHA256}"
: "${EXPECTED_SCAN_RUNTIME_SHA256:?set pinned Scan runtime fingerprint}"
export EXPECTED_JOB_ID="home-0928quater-resume-cap-discovery-v1"
export EXECUTION_PROFILE=home
export CAP_DISCOVERY_MODE=1
export MATRIX_RESUME_PREFIX="r2:jass-data/runs/home-0928-l3-conversion-2x2-eval-only-v1/20260723T203236Z-5ce2685f"
export MATRIX_RESUME_EXPECTED_CODE_SHA="5ce2685fcdc68e96c518741a52612abc86525ca6"
export MATRIX_RESUME_EXPECTED_JOB="home-0928-l3-conversion-2x2-eval-only-v1"
export SCAN_BIN="${SCAN_BIN:-/root/jass-scan/scan_linux}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 CONVERSION_2X2_EVAL_GO=1
export NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 60s 5400s \
  bash jobs/templates/l3-conversion-2x2-eval-only-v1.sh
