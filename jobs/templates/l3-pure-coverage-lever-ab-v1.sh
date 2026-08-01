#!/usr/bin/env bash
# L3-PURE — generic causal A/B for one self-play coverage lever.
#
# COVERAGE_LEVER must be exactly one of:
#   phase_sampling : historical 1/4 sampling vs phase-aware sampling
#   topk_softmax   : uniform vs score-softmax selection inside the same TOPK3 set
#   regret_restart : no restart vs 20% restart from a parent-regret archive
#   opening_pool   : random-8 openings vs a 50% stochastic master pool
#   replay_ratio   : 100% fresh vs 50% fresh / 50% rolling replay
#
# Except when replay itself is the tested factor, both arms use the same 50/50
# rolling mix: 1M newly generated records plus the same deterministic 1M sample
# of the authenticated post-fix UNIFORM corpus from the prerequisite. The
# replay A/B compares 2M fresh against a deterministic 1M sample of the exact
# same 2M fresh corpus plus 1M replay. The job never measures strength,
# promotes, queues a continuation, or
# selects a parent from the prerequisite run.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${COVERAGE_LEVER:?}"
: "${PREREQUISITE_PREFIX:?}"; : "${EXPECTED_PREREQUISITE_JOB:?}"
: "${TOPK_READOUT_PREFIX:?}"; : "${EXPECTED_TOPK_READOUT_JOB:?}"
: "${PARENT_TRAIN_PREFIX:?}"; : "${EXPECTED_PARENT_TRAIN_JOB:?}"
: "${PARENT_ARTEFACT:?}"; : "${PARENT_MODEL_SHA:?}"; : "${PARENT_NAME:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/stage.txt"
: > "$RES"
echo preflight > "$STAGE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" > "$STAGE"; say "phase=$1"; }

RECORDS=${RECORDS:-2000000}
FRESH_RECORDS=${FRESH_RECORDS:-1000000}
SHARDS=${SHARDS:-6}
LABEL_DEPTH=4
PLAY_DEPTH=8
MAXPLIES=260
EXPLORE_EPS=8
EXPLORE_DECAY=60
TOPK=3
EXPLORE_MARGIN=50
SOFTMAX_TEMPERATURE_CP=50
PHASE_SAMPLE_SPEC="opening=8,midgame=4,late-mid=3,endgame=2,deep-eg=1"
REGRET_SEED_FRAC=20
REGRET_MAX_POSITIONS=4000
OPENING_POOL_FRAC=50
OPENING_POOL_POSITIONS=8000
OPENING_POOL_MIN_PLY=8
OPENING_POOL_MAX_PLY=20
OPENING_POOL_MIN_PIECES=34
MASTER_CORPUS_GIT_REF=${MASTER_CORPUS_GIT_REF:-34761f9d03d93d5e2ee18a66bbddeef604e49d24}
MASTER_CORPUS_GIT_PATH=${MASTER_CORPUS_GIT_PATH:-jobs/results/0014-fetch-master-games/artefacts/master-1600.jnnw}
MASTER_CORPUS_GIT_BLOB=${MASTER_CORPUS_GIT_BLOB:-4ec127ffc32e2eee9e4a36f656ce4d97fac8d04e}
MASTER_CORPUS_MODE=${MASTER_CORPUS_MODE:-git}
MASTER_CORPUS_LOCAL_PATH=${MASTER_CORPUS_LOCAL_PATH:-}
MASTER_CORPUS_LOCAL_SHA256=${MASTER_CORPUS_LOCAL_SHA256:-}
BASE_SEED=3141592
SPLIT_SEED=1618033
MIX_SEED=1414213
HOLDOUT_MOD=10
GEN_TIMEOUT_CONTROL=${GEN_TIMEOUT_CONTROL:-5400}
GEN_TIMEOUT_TREATMENT=${GEN_TIMEOUT_TREATMENT:-6000}
FIT_TIMEOUT=${FIT_TIMEOUT:-7200}
L2=3e-5
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
CHUNK=20000
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

case "$COVERAGE_LEVER" in
  phase_sampling|topk_softmax|regret_restart|opening_pool|replay_ratio) ;;
  *) die "unsupported COVERAGE_LEVER=$COVERAGE_LEVER" ;;
esac

