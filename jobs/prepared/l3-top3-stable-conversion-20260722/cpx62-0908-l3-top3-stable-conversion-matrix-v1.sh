#!/usr/bin/env bash
# id: cpx62-0908-l3-top3-stable-conversion-matrix-v1
# description: corrected d10 Scan/G0/G4 seven-arm causal conversion matrix on a 384-position self-play-reachable stable TOP3 pool
# expected_duration: 12-22 min on measured cpx62 nproc=16; hard cap 35 min
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set merged develop SHA containing the reviewed 0908 pool/matrix tools}"
: "${EXPECTED_SCAN_SHA256:?set sha256 of /root/jass-scan/scan_linux after read-only verification}"
: "${EXPECTED_SCAN_RUNTIME_SHA256:?set canonical fingerprint of Scan binary/ini/data-eval after read-only verification}"
export EXPECTED_JOB_ID="cpx62-0908-l3-top3-stable-conversion-matrix-v1"
export SOURCE_0842_PREFIX="r2:jass-data/runs/cpx62-0842-l3-p1-frozen-v1/20260719T175711Z-337ccbdc"
export EVAL_0890BIS_PREFIX="r2:jass-data/runs/ccx33-0890bis-l3-imbalance2-top3-selfplay-2m-p1/20260722T105552Z-952bea08"
export SCAN_BIN="${SCAN_BIN:-/root/jass-scan/scan_linux}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 CAUSAL_MATRIX_GO=1
export NO_AUTOMATIC_CONTINUATION=1
export DEPTH=10 MAXPLIES=400 POOL_POSITIONS=384
export NSHARDS=16 PAR=16 GAME_TIMEOUT=120 SHARD_TIMEOUT=1200 GLOBAL_TIMEOUT=2100
export JASS_BUILD_JOBS=4 POOL_SEED=271828 BOOTSTRAP=10000 BOOTSTRAP_SEED=271828
export EXPECTED_SEARCH_SHA256="61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1"
exec timeout -k 60s "${GLOBAL_TIMEOUT}s" \
  bash jobs/templates/l3-top3-stable-conversion-matrix-v1.sh
