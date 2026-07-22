#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# L3-IMBALANCE2-TOP3: P1 G1-G4 trained only from 16v18, 17v19 and 18v20 self-play.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_JOB_ID:?runner v3 must provide JASS_JOB_ID}"
: "${EXPECTED_CODE_SHA:?pin the merged jass SHA}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
POOLS="$W/imbalance2-pools"
mkdir -p "$W" "$ART" "$GEOM" "$POOLS"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

FRESH="${FRESH:-500000}"
GENERATIONS="${GENERATIONS:-4}"
SEED_CLEAN="${SEED_CLEAN:-0}"
PAR_GEN="${PAR_GEN:-6}"
MAXPLIES="${MAXPLIES:-260}"
LABEL_DEPTH="${LABEL_DEPTH:-4}"
PLAY_DEPTH="${PLAY_DEPTH:-8}"
RANDOM_OPEN_PLIES="${RANDOM_OPEN_PLIES:-8}"
EXPLORE_EPS="${EXPLORE_EPS:-8}"
EXPLORE_DECAY_PLIES="${EXPLORE_DECAY_PLIES:-60}"
HOLDOUT_MOD="${HOLDOUT_MOD:-10}"
BASE_SEED="${BASE_SEED:-271828}"
MAXIT="${MAXIT:-25}"
L2="${L2:-3e-5}"
CHUNK="${CHUNK:-500000}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
GEN_SHARD_TIMEOUT="${GEN_SHARD_TIMEOUT:-43200}"
EVAL_SHARD_TIMEOUT="${EVAL_SHARD_TIMEOUT:-7200}"
TRAIN_SEEDS_PER_SIDE="${TRAIN_SEEDS_PER_SIDE:-2048}"
EVAL_PER_STRATUM="${EVAL_PER_STRATUM:-64}"
EVAL_SHARDS="${EVAL_SHARDS:-6}"
PAR_EVAL="${PAR_EVAL:-4}"
WIN_WEIGHT="${WIN_WEIGHT:-1}"
DRAW_WEIGHT="${DRAW_WEIGHT:-2}"
LOSS_WEIGHT="${LOSS_WEIGHT:-4}"
export IMBALANCE2_REWEIGHT_POLICY=role-aware-v2

EXPECTED_SEARCH_OVERRIDES="qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
L3_SEARCH_OVERRIDES="${L3_SEARCH_OVERRIDES:-$EXPECTED_SEARCH_OVERRIDES}"
L3_BASE_SEARCH_PARAMS="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=1,qs_sacs=1,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
L3_SEARCH_PARAMS="$(python3 - "$L3_BASE_SEARCH_PARAMS" "$L3_SEARCH_OVERRIDES" <<'PY'
import sys
base, overrides = sys.argv[1:]
order=[]; values={}
for token in base.split(','):
    k,v=token.split('=',1); order.append(k); values[k]=v
if len(order) != 63 or len(set(order)) != 63:
    raise SystemExit('expected 63 unique search keys')
for token in overrides.split(','):
    k,v=token.split('=',1)
    if k not in values: raise SystemExit(f'unknown override {k}')
    int(v); values[k]=v
print(','.join(f'{k}={values[k]}' for k in order))
PY
)"

RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
: > "$RES"; : > "$PROG"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
run_pids(){ local label="$1"; shift; local fail=0 p; for p in "$@"; do wait "$p" || fail=$((fail+1)); done; [ "$fail" -eq 0 ] || die "$label: $fail failed process(es)"; }
MEMPROBE_PID=""
start_memprobe(){ ( local min=99999999 a; echo "$min" > "$W/.min_mem_mb"; while true; do
  a="$(awk '/MemAvailable/{printf "%d",$2/1024}' /proc/meminfo 2>/dev/null)"
  [ "${a:-99999999}" -lt "$min" ] && { min="$a"; echo "$min" > "$W/.min_mem_mb"; }
  { TZ=Europe/Paris date '+time_fr=%Y-%m-%dT%H:%M:%S%z'; echo "min_mem_available_mb=$min"; } > "$PROG.tmp" && mv "$PROG.tmp" "$PROG"
  sleep 20; done ) & MEMPROBE_PID="$!"; }