MON=""
monitor(){
  (
    local t0; t0=$(date +%s)
    while true; do
      {
        local elapsed; elapsed=$(( ($(date +%s) - t0) / 60 ))
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'lever=%s\nelapsed_min=%d\n' "$COVERAGE_LEVER" "$elapsed"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in control treatment; do
          awk -v a="$arm" '
            /positions$/ { done[FILENAME]=$4; total[FILENAME]=$6 }
            END {
              for (k in done) { d+=done[k]; t+=total[k] }
              if (t>0) printf "%s_positions=%d/%d (%.1f%%)\n",a,d,t,100*d/t
            }' "$W"/"$arm"-s*.log 2>/dev/null || true
          [ -f "$W/fit-$arm.log" ] &&
            printf 'fit_%s_lines=%s\n' "$arm" "$(wc -l < "$W/fit-$arm.log")"
        done
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MON="$!"
}

finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$W/venv" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

phase preflight
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$RECORDS" -eq 2000000 ] || die "causal contract requires 2M records per arm"
[ "$FRESH_RECORDS" -eq 1000000 ] ||
  die "replay contract requires 1M fresh records per arm"
[ "$SHARDS" -eq 6 ] || die "causal contract requires 6 shards per arm"
[ "$(nproc)" -ge 12 ] || die "HOME requires at least 12 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 22000 ] ||
  die "need 22 GiB free"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
grep -q -- "--sample-rate-by-phase" src/main.cpp ||
  die "code lacks phase-aware sampling"
grep -q -- "--explore-temperature-cp" src/main.cpp ||
  die "code lacks Top-K softmax"
grep -q '"mine-regret"' tools/selfplay_frontier.py ||
  die "code lacks regret archive miner"
grep -q -- "--opening-pool-frac" src/main.cpp ||
  die "code lacks stochastic opening pool"
test -f tools/build_master_opening_pool.py ||
  die "master opening pool builder missing"
monitor

phase fetch-and-authenticate-prerequisite
python3 jobs/tools/fetch_result_files.py --prefix "$PREREQUISITE_PREFIX" \
  --expected-state completed \
  --file artefacts/JASS_CONTROL_SUMMARY.json=prerequisite.json \
  --out-dir "$IN" --report "$ART/verified-prerequisite.json" \
  > "$W/fetch-prerequisite.log" 2>&1
python3 - "$ART/verified-prerequisite.json" "$IN/prerequisite.json" \
  "$EXPECTED_PREREQUISITE_JOB" <<'PY'
import json
import sys
verified = json.load(open(sys.argv[1]))
summary = json.load(open(sys.argv[2]))
if verified.get("job_id") != sys.argv[3] or verified.get("result_state") != "completed":
    raise SystemExit("prerequisite identity/state mismatch")
if summary.get("verdict") != "L3_PURE_TOPK_CAUSAL_AB_ARMS_READY":
    raise SystemExit("prerequisite arms are not valid")
if summary.get("promotion_authorized") is not False:
    raise SystemExit("prerequisite promotion guard drift")
if summary.get("automatic_next_job") is not None:
    raise SystemExit("prerequisite automatic continuation drift")
PY

phase fetch-and-authenticate-topk-readout-closure
python3 jobs/tools/fetch_result_files.py --prefix "$TOPK_READOUT_PREFIX" \
  --expected-state completed \
  --file artefacts/JASS_CONTROL_SUMMARY.json=topk-readout.json \
  --out-dir "$IN" --report "$ART/verified-topk-readout.json" \
  > "$W/fetch-topk-readout.log" 2>&1
python3 - "$ART/verified-topk-readout.json" "$IN/topk-readout.json" \
  "$EXPECTED_TOPK_READOUT_JOB" <<'PY'
import json
import sys
verified = json.load(open(sys.argv[1]))
summary = json.load(open(sys.argv[2]))
if verified.get("job_id") != sys.argv[3] or verified.get("result_state") != "completed":
    raise SystemExit("TOPK readout identity/state mismatch")
serialized = json.dumps(summary).upper()
if "TOPK3" not in serialized or "UNIFORM" not in serialized:
    raise SystemExit("TOPK3-vs-UNIFORM matchup not authenticated")
views = summary.get("views_summed", {})
if int(views.get("n", 0)) < 5400:
    raise SystemExit("TOPK readout lacks useful two-view power")
if summary.get("promotion_authorized") is not False:
    raise SystemExit("TOPK readout promotion guard drift")
if summary.get("automatic_next_job") is not None:
    raise SystemExit("TOPK readout automatic continuation drift")
PY

phase fetch-and-authenticate-parent
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_TRAIN_PREFIX" \
  --expected-state completed \
  --file "artefacts/$PARENT_ARTEFACT=PARENT.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-parent.json" \
  > "$W/fetch-parent.log" 2>&1
python3 - "$ART/verified-parent.json" "$EXPECTED_PARENT_TRAIN_JOB" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit("parent source identity/state mismatch")
PY
gunzip -c "$IN/PARENT.pjtw.gz" > "$W/PARENT.pjtw"
[ "$(sha256sum "$W/PARENT.pjtw" | awk '{print $1}')" = "$PARENT_MODEL_SHA" ] ||
  die "parent model hash drift"

phase fetch-and-authenticate-postfix-replay
: "${REPLAY_SOURCE_DATA_GZ_SHA:?}"
: "${REPLAY_SOURCE_META_GZ_SHA:?}"
python3 jobs/tools/fetch_result_files.py --prefix "$PREREQUISITE_PREFIX" \
  --expected-state completed \
  --file artefacts/uniform.jnnw.gz=replay-source.jnnw.gz \
  --file artefacts/uniform.jsm.gz=replay-source.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-replay-source.json" \
  > "$W/fetch-replay-source.log" 2>&1
[ "$(sha256sum "$IN/replay-source.jnnw.gz" | awk '{print $1}')" = \
  "$REPLAY_SOURCE_DATA_GZ_SHA" ] || die "replay data hash drift"
[ "$(sha256sum "$IN/replay-source.jsm.gz" | awk '{print $1}')" = \
  "$REPLAY_SOURCE_META_GZ_SHA" ] || die "replay meta hash drift"
gunzip -c "$IN/replay-source.jnnw.gz" > "$W/replay-source.jnnw"
gunzip -c "$IN/replay-source.jsm.gz" > "$W/replay-source.jsm"
python3 jobs/tools/assert_corpus_wdl.py --data "$W/replay-source.jnnw" \
  --out "$ART/replay-source-wdl.json" > "$W/replay-source-wdl.log" 2>&1 ||
  die "replay source WDL canary failed"

phase build-and-test
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests > "$W/build.log" 2>&1
ctest --test-dir "$W/build" --output-on-failure > "$W/ctest.log" 2>&1
J="$W/build/jass"
[ "$("$J" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"

if [ "$COVERAGE_LEVER" = regret_restart ]; then
  phase build-authenticated-regret-archive
  "$J" --rewrite-scores-with-nnue "$W/replay-source.jnnw" \
    "$W/archive-scored.jnnw" --nnue "$W/PARENT.pjtw" \
    > "$W/archive-score.log" 2>&1
  python3 tools/selfplay_frontier.py mine-regret \
    --data "$W/replay-source.jnnw" --meta "$W/replay-source.jsm" \
    --scored-data "$W/archive-scored.jnnw" \
    --out "$W/regret-seeds.jnnw" --manifest "$ART/regret-archive.json" \
    --max-positions "$REGRET_MAX_POSITIONS" --score-scale-cp 100 \
    --seed "$BASE_SEED" > "$W/archive-mine.log" 2>&1
  gzip -n -c "$W/regret-seeds.jnnw" > "$ART/regret-seeds.jnnw.gz"
fi

if [ "$COVERAGE_LEVER" = opening_pool ]; then
  phase build-authenticated-master-opening-pool
  case "$MASTER_CORPUS_MODE" in
    git)
      [ "$(git rev-parse "$MASTER_CORPUS_GIT_REF:$MASTER_CORPUS_GIT_PATH")" = \
        "$MASTER_CORPUS_GIT_BLOB" ] || die "master corpus Git blob drift"
      git show "$MASTER_CORPUS_GIT_REF:$MASTER_CORPUS_GIT_PATH" \
        > "$W/master-openings-source.jnnw"
      MASTER_SOURCE_LABEL="lidraughts-git-13266-games"
      ;;
    local)
      [ -n "$MASTER_CORPUS_LOCAL_PATH" ] &&
        [ -n "$MASTER_CORPUS_LOCAL_SHA256" ] ||
        die "local master corpus requires path and pinned SHA256"
      [ -f "$MASTER_CORPUS_LOCAL_PATH" ] || die "local master corpus missing"
      [ "$(sha256sum "$MASTER_CORPUS_LOCAL_PATH" | awk '{print $1}')" = \
        "$MASTER_CORPUS_LOCAL_SHA256" ] || die "local master corpus SHA drift"
      cp "$MASTER_CORPUS_LOCAL_PATH" "$W/master-openings-source.jnnw"
      MASTER_SOURCE_LABEL="lidraughts-local-full-authenticated"
      ;;
    *) die "unsupported MASTER_CORPUS_MODE=$MASTER_CORPUS_MODE" ;;
  esac
  python3 tools/build_master_opening_pool.py \
    --jass "$J" --data "$W/master-openings-source.jnnw" \
    --out "$W/master-openings.fen" \
    --manifest "$ART/master-opening-pool.json" \
    --positions "$OPENING_POOL_POSITIONS" \
    --min-ply "$OPENING_POOL_MIN_PLY" --max-ply "$OPENING_POOL_MAX_PLY" \
    --min-pieces "$OPENING_POOL_MIN_PIECES" --seed "$BASE_SEED" \
    --source-label "$MASTER_SOURCE_LABEL" \
    > "$W/master-opening-pool.log" 2>&1
  python3 jobs/tools/validate_opening_pool.py \
    --pool "$W/master-openings.fen" \
    --expected "$OPENING_POOL_POSITIONS" --generator-seed "$BASE_SEED" \
    --out "$ART/master-opening-pool-validation.json" \
    > "$W/master-opening-pool-validation.log" 2>&1
  cp "$W/master-openings.fen" "$W/opening-exclusions.fen"
