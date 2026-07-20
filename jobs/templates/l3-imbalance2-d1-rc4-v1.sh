#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# D1-A RC4: same immutable G4 corpus, control vs four role-conditioned extras.
# No new training self-play; new C64/D64 evaluation pools; no automatic D1-B.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?pin reviewed merged SHA}"
: "${P1_PREFIX:?immutable completed 0852 role-aware P1 prefix}"
: "${EXPECTED_P1_JOB_ID:?}"
: "${D0_PREFIX:?immutable completed 0871 D0 prefix}"
: "${EXPECTED_D0_JOB_ID:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
INPUTS="$JASS_RESULT_DIR/inputs"
CONTROL_SRC="$W/control-src"
RC4_SRC="$W/rc4-src"
GEOM="$W/geom8"
POOLS="$W/d1-pools"
REPORTS="$W/reports"
SENTINEL="$W/sentinel"
mkdir -p "$W" "$ART" "$INPUTS/p1" "$INPUTS/d0" "$CONTROL_SRC" "$RC4_SRC" \
  "$GEOM" "$POOLS" "$REPORTS" "$SENTINEL"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

POOL_SEED="${POOL_SEED:-314159}"
PLATEAU_PER_STRATUM="${PLATEAU_PER_STRATUM:-64}"
DEPTH="${DEPTH:-10}"
MAXPLIES="${MAXPLIES:-400}"
NSHARDS="${NSHARDS:-8}"
PAR="${PAR:-8}"
SENTINEL_SHARDS="${SENTINEL_SHARDS:-4}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-21600}"
BOOTSTRAP="${BOOTSTRAP:-10000}"
HOLDOUT_MOD="${HOLDOUT_MOD:-10}"
BASE_SEED="${BASE_SEED:-271828}"
L2="${L2:-3e-5}"
MAXIT="${MAXIT:-25}"
CHUNK="${CHUNK:-500000}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
GENERALIST_PAIRS="${GENERALIST_PAIRS:-64}"

RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
: > "$RES"; : > "$PROG"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
run_pids(){ local label="$1"; shift; local failed=0 pid; for pid in "$@"; do wait "$pid" || failed=$((failed+1)); done; [ "$failed" -eq 0 ] || die "$label: $failed failed process(es)"; }
finalize(){
  rc=$?; trap - EXIT; set +e
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$CONTROL_SRC" "$RC4_SRC" "$W/build-control" "$W/build-rc4" "$INPUTS" \
    "$W/control.feat" "$W/rc4.feat" "$W/g4.fit.jnnw" "$W/g4.fit.jsm" "$W/g4.weighted.jnnw" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-IMBALANCE2 D1-A RC4 representation screen ==="
[ -z "$(git branch --show-current)" ] || die "runner worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${D1_RC4_GO:-0}" = 1 ] || die "D1_RC4_GO=1 missing"
[ "$POOL_SEED" -eq 314159 ] || die "D1 C64/D64 seed must remain 314159"
[ "$PLATEAU_PER_STRATUM" -eq 64 ] || die "D1 requires 64 positions per stratum/pool"
[ "$DEPTH" -eq 10 ] && [ "$MAXPLIES" -eq 400 ] || die "D1 conversion gate requires d10/maxplies400"
[ "$NSHARDS" -eq 8 ] && [ "$PAR" -eq 8 ] || die "D1 requires 8 shards / 8 parallel"
[ "$SENTINEL_SHARDS" -eq 4 ] || die "D1 sentinel contract requires four shards"
[ "$BOOTSTRAP" -ge 10000 ] || die "D1 requires >=10000 bootstrap replicates"
[ "$HOLDOUT_MOD" -eq 10 ] && [ "$BASE_SEED" -eq 271828 ] || die "G4 split contract mismatch"
[ "$L2" = 3e-5 ] && [ "$MAXIT" -eq 25 ] && [ "$CHUNK" -eq 500000 ] || die "fit contract mismatch"
[ "$GENERALIST_PAIRS" -eq 64 ] || die "generalist guard requires 64 pairs"
[ "$(nproc)" -ge "$PAR" ] || die "not enough CPUs"
[ "$(awk '/MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo)" -ge 14000 ] || die "requires >=14 GiB RAM"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')" -ge 30000 ] || die "less than 30 GiB free"

