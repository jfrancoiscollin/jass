#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Re-assess historical P1 V1 and new role-aware P1 V2 on identical A64/B64 pools.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?pin reviewed merge SHA}"
: "${V1_P1_PREFIX:?immutable completed result prefix for historical 0847 P1}"
: "${V2_P1_PREFIX:?immutable completed result prefix for role-aware V2 P1}"
: "${EXPECTED_V1_JOB_ID:?expected historical source job id}"
: "${EXPECTED_V2_JOB_ID:?expected role-aware source job id}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
INPUTS="$JASS_RESULT_DIR/inputs"
REPORTS="$W/reports"
mkdir -p "$W" "$ART" "$INPUTS/v1" "$INPUTS/v2" "$REPORTS"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

DEPTH="${DEPTH:-10}"
MAXPLIES="${MAXPLIES:-400}"
NSHARDS="${NSHARDS:-8}"
PAR="${PAR:-8}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-21600}"
BOOTSTRAP="${BOOTSTRAP:-10000}"
PLATEAU_PER_STRATUM="${PLATEAU_PER_STRATUM:-64}"
PLATEAU_SEED="${PLATEAU_SEED:-161803}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"

RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
: > "$RES"
: > "$PROG"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
run_pids(){ local label="$1"; shift; local failed=0 pid; for pid in "$@"; do wait "$pid" || failed=$((failed+1)); done; [ "$failed" -eq 0 ] || die "$label: $failed failed shard(s)"; }
finalize(){
  rc=$?; trap - EXIT; set +e
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$INPUTS" "$REPORTS" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-IMBALANCE2 P1 V1/V2 common A64/B64 comparison ==="
[ -z "$(git branch --show-current)" ] || die "runner worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${COMPARISON_GO:-0}" = 1 ] || die "COMPARISON_GO=1 missing"
[ "$DEPTH" -eq 10 ] || die "P1 re-assess requires d10"
[ "$MAXPLIES" -eq 400 ] || die "P1 re-assess requires maxplies=400"
[ "$NSHARDS" -eq 8 ] && [ "$PAR" -eq 8 ] || die "comparison requires 8 shards / 8 parallel"
[ "$BOOTSTRAP" -ge 10000 ] || die "comparison requires >=10000 bootstrap replicates"
[ "$PLATEAU_PER_STRATUM" -eq 64 ] || die "comparison requires 64 positions per stratum"
[ "$PLATEAU_SEED" -eq 161803 ] || die "comparison requires independent plateau seed 161803"
[ "$(nproc)" -ge "$PAR" ] || die "not enough CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')" -ge 10000 ] || die "less than 10 GiB free"

python3 -m py_compile \
  jobs/tools/fetch_result_files.py \
  jobs/tools/imbalance2_scan_gate.py \
  jobs/tools/imbalance2_plateau.py \
  jobs/tools/imbalance2_lineage_compare.py
python3 jobs/tests/test_imbalance2_p1_compare.py > "$W/test-p1-compare.log" 2>&1 || die "P1 comparison tests failed"

fetch_lineage(){
  local label="$1" prefix="$2" expected_job="$3"
  local out="$INPUTS/$label"
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" \
    --file artefacts/g1.pjtw.gz=g1.pjtw.gz \
    --file artefacts/g2.pjtw.gz=g2.pjtw.gz \
    --file artefacts/g3.pjtw.gz=g3.pjtw.gz \
    --file artefacts/g4.pjtw.gz=g4.pjtw.gz \
    --file artefacts/l3-imbalance2-p1-manifest.json=lineage-manifest.json \
    "$@" --out-dir "$out" --report "$ART/verified-$label-source.json" \
    > "$W/fetch-$label.log" 2>&1
  python3 - "$ART/verified-$label-source.json" "$expected_job" <<'PY'
import json,sys
report=json.load(open(sys.argv[1]))
if report.get('job_id') != sys.argv[2]:
    raise SystemExit(f"source job mismatch: {report.get('job_id')} != {sys.argv[2]}")
PY
}

# V2 publishes the immutable common A64/B64 pools. The historical V1 models are
# deliberately evaluated on these same new pools rather than their old n=144 pools.
fetch_lineage v1 "$V1_P1_PREFIX" "$EXPECTED_V1_JOB_ID"
python3 jobs/tools/fetch_result_files.py --prefix "$V2_P1_PREFIX" \
  --file artefacts/g1.pjtw.gz=g1.pjtw.gz \
  --file artefacts/g2.pjtw.gz=g2.pjtw.gz \
  --file artefacts/g3.pjtw.gz=g3.pjtw.gz \
  --file artefacts/g4.pjtw.gz=g4.pjtw.gz \
  --file artefacts/l3-imbalance2-p1-manifest.json=lineage-manifest.json \
  --file artefacts/imbalance2-pools-manifest.json=pools-manifest.json \
  --file artefacts/plateau-a.jnnw.gz=plateau-a.jnnw.gz \
  --file artefacts/plateau-a.json=plateau-a.json \
  --file artefacts/plateau-b.jnnw.gz=plateau-b.jnnw.gz \
  --file artefacts/plateau-b.json=plateau-b.json \
  --out-dir "$INPUTS/v2" --report "$ART/verified-v2-source.json" \
  > "$W/fetch-v2.log" 2>&1
