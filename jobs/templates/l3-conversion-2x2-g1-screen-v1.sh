#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# One-generation 2x2 ablation: standard/TOP3 starts x role-aware V2 off/on.
# Each off/on pair shares byte-identical self-play and split data.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${EXPECTED_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?}"
: "${SCAN_BIN:?}"
: "${EXPECTED_SCAN_SHA256:?}"
: "${EXPECTED_SCAN_RUNTIME_SHA256:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
GEOM="$W/geom8"
POOLS="$W/top3-seeds"
INPUTS="$W/inputs"
MATRIX="$W/matrix"
BALANCED="$W/balanced"
mkdir -p "$W" "$ART" "$GEOM" "$POOLS" "$INPUTS" "$MATRIX" "$BALANCED"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

FRESH=500000
NSHARDS_STANDARD=8
TOP3_PRODUCERS=6
PLAY_DEPTH=8
LABEL_DEPTH=4
MAXPLIES=260
BASE_SEED=271828
RANDOM_OPEN_PLIES=8
EXPLORE_EPS=8
EXPLORE_DECAY_PLIES=60
HOLDOUT_MOD=10
L2=3e-5
MAXIT=25
CHUNK=500000
GEN_SHARD_TIMEOUT=2700
MATRIX_SHARD_TIMEOUT=900
BALANCED_SHARD_TIMEOUT=900
JASS_BUILD_JOBS=4
BOOTSTRAP=10000
BALANCED_OPENINGS=64
BALANCED_GAMES=128
POOL_PREFIX="r2:jass-data/runs/cpx62-0921-l3-pure-top3-stable-conversion-matrix-v1/20260723T134611Z-fbf0c93e"
POOL_SHA256="dfdbc788b715c7faab1c2e1dc1a1a7a7f7016eb1c4920b3544deacf973b569d0"
PROOF_SHA256="70daef6cd5a4c9c57d48c0afaaa4622092a25141b70fc8ce3a838e073b2a9e02"
SEARCH_SHA256="61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1"
CANDIDATES=(standard_off standard_on top3_off top3_on)
MATRIX_ARMS=(g4_g0 g0_g4 g4_g4)
TOTAL_MATRIX_GAMES=$((384 * (1 + 4 * 3)))

L3_SEARCH_PARAMS="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
PHASE="$W/phase.txt"
: > "$RES"
: > "$PROG"
printf '%s\n' initializing > "$PHASE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
set_phase(){ printf '%s\n' "$1" > "$PHASE.tmp"; mv "$PHASE.tmp" "$PHASE"; }

MONITOR_PID=""
ACTIVE_PIDS=()
SOURCE_BACKUPS=()
SOURCE_PATHS=()

