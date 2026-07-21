#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# W1 screen: fixed role-aware 1/2/4 vs W0 stratum-adaptive weights.
# Same immutable G4 source, split, warm start, binary, search and optimizer.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?pin reviewed merged SHA}"
: "${P1_PREFIX:?}"; : "${EXPECTED_P1_JOB_ID:?}"
: "${W0_PREFIX:?}"; : "${EXPECTED_W0_JOB_ID:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; INPUTS="$JASS_RESULT_DIR/inputs"
GEOM="$W/geom8"; POOLS="$W/w1-pools"; REPORTS="$W/reports"
mkdir -p "$W" "$ART" "$INPUTS/p1" "$INPUTS/w0" "$GEOM" "$POOLS" "$REPORTS"
exec 9>"$JASS_RESULT_DIR/job.lock"; flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

POOL_SEED="${POOL_SEED:-141421}"; PLATEAU_PER_STRATUM="${PLATEAU_PER_STRATUM:-64}"
DEPTH="${DEPTH:-10}"; MAXPLIES="${MAXPLIES:-400}"; NSHARDS="${NSHARDS:-8}"; PAR="${PAR:-8}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-21600}"; BOOTSTRAP="${BOOTSTRAP:-10000}"
HOLDOUT_MOD="${HOLDOUT_MOD:-10}"; BASE_SEED="${BASE_SEED:-271828}"; RESAMPLE_SEED="${RESAMPLE_SEED:-271832}"
L2="${L2:-3e-5}"; MAXIT="${MAXIT:-25}"; CHUNK="${CHUNK:-500000}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"; GENERALIST_PAIRS="${GENERALIST_PAIRS:-64}"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; : > "$RES"; : > "$PROG"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
run_pids(){ local label="$1"; shift; local failed=0 pid; for pid in "$@"; do wait "$pid" || failed=$((failed+1)); done; [ "$failed" -eq 0 ] || die "$label: $failed failed process(es)"; }
finalize(){ rc=$?; trap - EXIT; set +e; [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"; [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true; rm -rf "$W/build" "$INPUTS" "$GEOM" "$W"/*.feat "$W"/*.jnnw "$W"/*.jsm 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-IMBALANCE2 W1 stratum-adaptive weight screen ==="
[ -z "$(git branch --show-current)" ] || die "runner worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] && [ "${W1_ADAPTIVE_GO:-0}" = 1 ] || die "explicit W1 go missing"
[ "$POOL_SEED" -eq 141421 ] && [ "$PLATEAU_PER_STRATUM" -eq 64 ] || die "E64/F64 contract mismatch"
[ "$DEPTH" -eq 10 ] && [ "$MAXPLIES" -eq 400 ] && [ "$NSHARDS" -eq 8 ] && [ "$PAR" -eq 8 ] || die "evaluation contract mismatch"
[ "$BOOTSTRAP" -ge 10000 ] && [ "$HOLDOUT_MOD" -eq 10 ] && [ "$BASE_SEED" -eq 271828 ] && [ "$RESAMPLE_SEED" -eq 271832 ] || die "statistical/split contract mismatch"
[ "$L2" = 3e-5 ] && [ "$MAXIT" -eq 25 ] && [ "$CHUNK" -eq 500000 ] && [ "$GENERALIST_PAIRS" -eq 64 ] || die "fit/guard contract mismatch"
[ "$(nproc)" -ge 8 ] || die "requires >=8 CPUs"
[ "$(awk '/MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo)" -ge 14000 ] || die "requires >=14 GiB RAM"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')" -ge 20000 ] || die "less than 20 GiB free"

python3 -m py_compile jobs/tools/fetch_result_files.py jobs/tools/prepare_imbalance2_training.py \
  jobs/tools/imbalance2_adaptive_reweight.py jobs/tools/make_imbalance2_pools.py \
  jobs/tools/imbalance2_scan_gate.py jobs/tools/imbalance2_weight_generalist.py \
  jobs/tools/imbalance2_w1_screen_report.py tools/selfplay_frontier.py pattern_jass/tools/train_stream.py
python3 jobs/tests/test_imbalance2_w1_adaptive.py > "$W/test-w1.log" 2>&1 || die "W1 tests failed"

echo stage=fetch_sources > "$PROG"
python3 jobs/tools/fetch_result_files.py --prefix "$P1_PREFIX" \
  --file artefacts/g3.pjtw.gz=g3.pjtw.gz --file artefacts/g4.pjtw.gz=published-g4.pjtw.gz \
  --file artefacts/g4-source.jnnw.gz=g4-source.jnnw.gz --file artefacts/g4-source.jsm.gz=g4-source.jsm.gz \
  --file artefacts/g4-reweight.json=published-g4-reweight.json --file artefacts/g4-split.json=published-g4-split.json \
  --file artefacts/l3-imbalance2-p1-manifest.json=lineage-manifest.json \
  --expected-state completed --out-dir "$INPUTS/p1" --report "$ART/verified-p1-source.json" > "$W/fetch-p1.log" 2>&1 || die "P1 source fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$W0_PREFIX" \
  --file artefacts/w0-oracle-weight-calibration.json=w0-policy.json \
  --expected-state completed --out-dir "$INPUTS/w0" --report "$ART/verified-w0-source.json" > "$W/fetch-w0.log" 2>&1 || die "W0 source fetch failed"

python3 - "$INPUTS" "$ART" "$EXPECTED_P1_JOB_ID" "$EXPECTED_W0_JOB_ID" <<'PY'
import gzip,hashlib,json,struct,sys
from pathlib import Path
root=Path(sys.argv[1]); art=Path(sys.argv[2]); p1id=sys.argv[3]; w0id=sys.argv[4]
for label,path,expected in (('p1',art/'verified-p1-source.json',p1id),('w0',art/'verified-w0-source.json',w0id)):
 payload=json.loads(path.read_text())
 if payload.get('job_id') != expected or payload.get('result_state') != 'completed': raise SystemExit(f'{label}: source identity/state mismatch')
p1=json.loads((root/'p1/lineage-manifest.json').read_text())
if p1.get('lineage') != 'L3-IMBALANCE2-ROLE-V2' or p1.get('phase') != 'P1' or p1.get('generation_range') != [1,4]: raise SystemExit('P1 lineage contract mismatch')
search=p1.get('search_params','')
if len(search.split(',')) != 63: raise SystemExit('P1 search fingerprint is not fully pinned')
params=dict(token.split('=',1) for token in search.split(',')); required={'qs_threat_ext':'0','qs_sacs':'0','qs_sacs_depth0_only':'1','qs_forcing_depth':'0','qs_promo_depth':'0'}
if any(params.get(k) != v for k,v in required.items()): raise SystemExit('P1 search fingerprint is not Q00')
raw=gzip.decompress((root/'p1/g4-source.jnnw.gz').read_bytes()); meta=gzip.decompress((root/'p1/g4-source.jsm.gz').read_bytes())
if raw[:4] != b'JNNW' or struct.unpack_from('<I',raw,4)[0] != 500000: raise SystemExit('G4 source is not 500000 records')
if meta[:4] != b'JSM1' or struct.unpack_from('<I',meta,4)[0] != 500000: raise SystemExit('G4 metadata mismatch')
(root/'g4-source.jnnw').write_bytes(raw); (root/'g4-source.jsm').write_bytes(meta); (root/'g3.pjtw').write_bytes(gzip.decompress((root/'p1/g3.pjtw.gz').read_bytes()))
w0=json.loads((root/'w0/w0-policy.json').read_text())
if w0.get('decision') != 'W0_ORACLE_WEIGHT_CALIBRATION_READY' or w0.get('classification') != 'STRATUM_ORACLE_WEIGHTING_SUPPORTED_DENSITY_ONLY_NOT_SUPPORTED': raise SystemExit('W0 verdict mismatch')
if w0.get('diagnostics',{}).get('pool_stability_pass') is not True or w0.get('diagnostics',{}).get('density_only_hypothesis_pass') is not False: raise SystemExit('W0 stability/density contract mismatch')
(root/'search-params.txt').write_text(search+'\n')
proof={'schema':1,'protocol':'w1-adaptive-source-contract','p1_job_id':p1id,'w0_job_id':w0id,'p1_prefix':json.loads((art/'verified-p1-source.json').read_text()).get('prefix'),'w0_prefix':json.loads((art/'verified-w0-source.json').read_text()).get('prefix'),'g4_source_records':500000,'g4_source_jnnw_sha256':hashlib.sha256(raw).hexdigest(),'g4_source_jsm_sha256':hashlib.sha256(meta).hexdigest(),'w0_policy_sha256':hashlib.sha256((root/'w0/w0-policy.json').read_bytes()).hexdigest(),'search_params_sha256':hashlib.sha256(search.encode()).hexdigest(),'same_source_bytes_both_arms':True,'same_warm_start_both_arms':True,'scan_used_for_training_labels':False,'oracle_used_for_sampling_weights':True,'new_training_selfplay_games':0}
(art/'w1-source-contract.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
PY
SEARCH_PARAMS="$(cat "$INPUTS/search-params.txt")"

echo stage=prepare_control_and_adaptive_training > "$PROG"
python3 tools/selfplay_frontier.py split --data "$INPUTS/g4-source.jnnw" --meta "$INPUTS/g4-source.jsm" \
  --out-data "$W/g4.fit.jnnw" --out-meta "$W/g4.fit.jsm" --holdout-mod "$HOLDOUT_MOD" --seed "$BASE_SEED" \
  --manifest "$ART/w1-split.json" > "$W/split.log" 2>&1
HOLDOUT_COUNT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/w1-split.json")"; [ "$HOLDOUT_COUNT" -gt 0 ] || die "empty holdout"
env IMBALANCE2_REWEIGHT_POLICY=role-aware-v2 python3 jobs/tools/prepare_imbalance2_training.py reweight \
  --input "$W/g4.fit.jnnw" --output "$W/control.weighted.jnnw" --holdout-count "$HOLDOUT_COUNT" \
  --win-weight 1 --draw-weight 2 --loss-weight 4 --seed "$RESAMPLE_SEED" --report "$ART/w1-control-reweight.json" > "$W/control-reweight.log" 2>&1
python3 jobs/tools/imbalance2_adaptive_reweight.py --input "$W/g4.fit.jnnw" --output "$W/adaptive.weighted.jnnw" \
  --policy "$INPUTS/w0/w0-policy.json" --holdout-count "$HOLDOUT_COUNT" --seed "$RESAMPLE_SEED" \
  --report "$ART/w1-adaptive-reweight.json" > "$W/adaptive-reweight.log" 2>&1
python3 - "$W/control.weighted.jnnw" "$W/adaptive.weighted.jnnw" "$HOLDOUT_COUNT" "$ART/w1-training-bytes-contract.json" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
c=Path(sys.argv[1]).read_bytes(); a=Path(sys.argv[2]).read_bytes(); hold=int(sys.argv[3]); rec=38
for name,raw in (('control',c),('adaptive',a)):
 if raw[:4] != b'JNNW' or struct.unpack_from('<I',raw,4)[0] != 500000: raise SystemExit(f'{name}: invalid weighted corpus')
if c[-hold*rec:] != a[-hold*rec:]: raise SystemExit('control/adaptive holdout bytes differ')
Path(sys.argv[4]).write_text(json.dumps({'schema':1,'same_total_records':True,'same_holdout_bytes':True,'holdout_records':hold,'holdout_sha256':hashlib.sha256(c[-hold*rec:]).hexdigest(),'control_training_sha256':hashlib.sha256(c[8:-hold*rec]).hexdigest(),'adaptive_training_sha256':hashlib.sha256(a[8:-hold*rec]).hexdigest(),'only_intended_difference':'training_row_resampling_policy'},indent=2,sort_keys=True)+'\n')
PY

echo stage=build_and_fit > "$PROG"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-patterns.log" 2>&1; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] || die "8cf geometry mismatch"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone-egdb.log" 2>&1
EGDIR=""; for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }; done; [ -n "$EGDIR" ] || die "exact EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="${JASS_EGDB_CACHE_MB:-128}"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1; cmake --build "$W/build" -j"$JASS_BUILD_JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "jass build missing"
for arm in control adaptive; do
  "$J" --dump-eval-features "$W/${arm}.weighted.jnnw" "$W/${arm}.feat" > "$W/${arm}-features.log" 2>&1
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/train_stream.py \
    --data "$W/${arm}.weighted.jnnw" --feat "$W/${arm}.feat" --out "$W/${arm}.pjtw" --target wdl --loss logistic \
    --color-fold --tempo-stage --warm-start "$INPUTS/g3.pjtw" --holdout-count "$HOLDOUT_COUNT" \
    --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" > "$W/train-${arm}.log" 2>&1
done
python3 - "$W/control.pjtw" "$W/adaptive.pjtw" "$ART/w1-fit-contract.json" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
def head(path):
 raw=Path(path).read_bytes()
 if raw[:4] != b'PJTW': raise SystemExit(f'{path}: bad PJTW magic')
 return {'sha256':hashlib.sha256(raw).hexdigest(),'n_pat':struct.unpack_from('<I',raw,12)[0],'n_ext':struct.unpack_from('<I',raw,16)[0],'bytes':len(raw)}
c=head(sys.argv[1]); a=head(sys.argv[2])
if c['n_pat'] != a['n_pat'] or c['n_ext'] != 120 or a['n_ext'] != 120: raise SystemExit(f'layout mismatch: {c} {a}')
Path(sys.argv[3]).write_text(json.dumps({'schema':1,'protocol':'w1-same-corpus-weight-only-refit','control':c,'adaptive':a,'same_source':True,'same_split':True,'same_holdout':True,'same_feature_extractor':True,'same_optimizer':True,'same_warm_start_g3':True,'only_intended_difference':'resampling_weights'},indent=2,sort_keys=True)+'\n')
PY
gzip -n -c "$W/control.pjtw" > "$ART/w1-control-refit.pjtw.gz"; gzip -n -c "$W/adaptive.pjtw" > "$ART/w1-adaptive.pjtw.gz"

echo stage=generate_e64_f64 > "$PROG"
python3 jobs/tools/make_imbalance2_pools.py --out-dir "$POOLS/raw" --train-per-side 1 --bench-per-stratum 1 \
  --plateau-per-stratum "$PLATEAU_PER_STRATUM" --seed "$POOL_SEED" --plateau-seed "$POOL_SEED" > "$W/pools.log" 2>&1
mv "$POOLS/raw/plateau-a.jnnw" "$POOLS/plateau-e.jnnw"; mv "$POOLS/raw/plateau-a.json" "$POOLS/plateau-e.json"
mv "$POOLS/raw/plateau-b.jnnw" "$POOLS/plateau-f.jnnw"; mv "$POOLS/raw/plateau-b.json" "$POOLS/plateau-f.json"
python3 - "$POOLS" "$ART/w1-e64-f64-manifest.json" "$POOL_SEED" "$PLATEAU_PER_STRATUM" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
root=Path(sys.argv[1]); seed=int(sys.argv[3]); per=int(sys.argv[4]); files={}
for pool in ('e','f'):
 data=root/f'plateau-{pool}.jnnw'; meta=root/f'plateau-{pool}.json'; raw=data.read_bytes(); rows=json.loads(meta.read_text())
 if raw[:4] != b'JNNW' or struct.unpack_from('<I',raw,4)[0] != 18*per or len(rows) != 18*per: raise SystemExit(f'pool {pool}: record count mismatch')
 if {str(row['stratum']) for row in rows} != {f'{n}v{n+2}' for n in range(1,19)}: raise SystemExit(f'pool {pool}: strata mismatch')
 files[data.name]={'sha256':hashlib.sha256(raw).hexdigest(),'records':18*per,'metadata':meta.name,'semantic_pool':pool.upper()+'64'}
Path(sys.argv[2]).write_text(json.dumps({'schema':1,'protocol':'w1-independent-e64-f64','seed':seed,'per_stratum':per,'records_per_pool':18*per,'historical_a64_b64_reused':False,'historical_c64_d64_reused':False,'oracle_used_for_selection':False,'files':files},indent=2,sort_keys=True)+'\n')
PY
for pool in e f; do gzip -n -c "$POOLS/plateau-${pool}.jnnw" > "$ART/plateau-${pool}.jnnw.gz"; cp "$POOLS/plateau-${pool}.json" "$ART/plateau-${pool}.json"; done

run_arm_pool(){
  local arm="$1"; local pattern="$2"; local pool="$3"; local dir="$REPORTS/$arm/$pool"
  mkdir -p "$dir"; local -a pids=() outputs=(); local shard out
  for shard in $(seq 0 $((NSHARDS-1))); do
    out="$dir/plateau-${pool}.s${shard}.json"; outputs+=("$out")
    timeout "$SHARD_TIMEOUT" python3 jobs/tools/imbalance2_scan_gate.py run --engine candidate --jass "$J" --pattern "$pattern" \
      --pool "$POOLS/plateau-${pool}.jnnw" --meta "$POOLS/plateau-${pool}.json" --search-params "$SEARCH_PARAMS" \
      --depth "$DEPTH" --max-plies "$MAXPLIES" --shard "$shard" --nshards "$NSHARDS" --out "$out" \
      > "$W/${arm}-${pool}-s${shard}.log" 2>&1 &
    pids+=("$!"); if [ "${#pids[@]}" -ge "$PAR" ]; then run_pids "$arm pool $pool" "${pids[@]}"; pids=(); fi
  done
  [ "${#pids[@]}" -eq 0 ] || run_pids "$arm pool $pool final" "${pids[@]}"; printf '%s\n' "${outputs[@]}" > "$dir/inputs.list"
}

echo stage=evaluate_e64_f64 > "$PROG"
run_arm_pool control "$W/control.pjtw" e; run_arm_pool control "$W/control.pjtw" f
run_arm_pool adaptive "$W/adaptive.pjtw" e; run_arm_pool adaptive "$W/adaptive.pjtw" f

echo stage=generalist_guard > "$PROG"
python3 jobs/tools/imbalance2_weight_generalist.py --jass "$J" --control-pattern "$W/control.pjtw" --adaptive-pattern "$W/adaptive.pjtw" \
  --openings data/dilf_combinations.fen --search-params "$SEARCH_PARAMS" --pairs "$GENERALIST_PAIRS" --depth 8 --max-plies 200 \
  --bootstrap "$BOOTSTRAP" --seed "$POOL_SEED" --out "$ART/w1-generalist-guard.json" > "$W/generalist.log" 2>&1
python3 - "$REPORTS" "$W/w1-manifest.json" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); sets={}
for arm in ('control','adaptive'):
 sets[arm]=sum(((root/arm/pool/'inputs.list').read_text().splitlines() for pool in ('e','f')),[])
Path(sys.argv[2]).write_text(json.dumps({'schema':1,'same_pools':True,'same_search_budget':True,'pool_labels':{'plateau-e.jnnw':'E64','plateau-f.jnnw':'F64'},'report_sets':sets},indent=2,sort_keys=True)+'\n')
PY

echo stage=aggregate_verdict > "$PROG"
python3 jobs/tools/imbalance2_w1_screen_report.py --manifest "$W/w1-manifest.json" --generalist "$ART/w1-generalist-guard.json" \
  --policy-report "$ART/w1-adaptive-reweight.json" --out "$ART/w1-adaptive-screen-decision.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" --bootstrap "$BOOTSTRAP" --seed "$POOL_SEED" --min-effect 0.02 \
  --min-nonworse-strata 12 --max-stratum-regression 0.10 --max-excluded 2 --max-excluded-fraction 0.001 \
  > "$W/aggregate.log" 2>&1 || { cat "$W/aggregate.log" | tee -a "$RES"; exit 1; }
tar -C "$REPORTS" -czf "$ART/w1-e64-f64-raw-reports.tar.gz" .
python3 - "$ART/w1-adaptive-screen-decision.json" "$ART" "$RES" <<'PY'
import json,sys
from pathlib import Path
p=json.load(open(sys.argv[1])); art=Path(sys.argv[2]); macro=p['paired']['macro_equal_stratum']; gen=p['generalist_gate']
def safe(v): return ('P' if v>=0 else 'M')+f'{abs(v):.4f}'.replace('.','_')
markers=[f"VERDICT__{p['decision']}",f"MACRO_DELTA_ADAPTIVE_MINUS_CONTROL__{safe(macro['adaptive_minus_control_failure_cost'])}",f"NONWORSE_STRATA__{macro['nonworse_strata']}_OF_18",f"GENERALIST_PASS__{str(bool(gen['pass'])).upper()}",'CONFIRMATION_REQUIRES_FRESH_C512_CROSSFIT__TRUE','TRAINING_CONTINUATION_AUTHORIZED__FALSE','PROMOTION_AUTHORIZED__FALSE']
for name in markers: (art/name).write_text(name+'\n')
with Path(sys.argv[3]).open('a') as f:
 f.write(f"decision={p['decision']}\nmacro_delta={macro['adaptive_minus_control_failure_cost']:.6f} ci95={macro['stratified_bootstrap_95']} nonworse={macro['nonworse_strata']}/18\ngeneralist_score={gen['adaptive_score_rate']:.4f} ci95={gen['paired_bootstrap_95']} pass={gen['pass']}\ntraining_continuation_authorized=false promotion_authorized=false automatic_next_job=null\n")
PY
echo stage=completed > "$PROG"; say "=== W1 adaptive screen complete; confirmation and promotion remain unauthorized ==="
