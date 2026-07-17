#!/usr/bin/env bash
# id: cpx62-0779-mtc-audit-v1
# description: complete MTC path/cache/concurrent-read audit on cpx62
# expected_duration: 10-25 min; prepared only
set -Eeuo pipefail
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
export TMPDIR="$JASS_RESULT_DIR/tmp"; mkdir -p "$TMPDIR"
export JASS_EGDB_PATH=/root/egdb_extracted/app
export JASS_EGDB_MTC_PATH=/root/egdb_mtc/app
export MTC_SMOKE_PROCS=2 MTC_AUDIT_MAX_PROCS=24
export MTC_CACHE_MB_PER_PROC=384 MTC_PROBE_POSITIONS=2000
export JASS_BUILD_JOBS=8
exec bash jobs/templates/mtc-audit-runner-v3.sh