stop_memprobe(){ [ -n "$MEMPROBE_PID" ] && { kill "$MEMPROBE_PID" 2>/dev/null || true; wait "$MEMPROBE_PID" 2>/dev/null || true; }; MEMPROBE_PID=""; }
finalize(){
  rc=$?; trap - EXIT; set +e; stop_memprobe
  [ -f "$W/.min_mem_mb" ] && say "min_mem_available_mb=$(cat "$W/.min_mem_mb")"
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  if [ -d "$W" ]; then (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true; fi
  rm -rf "$W/build" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-IMBALANCE2-TOP3 P1 G1-G4 d8 ==="
[ -z "$(git branch --show-current)" ] || die "runner code worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "$PAR_GEN" -eq 6 ] || die "top3 requires six parallel producers"
[ "$MAXPLIES" -eq 260 ] && [ "$LABEL_DEPTH" -eq 4 ] && [ "$PLAY_DEPTH" -eq 8 ] || die "play contract mismatch"
[ "$HOLDOUT_MOD" -eq 10 ] && [ "$BASE_SEED" -eq 271828 ] || die "split/seed contract mismatch"
[ "$MAXIT" -eq 25 ] && [ "$L2" = 3e-5 ] && [ "$CHUNK" -eq 500000 ] || die "fit contract mismatch"
[ "$EVAL_PER_STRATUM" -eq 64 ] && [ "$EVAL_SHARDS" -eq 6 ] && [ "$PAR_EVAL" -eq 4 ] || die "evaluation contract mismatch"
[ "$SEED_CLEAN" = 0 ] || [ "$SEED_CLEAN" = 1 ] || die "SEED_CLEAN must be 0 or 1"
if [ "$SEED_CLEAN" = 1 ]; then
  [ "$FRESH" -eq 100000 ] && [ "$GENERATIONS" -eq 1 ] || die "seed-clean screen requires 100000 records and one generation"
  [ "$RANDOM_OPEN_PLIES" -eq 0 ] && [ "$EXPLORE_EPS" -eq 0 ] && [ "$EXPLORE_DECAY_PLIES" -eq 0 ] || die "seed-clean exploration must be fully disabled"
  [ "$WIN_WEIGHT" = 1 ] && [ "$DRAW_WEIGHT" = 1 ] && [ "$LOSS_WEIGHT" = 1 ] || die "seed-clean requires natural unweighted WDL"
  [ "$GEN_SHARD_TIMEOUT" -ge 900 ] && [ "$EVAL_SHARD_TIMEOUT" -ge 900 ] || die "seed-clean shard timeouts are too short"
else
  [ "$FRESH" -eq 500000 ] && [ "$GENERATIONS" -eq 4 ] || die "standard TOP3 requires 500000 records and four generations"
  [ "$RANDOM_OPEN_PLIES" -eq 8 ] && [ "$EXPLORE_EPS" -eq 8 ] && [ "$EXPLORE_DECAY_PLIES" -eq 60 ] || die "exploration contract mismatch"
  [ "$WIN_WEIGHT" = 1 ] && [ "$DRAW_WEIGHT" = 2 ] && [ "$LOSS_WEIGHT" = 4 ] || die "requires fixed role-aware 1/2/4"
fi
[ "$L3_SEARCH_OVERRIDES" = "$EXPECTED_SEARCH_OVERRIDES" ] || die "Q00 fingerprint required"
[ "$(nproc)" -ge 8 ] || die "ccx33 requires at least 8 CPUs"
MEM_MB="$(awk '/MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo)"
[ "${MEM_MB:-0}" -ge 14000 ] || die "requires >=14 GiB RAM"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')" -ge 20000 ] || die "less than 20 GiB free"
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA="$(df -Pm /root | awk 'NR==2 {print $4}')"; [ "${DFA:-0}" -gt 3000 ] || die "disk below 3 GiB free"
start_memprobe

python3 -m py_compile jobs/tools/make_imbalance2_pools.py jobs/tools/prepare_imbalance2_training.py \
  jobs/tools/imbalance2_scan_gate.py tools/selfplay_frontier.py jobs/tools/aggregate_l3_exploration.py \
  pattern_jass/tools/train_stream.py pattern_jass/tools/make_bootstrap_eval.py
python3 jobs/tests/test_l3_imbalance2_top3_prepared.py > "$W/test-top3.log" 2>&1 || die "top3 contract tests failed"
python3 jobs/tests/test_imbalance2_tools.py > "$W/test-tools.log" 2>&1 || die "imbalance2 tool tests failed"

for source in src/scan_eval.cpp src/search.cpp src/movegen.cpp; do
  git show "HEAD:$source" > "$W/expected-$(basename "$source")"
  cmp -s "$source" "$W/expected-$(basename "$source")" || die "$source differs from pinned HEAD"
done
grep -q "g_emasks" src/scan_eval.cpp || die "architecture guard: scan_eval lacks g_emasks"
grep -q "has_any_capture" src/search.cpp || die "architecture guard: search lacks has_any_capture"
grep -q "has_any_capture" src/movegen.cpp || die "architecture guard: movegen lacks has_any_capture"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
NPAT="$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"
[ "$NPAT" -eq 4251528 ] || die "8cf geometry mismatch"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$JASS_BUILD_JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "jass binary missing"

python3 jobs/tools/make_imbalance2_pools.py --out-dir "$POOLS" \
  --train-per-side "$TRAIN_SEEDS_PER_SIDE" --bench-per-stratum "$EVAL_PER_STRATUM" \
  --plateau-per-stratum 1 --seed "$BASE_SEED" > "$W/pools.log" 2>&1
python3 - "$POOLS" "$ART" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
pools=Path(sys.argv[1]); art=Path(sys.argv[2]); wanted={'16v18','17v19','18v20'}
def read(path):
    raw=path.read_bytes(); n=struct.unpack_from('<I',raw,4)[0]; body=raw[8:]
    return [body[i*38:(i+1)*38] for i in range(n)]
def write(path, rows):
    raw=b'JNNW'+struct.pack('<I',len(rows))+b''.join(rows); path.write_bytes(raw); return hashlib.sha256(raw).hexdigest()
manifest={'schema':1,'lineage':'L3-IMBALANCE2-TOP3','strata':sorted(wanted),'per_stratum':64,'files':{}}
for label in ('a','b'):
    rows=read(pools/f'benchmark-{label}.jnnw')
    meta=json.loads((pools/f'benchmark-{label}.json').read_text())
    selected=[(r,m) for r,m in zip(rows,meta,strict=True) if m['stratum'] in wanted]
    out_rows=[r for r,_ in selected]; out_meta=[m for _,m in selected]
    data=pools/f'top3-{label}.jnnw'; meta_path=pools/f'top3-{label}.json'
    sha=write(data,out_rows); meta_path.write_text(json.dumps(out_meta,indent=2)+'\n')
    if len(out_rows)!=192: raise SystemExit(f'top3-{label}: expected 192 rows, got {len(out_rows)}')
    manifest['files'][data.name]={'records':len(out_rows),'sha256':sha,'metadata':meta_path.name,'pool':label.upper()}
    (art/f'top3-{label}.jnnw.gz').write_bytes(__import__('gzip').compress(data.read_bytes(),mtime=0))
    (art/f'top3-{label}.json').write_text(meta_path.read_text())
(art/'top3-pools-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
PY

python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/g0-material.pjtw" \
  --n-pat "$NPAT" --n-ext 120 --men 1 --king 3 --king-center 0 --mobility 0 > "$W/g0-material.log" 2>&1
PILOT="$W/g0-material.pjtw"
gzip -n -c "$PILOT" > "$ART/g0-material.pjtw.gz"

BASE_PER_STRATUM=$((FRESH / 3)); REMAINDER=$((FRESH % 3))
sampling_flags=()
pair_flags=(--pair-openings)
if [ "$SEED_CLEAN" = 1 ]; then
  sampling_flags=(--quiet-only --sample-initial)
  pair_flags=()
fi
for generation in $(seq 1 "$GENERATIONS"); do
  { echo "stage=generation"; echo "generation=$generation"; echo "records_target=$FRESH"; } > "$PROG"
  say "--- TOP3 G$generation play=d$PLAY_DEPTH pilot=$(basename "$PILOT") ---"
  pids=(); merge_args=(); rollout_logs=(); part=0; logical=0
  for low in 16 17 18; do
    high=$((low + 2)); target_stratum="$BASE_PER_STRATUM"
    [ "$logical" -lt "$REMAINDER" ] && target_stratum=$((target_stratum + 1))
    target_w=$(( (target_stratum + 1) / 2 )); target_b=$(( target_stratum - target_w ))
    for adv in W B; do
      target="$target_w"; [ "$adv" = B ] && target="$target_b"
      data="$W/g${generation}.p${part}.jnnw"; meta="$W/g${generation}.p${part}.jsm"
      log="$W/g${generation}.p${part}.log"; report="$ART/g${generation}-p${part}-outcome.json"
      seed=$((BASE_SEED + generation * 100000 + part))
      seed_file="$(printf '%s/train-%02dv%02d-up%s.jnnw' "$POOLS" "$low" "$high" "$adv")"
      merge_args+=(--pair "$data" "$meta"); rollout_logs+=("$log")
      (
        timeout "$GEN_SHARD_TIMEOUT" "$J" --gen-data-wdl "$target" "$data.tmp" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$seed" \
          --nnue "$PILOT" --search-params-play "$L3_SEARCH_PARAMS" --wdl-zero-score \
          --seed-file "$seed_file" --seed-frac 100 --random-open-plies "$RANDOM_OPEN_PLIES" \
          --explore-eps "$EXPLORE_EPS" --explore-decay-plies "$EXPLORE_DECAY_PLIES" \
          "${pair_flags[@]}" --drop-plycap --sample-meta-out "$meta" "${sampling_flags[@]}"
        python3 jobs/tools/prepare_imbalance2_training.py encode --input "$data.tmp" --output "$data" \
          --advantaged-side "$adv" --report "$report"
        rm -f "$data.tmp"
      ) > "$log" 2>&1 &
      pids+=("$!"); part=$((part + 1))
    done
    logical=$((logical + 1))
  done
  run_pids "G$generation producers" "${pids[@]}"
  for log in "$W/g${generation}.p"*.log; do
    grep -q 'label_score_searches=0' "$log" || die "zero-score proof missing: $log"
    grep -q 'seed_frac=100%' "$log" || die "seed-only proof missing: $log"
  done
  python3 tools/selfplay_frontier.py merge "${merge_args[@]}" --out-data "$W/g${generation}.raw.jnnw" \
    --out-meta "$W/g${generation}.raw.jsm" --manifest "$ART/g${generation}-merge.json" > "$W/g${generation}-merge.log" 2>&1
  python3 jobs/tools/aggregate_l3_exploration.py --log "${rollout_logs[@]}" \
    --expected-random-open "$RANDOM_OPEN_PLIES" --expected-eps "$EXPLORE_EPS" --expected-decay "$EXPLORE_DECAY_PLIES" \
    --manifest "$ART/g${generation}-exploration.json" > "$W/g${generation}-exploration.log" 2>&1
  python3 tools/selfplay_frontier.py profile --data "$W/g${generation}.raw.jnnw" --meta "$W/g${generation}.raw.jsm" \
    --manifest "$ART/g${generation}-profile.json" > "$W/g${generation}-profile.log" 2>&1
  python3 tools/selfplay_frontier.py split --data "$W/g${generation}.raw.jnnw" --meta "$W/g${generation}.raw.jsm" \
    --out-data "$W/g${generation}.fit.jnnw" --out-meta "$W/g${generation}.fit.jsm" \
    --holdout-mod "$HOLDOUT_MOD" --seed "$BASE_SEED" --manifest "$ART/g${generation}-split.json" > "$W/g${generation}-split.log" 2>&1
  HOLDOUT_COUNT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/g${generation}-split.json")"
  [ "$HOLDOUT_COUNT" -gt 0 ] || die "empty holdout"
  if [ "$SEED_CLEAN" = 1 ]; then
    cp "$W/g${generation}.fit.jnnw" "$W/g${generation}.weighted.jnnw"
    python3 - "$W/g${generation}.weighted.jnnw" "$HOLDOUT_COUNT" "$ART/g${generation}-reweight.json" <<'PY'
import json,struct,sys
from pathlib import Path
raw=Path(sys.argv[1]).read_bytes(); n=struct.unpack_from('<I',raw,4)[0]
Path(sys.argv[3]).write_text(json.dumps({'schema':1,'mode':'natural_unweighted_wdl','records':n,'holdout_records':int(sys.argv[2]),'resampling_applied':False},indent=2,sort_keys=True)+'\n')
PY
  else
    python3 jobs/tools/prepare_imbalance2_training.py reweight --input "$W/g${generation}.fit.jnnw" \
      --output "$W/g${generation}.weighted.jnnw" --holdout-count "$HOLDOUT_COUNT" \
      --win-weight "$WIN_WEIGHT" --draw-weight "$DRAW_WEIGHT" --loss-weight "$LOSS_WEIGHT" \
      --seed $((BASE_SEED + generation)) --report "$ART/g${generation}-reweight.json"
  fi
  "$J" --dump-eval-features "$W/g${generation}.weighted.jnnw" "$W/g${generation}.feat" > "$W/g${generation}-features.log" 2>&1
  warm=(--warm-start "$PILOT"); [ "$generation" -eq 1 ] && warm=()
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/train_stream.py \
    --data "$W/g${generation}.weighted.jnnw" --feat "$W/g${generation}.feat" --out "$W/g${generation}.pjtw" \
    --target wdl --loss logistic --color-fold --tempo-stage "${warm[@]}" --holdout-count "$HOLDOUT_COUNT" \
    --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" > "$W/g${generation}-train.log" 2>&1
  [ -s "$W/g${generation}.pjtw" ] || die "G$generation student missing"
  gzip -n -c "$W/g${generation}.pjtw" > "$ART/g${generation}.pjtw.gz"
  gzip -n -c "$W/g${generation}.raw.jnnw" > "$ART/g${generation}-source.jnnw.gz"
  gzip -n -c "$W/g${generation}.raw.jsm" > "$ART/g${generation}-source.jsm.gz"
  PILOT="$W/g${generation}.pjtw"
  say "G$generation complete: strata=16v18,17v19,18v20 source_records=$FRESH selfplay_only=1"
done

run_eval(){
  local model_label="$1" pattern="$2" pool_label="$3"
  local pool="$POOLS/top3-${pool_label}.jnnw" meta="$POOLS/top3-${pool_label}.json" pids=() shard
  for shard in $(seq 0 $((EVAL_SHARDS - 1))); do
    timeout "$EVAL_SHARD_TIMEOUT" python3 jobs/tools/imbalance2_scan_gate.py run --engine candidate --jass "$J" --pattern "$pattern" \
      --pool "$pool" --meta "$meta" --search-params "$L3_SEARCH_PARAMS" --depth "$PLAY_DEPTH" --max-plies 400 \
      --shard "$shard" --nshards "$EVAL_SHARDS" --out "$ART/eval-${model_label}-${pool_label}-s${shard}.json" \
      > "$W/eval-${model_label}-${pool_label}-s${shard}.log" 2>&1 &
    pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR_EVAL" ]; then run_pids "eval $model_label/$pool_label" "${pids[@]}"; pids=(); fi
  done
  [ "${#pids[@]}" -eq 0 ] || run_pids "eval $model_label/$pool_label final" "${pids[@]}"
}
{ echo "stage=evaluation"; echo "final_model=g${GENERATIONS}"; echo "paired_games_target=384"; } > "$PROG"
run_eval g0 "$W/g0-material.pjtw" a
run_eval g0 "$W/g0-material.pjtw" b
FINAL_MODEL="g${GENERATIONS}"
run_eval "$FINAL_MODEL" "$W/${FINAL_MODEL}.pjtw" a
run_eval "$FINAL_MODEL" "$W/${FINAL_MODEL}.pjtw" b

python3 - "$ART" "$FINAL_MODEL" "$SEED_CLEAN" <<'PY'
import json,random,sys
from collections import defaultdict
from pathlib import Path
art=Path(sys.argv[1]); final=sys.argv[2]; seed_clean=bool(int(sys.argv[3])); cats=('win','draw','loss'); cost={'win':0.0,'draw':1.0,'loss':2.0}
def load(model):
    out={}; errors=[]
    for path in sorted(art.glob(f'eval-{model}-*-s*.json')):
        pool=path.name.split('-')[2]
        payload=json.loads(path.read_text())
        for row in payload['rows']:
            key=(pool,int(row['index']))
            if key in out: raise SystemExit(f'duplicate {model} key {key}')
            if 'error' in row: errors.append({'key':key,'error':row['error']}); continue
            out[key]=row
    return out,errors
def rates(rows,key):
    n=len(rows); return {c:sum(r[key]==c for r in rows)/n for c in cats}
def interval(values):
    values=sorted(values); n=len(values); return [values[int(.025*(n-1))],values[int(.975*(n-1))]]
g0,e0=load('g0'); student,e1=load(final); keys=sorted(set(g0)|set(student)); rows=[]
for key in keys:
    if key not in g0 or key not in student: continue
    rows.append({'pool':key[0],'index':key[1],'stratum':student[key]['stratum'],'g0':g0[key]['outcome'],final:student[key]['outcome']})
if len(rows)!=384: raise SystemExit(f'expected 384 paired rows, got {len(rows)}')
r0=rates(rows,'g0'); r1=rates(rows,final)
c0=sum(cost[r['g0']] for r in rows)/len(rows); c1=sum(cost[r[final]] for r in rows)/len(rows)
rng=random.Random(271828); win_delta=[]; cost_delta=[]
for _ in range(5000):
    sample=[rows[rng.randrange(len(rows))] for _ in rows]
    win_delta.append(sum(r[final]=='win' for r in sample)/len(sample)-sum(r['g0']=='win' for r in sample)/len(sample))
    cost_delta.append(sum(cost[r[final]]-cost[r['g0']] for r in sample)/len(sample))
strata={}; groups=defaultdict(list); pools=defaultdict(list)
for row in rows: groups[row['stratum']].append(row); pools[row['pool']].append(row)
for name in sorted(groups): strata[name]={'n':len(groups[name]),'g0':rates(groups[name],'g0'),final:rates(groups[name],final)}
pool_report={name:{'n':len(group),'g0':rates(group,'g0'),final:rates(group,final)} for name,group in sorted(pools.items())}
no_errors=not e0 and not e1
target_reached=no_errors and r1['win']>=0.80 and all(v[final]['win']>=0.75 for v in strata.values()) and c1<c0
screen_signal=no_errors and (r1['win']-r0['win'])>=0.02 and c1<c0
signal=screen_signal if seed_clean else target_reached
decision='SEED_CLEAN_SCREEN_SIGNAL' if seed_clean and signal else ('SEED_CLEAN_SCREEN_NO_SIGNAL' if seed_clean else ('TOP3_SPECIALIZATION_SIGNAL' if signal else 'TOP3_TARGET_NOT_REACHED'))
payload={'schema':1,'lineage':'L3-IMBALANCE2-TOP3','protocol':'seed-clean-screen' if seed_clean else 'standard-top3','final_model':final,'decision':decision,'pass':signal,'paired_games':len(rows),
 'hypothesis':'material-up win rate around 0.80-0.90 on 16v18,17v19,18v20',
 'g0':r0,final:r1,f'{final}_in_80_90_band':0.80<=r1['win']<=0.90,f'{final}_minus_g0_win_rate':r1['win']-r0['win'],
 f'{final}_minus_g0_win_rate_bootstrap_95':interval(win_delta),'failure_cost_2loss_plus_draw':{'g0':c0,final:c1,'delta':c1-c0,'bootstrap_95':interval(cost_delta)},
 'strata':strata,'pools':pool_report,'errors':{'g0':e0,final:e1},
 'target_reached':target_reached,'screen_signal':screen_signal,
 'criteria':({'student_minus_g0_win_min':0.02,'student_cost_below_g0':True,'max_errors':0} if seed_clean else {f'global_{final}_win_min':0.80,f'each_stratum_{final}_win_min':0.75,f'{final}_cost_below_g0':True,'max_errors':0}),
 'promotion_authorized':False,'training_continuation_authorized':False,'automatic_next_job':None}
(art/'top3-selfplay-decision.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/f'VERDICT__{decision}').write_text(decision+'\n')
(art/'PROMOTION_AUTHORIZED__FALSE').write_text('promotion_authorized=false\n')
(art/'TRAINING_CONTINUATION_AUTHORIZED__FALSE').write_text('training_continuation_authorized=false\n')
print(decision)
PY

python3 - "$ART" "$EXPECTED_CODE_SHA" "$L3_SEARCH_PARAMS" "$GENERATIONS" "$FRESH" "$RANDOM_OPEN_PLIES" "$EXPLORE_EPS" "$EXPLORE_DECAY_PLIES" "$SEED_CLEAN" <<'PY'
import hashlib,json,sys
from pathlib import Path
art=Path(sys.argv[1]); sha=sys.argv[2]; search=sys.argv[3]; generations=int(sys.argv[4]); fresh=int(sys.argv[5]); random_open=int(sys.argv[6]); eps=int(sys.argv[7]); decay=int(sys.argv[8]); seed_clean=bool(int(sys.argv[9]))
students={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(art.glob('g[1-4].pjtw.gz'))}
decision=json.loads((art/'top3-selfplay-decision.json').read_text())
payload={'schema':1,'lineage':'L3-IMBALANCE2-TOP3','phase':'SEED_CLEAN_SCREEN' if seed_clean else 'P1','generation_range':[1,generations],'play_depth':8,'code_sha':sha,
 'source_positions_per_generation':fresh,'start_strata':['16v18','17v19','18v20'],
 'start_distribution':'equal per stratum and balanced initial advantaged colour','trajectory_policy':'terminal WDL self-play only; no static TB teacher',
 'external_teacher_used':False,'egdb_training_labels_used':False,'scan_used_for_training':False,'gen2_used_for_training':False,
 'geometry':'8cf','search_params':search,'search_params_count':len(search.split(',')),
 'recipe':{'bootstrap':'G0 material men=1 king=3','fresh_corpus_only':True,'random_open_plies':random_open,'epsilon_percent':eps,'explore_decay_plies':decay,
 'quiet_only':seed_clean,'sample_initial':seed_clean,'pair_openings':not seed_clean,'natural_unweighted_wdl':seed_clean,
 'fit':{'target':'wdl','loss':'logistic','color_fold':True,'tempo_stage':True,'l2':3e-5,'max_iter':25,'chunk':500000,
 'role_aware_fixed_resampling':None if seed_clean else {'expected':1,'draw':2,'upset':4}},'primary_seed':271828},
 'evaluation':decision,'student_sha256':students,'promotion_authorized':False,'training_continuation_authorized':False,'automatic_next_job':None}
(art/'l3-imbalance2-top3-p1-manifest.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
DECISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["decision"])' "$ART/top3-selfplay-decision.json")"
say "=== L3-IMBALANCE2-TOP3 complete: $DECISION; no automatic continuation ==="