python3 - "$ART/verified-v2-source.json" "$EXPECTED_V2_JOB_ID" <<'PY'
import json,sys
report=json.load(open(sys.argv[1]))
if report.get('job_id') != sys.argv[2]:
    raise SystemExit(f"source job mismatch: {report.get('job_id')} != {sys.argv[2]}")
PY

python3 - "$INPUTS" "$PLATEAU_PER_STRATUM" "$PLATEAU_SEED" "$ART/source-contract.json" <<'PY'
import gzip,hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); per=int(sys.argv[2]); seed=int(sys.argv[3]); out=Path(sys.argv[4])
v1=json.loads((root/'v1/lineage-manifest.json').read_text())
v2=json.loads((root/'v2/lineage-manifest.json').read_text())
pools=json.loads((root/'v2/pools-manifest.json').read_text())
if v1.get('lineage') != 'L3-IMBALANCE2' or v2.get('lineage') != 'L3-IMBALANCE2-ROLE-V2':
    raise SystemExit('lineage identity mismatch')
for payload in (v1,v2):
    if payload.get('phase') != 'P1' or payload.get('generation_range') != [1,4]:
        raise SystemExit('source is not a complete P1 G1-G4 chain')
if v1.get('search_params') != v2.get('search_params') or len(v1.get('search_params','').split(',')) != 63:
    raise SystemExit('V1/V2 search fingerprints differ')
for label,payload in (('v1',v1),('v2',v2)):
    for generation in range(1,5):
        name=f'g{generation}.pjtw.gz'
        got=hashlib.sha256((root/label/name).read_bytes()).hexdigest()
        if payload.get('student_sha256',{}).get(name) != got:
            raise SystemExit(f'{label} {name}: checksum differs from lineage manifest')
if pools.get('plateau_seed') != seed or pools.get('plateau_per_stratum') != per:
    raise SystemExit('A64/B64 pool seed or size differs from preregistration')
if pools.get('plateau_records_per_pool') != 18*per:
    raise SystemExit('A64/B64 pool count mismatch')
proof={
  'schema':1,'v1_lineage':v1['lineage'],'v2_lineage':v2['lineage'],
  'search_params_sha256':hashlib.sha256(v1['search_params'].encode()).hexdigest(),
  'plateau_seed':seed,'plateau_per_stratum':per,'records_per_pool':18*per,
  'pools':{},'external_references_used':False,
}
for pool in ('a','b'):
    compressed=root/f'v2/plateau-{pool}.jnnw.gz'
    raw=gzip.decompress(compressed.read_bytes())
    expected=pools['files'][f'plateau-{pool}.jnnw']['sha256']
    got=hashlib.sha256(raw).hexdigest()
    if got != expected:
        raise SystemExit(f'plateau-{pool}: uncompressed SHA mismatch')
    (root/f'plateau-{pool}.jnnw').write_bytes(raw)
    (root/f'plateau-{pool}.json').write_bytes((root/f'v2/plateau-{pool}.json').read_bytes())
    proof['pools'][pool]={'sha256':got,'records':18*per}
out.write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
(root/'search-params.txt').write_text(v1['search_params']+'\n')
PY
SEARCH_PARAMS="$(cat "$INPUTS/search-params.txt")"
cp "$INPUTS/v2/pools-manifest.json" "$ART/a64-b64-pools-manifest.json"
cp "$INPUTS/plateau-a.json" "$ART/plateau-a64.json"
cp "$INPUTS/plateau-b.json" "$ART/plateau-b64.json"
gzip -n -c "$INPUTS/plateau-a.jnnw" > "$ART/plateau-a64.jnnw.gz"
gzip -n -c "$INPUTS/plateau-b.jnnw" > "$ART/plateau-b64.jnnw.gz"

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
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "comparison build has no exact EGDB"
cmake --build "$W/build" -j"$JASS_BUILD_JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"

for lineage in v1 v2; do
  for generation in 1 2 3 4; do
    gzip -dc "$INPUTS/$lineage/g${generation}.pjtw.gz" > "$INPUTS/$lineage/g${generation}.pjtw"
  done
done