else
  printf '# no external opening pool for lever=%s\n' "$COVERAGE_LEVER" \
    > "$W/opening-exclusions.fen"
fi
gzip -n -c "$W/opening-exclusions.fen" > "$ART/opening-exclusions.fen.gz"

gen_arm(){
  local arm="$1" timeout_s="$2"
  local arm_fresh="$FRESH_RECORDS"
  [ "$COVERAGE_LEVER" = replay_ratio ] && arm_fresh="$RECORDS"
  local base=$((arm_fresh / SHARDS)) rem=$((arm_fresh % SHARDS))
  local count shard failed=0 pid rc idx
  local pids=() shards=() treatment_args=() common_args=()

  case "$COVERAGE_LEVER" in
    phase_sampling)
      [ "$arm" = treatment ] &&
        treatment_args=(--sample-rate-by-phase "$PHASE_SAMPLE_SPEC")
      ;;
    topk_softmax)
      common_args=(--explore-topk "$TOPK" --explore-margin "$EXPLORE_MARGIN")
      [ "$arm" = treatment ] &&
        treatment_args=(--explore-temperature-cp "$SOFTMAX_TEMPERATURE_CP")
      ;;
    regret_restart)
      [ "$arm" = treatment ] &&
        treatment_args=(--seed-file "$W/regret-seeds.jnnw" --seed-frac "$REGRET_SEED_FRAC")
      ;;
    opening_pool)
      [ "$arm" = treatment ] &&
        treatment_args=(--opening-pool "$W/master-openings.fen"
          --opening-pool-frac "$OPENING_POOL_FRAC"
          --opening-pool-post-plies 0)
      ;;
  esac

  : > "$ART/producer-exits-$arm.txt"
  for shard in $(seq 0 $((SHARDS - 1))); do
    count="$base"; [ "$shard" -lt "$rem" ] && count=$((count + 1))
    timeout "$timeout_s" "$J" --gen-data-wdl "$count" \
      "$W/$arm-s$shard.jnnw" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" \
      $((BASE_SEED + shard)) \
      --nnue "$W/PARENT.pjtw" --search-params-play "$Q00" --wdl-zero-score \
      --random-open-plies 8 --explore-eps "$EXPLORE_EPS" \
      --explore-decay-plies "$EXPLORE_DECAY" --split-selfplay-rngs \
      "${common_args[@]}" "${treatment_args[@]}" \
      --pair-openings --drop-plycap --sample-meta-out "$W/$arm-s$shard.jsm" \
      < /dev/null > "$W/$arm-s$shard.log" 2>&1 &
    pids+=("$!"); shards+=("$shard")
  done
  for idx in "${!pids[@]}"; do
    pid="${pids[$idx]}"; shard="${shards[$idx]}"
    if wait "$pid"; then rc=0; else rc=$?; fi
    printf 'arm=%s shard=%s pid=%s rc=%s timeout_s=%s\n' \
      "$arm" "$shard" "$pid" "$rc" "$timeout_s" |
      tee -a "$ART/producer-exits-$arm.txt"
    [ "$rc" -eq 0 ] || failed=$((failed + 1))
  done
  [ "$failed" -eq 0 ] || die "$arm generation: $failed producer failures"
}

