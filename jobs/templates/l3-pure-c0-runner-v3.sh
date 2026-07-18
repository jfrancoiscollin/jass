#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# One matched arm of L3-PURE C0: material seed -> G1/G2/G3 terminal-WDL fits.
# ARM=A never seeds from a frontier. ARM=B mines F1/F2 from its own preceding
# corpus and starts FRONTIER_FRAC percent of G2/G3 games there.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_JOB_ID:?runner v3 must provide JASS_JOB_ID}"
: "${ARM:?set ARM=A or ARM=B}"

case "$ARM" in
  A) : "${FRONTIER_FRAC:=0}" ;;
  B) : "${FRONTIER_FRAC:=25}" ;;
  *) echo "ABORT: ARM must be A or B" >&2; exit 2 ;;
esac

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$GEOM"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

NGEN="${NGEN:-3}"
FRESH="${FRESH:-500000}"
NSHARDS="${NSHARDS:-8}"
PAR_GEN="${PAR_GEN:-8}"
MAXPLIES="${MAXPLIES:-260}"
LABEL_DEPTH="${LABEL_DEPTH:-4}"
RANDOM_OPEN_PLIES="${RANDOM_OPEN_PLIES:-8}"
EXPLORE_EPS="${EXPLORE_EPS:-8}"
EXPLORE_DECAY_PLIES="${EXPLORE_DECAY_PLIES:-60}"
HOLDOUT_MOD="${HOLDOUT_MOD:-10}"
BASE_SEED="${BASE_SEED:-314159}"
MAXIT="${MAXIT:-25}"
L2="${L2:-3e-5}"
CHUNK="${CHUNK:-500000}"
FRONTIER_MAX="${FRONTIER_MAX:-4000}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-21600}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
# Normative C0 search fingerprint. Keep play and label search identical and do
# not inherit mutable engine defaults; any change requires a separate fork.
L3_SEARCH_PARAMS="qs_threat_ext=1,qs_sacs=1,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
readonly L3_SEARCH_PARAMS
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
: > "$RES"
: > "$PROG"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }

MONITOR_PID=""
stop_monitor(){
  [ -n "$MONITOR_PID" ] || return 0
  kill "$MONITOR_PID" 2>/dev/null || true
  wait "$MONITOR_PID" 2>/dev/null || true
  MONITOR_PID=""
}
start_monitor(){
  local generation="$1"
  (
    while true; do
      {
        TZ=Europe/Paris date '+time_fr=%Y-%m-%dT%H:%M:%S%z'
        printf 'generation=%s arm=%s\n' "$generation" "$ARM"
        for log in "$W/g${generation}.s"*.log; do
          [ -f "$log" ] || continue
          printf '%s: ' "$(basename "$log")"
          grep -E 'played [0-9]+ games|wrote [0-9]+ WDL' "$log" | tail -1 || true
        done
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      sleep 600
    done
  ) &
  MONITOR_PID="$!"
}

run_pids(){
  local label="$1"; shift
  local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail shard(s) failed"
}

finalize(){
  rc=$?
  trap - EXIT
  set +e
  stop_monitor
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  if [ -d "$W" ]; then
    (cd "$W" && find . -type f -name '*.log' -print0 |
      tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  fi
  rm -rf "$W/build" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-PURE C0 arm $ARM ==="
[ -z "$(git branch --show-current)" ] || die "runner code worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing (requires measured rate, ETA and explicit JFC go)"
NPROC="$(nproc)"
[ "$NSHARDS" -le "$NPROC" ] || die "NSHARDS=$NSHARDS exceeds nproc=$NPROC"
FREE_MB="$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')"
[ "${FREE_MB:-0}" -ge 5000 ] || die "less than 5 GiB free on result filesystem"
say "preflight: nproc=$NPROC nshards=$NSHARDS free_mb=$FREE_MB timeout_per_shard=${SHARD_TIMEOUT}s"
CODE_SHA="$(git rev-parse HEAD)"
SEARCH_PARAMS_SHA256="$(printf '%s' "$L3_SEARCH_PARAMS" | sha256sum | awk '{print $1}')"
say "search_fingerprint: scope=play_and_label params=$L3_SEARCH_PARAMS sha256=$SEARCH_PARAMS_SHA256"
python3 - "$ART/l3-run-config.json" "$ARM" "$CODE_SHA" "$L3_SEARCH_PARAMS" \
  "$SEARCH_PARAMS_SHA256" <<'PY'
import hashlib, json, sys
from pathlib import Path
spec = sys.argv[4]
payload = {
  "schema": 1,
  "lineage": "L3-PURE",
  "experiment": "C0",
  "arm": sys.argv[2],
  "code_sha": sys.argv[3],
  "search_params_scope": "play_and_label",
  "search_params": spec,
  "search_params_map": {
    key: int(value) for key, value in
    (token.split("=", 1) for token in spec.split(","))
  },
  "search_params_sha256": sys.argv[5],
  "search_params_inherited_defaults": False,
}
assert hashlib.sha256(spec.encode()).hexdigest() == sys.argv[5]
Path(sys.argv[1]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
python3 -m py_compile \
  tools/selfplay_frontier.py \
  pattern_jass/tools/train.py \
  pattern_jass/tools/train_stream.py \
  pattern_jass/tools/make_bootstrap_eval.py
python3 jobs/tests/test_selfplay_frontier.py > "$W/test-frontier.log" 2>&1 \
  || die "selfplay frontier tests failed"
python3 tools/test_prior_train.py > "$W/test-warm-start.log" 2>&1 \
  || die "warm-start tests failed"

# Freeze the small 8cf geometry before building. The runner owns this
# detached worktree, so generated source changes cannot affect another job.
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
NPAT="$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"
[ "$NPAT" -eq 4251528 ] || die "8cf geometry mismatch: n_pat=$NPAT"

# Runner-v3 pins one immutable SHA. Verify the performance-critical sources in
# the worktree are exactly those of that SHA, then assert the known NPS guards.
for source in src/scan_eval.cpp src/search.cpp src/movegen.cpp; do
  git show "HEAD:$source" > "$W/expected-$(basename "$source")"
  cmp -s "$source" "$W/expected-$(basename "$source")" \
    || die "$source differs from pinned HEAD"
done
grep -q "g_emasks" src/scan_eval.cpp || die "scan_eval missing g_emasks"
grep -q "has_any_capture" src/search.cpp || die "search missing has_any_capture"
grep -q "has_any_capture" src/movegen.cpp || die "movegen missing has_any_capture"
say "architecture guard: pinned sources + g_emasks + has_any_capture OK"

FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl \
  /root/egdb_intl > "$W/clone-egdb.log" 2>&1
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "exact EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR"

cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "build has no exact EGDB"
cmake --build "$W/build" -j"$JASS_BUILD_JOBS" --target jass \
  > "$W/build.log" 2>&1
J="$W/build/jass"

# Rule-derived seed only: man=1, king=3, every learned positional term at zero.
python3 pattern_jass/tools/make_bootstrap_eval.py \
  --out "$W/g0-material.pjtw" --n-pat "$NPAT" --n-ext 120 \
  --men 1 --king 3 --king-center 0 --mobility 0 \
  > "$W/g0-material.log" 2>&1
[ -s "$W/g0-material.pjtw" ] || die "material seed missing"
gzip -n -c "$W/g0-material.pjtw" > "$ART/g0-material.pjtw.gz"

PILOT="$W/g0-material.pjtw"
FRONTIER=""
PER_SHARD=$(( (FRESH + NSHARDS - 1) / NSHARDS ))

for generation in $(seq 1 "$NGEN"); do
  case "$generation" in
    1|2) PLAY_DEPTH=8 ;;
    *)   PLAY_DEPTH=10 ;;
  esac
  say "--- G$generation/$NGEN arm=$ARM play=d$PLAY_DEPTH pilot=$(basename "$PILOT") ---"
  pids=()
  merge_args=()
  start_monitor "$generation"
  for shard in $(seq 0 $((NSHARDS - 1))); do
    data="$W/g${generation}.s${shard}.jnnw"
    meta="$W/g${generation}.s${shard}.jsm"
    log="$W/g${generation}.s${shard}.log"
    seed=$((BASE_SEED + generation * 10000 + shard))
    frontier_args=()
    if [ "$ARM" = B ] && [ "$generation" -gt 1 ]; then
      [ -s "$FRONTIER" ] || die "G$generation requires previous frontier"
      frontier_args=(--seed-file "$FRONTIER" --seed-frac "$FRONTIER_FRAC")
    fi
    timeout "$SHARD_TIMEOUT" "$J" --gen-data-wdl \
      "$PER_SHARD" "$data" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$seed" \
      --nnue "$PILOT" \
      --search-params "$L3_SEARCH_PARAMS" \
      --random-open-plies "$RANDOM_OPEN_PLIES" \
      --explore-eps "$EXPLORE_EPS" \
      --explore-decay-plies "$EXPLORE_DECAY_PLIES" \
      --pair-openings \
      --drop-plycap \
      --sample-meta-out "$meta" \
      "${frontier_args[@]}" > "$log" 2>&1 &
    pids+=("$!")
    merge_args+=(--pair "$data" "$meta")
    if [ "${#pids[@]}" -ge "$PAR_GEN" ]; then
      run_pids "G$generation generation batch" "${pids[@]}"
      pids=()
    fi
  done
  [ "${#pids[@]}" -eq 0 ] || run_pids "G$generation generation" "${pids[@]}"
  stop_monitor

  python3 tools/selfplay_frontier.py merge \
    "${merge_args[@]}" \
    --out-data "$W/g${generation}.raw.jnnw" \
    --out-meta "$W/g${generation}.raw.jsm" \
    --manifest "$ART/g${generation}-merge.json" \
    > "$W/g${generation}-merge.log" 2>&1
  python3 tools/selfplay_frontier.py split \
    --data "$W/g${generation}.raw.jnnw" \
    --meta "$W/g${generation}.raw.jsm" \
    --out-data "$W/g${generation}.fit.jnnw" \
    --out-meta "$W/g${generation}.fit.jsm" \
    --holdout-mod "$HOLDOUT_MOD" --seed "$BASE_SEED" \
    --manifest "$ART/g${generation}-split.json" \
    > "$W/g${generation}-split.log" 2>&1
  HOLDOUT_COUNT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/g${generation}-split.json")"
  [ "$HOLDOUT_COUNT" -gt 0 ] || die "G$generation empty holdout"

  "$J" --dump-eval-features "$W/g${generation}.fit.jnnw" \
    "$W/g${generation}.feat" > "$W/g${generation}-features.log" 2>&1
  # G0 is a rule-derived playing seed, not a learned student.  G1 therefore
  # starts the optimiser at zero; only G2/G3 continue numerically from the
  # preceding student, as required by L3_PURE_PLAN.md section 2.3.
  warm_start_args=()
  if [ "$generation" -gt 1 ]; then
    warm_start_args=(--warm-start "$PILOT")
  fi
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    python3 pattern_jass/tools/train_stream.py \
      --data "$W/g${generation}.fit.jnnw" \
      --feat "$W/g${generation}.feat" \
      --out "$W/g${generation}.pjtw" \
      --target wdl --loss logistic --color-fold --tempo-stage \
      "${warm_start_args[@]}" --holdout-count "$HOLDOUT_COUNT" \
      --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
      > "$W/g${generation}-train.log" 2>&1
  [ -s "$W/g${generation}.pjtw" ] || die "G$generation student missing"
  gzip -n -c "$W/g${generation}.pjtw" > "$ART/g${generation}.pjtw.gz"
  gzip -n -c "$W/g${generation}.raw.jnnw" > "$ART/g${generation}-selfplay.jnnw.gz"
  gzip -n -c "$W/g${generation}.raw.jsm" > "$ART/g${generation}-selfplay.jsm.gz"

  if [ "$ARM" = B ] && [ "$generation" -lt "$NGEN" ]; then
    FRONTIER="$W/frontier-g${generation}.jnnw"
    python3 tools/selfplay_frontier.py mine \
      --data "$W/g${generation}.raw.jnnw" \
      --meta "$W/g${generation}.raw.jsm" \
      --out "$FRONTIER" \
      --manifest "$ART/frontier-g${generation}.json" \
      --max-positions "$FRONTIER_MAX" \
      --min-pieces 8 --max-pieces 24 --margin-min 1 --margin-max 3 \
      --converted-fraction 0.20 --seed "$BASE_SEED" \
      > "$W/frontier-g${generation}.log" 2>&1 \
      || die "G$generation produced no usable moving frontier"
    gzip -n -c "$FRONTIER" > "$ART/frontier-g${generation}.jnnw.gz"
  fi

  PILOT="$W/g${generation}.pjtw"
  say "G$generation complete: holdout=$HOLDOUT_COUNT frontier=$([ -n "$FRONTIER" ] && echo on || echo off)"
done

python3 - "$ART" "$ARM" "$NGEN" "$FRESH" "$FRONTIER_FRAC" \
  "$L3_SEARCH_PARAMS" "$SEARCH_PARAMS_SHA256" "$CODE_SHA" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); arm=sys.argv[2]; ngen=int(sys.argv[3])
payload={
  "schema":1,
  "scientific_status":"complete_generation_chain",
  "lineage":"L3-PURE",
  "arm":arm,
  "generations":ngen,
  "positions_per_generation":int(sys.argv[4]),
  "frontier_game_percent":int(sys.argv[5]) if arm=="B" else 0,
  "training_sources":["selfplay_terminal_wdl", "self_generated_frontier" if arm=="B" else "selfplay_only"],
  "forbidden_sources_used":[],
  "external_teacher_inputs":0,
  "deep_relabel":False,
  "material_adjudication":False,
  "mmto":False,
  "parent_anchor":False,
  "plycap_policy":"drop_game_samples",
  "code_sha":sys.argv[8],
  "search_params_scope":"play_and_label",
  "search_params":sys.argv[6],
  "search_params_map":{
    key:int(value) for key,value in
    (token.split("=",1) for token in sys.argv[6].split(","))
  },
  "search_params_sha256":sys.argv[7],
  "search_params_inherited_defaults":False,
}
for p in sorted(root.glob("g*.pjtw.gz")):
  payload.setdefault("champion_sha256",{})[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
(root/"l3-pure-manifest.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
PY

say "=== L3-PURE arm $ARM complete; models are candidates, not promoted champions ==="
