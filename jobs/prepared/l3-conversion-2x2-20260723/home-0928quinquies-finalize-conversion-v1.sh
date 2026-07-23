#!/usr/bin/env bash
# id: home-0928quinquies-finalize-conversion-v1
# description: reuse the complete discovered matrix, run balanced guard, report 2x2
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed develop SHA containing three-cap finalizer}"
: "${EXPECTED_SCAN_SHA256:?set pinned Scan executable SHA256}"
: "${EXPECTED_SCAN_RUNTIME_SHA256:?set pinned Scan runtime fingerprint}"
export EXPECTED_JOB_ID="home-0928quinquies-finalize-conversion-v1"
export EXECUTION_PROFILE=home
export CAP_DISCOVERY_MODE=0
export MATRIX_RESUME_PREFIX="r2:jass-data/runs/home-0928quater-resume-cap-discovery-v1/20260723T210422Z-c8e286d5"
export MATRIX_RESUME_EXPECTED_CODE_SHA="c8e286d5840149ed73a181cd9506ca0a3f494e74"
export MATRIX_RESUME_EXPECTED_JOB="home-0928quater-resume-cap-discovery-v1"
export MATRIX_RESUME_EXPECTED_STATE=completed
export SCAN_BIN="${SCAN_BIN:-/root/jass-scan/scan_linux}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 CONVERSION_2X2_EVAL_GO=1
export NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 60s 5400s \
  bash jobs/templates/l3-conversion-2x2-eval-only-v1.sh