phase generate-control-then-treatment
gen_arm control "$GEN_TIMEOUT_CONTROL"
gen_arm treatment "$GEN_TIMEOUT_TREATMENT"

for arm in control treatment; do
  for log in "$W/$arm"-s*.log; do
    grep -q 'label_score_searches=0' "$log" || die "score-label search in $log"
    grep -q '^EXPLORATION ' "$log" || die "missing exploration counters in $log"
    grep -q '^SAMPLEPHASE ' "$log" || die "missing phase counters in $log"
    grep -q '^OPENING_SOURCE ' "$log" || die "missing opening-source counters in $log"
  done
  grep '^EXPLORATION ' "$W/$arm"-s*.log > "$ART/exploration-$arm.txt"
  grep '^SAMPLEPHASE ' "$W/$arm"-s*.log > "$ART/samplephase-$arm.txt"
  grep '^OPENING_SOURCE ' "$W/$arm"-s*.log > "$ART/opening-source-$arm.txt"
done

python3 - "$ART" "$COVERAGE_LEVER" "$PLAY_DEPTH" \
  "$SOFTMAX_TEMPERATURE_CP" "$REGRET_SEED_FRAC" "$OPENING_POOL_FRAC" <<'PY'
import json
import pathlib
import sys

art = pathlib.Path(sys.argv[1])
lever = sys.argv[2]
play_depth, temperature, seed_frac, opening_pool_frac = map(int, sys.argv[3:7])

