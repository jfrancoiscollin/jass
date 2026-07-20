#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# D0 causal diagnostic after the role-aware V2 P2 stop verdict.
# Reuses immutable G4/G8 reports/models and the EGDB/Scan reference; no training.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?pin reviewed merged SHA}"
: "${P1_PREFIX:?completed 0852-style role-aware P1 prefix}"
: "${P2_PREFIX:?completed 0859-style role-aware P2 prefix}"
: "${P1_RAW_PREFIX:?failed 0853-style raw P1 comparison prefix}"
: "${P2_RAW_PREFIX:?failed 0864-style raw P2 plateau prefix}"
: "${REFERENCE_PREFIX:?completed 0862-style material reference prefix}"
: "${EXPECTED_P1_JOB_ID:?}"
: "${EXPECTED_P2_JOB_ID:?}"
: "${EXPECTED_P1_RAW_JOB_ID:?}"
: "${EXPECTED_P2_RAW_JOB_ID:?}"
: "${EXPECTED_REFERENCE_JOB_ID:?}"
: "${SCAN_BIN:?path to reviewed Scan binary}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
INPUTS="$JASS_RESULT_DIR/inputs"
RAW="$W/raw"
CLEAN="$W/clean"
REPLAY="$W/replay"
mkdir -p "$W" "$ART" "$INPUTS/p1" "$INPUTS/p2" "$INPUTS/raw-p1" \
  "$INPUTS/raw-p2" "$INPUTS/reference" "$RAW/p1" "$RAW/p2" "$RAW/reference" \
  "$CLEAN" "$REPLAY"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

DEPTHS="${DEPTHS:-8,10,12,14}"
NSHARDS="${NSHARDS:-8}"
PAR="${PAR:-8}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-21600}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
SENTINELS="${SENTINELS:-30}"
PER_FAMILY="${PER_FAMILY:-10}"
PLATEAU_PER_STRATUM="${PLATEAU_PER_STRATUM:-64}"
PLATEAU_SEED="${PLATEAU_SEED:-161803}"
MAX_EXCLUDED_POSITIONS="${MAX_EXCLUDED_POSITIONS:-2}"
MAX_EXCLUDED_FRACTION="${MAX_EXCLUDED_FRACTION:-0.001}"
SCAN_BB_SIZE="${SCAN_BB_SIZE:-0}"

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
  rm -rf "$W/build" "$INPUTS" "$RAW" "$CLEAN" "$REPLAY" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-IMBALANCE2 D0 causal diagnostic ==="
[ -z "$(git branch --show-current)" ] || die "runner worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${D0_DIAGNOSTIC_GO:-0}" = 1 ] || die "D0_DIAGNOSTIC_GO=1 missing"
[ "$DEPTHS" = "8,10,12,14" ] || die "D0 depth ladder must be 8,10,12,14"
[ "$NSHARDS" -eq 8 ] && [ "$PAR" -eq 8 ] || die "D0 requires 8 shards / 8 parallel"
[ "$SENTINELS" -ge 20 ] && [ "$SENTINELS" -le 40 ] || die "D0 requires 20..40 sentinels"
[ "$PER_FAMILY" -eq 10 ] && [ "$SENTINELS" -eq 30 ] || die "reviewed D0 contract is 10 per family / 30 total"
[ "$PLATEAU_PER_STRATUM" -eq 64 ] || die "D0 requires A64/B64"
[ "$PLATEAU_SEED" -eq 161803 ] || die "D0 requires plateau seed 161803"
[ "$MAX_EXCLUDED_POSITIONS" -le 2 ] || die "exclusion cap may not exceed two positions"
[ "$SCAN_BB_SIZE" -eq 0 ] || die "D0 Scan reference requires bb-size=0"
[ -x "$SCAN_BIN" ] || die "Scan binary missing or not executable"
[ "$(nproc)" -ge "$PAR" ] || die "not enough CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')" -ge 10000 ] || die "less than 10 GiB free"

python3 -m py_compile \
  jobs/tools/fetch_result_files.py \
  jobs/tools/imbalance2_symmetric_exclusion.py \
  jobs/tools/imbalance2_d0_select.py \
  jobs/tools/imbalance2_d0_replay.py \
  jobs/tools/imbalance2_d0_report.py
