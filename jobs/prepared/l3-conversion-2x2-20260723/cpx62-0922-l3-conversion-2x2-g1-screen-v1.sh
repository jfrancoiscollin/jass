#!/usr/bin/env bash
# id: cpx62-0922-l3-conversion-2x2-g1-screen-v1
# description: matched G1 2x2 standard/TOP3 starts x role-aware V2 off/on
# expected_duration: 30-45 min on measured cpx62 nproc=16; hard cap 60 min
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed develop SHA containing 0922}"
: "${EXPECTED_SCAN_SHA256:?set pinned Scan executable SHA256}"
: "${EXPECTED_SCAN_RUNTIME_SHA256:?set pinned Scan runtime fingerprint}"
export EXPECTED_JOB_ID="cpx62-0922-l3-conversion-2x2-g1-screen-v1"
export SCAN_BIN="${SCAN_BIN:-/root/jass-scan/scan_linux}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 CONVERSION_2X2_GO=1
export NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 60s 3600s \
  bash jobs/templates/l3-conversion-2x2-g1-screen-v1.sh
