#!/usr/bin/env bash
# id: ccx33-l3-imbalance2-p2-consolidate
# description: alternate-box consolidation of existing G4-G8 A64/B64 reports; no games replayed
# expected_duration: less than 10 minutes; same scientific contract as cpx62
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set merged jass SHA}"
: "${P1_RAW_PREFIX:?set failed raw P1 comparison prefix (0853)}"
: "${P2_RAW_PREFIX:?set failed raw P2 plateau prefix (0864)}"
: "${REFERENCE_PREFIX:?set completed difficulty-reference prefix (0862)}"
: "${EXPECTED_P1_JOB_ID:?set expected P1 raw job id}"
: "${EXPECTED_P2_JOB_ID:?set expected P2 raw job id}"
: "${EXPECTED_REFERENCE_JOB_ID:?set expected reference job id}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 CONSOLIDATION_GO=1
export BOOTSTRAP=10000 SEED=161806 EXPECTED_PER_STRATUM=64
export MAX_EXCLUDED_POSITIONS=2 MAX_EXCLUDED_FRACTION=0.001
export MIN_EFFECT=0.02 MIN_NONWORSE_STRATA=12 MAX_STRATUM_REGRESSION=0.10
exec bash jobs/templates/l3-imbalance2-p2-consolidate-v1.sh
