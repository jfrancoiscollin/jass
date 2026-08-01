#!/usr/bin/env bash
# id: cpx62-1142-l3-scan-blind-spot-atlas-exact-v1
# First pass: Scan-judged atlas of champion EXACT under the 8cf build.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set the reviewed develop SHA shared by both atlas passes}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="cpx62-1142-l3-scan-blind-spot-atlas-exact-v1"
export SCAN_BIN="/root/jass-scan/scan_linux"
export EXPECTED_SCAN_SHA256="a634cbb44c9528eab277cdf6cdf8d29d506318ce5fba3f9bc69c2025b5941864"
export EXPECTED_SCAN_EVAL_SHA256="0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba"
export BUDGET_S=1500 PLAY_DEPTH=8 JUDGE_DEPTH=10 MAX_PLIES=160
export GAMES_CAP=100000 MIN_POSITIONS=200 SHARDS=16
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 3600s \
  bash jobs/templates/l3-scan-blind-spot-atlas-v1.sh --variant exact