restore_src(){
  local index
  for index in "${!SOURCE_PATHS[@]}"; do
    [ -f "${SOURCE_BACKUPS[$index]}" ] || continue
    cp "${SOURCE_BACKUPS[$index]}" "${SOURCE_PATHS[$index]}"
  done
}
stop_monitor(){
  [ -n "$MONITOR_PID" ] || return 0
  kill "$MONITOR_PID" 2>/dev/null || true
  wait "$MONITOR_PID" 2>/dev/null || true
  MONITOR_PID=""
}
start_monitor(){
  local started="$1"
  (
    while true; do
      python3 - "$W" "$started" "$PROG.tmp" "$PHASE" "$TOTAL_MATRIX_GAMES" <<'PY'
import datetime as dt, glob, json, os, sys, time
root, started, out, phase_path, matrix_total = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4], int(sys.argv[5])
try:
    phase = open(phase_path, encoding="utf-8").read().strip()
except OSError:
    phase = "unknown"
completed = 0
for path in glob.glob(os.path.join(root, "matrix", "**", "*.progress.json"), recursive=True):
    try:
        completed += int(json.load(open(path, encoding="utf-8")).get("completed", 0))
    except (OSError, ValueError):
        pass
elapsed = max(time.time() - started, 0.001)
now = dt.datetime.now(dt.timezone(dt.timedelta(hours=2)))
with open(out, "w", encoding="utf-8") as handle:
    handle.write(f"time_fr={now.isoformat()}\nphase={phase}\nelapsed_s={elapsed:.0f}\n")
    handle.write(f"matrix_games={completed}/{matrix_total}\n")
    for pattern in ("standard.s*.log", "top3.p*.log"):
        sizes = sum(os.path.getsize(p) for p in glob.glob(os.path.join(root, pattern)))
        handle.write(f"log_bytes_{pattern.split('.')[0]}={sizes}\n")
PY
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/.PROGRESS.txt.tmp"
      mv "$ART/.PROGRESS.txt.tmp" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MONITOR_PID="$!"
}
run_pids(){
  local label="$1"; shift
  local failed=0 pid
  ACTIVE_PIDS=("$@")
  for pid in "$@"; do wait "$pid" || failed=$((failed + 1)); done
  ACTIVE_PIDS=()
  [ "$failed" -eq 0 ] || die "$label: $failed failed/timed-out process(es)"
}
finalize(){
  rc=$?
  trap - EXIT ERR INT TERM
  set +e
  stop_monitor
  if [ "${#ACTIVE_PIDS[@]}" -gt 0 ]; then
    kill "${ACTIVE_PIDS[@]}" 2>/dev/null || true
    for pid in "${ACTIVE_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
  fi
  restore_src
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  [ -d "$MATRIX" ] && tar -C "$W" -czf "$ART/conversion-2x2-matrix-raw.tar.gz" matrix 2>/dev/null || true
  [ -d "$BALANCED" ] && tar -C "$W" -czf "$ART/conversion-2x2-balanced-raw.tar.gz" balanced 2>/dev/null || true
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$INPUTS" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 130' INT
trap 'exit 143' TERM

say "=== $JASS_JOB_ID — L3 conversion 2x2 G1 screen ==="
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ -z "$(git branch --show-current)" ] || die "code worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${CONVERSION_2X2_GO:-0}" = 1 ] || die "CONVERSION_2X2_GO=1 missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "NO_AUTOMATIC_CONTINUATION=1 missing"
[ "$FRESH" -eq 500000 ] || die "each source distribution requires 500000 records"
[ "$NSHARDS_STANDARD" -eq 8 ] && [ "$TOP3_PRODUCERS" -eq 6 ] || die "producer contract mismatch"
[ "$PLAY_DEPTH" -eq 8 ] && [ "$LABEL_DEPTH" -eq 4 ] && [ "$MAXPLIES" -eq 260 ] || die "play contract mismatch"
[ "$GEN_SHARD_TIMEOUT" -eq 2700 ] || die "generation timeout drift"
[ "$MATRIX_SHARD_TIMEOUT" -eq 900 ] && [ "$BALANCED_SHARD_TIMEOUT" -eq 900 ] || die "evaluation timeout drift"
[ "$BOOTSTRAP" -eq 10000 ] && [ "$BALANCED_GAMES" -eq 128 ] || die "reporting contract drift"

JOB_STARTED_EPOCH="$(date +%s)"
start_monitor "$JOB_STARTED_EPOCH"
set_phase preflight

