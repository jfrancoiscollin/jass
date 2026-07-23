#!/usr/bin/env bash
# id: cpx62-0922quater-l3-conversion-2x2-eval-only-v1
# description: clean evaluation-only recovery with 8cf emit and one pinned ply-cap adjudication
# expected_duration: 12-18 min on measured cpx62 nproc=16; hard cap 30 min
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed develop SHA containing 0922quater}"
: "${EXPECTED_SCAN_SHA256:?set pinned Scan executable SHA256}"
: "${EXPECTED_SCAN_RUNTIME_SHA256:?set pinned Scan runtime fingerprint}"
export EXPECTED_JOB_ID="cpx62-0922quater-l3-conversion-2x2-eval-only-v1"
export SCAN_BIN="${SCAN_BIN:-/root/jass-scan/scan_linux}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 CONVERSION_2X2_EVAL_GO=1
export NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 60s 1800s \
  bash jobs/templates/l3-conversion-2x2-eval-only-v1.sh