python3 -m py_compile \
  jobs/tools/fetch_result_files.py \
  jobs/tools/apply_imbalance2_rc4_patch.py \
  jobs/tools/prepare_imbalance2_training.py \
  jobs/tools/make_imbalance2_pools.py \
  jobs/tools/imbalance2_scan_gate.py \
  jobs/tools/imbalance2_d1_rc4_sentinel.py \
  jobs/tools/imbalance2_d1_rc4_generalist.py \
  jobs/tools/imbalance2_d1_rc4_report.py \
  tools/selfplay_frontier.py pattern_jass/tools/train_stream.py
python3 jobs/tests/test_imbalance2_d1_rc4.py > "$W/test-d1-rc4.log" 2>&1 || die "D1 RC4 tests failed"

echo "stage=fetch_sources" > "$PROG"
python3 jobs/tools/fetch_result_files.py --prefix "$P1_PREFIX" \
  --file artefacts/g4-source.jnnw.gz=g4-source.jnnw.gz \
  --file artefacts/g4-source.jsm.gz=g4-source.jsm.gz \
  --file artefacts/g4-reweight.json=g4-reweight.json \
  --file artefacts/g4-split.json=g4-split.json \
  --file artefacts/g4.pjtw.gz=g4.pjtw.gz \
  --file artefacts/l3-imbalance2-p1-manifest.json=lineage-manifest.json \
  --expected-state completed --out-dir "$INPUTS/p1" --report "$ART/verified-p1-source.json" \
  > "$W/fetch-p1.log" 2>&1 || die "P1 source fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$D0_PREFIX" \
  --file artefacts/d0-causal-report.json=d0-causal-report.json \
  --file artefacts/c0-decision.json=d0-decision.json \
  --file artefacts/source-contract.json=d0-source-contract.json \
  --expected-state completed --out-dir "$INPUTS/d0" --report "$ART/verified-d0-source.json" \
  > "$W/fetch-d0.log" 2>&1 || die "D0 source fetch failed"

python3 - "$INPUTS" "$ART" "$EXPECTED_P1_JOB_ID" "$EXPECTED_D0_JOB_ID" <<'PY'
import gzip,hashlib,json,struct,sys
from pathlib import Path
root=Path(sys.argv[1]); art=Path(sys.argv[2]); p1id=sys.argv[3]; d0id=sys.argv[4]
for label,path,expected in (
 ('p1',art/'verified-p1-source.json',p1id),('d0',art/'verified-d0-source.json',d0id)):
 payload=json.loads(path.read_text())
 if payload.get('job_id') != expected or payload.get('result_state') != 'completed':
  raise SystemExit(f'{label}: source identity/state mismatch')
p1=json.loads((root/'p1/lineage-manifest.json').read_text())
if p1.get('lineage') != 'L3-IMBALANCE2-ROLE-V2' or p1.get('phase') != 'P1' or p1.get('generation_range') != [1,4]:
 raise SystemExit('P1 lineage contract mismatch')
search=p1.get('search_params','')
if len(search.split(',')) != 63:
 raise SystemExit('P1 search fingerprint is not fully pinned')
required={'qs_threat_ext':'0','qs_sacs':'0','qs_sacs_depth0_only':'1','qs_forcing_depth':'0','qs_promo_depth':'0'}
params=dict(token.split('=',1) for token in search.split(','))
if any(params.get(k) != v for k,v in required.items()):
 raise SystemExit('P1 search fingerprint is not Q00')
model=root/'p1/g4.pjtw.gz'
if hashlib.sha256(model.read_bytes()).hexdigest() != p1.get('student_sha256',{}).get('g4.pjtw.gz'):
 raise SystemExit('G4 model checksum mismatch')
