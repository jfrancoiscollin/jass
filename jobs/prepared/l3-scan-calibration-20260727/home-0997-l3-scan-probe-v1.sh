#!/usr/bin/env bash
# id: home-0997-l3-scan-probe-v1
# Measure real Scan-match throughput per regime on HOME before the full matrix.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0997-l3-scan-probe-v1"
export SCAN_BIN="${SCAN_BIN:-/root/jass-scan/scan_linux}"
export EXPECTED_SCAN_SHA256="a634cbb44c9528eab277cdf6cdf8d29d506318ce5fba3f9bc69c2025b5941864"
export CHAMPION_TRAIN_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
export EXPECTED_CHAMPION_TRAIN_JOB="home-0977-l3-pure-turnover1to1-train-v1"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 5400s \
  bash jobs/templates/l3-scan-probe-v1.sh