def counters(path):
    rows = []
    for line in path.read_text().splitlines():
        row = {}
        for token in line.split()[1:]:
            key, sep, value = token.partition("=")
            if sep and value.lstrip("-").isdigit():
                row[key] = int(value)
        rows.append(row)
    if len(rows) != 6:
        raise SystemExit(f"{path}: expected six shard rows, got {len(rows)}")
    return rows

explore = {a: counters(art / f"exploration-{a}.txt")
           for a in ("control", "treatment")}
phase = {a: counters(art / f"samplephase-{a}.txt")
         for a in ("control", "treatment")}
openings = {a: counters(art / f"opening-source-{a}.txt")
            for a in ("control", "treatment")}
for arm in explore:
    if {r.get("split_selfplay_rngs") for r in explore[arm]} != {1}:
        raise SystemExit(f"{arm}: split RNGs inactive")

if lever == "phase_sampling":
    expected = {
        "opening_denom": 8, "midgame_denom": 4, "late-mid_denom": 3,
        "endgame_denom": 2, "deep-eg_denom": 1,
    }
    for key, value in expected.items():
        if {r.get(key) for r in phase["treatment"]} != {value}:
            raise SystemExit(f"phase treatment drift for {key}")
    for key in expected:
        if {r.get(key) for r in phase["control"]} != {4}:
            raise SystemExit(f"phase control drift for {key}")
elif lever == "topk_softmax":
    for arm in explore:
        if sum(r.get("topk_ranked_plies", 0) for r in explore[arm]) <= 0:
            raise SystemExit(f"{arm}: TOPK never ranked")
        if {r.get("topk_rank_depth") for r in explore[arm]} != {play_depth - 1}:
            raise SystemExit(f"{arm}: TOPK ranking depth drift")
    if sum(r.get("topk_softmax_plies", 0) for r in explore["control"]) != 0:
        raise SystemExit("control unexpectedly used softmax")
    if sum(r.get("topk_softmax_plies", 0) for r in explore["treatment"]) <= 0:
        raise SystemExit("treatment softmax never fired")
    if {r.get("explore_temperature_cp") for r in explore["treatment"]} != {temperature}:
        raise SystemExit("treatment temperature drift")
