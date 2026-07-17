#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Fail-closed environment audit for the MTC database used by post-probe jobs.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_EGDB_MTC_PATH:?set the exact MTC directory used by future jobs}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$ART"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: instance active" >&2; exit 3; }

SMOKE_PROCS="${MTC_SMOKE_PROCS:-2}"
MAX_PROCS="${MTC_AUDIT_MAX_PROCS:-24}"
CACHE_MB="${MTC_CACHE_MB_PER_PROC:-256}"
PROBE_POSITIONS="${MTC_PROBE_POSITIONS:-2000}"
TIMEOUT_SECONDS="${MTC_SMOKE_TIMEOUT:-1800}"
JOBS="${JASS_BUILD_JOBS:-8}"
MTC="$JASS_EGDB_MTC_PATH"
WLD="${JASS_EGDB_PATH:-}"

die(){ echo "ABORT: $*" >&2; exit 1; }
[[ "$SMOKE_PROCS" =~ ^[0-9]+$ ]] && [ "$SMOKE_PROCS" -ge 2 ] || \
  die "MTC_SMOKE_PROCS must be an integer >= 2"
[[ "$MAX_PROCS" =~ ^[0-9]+$ ]] && [ "$MAX_PROCS" -ge "$SMOKE_PROCS" ] || \
  die "MTC_AUDIT_MAX_PROCS must cover the concurrent smoke"
[[ "$CACHE_MB" =~ ^[0-9]+$ ]] && [ "$CACHE_MB" -gt 0 ] || \
  die "MTC_CACHE_MB_PER_PROC must be positive"
if [ -z "$WLD" ]; then
  for candidate in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
    if ls "$candidate"/db*.idx1 >/dev/null 2>&1; then WLD="$candidate"; break; fi
  done
fi
[ -n "$WLD" ] || die "base WLD introuvable"
[ -r "$MTC" ] || die "base MTC non lisible: $MTC"
find "$MTC" -type f -print -quit | grep -q . || die "base MTC vide: $MTC"
export JASS_EGDB_PATH="$WLD"

finalize(){
  rc=$?
  trap - EXIT
  set +e
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT

python3 -m py_compile jobs/tools/cache_guard.py jobs/tools/mtc_audit.py
python3 jobs/tests/test_cache_guard.py > "$W/test-cache-mtc.log" 2>&1
python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB" --procs "$MAX_PROCS" \
  > "$ART/mtc-cache-guard.json"

[ -d /root/egdb_intl ] || \
  git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl \
    > "$W/clone-egdb.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "build sans EGDB"
cmake --build "$W/build" -j"$JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"

pids=()
for shard in $(seq 0 $((SMOKE_PROCS-1))); do
  timeout "$TIMEOUT_SECONDS" "$J" --egdb-mtc-probe \
    "$WLD" "$MTC" "$PROBE_POSITIONS" "$CACHE_MB" \
    > "$W/mtc-smoke-$shard.log" 2>&1 &
  pids+=("$!")
done
SMOKE_OK=true
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then SMOKE_OK=false; fi
done

python3 jobs/tools/mtc_audit.py --cache-mb "$CACHE_MB" --procs "$MAX_PROCS" \
  --smoke-ok "$SMOKE_OK" --smoke-procs "$SMOKE_PROCS" --require-smoke \
  --out "$ART/mtc-audit.json"
echo "MTC audit complete: host=$(hostname) wld=$WLD mtc=$MTC smoke=$SMOKE_PROCS peak=$MAX_PROCS"