raw=gzip.decompress((root/'p1/g4-source.jnnw.gz').read_bytes())
meta=gzip.decompress((root/'p1/g4-source.jsm.gz').read_bytes())
if raw[:4] != b'JNNW' or struct.unpack_from('<I',raw,4)[0] != 500000:
 raise SystemExit('G4 source is not the immutable 500000-record corpus')
if meta[:4] != b'JSM1' or struct.unpack_from('<I',meta,4)[0] != 500000:
 raise SystemExit('G4 metadata does not align to the source corpus')
(root/'g4-source.jnnw').write_bytes(raw); (root/'g4-source.jsm').write_bytes(meta)
d0=json.loads((root/'d0/d0-causal-report.json').read_text())
if d0.get('decision') != 'D0_CAUSAL_PROFILE_READY' or d0.get('sentinel_count') != 30:
 raise SystemExit('D0 report contract mismatch')
counts=d0.get('hypothesis_counts',{})
if counts.get('REPRESENTATION_OR_OBJECTIVE_CANDIDATE') != 7 or counts.get('SEARCH_AND_EVAL_MIXED') != 23:
 raise SystemExit('D0 hypothesis profile differs from reviewed result')
(root/'search-params.txt').write_text(search+'\n')
proof={'schema':1,'protocol':'d1-rc4-source-contract','p1_job_id':p1id,'d0_job_id':d0id,
 'p1_prefix':json.loads((art/'verified-p1-source.json').read_text()).get('prefix'),
 'd0_prefix':json.loads((art/'verified-d0-source.json').read_text()).get('prefix'),
 'g4_source_records':500000,'g4_source_jnnw_sha256':hashlib.sha256(raw).hexdigest(),
 'g4_source_jsm_sha256':hashlib.sha256(meta).hexdigest(),
 'g4_model_gzip_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
 'search_params_sha256':hashlib.sha256(search.encode()).hexdigest(),
 'same_source_bytes_both_arms':True,'scan_used_for_training':False,'new_training_selfplay_games':0}
