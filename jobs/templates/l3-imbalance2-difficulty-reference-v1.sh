#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Material-difficulty reference on immutable A64/B64 pools:
# exact EGDB WDL for 1v3/2v4; Scan d10 self-play for 3v5..18v20.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?pin reviewed merge SHA}"
: "${V2_P1_PREFIX:?immutable completed role-aware V2 P1 result prefix}"
: "${EXPECTED_V2_JOB_ID:?expected role-aware source job id}"
: "${SCAN_BIN:?path to reviewed Scan binary}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
INPUTS="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$INPUTS"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

DEPTH="${DEPTH:-10}"
MAXPLIES="${MAXPLIES:-400}"
NSHARDS="${NSHARDS:-8}"
PAR="${PAR:-8}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-21600}"
PLATEAU_PER_STRATUM="${PLATEAU_PER_STRATUM:-64}"
PLATEAU_SEED="${PLATEAU_SEED:-161803}"
EXACT_MAX_PIECES="${EXACT_MAX_PIECES:-6}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"

RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
: > "$RES"; : > "$PROG"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
run_pids(){ local label="$1"; shift; local failed=0 pid; for pid in "$@"; do wait "$pid" || failed=$((failed+1)); done; [ "$failed" -eq 0 ] || die "$label: $failed failed shard(s)"; }
finalize(){
  rc=$?; trap - EXIT; set +e
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$INPUTS" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-IMBALANCE2 A64/B64 difficulty reference ==="
[ -z "$(git branch --show-current)" ] || die "runner worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${REFERENCE_GO:-0}" = 1 ] || die "REFERENCE_GO=1 missing"
[ "$DEPTH" -eq 10 ] || die "Scan reference requires d10"
[ "$MAXPLIES" -eq 400 ] || die "Scan reference requires maxplies=400"
[ "$NSHARDS" -eq 8 ] && [ "$PAR" -eq 8 ] || die "reference requires 8 shards / 8 parallel"
[ "$PLATEAU_PER_STRATUM" -eq 64 ] || die "reference requires 64 positions per stratum"
[ "$PLATEAU_SEED" -eq 161803 ] || die "reference requires plateau seed 161803"
[ "$EXACT_MAX_PIECES" -eq 6 ] || die "exact EGDB boundary must remain 6 total pieces"
[ -x "$SCAN_BIN" ] || die "Scan binary missing or not executable"
[ "$(nproc)" -ge "$PAR" ] || die "not enough CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')" -ge 10000 ] || die "less than 10 GiB free"

python3 -m py_compile jobs/tools/fetch_result_files.py jobs/tools/imbalance2_scan_gate.py \
  jobs/tools/imbalance2_difficulty_reference.py

python3 jobs/tools/fetch_result_files.py --prefix "$V2_P1_PREFIX" \
  --file artefacts/l3-imbalance2-p1-manifest.json=lineage-manifest.json \
  --file artefacts/imbalance2-pools-manifest.json=pools-manifest.json \
  --file artefacts/plateau-a.jnnw.gz=plateau-a.jnnw.gz \
  --file artefacts/plateau-a.json=plateau-a.json \
  --file artefacts/plateau-b.jnnw.gz=plateau-b.jnnw.gz \
  --file artefacts/plateau-b.json=plateau-b.json \
  --out-dir "$INPUTS" --report "$ART/verified-v2-source.json" \
  > "$W/fetch-v2.log" 2>&1

python3 - "$ART/verified-v2-source.json" "$EXPECTED_V2_JOB_ID" "$INPUTS" \
  "$PLATEAU_PER_STRATUM" "$PLATEAU_SEED" "$ART/source-contract.json" <<'PY'
import gzip,hashlib,json,sys
from pathlib import Path
report=json.load(open(sys.argv[1])); expected_job=sys.argv[2]; root=Path(sys.argv[3])
per=int(sys.argv[4]); seed=int(sys.argv[5]); out=Path(sys.argv[6])
if report.get('job_id') != expected_job:
    raise SystemExit(f"source job mismatch: {report.get('job_id')} != {expected_job}")
lineage=json.loads((root/'lineage-manifest.json').read_text())
pools=json.loads((root/'pools-manifest.json').read_text())
if lineage.get('lineage') != 'L3-IMBALANCE2-ROLE-V2' or lineage.get('phase') != 'P1':
    raise SystemExit('source is not role-aware V2 P1')
if pools.get('plateau_seed') != seed or pools.get('plateau_per_stratum') != per:
    raise SystemExit('A64/B64 seed or size mismatch')
if pools.get('plateau_records_per_pool') != 18*per:
    raise SystemExit('A64/B64 record count mismatch')
proof={'schema':1,'job_id':expected_job,'plateau_seed':seed,'plateau_per_stratum':per,'pools':{}}
for pool in ('a','b'):
    raw=gzip.decompress((root/f'plateau-{pool}.jnnw.gz').read_bytes())
    expected=pools['files'][f'plateau-{pool}.jnnw']['sha256']
    got=hashlib.sha256(raw).hexdigest()
    if got != expected:
        raise SystemExit(f'plateau-{pool}: SHA mismatch')
    (root/f'plateau-{pool}.jnnw').write_bytes(raw)
    proof['pools'][pool]={'sha256':got,'records':18*per}
