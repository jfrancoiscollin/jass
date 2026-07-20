#!/usr/bin/env bash
# id: cpx62-l3-imbalance2-a64-b64-difficulty-reference
# description: exact EGDB WDL for 1v3/2v4 and Scan d10 reference for 3v5..18v20 on common A64/B64 pools
# expected_duration: pending calibration; 2,048 Scan high-material games plus exact TB relabel
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set merged jass SHA}"
: "${V2_P1_PREFIX:?set immutable completed role-aware V2 P1 prefix}"
: "${EXPECTED_V2_JOB_ID:?set expected role-aware V2 P1 job id}"
: "${SCAN_BIN:?set reviewed Scan binary path}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 REFERENCE_GO=1
export DEPTH=10 MAXPLIES=400 NSHARDS=8 PAR=8 SHARD_TIMEOUT=21600
export PLATEAU_PER_STRATUM=64 PLATEAU_SEED=161803 EXACT_MAX_PIECES=6
export JASS_BUILD_JOBS=8
exec bash jobs/templates/l3-imbalance2-difficulty-reference-v1.sh