find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
NPROC="$(nproc)"
[ "$NPROC" -eq 16 ] || die "CPX62 nproc drift: expected 16, got $NPROC"
MEM_MB="$(awk '/MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo)"
[ "${MEM_MB:-0}" -ge 30000 ] || die "requires CPX62 >=30 GiB"
FREE_MB="$(df -Pm /root | awk 'NR==2 {print $4}')"
[ "${FREE_MB:-0}" -gt 10000 ] || die "free disk below 10 GiB"
[ -x "$SCAN_BIN" ] || die "Scan binary missing"
[ "$(sha256sum "$SCAN_BIN" | awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] || die "Scan SHA mismatch"
[ "$(printf '%s' "$L3_SEARCH_PARAMS" | sha256sum | awk '{print $1}')" = "$SEARCH_SHA256" ] || die "search fingerprint mismatch"
say "sizing: nproc=16 source=2x500000 shared pairwise; producers=8+6 concurrent; anchor_0842=4x500k/985s; anchor_0890bis=4x2M/22821s_ccx33; ETA=30-45min; hard_cap=60min"
say "preflight: mem_mb=$MEM_MB free_mb=$FREE_MB gen_timeout=${GEN_SHARD_TIMEOUT}s matrix_timeout=${MATRIX_SHARD_TIMEOUT}s"

set_phase smoke_tests
bash -n "$0"
python3 -m py_compile \
  jobs/tools/l3_conversion_2x2_report.py \
  jobs/tools/stable_conversion_matrix.py \
  jobs/tools/prepare_imbalance2_training.py \
  jobs/tools/fetch_result_files.py \
  jobs/tools/jass_vs_jass_arch.py \
  tools/selfplay_frontier.py
python3 jobs/tests/test_l3_conversion_2x2_report.py > "$W/test-2x2-report.log" 2>&1 \
  || die "2x2 report round-trip tests failed"
python3 jobs/tests/test_l3_conversion_2x2_job.py > "$W/test-2x2-job.log" 2>&1 \
  || die "2x2 job contract tests failed"
python3 jobs/tests/test_stable_conversion_matrix.py > "$W/test-matrix.log" 2>&1 \
  || die "stable matrix tests failed"
say "smoke: bash syntax + python compile + reporting/matrix round-trip OK"

set_phase architecture_build
for source in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
  backup="$W/original-$(basename "$source")"
  cp "$source" "$backup"
  SOURCE_PATHS+=("$source")
  SOURCE_BACKUPS+=("$backup")
  git show "$EXPECTED_CODE_SHA:$source" > "$source"
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
J="$W/build/jass"
[ -x "$J" ] || die "jass binary missing"

python3 pattern_jass/tools/make_bootstrap_eval.py \
  --out "$W/g0-material.pjtw" --n-pat "$NPAT" --n-ext 120 \
  --men 1 --king 3 --king-center 0 --mobility 0 > "$W/g0.log" 2>&1
gzip -n -c "$W/g0-material.pjtw" > "$ART/g0-material.pjtw.gz"

set_phase fetch_stable_pool
python3 jobs/tools/fetch_result_files.py --prefix "$POOL_PREFIX" \
  --file artefacts/stable-top3.fen=stable-top3.fen \
  --file artefacts/stable-top3.proof.jsonl=stable-top3.proof.jsonl \
  --file artefacts/pool-contract.json=pool-contract.json \
  --out-dir "$INPUTS" --report "$ART/verified-0921-pool.json" > "$W/fetch-pool.log" 2>&1
[ "$(sha256sum "$INPUTS/stable-top3.fen" | awk '{print $1}')" = "$POOL_SHA256" ] || die "pool SHA mismatch"
[ "$(sha256sum "$INPUTS/stable-top3.proof.jsonl" | awk '{print $1}')" = "$PROOF_SHA256" ] || die "proof SHA mismatch"
cp "$INPUTS/stable-top3.fen" "$ART/stable-top3.fen"
cp "$INPUTS/stable-top3.proof.jsonl" "$ART/stable-top3.proof.jsonl"
cp "$INPUTS/pool-contract.json" "$ART/pool-contract.json"

set_phase generate_shared_G1_corpora
python3 jobs/tools/make_imbalance2_pools.py --out-dir "$POOLS" \
  --train-per-side 2048 --bench-per-stratum 64 --plateau-per-stratum 1 \
  --seed "$BASE_SEED" > "$W/make-top3-pools.log" 2>&1

pids=()
std_merge_args=()
std_per_shard=$((FRESH / NSHARDS_STANDARD))
for shard in $(seq 0 $((NSHARDS_STANDARD - 1))); do
  data="$W/standard.s${shard}.jnnw"
  meta="$W/standard.s${shard}.jsm"
  log="$W/standard.s${shard}.log"
  seed=$((BASE_SEED + 10000 + shard))
  timeout "$GEN_SHARD_TIMEOUT" "$J" --gen-data-wdl \
    "$std_per_shard" "$data" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$seed" \
    --nnue "$W/g0-material.pjtw" --search-params-play "$L3_SEARCH_PARAMS" \
    --wdl-zero-score --random-open-plies "$RANDOM_OPEN_PLIES" \
    --explore-eps "$EXPLORE_EPS" --explore-decay-plies "$EXPLORE_DECAY_PLIES" \
    --pair-openings --drop-plycap --sample-meta-out "$meta" > "$log" 2>&1 &
  pids+=("$!")
  std_merge_args+=(--pair "$data" "$meta")
done

top_merge_args=()
base_per_stratum=$((FRESH / 3))
remainder=$((FRESH % 3))
part=0
logical=0
for low in 16 17 18; do
  high=$((low + 2))
  target_stratum="$base_per_stratum"
  [ "$logical" -lt "$remainder" ] && target_stratum=$((target_stratum + 1))
  target_w=$(( (target_stratum + 1) / 2 ))
  target_b=$(( target_stratum - target_w ))
  for adv in W B; do
    target="$target_w"; [ "$adv" = B ] && target="$target_b"
    data="$W/top3.p${part}.jnnw"
    meta="$W/top3.p${part}.jsm"
    log="$W/top3.p${part}.log"
    report="$ART/top3-p${part}-outcome.json"
    seed=$((BASE_SEED + 100000 + part))
    seed_file="$(printf '%s/train-%02dv%02d-up%s.jnnw' "$POOLS" "$low" "$high" "$adv")"
    (
      timeout "$GEN_SHARD_TIMEOUT" "$J" --gen-data-wdl \
        "$target" "$data.tmp" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$seed" \
        --nnue "$W/g0-material.pjtw" --search-params-play "$L3_SEARCH_PARAMS" \
        --wdl-zero-score --seed-file "$seed_file" --seed-frac 100 \
        --random-open-plies "$RANDOM_OPEN_PLIES" --explore-eps "$EXPLORE_EPS" \
        --explore-decay-plies "$EXPLORE_DECAY_PLIES" --pair-openings \
        --drop-plycap --sample-meta-out "$meta"
      python3 jobs/tools/prepare_imbalance2_training.py encode \
        --input "$data.tmp" --output "$data" --advantaged-side "$adv" --report "$report"
      rm -f "$data.tmp"
    ) > "$log" 2>&1 &
    pids+=("$!")
    top_merge_args+=(--pair "$data" "$meta")
    part=$((part + 1))
  done
  logical=$((logical + 1))
done
[ "${#pids[@]}" -eq 14 ] || die "expected 14 concurrent producers, got ${#pids[@]}"
run_pids "shared G1 source generation" "${pids[@]}"

for log in "$W/standard.s"*.log "$W/top3.p"*.log; do
  grep -q 'label_score_searches=0' "$log" || die "zero-score proof missing: $log"
done
for log in "$W/top3.p"*.log; do
  grep -q 'seed_frac=100%' "$log" || die "TOP3 seed-only proof missing: $log"
done

python3 tools/selfplay_frontier.py merge "${std_merge_args[@]}" \
  --out-data "$W/standard.raw.jnnw" --out-meta "$W/standard.raw.jsm" \
  --manifest "$ART/standard-merge.json" > "$W/standard-merge.log" 2>&1
python3 tools/selfplay_frontier.py merge "${top_merge_args[@]}" \
  --out-data "$W/top3.raw.jnnw" --out-meta "$W/top3.raw.jsm" \
  --manifest "$ART/top3-merge.json" > "$W/top3-merge.log" 2>&1

prepare_distribution(){
  local distribution="$1"
  python3 tools/selfplay_frontier.py profile \
    --data "$W/$distribution.raw.jnnw" --meta "$W/$distribution.raw.jsm" \
    --manifest "$ART/$distribution-profile.json" > "$W/$distribution-profile.log" 2>&1
  python3 tools/selfplay_frontier.py split \
    --data "$W/$distribution.raw.jnnw" --meta "$W/$distribution.raw.jsm" \
    --out-data "$W/$distribution.fit.jnnw" --out-meta "$W/$distribution.fit.jsm" \
    --holdout-mod "$HOLDOUT_MOD" --seed "$BASE_SEED" \
    --manifest "$ART/$distribution-split.json" > "$W/$distribution-split.log" 2>&1
  local holdout
  holdout="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/$distribution-split.json")"
  [ "$holdout" -gt 0 ] || die "$distribution empty holdout"
  IMBALANCE2_REWEIGHT_POLICY=role-aware-v2 \
    python3 jobs/tools/prepare_imbalance2_training.py reweight \
      --input "$W/$distribution.fit.jnnw" --output "$W/$distribution.on.jnnw" \
      --holdout-count "$holdout" --win-weight 1 --draw-weight 2 --loss-weight 4 \
      --seed $((BASE_SEED + 1)) --report "$ART/$distribution-on-reweight.json"
  python3 - "$ART/$distribution-off-reweight.json" "$distribution" "$holdout" <<'PY'
import json, sys
json.dump({
    "schema": 1, "distribution": sys.argv[2], "policy": "off",
    "training_mode": "natural_unweighted_WDL",
    "holdout_records_untouched": int(sys.argv[3]),
}, open(sys.argv[1], "w", encoding="utf-8"), indent=2, sort_keys=True)
open(sys.argv[1], "a", encoding="utf-8").write("\n")
PY
  gzip -n -c "$W/$distribution.raw.jnnw" > "$ART/$distribution-source.jnnw.gz"
  gzip -n -c "$W/$distribution.raw.jsm" > "$ART/$distribution-source.jsm.gz"
}
prepare_distribution standard
prepare_distribution top3