(art/'source-contract.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
PY
SEARCH_PARAMS="$(cat "$INPUTS/search-params.txt")"

# Recreate the exact G4 split and role-aware weighting once; both arms consume the
# same weighted JNNW bytes.  Holdout rows remain untouched by the reweighter.
echo "stage=prepare_same_training_bytes" > "$PROG"
python3 tools/selfplay_frontier.py split \
  --data "$INPUTS/g4-source.jnnw" --meta "$INPUTS/g4-source.jsm" \
  --out-data "$W/g4.fit.jnnw" --out-meta "$W/g4.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$BASE_SEED" --manifest "$ART/d1-split.json" \
  > "$W/split.log" 2>&1
HOLDOUT_COUNT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/d1-split.json")"
[ "$HOLDOUT_COUNT" -gt 0 ] || die "empty holdout"
env IMBALANCE2_REWEIGHT_POLICY=role-aware-v2 python3 jobs/tools/prepare_imbalance2_training.py reweight \
  --input "$W/g4.fit.jnnw" --output "$W/g4.weighted.jnnw" --holdout-count "$HOLDOUT_COUNT" \
  --win-weight 1 --draw-weight 2 --loss-weight 4 --seed 271832 --report "$ART/d1-reweight.json" \
  > "$W/reweight.log" 2>&1

# Export two clean source copies from the reviewed SHA.  Only RC4 receives the
# deterministic experimental transform; the control source remains byte-identical.
echo "stage=build_control_and_rc4" > "$PROG"
git archive "$EXPECTED_CODE_SHA" | tar -x -C "$CONTROL_SRC"
git archive "$EXPECTED_CODE_SHA" | tar -x -C "$RC4_SRC"
python3 jobs/tools/apply_imbalance2_rc4_patch.py --source-root "$RC4_SRC" --report "$ART/rc4-source-transform.json" \
  > "$W/rc4-patch.log" 2>&1
python3 "$CONTROL_SRC/pattern_jass/tools/gen_patterns.py" --emit --variant 8cf > "$W/gen-patterns-control.log" 2>&1
python3 "$RC4_SRC/pattern_jass/tools/gen_patterns.py" --emit --variant 8cf > "$W/gen-patterns-rc4.log" 2>&1
cp "$CONTROL_SRC/pattern_jass/tools/patterns.py" "$GEOM/patterns.py"
NPAT="$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"
[ "$NPAT" -eq 4251528 ] || die "8cf geometry mismatch"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone-egdb.log" 2>&1
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "exact EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="${JASS_EGDB_CACHE_MB:-128}"
BASE_FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
cmake -S "$CONTROL_SRC" -B "$W/build-control" $BASE_FLAGS > "$W/cmake-control.log" 2>&1
cmake --build "$W/build-control" -j"$JASS_BUILD_JOBS" --target jass > "$W/build-control.log" 2>&1
cmake -S "$RC4_SRC" -B "$W/build-rc4" $BASE_FLAGS -DCMAKE_CXX_FLAGS=-DJASS_ROLE_CONVERSION=1 > "$W/cmake-rc4.log" 2>&1
cmake --build "$W/build-rc4" -j"$JASS_BUILD_JOBS" --target jass > "$W/build-rc4.log" 2>&1
JCONTROL="$W/build-control/jass"; JRC4="$W/build-rc4/jass"
[ -x "$JCONTROL" ] && [ -x "$JRC4" ] || die "control/RC4 build missing"

# Same labels, split, weights and optimiser contract; only the dumped feature
# matrix differs.  Both fits start from zero to avoid a dimension-mismatched warm start.
echo "stage=fit_control_and_rc4" > "$PROG"
"$JCONTROL" --dump-eval-features "$W/g4.weighted.jnnw" "$W/control.feat" > "$W/control-features.log" 2>&1
"$JRC4" --dump-eval-features "$W/g4.weighted.jnnw" "$W/rc4.feat" > "$W/rc4-features.log" 2>&1
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/train_stream.py \
  --data "$W/g4.weighted.jnnw" --feat "$W/control.feat" --out "$W/control.pjtw" \
  --target wdl --loss logistic --color-fold --tempo-stage --holdout-count "$HOLDOUT_COUNT" \
  --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" > "$W/train-control.log" 2>&1
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/train_stream.py \
  --data "$W/g4.weighted.jnnw" --feat "$W/rc4.feat" --out "$W/rc4.pjtw" \
  --target wdl --loss logistic --color-fold --tempo-stage --holdout-count "$HOLDOUT_COUNT" \
  --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" > "$W/train-rc4.log" 2>&1
python3 - "$W/control.pjtw" "$W/rc4.pjtw" "$ART/d1-fit-contract.json" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
control=Path(sys.argv[1]); rc4=Path(sys.argv[2]); out=Path(sys.argv[3])
def header(path):
 raw=path.read_bytes()
 if raw[:4] != b'PJTW': raise SystemExit(f'{path}: bad PJTW magic')
 return {'sha256':hashlib.sha256(raw).hexdigest(),'n_pat':struct.unpack_from('<I',raw,12)[0],'n_ext':struct.unpack_from('<I',raw,16)[0],'bytes':len(raw)}
c=header(control); r=header(rc4)
if c['n_ext'] != 120 or r['n_ext'] != 124 or c['n_pat'] != r['n_pat']:
 raise SystemExit(f'control/RC4 layout mismatch: {c} {r}')
p={'schema':1,'protocol':'d1-rc4-same-corpus-fit','control':c,'rc4':r,
 'same_weighted_jnnw':True,'same_holdout':True,'same_optimizer':True,
 'warm_start':False,'feature_difference_only':True}
out.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
PY
gzip -n -c "$W/control.pjtw" > "$ART/control-refit.pjtw.gz"
gzip -n -c "$W/rc4.pjtw" > "$ART/rc4.pjtw.gz"

# Generate fresh preregistered C64/D64 pools, independent of historical A64/B64.
echo "stage=generate_c64_d64" > "$PROG"
python3 jobs/tools/make_imbalance2_pools.py --out-dir "$POOLS/raw" \
  --train-per-side 1 --bench-per-stratum 1 --plateau-per-stratum "$PLATEAU_PER_STRATUM" \
  --seed "$POOL_SEED" --plateau-seed "$POOL_SEED" > "$W/pools.log" 2>&1
mv "$POOLS/raw/plateau-a.jnnw" "$POOLS/plateau-c.jnnw"
mv "$POOLS/raw/plateau-a.json" "$POOLS/plateau-c.json"
mv "$POOLS/raw/plateau-b.jnnw" "$POOLS/plateau-d.jnnw"
mv "$POOLS/raw/plateau-b.json" "$POOLS/plateau-d.json"
python3 - "$POOLS" "$ART/d1-c64-d64-manifest.json" "$POOL_SEED" "$PLATEAU_PER_STRATUM" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); seed=int(sys.argv[3]); per=int(sys.argv[4])
files={}
for pool in ('c','d'):
 data=root/f'plateau-{pool}.jnnw'; meta=root/f'plateau-{pool}.json'
 raw=data.read_bytes(); rows=json.loads(meta.read_text())
 if raw[:4] != b'JNNW' or struct.unpack_from('<I',raw,4)[0] != 18*per or len(rows) != 18*per:
  raise SystemExit(f'pool {pool}: record count mismatch')
 if {str(row['stratum']) for row in rows} != {f'{n}v{n+2}' for n in range(1,19)}:
  raise SystemExit(f'pool {pool}: strata mismatch')
 files[data.name]={'sha256':hashlib.sha256(raw).hexdigest(),'records':18*per,'metadata':meta.name,'semantic_pool':pool.upper()+'64'}