out.write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
PY

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone-egdb.log" 2>&1
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "exact EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="${JASS_EGDB_CACHE_MB:-128}"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-patterns.log" 2>&1
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "reference build has no exact EGDB"
cmake --build "$W/build" -j"$JASS_BUILD_JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"

prepare_pool(){
  local pool="$1"
  mkdir -p "$W/exact-$pool" "$W/high-$pool" "$W/scan-$pool"
  python3 jobs/tools/imbalance2_difficulty_reference.py extract \
    --pool "$INPUTS/plateau-${pool}.jnnw" --meta "$INPUTS/plateau-${pool}.json" \
    --mode exact --exact-max-pieces "$EXACT_MAX_PIECES" \
    --out-data "$W/exact-${pool}/plateau-${pool}.jnnw" \
    --out-meta "$W/exact-${pool}/plateau-${pool}.json" \
    --report "$W/exact-${pool}/extract.json" > "$W/extract-exact-${pool}.log"
  local expected
  expected="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["records"])' "$W/exact-${pool}/extract.json")"
  "$J" --egdb-relabel "$W/exact-${pool}/plateau-${pool}.jnnw" "$EGDIR" \
    "$W/exact-${pool}/plateau-${pool}-labelled.jnnw" 128 > "$W/egdb-${pool}.log" 2>&1
  grep -q "egdb-relabel: ${expected} records, ${expected} egdb-resolved" "$W/egdb-${pool}.log" \
    || die "pool $pool exact EGDB reference was not 100% resolved"
  python3 jobs/tools/imbalance2_difficulty_reference.py extract \
    --pool "$INPUTS/plateau-${pool}.jnnw" --meta "$INPUTS/plateau-${pool}.json" \
    --mode high --exact-max-pieces "$EXACT_MAX_PIECES" \
    --out-data "$W/high-${pool}/plateau-${pool}.jnnw" \
    --out-meta "$W/high-${pool}/plateau-${pool}.json" \
    --report "$W/high-${pool}/extract.json" > "$W/extract-high-${pool}.log"
}
for pool in a b; do prepare_pool "$pool"; done

run_scan_pool(){
  local pool="$1"
  local -a pids=() outputs=()
  local shard out
  for shard in $(seq 0 $((NSHARDS-1))); do
    out="$W/scan-${pool}/plateau-${pool}.s${shard}.json"
    outputs+=("$out")
    timeout "$SHARD_TIMEOUT" python3 jobs/tools/imbalance2_scan_gate.py run \
      --engine scan --jass "$J" --scan "$SCAN_BIN" --scan-bb-size 0 \
      --pool "$W/high-${pool}/plateau-${pool}.jnnw" \
      --meta "$W/high-${pool}/plateau-${pool}.json" \
      --depth "$DEPTH" --max-plies "$MAXPLIES" \
      --shard "$shard" --nshards "$NSHARDS" --out "$out" \
      > "$W/scan-${pool}-s${shard}.log" 2>&1 &
    pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR" ]; then
      run_pids "Scan pool $pool" "${pids[@]}"; pids=()
    fi
  done
  [ "${#pids[@]}" -eq 0 ] || run_pids "Scan pool $pool final" "${pids[@]}"
  printf '%s\n' "${outputs[@]}" > "$W/scan-${pool}/inputs.list"
}
scan_completed=0
for pool in a b; do
  run_scan_pool "$pool"
  scan_completed=$((scan_completed+1))
  printf 'completed_scan_reference_pools=%s/2\n' "$scan_completed" > "$PROG"
done

mapfile -t scan_a < "$W/scan-a/inputs.list"
mapfile -t scan_b < "$W/scan-b/inputs.list"
python3 jobs/tools/imbalance2_difficulty_reference.py aggregate \
  --tb-data "$W/exact-a/plateau-a-labelled.jnnw" --tb-meta "$W/exact-a/plateau-a.json" \
  --tb-data "$W/exact-b/plateau-b-labelled.jnnw" --tb-meta "$W/exact-b/plateau-b.json" \
  --scan-inputs "${scan_a[@]}" "${scan_b[@]}" \
  --scan-source-label scan_d10_selfplay_reference \
  --exact-max-pieces "$EXACT_MAX_PIECES" \
  --out "$ART/imbalance2-a64-b64-difficulty-reference.json" \
  > "$W/reference-aggregate.log"

tar -C "$W" -czf "$ART/difficulty-reference-raw.tar.gz" exact-a exact-b high-a high-b scan-a scan-b
python3 - "$ART/imbalance2-a64-b64-difficulty-reference.json" "$ART/reference-decision.json" <<'PY'
import json,sys
from pathlib import Path
p=json.load(open(sys.argv[1]))
assert p['exact_tb_strata'] == ['1v3','2v4']
assert p['scan_reference_is_exact'] is False
assert p['reference_used_for_training'] is False
out={
 'schema':1,'protocol':p['protocol'],'decision':'REFERENCE_PROFILE_READY',
 'exact_tb_strata':p['exact_tb_strata'],'scan_reference_strata':p['scan_reference_strata'],
 'scan_reference_is_exact':False,'training_input':False,'weighting_input':False,
 'promotion_authorized':False,'automatic_next_job':None,
}
Path(sys.argv[2]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
PY
say "REFERENCE_PROFILE_READY"