elif lever == "opening_pool":
    if sum(r.get("pool_games", 0) for r in openings["control"]) != 0:
        raise SystemExit("control unexpectedly used the master opening pool")
    if sum(r.get("pool_games", 0) for r in openings["treatment"]) <= 0:
        raise SystemExit("treatment master opening pool never fired")
    if {r.get("pool_frac") for r in openings["treatment"]} != {opening_pool_frac}:
        raise SystemExit("treatment opening-pool fraction drift")

(art / "lever-activation.json").write_text(json.dumps({
    "schema": 1, "lever": lever, "control": "historical/default",
    "treatment": {
        "phase_sampling": "8,4,3,2,1 denominators",
        "topk_softmax": f"TOPK3 margin50 temperature{temperature}cp",
        "regret_restart": f"parent-regret archive seed_frac={seed_frac}%",
        "opening_pool": f"{opening_pool_frac}% stochastic master opening pool",
        "replay_ratio": "100% fresh vs 50% fresh / 50% rolling replay",
    }[lever],
    "checks_passed": True,
}, indent=2, sort_keys=True) + "\n")
PY

phase merge-split-cover-fit
for arm in control treatment; do
  pairs=()
  for shard in $(seq 0 $((SHARDS - 1))); do
    pairs+=(--pair "$W/$arm-s$shard.jnnw" "$W/$arm-s$shard.jsm")
  done
  python3 tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested \
    --out-data "$W/$arm.fresh.jnnw" --out-meta "$W/$arm.fresh.jsm" \
    --manifest "$ART/$arm-fresh-merge.json" > "$W/$arm-fresh-merge.log" 2>&1
  if [ "$COVERAGE_LEVER" = replay_ratio ] && [ "$arm" = control ]; then
    python3 tools/selfplay_frontier.py mix \
      --source fresh "$W/$arm.fresh.jnnw" "$W/$arm.fresh.jsm" 1 \
      --target-records "$RECORDS" --seed "$MIX_SEED" --namespace-openings \
      --out-data "$W/$arm.raw.jnnw" --out-meta "$W/$arm.raw.jsm" \
      --manifest "$ART/$arm-mix.json" > "$W/$arm-mix.log" 2>&1
  else
    python3 tools/selfplay_frontier.py mix \
      --source fresh "$W/$arm.fresh.jnnw" "$W/$arm.fresh.jsm" 1 \
      --source replay "$W/replay-source.jnnw" "$W/replay-source.jsm" 1 \
      --target-records "$RECORDS" --seed "$MIX_SEED" --namespace-openings \
      --out-data "$W/$arm.raw.jnnw" --out-meta "$W/$arm.raw.jsm" \
      --manifest "$ART/$arm-mix.json" > "$W/$arm-mix.log" 2>&1
  fi
  python3 tools/selfplay_frontier.py split \
    --data "$W/$arm.raw.jnnw" --meta "$W/$arm.raw.jsm" \
    --out-data "$W/$arm.fit.jnnw" --out-meta "$W/$arm.fit.jsm" \
    --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
    --manifest "$ART/$arm-split.json" > "$W/$arm-split.log" 2>&1
  env PYTHONPATH="$GEOM:pattern_jass/tools" \
    python3 jobs/tools/l3_bucket_visits.py --data "$W/$arm.raw.jnnw" \
    --out "$ART/$arm-coverage.json" > "$W/$arm-coverage.log" 2>&1
  python3 jobs/tools/assert_corpus_wdl.py --data "$W/$arm.raw.jnnw" \
    --out "$ART/$arm-corpus-wdl.json" > "$W/$arm-corpus-wdl.log" 2>&1 ||
    die "$arm WDL canary failed"
  gzip -n -c "$W/$arm.raw.jnnw" > "$ART/$arm.jnnw.gz"
  gzip -n -c "$W/$arm.raw.jsm" > "$ART/$arm.jsm.gz"
done

python3 - "$ART/control-mix.json" "$ART/treatment-mix.json" \
  "$FRESH_RECORDS" "$RECORDS" "$COVERAGE_LEVER" <<'PY'
