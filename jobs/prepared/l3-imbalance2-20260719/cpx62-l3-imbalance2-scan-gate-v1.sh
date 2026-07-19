#!/usr/bin/env bash
# id: cpx62-l3-imbalance2-scan-gate-v1
# description: two independent fixed-pool WDL equivalence gates vs Scan
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?}"; : "${SCAN_BIN:?}"
: "${CANDIDATE_MODEL_URI:?}"; : "${CANDIDATE_MODEL_SHA256:?}"
: "${DEFENDER_MODEL_URI:?}"; : "${DEFENDER_MODEL_SHA256:?}"
: "${SEARCH_PARAMS:?copy the resolved 63-key Q00 fingerprint from the phase manifest}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1
export DEPTH=8 NSHARDS=8 PAR=8 MAXPLIES=260 BENCH_PER_STRATUM=24 BASE_SEED=271828
export GLOBAL_POINT_MARGIN=0.03 GLOBAL_CI_MARGIN=0.05 STRATUM_POINT_MARGIN=0.10 MIN_PER_STRATUM=20
exec bash jobs/templates/l3-imbalance2-scan-gate-v1.sh