python3 jobs/tests/test_imbalance2_d0.py > "$W/test-d0.log" 2>&1 || die "D0 tests failed"

echo "stage=fetch_sources" > "$PROG"
python3 jobs/tools/fetch_result_files.py --prefix "$P1_PREFIX" \
  --file artefacts/g4.pjtw.gz=g4.pjtw.gz \
  --file artefacts/l3-imbalance2-p1-manifest.json=lineage-manifest.json \
  --file artefacts/imbalance2-pools-manifest.json=pools-manifest.json \
  --file artefacts/plateau-a.jnnw.gz=plateau-a.jnnw.gz \
  --file artefacts/plateau-a.json=plateau-a.json \
  --file artefacts/plateau-b.jnnw.gz=plateau-b.jnnw.gz \
  --file artefacts/plateau-b.json=plateau-b.json \
  --expected-state completed --out-dir "$INPUTS/p1" --report "$ART/verified-p1-source.json" \
  > "$W/fetch-p1.log" 2>&1 || die "P1 source fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$P2_PREFIX" \
  --file artefacts/g8.pjtw.gz=g8.pjtw.gz \
  --file artefacts/l3-imbalance2-p2-manifest.json=lineage-manifest.json \
  --file artefacts/imbalance2-pools-manifest.json=pools-manifest.json \
  --expected-state completed --out-dir "$INPUTS/p2" --report "$ART/verified-p2-source.json" \
  > "$W/fetch-p2.log" 2>&1 || die "P2 source fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$P1_RAW_PREFIX" \
  --file artefacts/candidate-only-a64-b64-reports.tar.gz=reports.tar.gz \
  --expected-state failed --out-dir "$INPUTS/raw-p1" --report "$ART/verified-p1-raw-source.json" \
  > "$W/fetch-p1-raw.log" 2>&1 || die "P1 raw report fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$P2_RAW_PREFIX" \
  --file artefacts/candidate-p2-reports.tar.gz=reports.tar.gz \
  --expected-state failed --out-dir "$INPUTS/raw-p2" --report "$ART/verified-p2-raw-source.json" \
  > "$W/fetch-p2-raw.log" 2>&1 || die "P2 raw report fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$REFERENCE_PREFIX" \
  --file artefacts/difficulty-reference-raw.tar.gz=reference-raw.tar.gz \
  --file artefacts/imbalance2-a64-b64-difficulty-reference.json=difficulty-reference.json \
  --expected-state completed --out-dir "$INPUTS/reference" --report "$ART/verified-reference-source.json" \
  > "$W/fetch-reference.log" 2>&1 || die "difficulty reference fetch failed"

python3 - "$INPUTS" "$ART" "$EXPECTED_P1_JOB_ID" "$EXPECTED_P2_JOB_ID" \
  "$EXPECTED_P1_RAW_JOB_ID" "$EXPECTED_P2_RAW_JOB_ID" "$EXPECTED_REFERENCE_JOB_ID" \
  "$PLATEAU_PER_STRATUM" "$PLATEAU_SEED" <<'PY'
import gzip,hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); art=Path(sys.argv[2])
p1id,p2id,p1rid,p2rid,refid=sys.argv[3:8]; per=int(sys.argv[8]); seed=int(sys.argv[9])
reports=[
 ('p1',art/'verified-p1-source.json',p1id,'completed'),
 ('p2',art/'verified-p2-source.json',p2id,'completed'),
 ('p1_raw',art/'verified-p1-raw-source.json',p1rid,'failed'),
 ('p2_raw',art/'verified-p2-raw-source.json',p2rid,'failed'),
 ('reference',art/'verified-reference-source.json',refid,'completed'),
]
sources=[]
for label,path,expected,state in reports:
    payload=json.loads(path.read_text())
    if payload.get('job_id') != expected or payload.get('result_state') != state:
        raise SystemExit(f'{label}: source identity/state mismatch')
    sources.append({'label':label,'job_id':expected,'state':state,'prefix':payload.get('prefix')})
p1=json.loads((root/'p1/lineage-manifest.json').read_text())
p2=json.loads((root/'p2/lineage-manifest.json').read_text())
pools1=json.loads((root/'p1/pools-manifest.json').read_text())
pools2=json.loads((root/'p2/pools-manifest.json').read_text())
if p1.get('lineage') != 'L3-IMBALANCE2-ROLE-V2' or p1.get('phase') != 'P1':
    raise SystemExit('P1 lineage mismatch')