p={'schema':1,'protocol':'d1-independent-c64-d64','seed':seed,'per_stratum':per,
 'records_per_pool':18*per,'historical_a64_b64_reused':False,'files':files,
 'external_reference_used_for_selection':False}
out.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
PY
for pool in c d; do
  gzip -n -c "$POOLS/plateau-${pool}.jnnw" > "$ART/plateau-${pool}.jnnw.gz"
  cp "$POOLS/plateau-${pool}.json" "$ART/plateau-${pool}.json"
done

run_arm_pool(){
  local arm="$1" binary="$2" pattern="$3" pool="$4"
  local dir="$REPORTS/$arm/$pool"
  mkdir -p "$dir"
  local -a pids=() outputs=()
  local shard out
  for shard in $(seq 0 $((NSHARDS-1))); do
    out="$dir/plateau-${pool}.s${shard}.json"; outputs+=("$out")
    timeout "$SHARD_TIMEOUT" python3 jobs/tools/imbalance2_scan_gate.py run \
      --engine candidate --jass "$binary" --pattern "$pattern" \
      --pool "$POOLS/plateau-${pool}.jnnw" --meta "$POOLS/plateau-${pool}.json" \
      --search-params "$SEARCH_PARAMS" --depth "$DEPTH" --max-plies "$MAXPLIES" \
      --shard "$shard" --nshards "$NSHARDS" --out "$out" \
      > "$W/${arm}-${pool}-s${shard}.log" 2>&1 &
    pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR" ]; then run_pids "$arm pool $pool" "${pids[@]}"; pids=(); fi
  done
  [ "${#pids[@]}" -eq 0 ] || run_pids "$arm pool $pool final" "${pids[@]}"
  printf '%s\n' "${outputs[@]}" > "$dir/inputs.list"
}

echo "stage=evaluate_c64_d64" > "$PROG"
run_arm_pool control "$JCONTROL" "$W/control.pjtw" c
run_arm_pool control "$JCONTROL" "$W/control.pjtw" d
run_arm_pool rc4 "$JRC4" "$W/rc4.pjtw" c
run_arm_pool rc4 "$JRC4" "$W/rc4.pjtw" d