import json
import sys

control, treatment = (json.load(open(path)) for path in sys.argv[1:3])
fresh_records, records = map(int, sys.argv[3:5])
lever = sys.argv[5]

def sources(manifest):
    return {row["label"]: row for row in manifest["sources"]}

left, right = sources(control), sources(treatment)
if lever == "replay_ratio":
    if set(left) != {"fresh"} or left["fresh"]["selected_records"] != records:
        raise SystemExit("replay control is not 100% fresh")
    if right["fresh"]["selected_records"] != fresh_records:
        raise SystemExit("replay treatment fresh quota drift")
    if right["replay"]["selected_records"] != records - fresh_records:
        raise SystemExit("replay treatment memory quota drift")

    # Both generators ran the same seeds/policy/volume. Authenticate that the
    # complete 2M fresh inputs are identical before replacing half of one.
    for key in ("input_data_sha256", "input_meta_sha256"):
        if left["fresh"][key] != right["fresh"][key]:
            raise SystemExit(f"replay A/B fresh corpus drift: {key}")
else:
    for rows in (left, right):
        if rows["fresh"]["selected_records"] != fresh_records:
            raise SystemExit("fresh replay-mix quota drift")
        if rows["replay"]["selected_records"] != records - fresh_records:
            raise SystemExit("historical replay-mix quota drift")
    for key in ("selected_data_sha256", "selected_meta_sha256"):
        if left["replay"][key] != right["replay"][key]:
            raise SystemExit(f"arms received different replay sample: {key}")
PY

if [ "$COVERAGE_LEVER" = regret_restart ]; then
  python3 - "$ART/control-fresh-merge.json" "$ART/treatment-fresh-merge.json" <<'PY'
import json
import sys
control, treatment = (json.load(open(p)) for p in sys.argv[1:3])
if control.get("source_records", {}).get("frontier", 0) != 0:
    raise SystemExit("control unexpectedly contains restart records")
if treatment.get("source_records", {}).get("frontier", 0) <= 0:
    raise SystemExit("regret treatment contains no restart records")
PY
fi