if p2.get('lineage') != 'L3-IMBALANCE2-ROLE-V2' or p2.get('phase') != 'P2':
    raise SystemExit('P2 lineage mismatch')
if p1.get('search_params') != p2.get('search_params') or len(p1.get('search_params','').split(',')) != 63:
    raise SystemExit('P1/P2 search fingerprints differ')
for name,manifest,path in (
 ('g4.pjtw.gz',p1,root/'p1/g4.pjtw.gz'),
 ('g8.pjtw.gz',p2,root/'p2/g8.pjtw.gz'),
):
    got=hashlib.sha256(path.read_bytes()).hexdigest()
    if manifest.get('student_sha256',{}).get(name) != got:
        raise SystemExit(f'{name}: checksum differs from lineage manifest')
if pools1.get('plateau_seed') != seed or pools1.get('plateau_per_stratum') != per:
    raise SystemExit('P1 pool seed/size mismatch')
if pools1.get('plateau_records_per_pool') != 18*per:
    raise SystemExit('P1 pool count mismatch')
for pool in ('a','b'):
    key=f'plateau-{pool}.jnnw'
    if pools1.get('files',{}).get(key,{}).get('sha256') != pools2.get('files',{}).get(key,{}).get('sha256'):
        raise SystemExit(f'P1/P2 pool SHA mismatch for {pool}')
    raw=gzip.decompress((root/f'p1/plateau-{pool}.jnnw.gz').read_bytes())
    got=hashlib.sha256(raw).hexdigest()
    if got != pools1['files'][key]['sha256']:
        raise SystemExit(f'plateau-{pool}: uncompressed SHA mismatch')
    (root/f'plateau-{pool}.jnnw').write_bytes(raw)
    (root/f'plateau-{pool}.json').write_bytes((root/f'p1/plateau-{pool}.json').read_bytes())
reference=json.loads((root/'reference/difficulty-reference.json').read_text())
if reference.get('reference_used_for_training') is not False or reference.get('reference_used_for_weighting') is not False:
    raise SystemExit('difficulty reference may not be a train/weight input')
if reference.get('scan_reference_is_exact') is not False:
    raise SystemExit('Scan reference must remain non-exact')
(root/'search-params.txt').write_text(p1['search_params']+'\n')
(root/'g4.pjtw').write_bytes(gzip.decompress((root/'p1/g4.pjtw.gz').read_bytes()))
(root/'g8.pjtw').write_bytes(gzip.decompress((root/'p2/g8.pjtw.gz').read_bytes()))
proof={'schema':1,'protocol':'imbalance2-d0-source-contract','sources':sources,
       'g4_sha256':hashlib.sha256((root/'p1/g4.pjtw.gz').read_bytes()).hexdigest(),
       'g8_sha256':hashlib.sha256((root/'p2/g8.pjtw.gz').read_bytes()).hexdigest(),
       'search_params_sha256':hashlib.sha256(p1['search_params'].encode()).hexdigest(),
       'plateau_seed':seed,'plateau_per_stratum':per,'reference_for_reporting_only':True,
       'replayed_selfplay_games':0,'training_records':0}