# Matched d14 replay on the reviewed D0 sentinels.
echo "stage=sentinel_mechanism_gate" > "$PROG"
pids=(); sentinel_outputs=()
for shard in $(seq 0 $((SENTINEL_SHARDS-1))); do
  out="$SENTINEL/s${shard}.json"; sentinel_outputs+=("$out")
  timeout "$SHARD_TIMEOUT" python3 jobs/tools/imbalance2_d1_rc4_sentinel.py \
    --d0-report "$INPUTS/d0/d0-causal-report.json" \
    --control-jass "$JCONTROL" --control-pattern "$W/control.pjtw" \
    --rc4-jass "$JRC4" --rc4-pattern "$W/rc4.pjtw" \
    --search-params "$SEARCH_PARAMS" --depth 14 --shard "$shard" --nshards "$SENTINEL_SHARDS" \
    --out "$out" > "$W/sentinel-s${shard}.log" 2>&1 &
  pids+=("$!")
done
run_pids "D1 sentinel replay" "${pids[@]}"

# Secondary veto only: 64 deterministic colour-swapped pairs on a generalist set.
echo "stage=generalist_guard" > "$PROG"
python3 jobs/tools/imbalance2_d1_rc4_generalist.py \
  --control-jass "$JCONTROL" --control-pattern "$W/control.pjtw" \
  --rc4-jass "$JRC4" --rc4-pattern "$W/rc4.pjtw" \
  --openings data/dilf_combinations.fen --search-params "$SEARCH_PARAMS" \
  --pairs "$GENERALIST_PAIRS" --depth 8 --max-plies 200 --bootstrap "$BOOTSTRAP" --seed "$POOL_SEED" \
  --out "$ART/d1-rc4-generalist.json" > "$W/generalist.log" 2>&1

python3 - "$REPORTS" "$W/d1-manifest.json" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); sets={}
for arm in ('control','rc4'):
 paths=[]
 for pool in ('c','d'):
  paths.extend((root/arm/pool/'inputs.list').read_text().splitlines())
 sets[arm]=paths
out.write_text(json.dumps({'schema':1,'same_pools':True,'same_search_budget':True,
 'pool_labels':{'plateau-c.jnnw':'C64','plateau-d.jnnw':'D64'},'report_sets':sets},indent=2,sort_keys=True)+'\n')
PY

echo "stage=aggregate_verdict" > "$PROG"
python3 jobs/tools/imbalance2_d1_rc4_report.py --manifest "$W/d1-manifest.json" \
  --d0-report "$INPUTS/d0/d0-causal-report.json" --sentinel-inputs "${sentinel_outputs[@]}" \
  --generalist "$ART/d1-rc4-generalist.json" --out "$ART/d1-rc4-decision.json" \
  --bootstrap "$BOOTSTRAP" --seed "$POOL_SEED" --min-effect 0.02 --min-nonworse-strata 12 \
  --max-stratum-regression 0.10 --max-excluded 2 --max-excluded-fraction 0.001 \
  > "$W/aggregate.log" 2>&1

tar -C "$REPORTS" -czf "$ART/d1-c64-d64-raw-reports.tar.gz" .
tar -C "$SENTINEL" -czf "$ART/d1-sentinel-replays.tar.gz" .
python3 - "$ART/d1-rc4-decision.json" "$RES" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); macro=p['paired']['macro_equal_stratum']; sent=p['sentinel_gate']; gen=p['generalist_gate']
with open(sys.argv[2],'a') as f:
 f.write(f"decision={p['decision']}\n")
 f.write(f"macro_delta={macro['rc4_minus_control_failure_cost']:.6f} ci95={macro['stratified_bootstrap_95']} nonworse={macro['nonworse_strata']}/18\n")
 f.write(f"sentinel_corrected={sent['corrected_representation_cases']}/7 new_divergences={sent['new_divergences_non_target']} nps_ratio={sent['throughput']['rc4_over_control']:.4f}\n")
 f.write(f"generalist_score={gen['rc4_score_rate']:.4f} ci95={gen['paired_bootstrap_95']} pass={gen['pass']}\n")
 f.write("d1b_authorized=false promotion_authorized=false automatic_next_job=null\n")
PY
echo "stage=completed" > "$PROG"
say "=== D1-A RC4 complete; human review required, no automatic continuation ==="