train_cell(){
  local candidate="$1" distribution="$2" mode="$3"
  local data="$W/$distribution.fit.jnnw"
  [ "$mode" = on ] && data="$W/$distribution.on.jnnw"
  local holdout
  holdout="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/$distribution-split.json")"
  "$J" --dump-eval-features "$data" "$W/$candidate.feat" > "$W/$candidate-features.log" 2>&1
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    python3 pattern_jass/tools/train_stream.py \
      --data "$data" --feat "$W/$candidate.feat" --out "$W/$candidate.pjtw" \
      --target wdl --loss logistic --color-fold --tempo-stage \
      --holdout-count "$holdout" --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
      > "$W/$candidate-train.log" 2>&1
  [ -s "$W/$candidate.pjtw" ] || die "$candidate model missing"
  gzip -n -c "$W/$candidate.pjtw" > "$ART/$candidate.pjtw.gz"
}

set_phase train_four_G1_cells
train_cell standard_off standard off
train_cell standard_on standard on
train_cell top3_off top3 off
train_cell top3_on top3 on

python3 - "$ART/2x2-training-manifest.json" "$EXPECTED_CODE_SHA" "$L3_SEARCH_PARAMS" "$W" "$ART" <<'PY'
import hashlib, json, sys
from pathlib import Path
out, code, search, work_name, art_name = sys.argv[1:]
work, art = Path(work_name), Path(art_name)
profiles = {d: json.loads((art/f"{d}-profile.json").read_text()) for d in ("standard","top3")}
splits = {d: json.loads((art/f"{d}-split.json").read_text()) for d in ("standard","top3")}
reweights = {d: json.loads((art/f"{d}-on-reweight.json").read_text()) for d in ("standard","top3")}
models = {}
for candidate in ("standard_off","standard_on","top3_off","top3_on"):
    raw=(work/f"{candidate}.pjtw").read_bytes()
    models[candidate]={"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
payload={
 "schema":1,"experiment":"L3-CONVERSION-2X2-G1","code_sha":code,
 "source_records_per_distribution":500000,"generations":1,"play_depth":8,
 "geometry":"8cf","search_params":search,
 "search_params_sha256":hashlib.sha256(search.encode()).hexdigest(),
 "factors":{"start":["standard","TOP3"],"role_aware_v2":["off","on"]},
 "pairwise_source_reuse":{"standard_off_on":True,"top3_off_on":True},
 "profiles":profiles,"splits":splits,"reweights":reweights,"models":models,
 "promotion_authorized":False,"training_continuation_authorized":False,
 "automatic_next_job":None,
}
Path(out).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
PY

run_matrix_arm(){
  local candidate="$1" arm="$2" pattern="$3"
  local dir="$MATRIX/$candidate/$arm" shard pids=()
  mkdir -p "$dir"
  for shard in $(seq 0 15); do
    timeout "$MATRIX_SHARD_TIMEOUT" python3 jobs/tools/stable_conversion_matrix.py run \
      --pool "$INPUTS/stable-top3.fen" --proof "$INPUTS/stable-top3.proof.jsonl" \
      --arm "$arm" --shard-index "$shard" --nshards 16 --depth 10 \
      --max-plies 400 --game-timeout 120 --jass "$J" --scan "$SCAN_BIN" \
      --scan-runtime-sha256 "$EXPECTED_SCAN_RUNTIME_SHA256" \
      --g0 "$W/g0-material.pjtw" --g4 "$pattern" \
      --search-params "$L3_SEARCH_PARAMS" --output "$dir/s${shard}.jsonl" \
      --progress-file "$dir/s${shard}.progress.json" > "$dir/s${shard}.log" 2>&1 &
    pids+=("$!")
  done
  run_pids "matrix $candidate/$arm" "${pids[@]}"
}

set_phase stable_TOP3_matrix_4992_games
run_matrix_arm common g0_g0 "$W/g0-material.pjtw"
for candidate in "${CANDIDATES[@]}"; do
  for arm in "${MATRIX_ARMS[@]}"; do
    run_matrix_arm "$candidate" "$arm" "$W/$candidate.pjtw"
  done
done

set_phase balanced_guard_512_games
python3 - data/dilf_combinations.fen "$W/balanced-64.fen" "$BALANCED_OPENINGS" "$BASE_SEED" <<'PY'
import random, sys
rows=[]
for raw in open(sys.argv[1],encoding="utf-8"):
    line=raw.split("#",1)[0].strip()
    if line and line[0] in "WB" and ":W" in line and ":B" in line:
        rows.append(line)
want=int(sys.argv[3])
if len(rows)<want: raise SystemExit(f"need {want} balanced openings, got {len(rows)}")
chosen=random.Random(int(sys.argv[4])).sample(rows,want)
open(sys.argv[2],"w",encoding="utf-8").write("\n".join(chosen)+"\n")
PY
for candidate in "${CANDIDATES[@]}"; do
  dir="$BALANCED/$candidate"
  mkdir -p "$dir"
  pids=()
  for shard in $(seq 0 7); do
    timeout "$BALANCED_SHARD_TIMEOUT" python3 jobs/tools/jass_vs_jass_arch.py \
      --jass-a "$J" --pattern-a "$W/$candidate.pjtw" \
      --jass-b "$J" --pattern-b "$W/g0-material.pjtw" \
      --depth 8 --pairs 1 --max-plies 400 --game-timeout 120 \
      --shard "$shard" --nshards 8 --quiet \
      --search-params-a "$L3_SEARCH_PARAMS" --search-params-b "$L3_SEARCH_PARAMS" \
      --openings-file "$W/balanced-64.fen" > "$dir/s${shard}.log" 2>&1 &
    pids+=("$!")
  done
  run_pids "balanced guard $candidate" "${pids[@]}"
done

set_phase aggregate_and_decide
python3 jobs/tools/l3_conversion_2x2_report.py \
  --pool "$INPUTS/stable-top3.fen" --proof "$INPUTS/stable-top3.proof.jsonl" \
  --matrix-root "$MATRIX" --balanced-root "$BALANCED" \
  --balanced-games "$BALANCED_GAMES" --balanced-floor 0.40 \
  --bootstrap "$BOOTSTRAP" --seed "$BASE_SEED" \
  --output "$ART/conversion-2x2-g1-report.json" > "$W/report.log" 2>&1

python3 - "$ART/conversion-2x2-g1-report.json" "$ART/2x2-training-manifest.json" \
  "$W/g0-material.pjtw" "$ART/VERDICT__CONVERSION_2X2_G1_SCREEN_READY" "$RES" <<'PY'
import hashlib, json, sys
report=json.load(open(sys.argv[1],encoding="utf-8"))
training=json.load(open(sys.argv[2],encoding="utf-8"))
assert report["decision"]=="CONVERSION_2X2_G1_SCREEN_READY"
assert report["technical_status"]=="complete"
assert report["contract"]["positions"]==384
assert report["contract"]["balanced_games_per_candidate"]==128
assert report["provenance"]["engine"]["g0"]==hashlib.sha256(open(sys.argv[3],"rb").read()).hexdigest()
for candidate, model in training["models"].items():
    assert report["provenance"]["candidate_g4"][candidate]==model["sha256"], candidate
open(sys.argv[4],"w",encoding="utf-8").write(report["decision"]+"\n")
with open(sys.argv[5],"a",encoding="utf-8") as out:
    out.write("decision="+report["decision"]+"\n")
    out.write("balanced_guard="+str(report["balanced_guard"]["pass"]).lower()+"\n")
    out.write("factor_signals="+str(len(report["factor_signals_abs_ge_0_05_ci_excludes_zero"]))+"\n")
    for endpoint, factors in report["factor_effects"].items():
        out.write(endpoint+"="+json.dumps(factors,sort_keys=True)+"\n")
PY
printf '%s\n' "promotion_authorized=false" > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' "training_continuation_authorized=false" > "$ART/TRAINING_CONTINUATION_AUTHORIZED__FALSE"
printf '%s\n' "automatic_next_job=null" > "$ART/AUTOMATIC_NEXT_JOB__NULL"
set_phase complete
say "CONVERSION_2X2_G1_SCREEN_READY promotion=false continuation=false automatic_next_job=null"