(art/'source-contract.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
PY
SEARCH_PARAMS="$(cat "$INPUTS/search-params.txt")"

# Build the exact-EGDB 8cf engine used by both static Jass analyses.
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
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "D0 build has no exact EGDB"
cmake --build "$W/build" -j"$JASS_BUILD_JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"

# Rebuild the paired G4..G8 raw matrix and apply the same bounded symmetric exclusion.
tar -xzf "$INPUTS/raw-p1/reports.tar.gz" -C "$RAW/p1"
tar -xzf "$INPUTS/raw-p2/reports.tar.gz" -C "$RAW/p2"
tar -xzf "$INPUTS/reference/reference-raw.tar.gz" -C "$RAW/reference"
python3 - "$RAW/p1" "$RAW/p2" "$W/raw-manifest.json" <<'PY'
import glob,json,os,sys
p1,p2,out=sys.argv[1:]
def paths(pattern):
    values=sorted(glob.glob(pattern))
    if not values: raise SystemExit(f'no reports for {pattern}')
    return values
sets={'G4':paths(os.path.join(p1,'v2','G4','plateau-*.s*.json'))}
for generation in range(5,9):
    sets[f'G{generation}']=paths(os.path.join(p2,f'G{generation}','plateau-*.s*.json'))
json.dump({'schema':1,'same_pools':True,'same_search_budget':True,'report_sets':sets},open(out,'w'),indent=2,sort_keys=True)
PY
python3 jobs/tools/imbalance2_symmetric_exclusion.py \
  --manifest "$W/raw-manifest.json" --out-dir "$CLEAN" --out-manifest "$W/clean-manifest.json" \
  --report "$ART/symmetric-exclusions.json" --max-excluded-positions "$MAX_EXCLUDED_POSITIONS" \
  --max-excluded-fraction "$MAX_EXCLUDED_FRACTION" --expected-per-stratum "$PLATEAU_PER_STRATUM" \
  --allow-error-substring "no match in 60.0s" > "$W/clean.log" 2>&1 || die "symmetric exclusion failed"

echo "stage=select_sentinels" > "$PROG"
python3 jobs/tools/imbalance2_d0_select.py \
  --manifest "$W/clean-manifest.json" \
  --pool-a-data "$INPUTS/plateau-a.jnnw" --pool-a-meta "$INPUTS/plateau-a.json" \
  --pool-b-data "$INPUTS/plateau-b.jnnw" --pool-b-meta "$INPUTS/plateau-b.json" \
  --reference-raw "$RAW/reference" --per-family "$PER_FAMILY" --max-total "$SENTINELS" \
  --out "$ART/d0-sentinels.json" > "$W/select.log" 2>&1 || die "D0 sentinel selection failed"

echo "stage=multidepth_replay" > "$PROG"
pids=()
for shard in $(seq 0 $((NSHARDS-1))); do
  out="$REPLAY/d0-s${shard}.json"
  timeout "$SHARD_TIMEOUT" python3 jobs/tools/imbalance2_d0_replay.py \
    --sentinels "$ART/d0-sentinels.json" --jass "$J" \
    --g4-pattern "$INPUTS/g4.pjtw" --g8-pattern "$INPUTS/g8.pjtw" \
    --scan "$SCAN_BIN" --scan-bb-size "$SCAN_BB_SIZE" --search-params "$SEARCH_PARAMS" \
    --depths "$DEPTHS" --shard "$shard" --nshards "$NSHARDS" --out "$out" \
    > "$W/replay-s${shard}.log" 2>&1 &
  pids+=("$!")
  if [ "${#pids[@]}" -ge "$PAR" ]; then run_pids "D0 replay" "${pids[@]}"; pids=(); fi
done
[ "${#pids[@]}" -eq 0 ] || run_pids "D0 replay final" "${pids[@]}"

mapfile -t replay_inputs < <(find "$REPLAY" -maxdepth 1 -name 'd0-s*.json' -print | sort)
[ "${#replay_inputs[@]}" -eq "$NSHARDS" ] || die "missing replay shard outputs"
python3 jobs/tools/imbalance2_d0_report.py --sentinels "$ART/d0-sentinels.json" \
  --replay-inputs "${replay_inputs[@]}" --out "$ART/d0-causal-report.json" \
  > "$W/report.log" 2>&1 || die "D0 report aggregation failed"
tar -C "$REPLAY" -czf "$ART/d0-replay-traces.tar.gz" .

python3 - "$ART/d0-causal-report.json" "$ART/c0-decision.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
out={'schema':1,'protocol':p['protocol'],'decision':p['decision'],
     'sentinel_count':p['sentinel_count'],'searches':p['searches'],
     'hypothesis_counts':p['hypothesis_counts'],
     'recommendation_for_human_review':p['recommendation_for_human_review'],
     'classification_is_hypothesis_not_proof':True,
     'd1_authorized':False,'training_authorized':False,
     'promotion_authorized':False,'automatic_next_job':None}
json.dump(out,open(sys.argv[2],'w'),indent=2,sort_keys=True); print(json.dumps(out,indent=2))
PY
say "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["decision"])' "$ART/c0-decision.json")"
echo "stage=completed" > "$PROG"
