#!/usr/bin/env bash
# id: cpx62-0921-l3-pure-top3-stable-conversion-matrix-v1
# description: L3-PURE G0/G4 mirror of the seven-arm d10 stable TOP3 causal matrix
# expected_duration: 7-12 min on measured cpx62 nproc=16; hard cap 20 min
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed develop SHA containing the 0921 pure mirror}"
: "${EXPECTED_SCAN_SHA256:?set pinned Scan executable SHA256}"
: "${EXPECTED_SCAN_RUNTIME_SHA256:?set pinned Scan runtime fingerprint}"
export EXPECTED_JOB_ID="cpx62-0921-l3-pure-top3-stable-conversion-matrix-v1"
export SOURCE_0842_PREFIX="r2:jass-data/runs/cpx62-0842-l3-p1-frozen-v1/20260719T175711Z-337ccbdc"
export EVAL_SOURCE_MODE="pure-0842"
export SCAN_BIN="${SCAN_BIN:-/root/jass-scan/scan_linux}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 CAUSAL_MATRIX_GO=1
export NO_AUTOMATIC_CONTINUATION=1
export DEPTH=10 MAXPLIES=400 POOL_POSITIONS=384
export NSHARDS=16 PAR=16 GAME_TIMEOUT=120 SHARD_TIMEOUT=900 GLOBAL_TIMEOUT=1200
export JASS_BUILD_JOBS=4 POOL_SEED=271828 BOOTSTRAP=10000 BOOTSTRAP_SEED=271828
export EXPECTED_SEARCH_SHA256="61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1"
exec timeout -k 60s "${GLOBAL_TIMEOUT}s" \
  bash jobs/templates/l3-top3-stable-conversion-matrix-v1.sh
