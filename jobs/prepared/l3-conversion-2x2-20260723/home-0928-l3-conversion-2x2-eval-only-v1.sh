#!/usr/bin/env bash
# id: home-0928-l3-conversion-2x2-eval-only-v1
# description: HOME evaluation-only recovery of the matched G1 conversion 2x2
# expected_duration: 35-70 min on measured HOME nproc=16; hard cap 120 min
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed develop SHA containing HOME evaluation profile}"
: "${EXPECTED_SCAN_SHA256:?set pinned Scan executable SHA256}"
: "${EXPECTED_SCAN_RUNTIME_SHA256:?set pinned Scan runtime fingerprint}"
export EXPECTED_JOB_ID="home-0928-l3-conversion-2x2-eval-only-v1"
export EXECUTION_PROFILE=home
export SCAN_BIN="${SCAN_BIN:-/root/jass-scan/scan_linux}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 CONVERSION_2X2_EVAL_GO=1
export NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 60s 7200s \
  bash jobs/templates/l3-conversion-2x2-eval-only-v1.sh