run_model_pool(){
  local lineage="$1" generation="$2" pool="$3"
  local dir="$REPORTS/$lineage/G$generation"
  mkdir -p "$dir"
  local -a pids=() outputs=()
  local shard out
  for shard in $(seq 0 $((NSHARDS-1))); do
    out="$dir/plateau-${pool}.s${shard}.json"
    outputs+=("$out")
    timeout "$SHARD_TIMEOUT" python3 jobs/tools/imbalance2_scan_gate.py run \
      --engine candidate --jass "$J" \
      --pool "$INPUTS/plateau-${pool}.jnnw" --meta "$INPUTS/plateau-${pool}.json" \
      --pattern "$INPUTS/$lineage/g${generation}.pjtw" --search-params "$SEARCH_PARAMS" \
      --depth "$DEPTH" --max-plies "$MAXPLIES" \
      --shard "$shard" --nshards "$NSHARDS" --out "$out" \
      > "$W/${lineage}-g${generation}-${pool}-s${shard}.log" 2>&1 &
    pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR" ]; then
      run_pids "$lineage G$generation pool $pool" "${pids[@]}"
      pids=()
    fi
  done
  [ "${#pids[@]}" -eq 0 ] || run_pids "$lineage G$generation pool $pool final" "${pids[@]}"
  printf '%s\n' "${outputs[@]}" > "$dir/plateau-${pool}.list"
}

completed=0
for lineage in v1 v2; do
  for generation in 1 2 3 4; do
    for pool in a b; do
      run_model_pool "$lineage" "$generation" "$pool"
      completed=$((completed+1))
      printf 'completed_model_pools=%s/16\n' "$completed" > "$PROG"
    done
  done
done

python3 - "$REPORTS" "$W/comparison-manifest.json" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
lineages={}
for lineage in ('v1','v2'):
    generations={}
    for generation in range(1,5):
        paths=[]
        for pool in ('a','b'):
            paths.extend((root/lineage/f'G{generation}'/f'plateau-{pool}.list').read_text().splitlines())
        generations[f'G{generation}']=paths
    lineages[lineage]=generations
out.write_text(json.dumps({'schema':1,'same_pools':True,'same_search_budget':True,'lineages':lineages},indent=2,sort_keys=True)+'\n')
for lineage in ('v1','v2'):
    Path(out.parent/f'{lineage}-plateau-manifest.json').write_text(json.dumps({
      'schema':1,'same_search_budget':True,'generations':lineages[lineage]
    },indent=2,sort_keys=True)+'\n')
PY

python3 jobs/tools/imbalance2_plateau.py --manifest "$W/v1-plateau-manifest.json" \
  --out "$ART/v1-p1-a64-b64-plateau.json" --bootstrap "$BOOTSTRAP" --seed "$PLATEAU_SEED" \
  > "$W/v1-plateau.log"
python3 jobs/tools/imbalance2_plateau.py --manifest "$W/v2-plateau-manifest.json" \
  --out "$ART/v2-p1-a64-b64-plateau.json" --bootstrap "$BOOTSTRAP" --seed $((PLATEAU_SEED+1)) \
  > "$W/v2-plateau.log"
python3 jobs/tools/imbalance2_lineage_compare.py --manifest "$W/comparison-manifest.json" \
  --out "$ART/v1-v2-p1-a64-b64-comparison.json" --bootstrap "$BOOTSTRAP" --seed $((PLATEAU_SEED+2)) \
  --min-effect 0.02 > "$W/lineage-compare.log"

python3 - "$ART/v1-p1-a64-b64-plateau.json" "$ART/v2-p1-a64-b64-plateau.json" \
  "$ART/v1-v2-p1-a64-b64-comparison.json" "$ART/campaign-decision.json" <<'PY'
import json,sys
from pathlib import Path
v1=json.load(open(sys.argv[1])); v2=json.load(open(sys.argv[2])); cmp=json.load(open(sys.argv[3]))
if cmp['v2_clear_lead']:
    recommendation = (
      'REVIEW_EXTERNAL_GATE_FOR_V2' if v2['plateau_confirmed']
      else 'REVIEW_V2_FOR_P2_CONTINUATION'
    )
elif v1['plateau_confirmed'] and v2['plateau_confirmed']:
    recommendation='ROLE_V2_NO_LEAD_REDESIGN'
else:
    recommendation='INCONCLUSIVE_NO_AUTO_CONTINUATION'
out={
  'schema':1,'protocol':'p1-v1-reassess-plus-role-v2-on-common-a64-b64',
  'v1_plateau_decision':v1['decision'],'v2_plateau_decision':v2['decision'],
  'v1_v2_decision':cmp['decision'],'recommendation_for_review':recommendation,
  'external_references_used':False,'promotion_authorized':False,
  'p2_authorized':False,'automatic_next_job':None,
}
Path(sys.argv[4]).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(recommendation)
PY
say "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["recommendation_for_review"])' "$ART/campaign-decision.json")"