for arm in control treatment; do
  HOLD=$("$W/venv/bin/python" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' \
    "$ART/$arm-split.json")
  [ "$HOLD" -gt 0 ] || die "$arm holdout missing"
  "$J" --dump-eval-features "$W/$arm.fit.jnnw" "$W/$arm.feat" \
    > "$W/$arm-features.log" 2>&1
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    timeout "$FIT_TIMEOUT" \
    "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
    --data "$W/$arm.fit.jnnw" --feat "$W/$arm.feat" --out "$W/$arm.pjtw" \
    --target wdl --loss logistic --color-fold --tempo-stage \
    --warm-start "$W/PARENT.pjtw" --holdout-count "$HOLD" \
    --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
    --optimizer-report "$ART/$arm-optimizer.json" \
    > "$W/fit-$arm.log" 2>&1
  FIT_RC=$?
  set -e
  [ -s "$W/$arm.pjtw" ] && gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  [ "$FIT_RC" -eq 0 ] || die "$arm fit failed rc=$FIT_RC"
  "$W/venv/bin/python" - "$ART/$arm-optimizer.json" <<'PY' ||
import json
import sys
if not json.load(open(sys.argv[1])).get("success"):
    raise SystemExit(1)
PY
    die "$arm optimiser did not converge"
done

phase publish-certificate
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" \
  "$COVERAGE_LEVER" "$RECORDS" "$PARENT_NAME" "$PARENT_MODEL_SHA" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha, lever = sys.argv[3:5]
records = int(sys.argv[5])
parent_name, parent_sha = sys.argv[6:8]

def parse_rows(path):
    values = {}
    for line in path.read_text().splitlines():
        for token in line.split()[1:]:
            key, sep, value = token.partition("=")
            if sep and value.lstrip("-").isdigit():
                values.setdefault(key, []).append(int(value))
    additive = {
        "topk_ranked_plies", "topk_softmax_plies",
        "topk_selected_alternative", "topk_selected_rank_sum",
        "margin_singleton_plies", "topk_duplicate_candidates",
        "openings", "games", "random_open_moves", "play_plies",
        "eps_events", "eps_changed_best", "games_with_eps",
    }
    out = {}
    for key, rows in values.items():
        if key in additive or key.endswith("_selected") or key.endswith("_emitted"):
            out[key] = sum(rows)
        elif len(set(rows)) == 1:
            out[key] = rows[0]
        else:
            out[key] = sorted(set(rows))
    return out

arms = {}
for arm in ("control", "treatment"):
    cov = json.load(open(art / f"{arm}-coverage.json"))
    opt = json.load(open(art / f"{arm}-optimizer.json"))
    wdl = json.load(open(art / f"{arm}-corpus-wdl.json"))
    mix = json.load(open(art / f"{arm}-mix.json"))
    fit_log = (w / f"fit-{arm}.log").read_text(errors="replace")
    loss = re.search(r"HOLDOUT_LOGLOSS[ =:]+([0-9.]+)", fit_log)
    arms[arm] = {
        "model_sha256": hashlib.sha256((w / f"{arm}.pjtw").read_bytes()).hexdigest(),
        "exploration": parse_rows(art / f"exploration-{arm}.txt"),
        "sample_phase": parse_rows(art / f"samplephase-{arm}.txt"),
        "opening_source": parse_rows(art / f"opening-source-{arm}.txt"),
        "source_records": {
            row["label"]: row["selected_records"] for row in mix["sources"]
        },
        "wdl": wdl,
        "coverage": {
            "visited_buckets": cov["coverage"]["visited_buckets"],
            "visited_pct": round(100.0 * cov["coverage"]["coverage_fraction"], 3),
            "gini": cov["concentration"]["gini"],
            "buckets_ge_10": cov["coverage"]["buckets_with_at_least"]["ge_10"],
            "buckets_ge_100": cov["coverage"]["buckets_with_at_least"]["ge_100"],
        },
        "fit": {
            "iterations": opt.get("nit"),
            "converged": opt.get("success"),
            "holdout_logloss": float(loss.group(1)) if loss else None,
        },
    }

payload = {
    "schema": 1,
    "verdict": "L3_PURE_COVERAGE_LEVER_ARMS_READY",
    "coverage_lever": lever,
    "code_sha": code_sha,
    "parent": {"name": parent_name, "model_sha256": parent_sha},
    "primary_contrast": "treatment minus control",
    "records_per_arm": records,
    "replay_policy": (
        {
            "control": {"fresh_records": records, "replay_records": 0},
            "treatment": {
                "fresh_records": records // 2,
                "authenticated_postfix_uniform_replay_records": records // 2,
            },
            "mix_ratio_contrast": "100/0 vs 50/50",
            "fresh_inputs_byte_identical_before_treatment_sampling": True,
        }
        if lever == "replay_ratio"
        else {
            "fresh_records": records // 2,
            "authenticated_postfix_uniform_replay_records": records // 2,
            "mix_ratio": "50/50",
            "same_replay_sample_both_arms": True,
        }
    ),
    "single_factor": {
        "phase_sampling": "position sampling denominator by fixed phase",
        "topk_softmax": "rank selection distribution inside identical TOPK3 margin50 set",
        "regret_restart": "20% parent-regret archive restarts versus no restart",
        "opening_pool": "50% stochastic quiet master openings versus random-8 openings",
        "replay_ratio": "replace half of a byte-identical fresh corpus with rolling replay",
    }[lever],
    "master_opening_labels_or_moves_used_for_training": False,
    "arms": arms,
    "holdout_loss_is_diagnostic_only": True,
    "readout_required": (
        "treatment vs control on 1500 fresh paired openings, both colours, "
        "Q00 and native views, n=6000 summed before Elo"
    ),
    "promotion_authorized": False,
    "automatic_next_job": None,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n")
(art / "VERDICT__L3_PURE_COVERAGE_LEVER_ARMS_READY").write_text(
    "L3_PURE_COVERAGE_LEVER_ARMS_READY\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
for arm, result in arms.items():
    print(f"{arm}: model={result['model_sha256']} "
          f"coverage={result['coverage']['visited_pct']}% "
          f"converged={result['fit']['converged']}")
PY
phase complete
say "L3_PURE_COVERAGE_LEVER_ARMS_READY lever=$COVERAGE_LEVER promotion=false automatic_next_job=null"
