#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# L3-PURE C3-MF lineage-native fit-regularisation screen (L2 first triage).
# Every cell is the CURRENT recipe (the X_HHH_CONTROL exploration settings) and
# differs ONLY in the fit L2. Same material seed, Q00 search, terminal WDL only,
# no moving frontier. Baseline for the verdict is the published X1 X_HHH_CONTROL
# cell (0817, L2=3e-5); this runner generates the L2=1e-5 and L2=1e-4 cells.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner must provide JASS_ARTEFACT_DIR}"
: "${JASS_JOB_ID:?runner must provide JASS_JOB_ID}"
: "${ARM:?set ARM=A}"
: "${L3_VARIANT:?set the pre-registered C3-MF variant}"
[ "$ARM" = A ] || { echo "ABORT: C3-MF requires ARM=A" >&2; exit 2; }
: "${FRONTIER_FRAC:=0}"
[ "$FRONTIER_FRAC" = 0 ] || { echo "ABORT: C3-MF forbids frontier seeding" >&2; exit 2; }

L3_EXPERIMENT="C3-MF"
# All C3-MF cells use the current recipe (X_HHH_CONTROL): open 8, eps 8 %, decay 60.
case "$L3_VARIANT" in
  MF_L2LO)
    EXPECTED_RANDOM_OPEN=8 EXPECTED_EPS=8 EXPECTED_DECAY=60
    EXPECTED_L2=1e-5 DESIGN_ROLE=mf_l2_low ;;
  MF_L2HI)
    EXPECTED_RANDOM_OPEN=8 EXPECTED_EPS=8 EXPECTED_DECAY=60
    EXPECTED_L2=1e-4 DESIGN_ROLE=mf_l2_high ;;
  *) echo "ABORT: unknown C3-MF variant: $L3_VARIANT" >&2; exit 2 ;;
esac
EXPECTED_SEARCH_OVERRIDES="qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
L3_SEARCH_OVERRIDES="${L3_SEARCH_OVERRIDES:-$EXPECTED_SEARCH_OVERRIDES}"
[ "$L3_SEARCH_OVERRIDES" = "$EXPECTED_SEARCH_OVERRIDES" ] || {
  echo "ABORT: C3-MF requires the Q00 search fingerprint" >&2
  exit 2
}

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$GEOM"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

NGEN="${NGEN:-2}"
FRESH="${FRESH:-150000}"
NSHARDS="${NSHARDS:-8}"
PAR_GEN="${PAR_GEN:-8}"
MAXPLIES="${MAXPLIES:-260}"
LABEL_DEPTH="${LABEL_DEPTH:-4}"
RANDOM_OPEN_PLIES="${RANDOM_OPEN_PLIES:-$EXPECTED_RANDOM_OPEN}"
EXPLORE_EPS="${EXPLORE_EPS:-$EXPECTED_EPS}"
EXPLORE_DECAY_PLIES="${EXPLORE_DECAY_PLIES:-$EXPECTED_DECAY}"
HOLDOUT_MOD="${HOLDOUT_MOD:-10}"
BASE_SEED="${BASE_SEED:-271828}"
MAXIT="${MAXIT:-25}"
L2="${L2:-$EXPECTED_L2}"
CHUNK="${CHUNK:-500000}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-21600}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
# Full resolved SearchParams fingerprint: all 63 parser keys are pinned.
# Overrides freeze all five quiescence keys to the Q00 baseline.
L3_BASE_SEARCH_PARAMS="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=1,qs_sacs=1,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
L3_SEARCH_PARAMS="$(
python3 - "$L3_BASE_SEARCH_PARAMS" "$L3_SEARCH_OVERRIDES" <<'PY'
import sys
base_spec, override_spec = sys.argv[1:3]
order = []
values = {}
for token in base_spec.split(","):
    key, value = token.split("=", 1)
    if key in values:
        raise SystemExit(f"duplicate baseline search key: {key}")
    int(value)
    order.append(key)
    values[key] = value
if len(order) != 63:
    raise SystemExit(f"expected 63 pinned search keys, got {len(order)}")
for token in override_spec.split(","):
    key, value = token.split("=", 1)
    if key not in values:
        raise SystemExit(f"unknown search override: {key}")
    int(value)
    values[key] = value
print(",".join(f"{key}={values[key]}" for key in order))
PY
)"
readonly L3_EXPERIMENT L3_SEARCH_OVERRIDES L3_BASE_SEARCH_PARAMS L3_SEARCH_PARAMS
readonly EXPECTED_RANDOM_OPEN EXPECTED_EPS EXPECTED_DECAY EXPECTED_L2 DESIGN_ROLE
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
        printf 'generation=%s arm=%s l2=%s\n' "$generation" "$ARM" "$L2"
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

say "=== $JASS_JOB_ID — L3-PURE $L3_EXPERIMENT $L3_VARIANT (L2=$L2) ==="
[ -z "$(git branch --show-current)" ] || die "runner code worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing (requires measured rate, ETA and explicit JFC go)"
[ "$NGEN" -eq 2 ] || die "C3-MF is pre-registered for exactly 2 generations"
[ "$FRESH" -eq 150000 ] || die "C3-MF is pre-registered for exactly 150000 records/generation"
[ "$NSHARDS" -eq 8 ] || die "C3-MF requires NSHARDS=8"
[ "$PAR_GEN" -eq 8 ] || die "C3-MF requires PAR_GEN=8"
[ "$MAXPLIES" -eq 260 ] || die "C3-MF requires MAXPLIES=260"
[ "$LABEL_DEPTH" -eq 4 ] || die "C3-MF keeps the ignored label-depth argument at 4"
[ "$RANDOM_OPEN_PLIES" -eq "$EXPECTED_RANDOM_OPEN" ] || die "C3-MF random opening drift"
[ "$EXPLORE_EPS" -eq "$EXPECTED_EPS" ] || die "C3-MF epsilon drift"
[ "$EXPLORE_DECAY_PLIES" -eq "$EXPECTED_DECAY" ] || die "C3-MF decay drift"
[ "$HOLDOUT_MOD" -eq 10 ] || die "C3-MF requires HOLDOUT_MOD=10"
[ "$BASE_SEED" -eq 271828 ] || die "C3-MF primary screen requires BASE_SEED=271828"
[ "$MAXIT" -eq 25 ] || die "C3-MF requires MAXIT=25"
[ "$L2" = "$EXPECTED_L2" ] || die "C3-MF $L3_VARIANT requires L2=$EXPECTED_L2 (got $L2)"
[ "$CHUNK" -eq 500000 ] || die "C3-MF requires CHUNK=500000"
NPROC="$(nproc)"
[ "$NSHARDS" -le "$NPROC" ] || die "NSHARDS=$NSHARDS exceeds nproc=$NPROC"
FREE_MB="$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')"
[ "${FREE_MB:-0}" -ge 5000 ] || die "less than 5 GiB free on result filesystem"
say "preflight: nproc=$NPROC nshards=$NSHARDS free_mb=$FREE_MB l2=$L2 timeout_per_shard=${SHARD_TIMEOUT}s"
CODE_SHA="$(git rev-parse HEAD)"
SEARCH_PARAMS_SHA256="$(printf '%s' "$L3_SEARCH_PARAMS" | sha256sum | awk '{print $1}')"
say "search_fingerprint: scope=play params=$L3_SEARCH_PARAMS sha256=$SEARCH_PARAMS_SHA256"
python3 - "$ART/l3-run-config.json" "$L3_VARIANT" "$CODE_SHA" \
  "$L3_SEARCH_PARAMS" "$SEARCH_PARAMS_SHA256" "$L3_SEARCH_OVERRIDES" \
  "$NGEN" "$FRESH" "$NSHARDS" "$MAXPLIES" "$RANDOM_OPEN_PLIES" \
  "$EXPLORE_EPS" "$EXPLORE_DECAY_PLIES" "$HOLDOUT_MOD" "$BASE_SEED" \
  "$L2" "$MAXIT" "$CHUNK" "$DESIGN_ROLE" "$L3_EXPERIMENT" <<'PY'
import hashlib, json, sys
from pathlib import Path
spec = sys.argv[4]
params = {
    key: int(value) for key, value in
    (token.split("=", 1) for token in spec.split(","))
}
assert len(params) == 63
assert hashlib.sha256(spec.encode()).hexdigest() == sys.argv[5]
assert {
    key: params[key] for key in (
        "qs_threat_ext", "qs_sacs", "qs_sacs_depth0_only",
        "qs_forcing_depth", "qs_promo_depth",
    )
} == {
    "qs_threat_ext": 0, "qs_sacs": 0, "qs_sacs_depth0_only": 1,
    "qs_forcing_depth": 0, "qs_promo_depth": 0,
}
payload = {
  "schema": 3,
  "runner_version": 1,
  "lineage": "L3-PURE",
  "experiment": sys.argv[20],
  "variant": sys.argv[2],
  "code_sha": sys.argv[3],
  "generations": int(sys.argv[7]),
  "positions_per_generation": int(sys.argv[8]),
  "nshards": int(sys.argv[9]),
  "max_plies": int(sys.argv[10]),
  "play_depth_schedule": {"G1": 8, "G2": 8},
  "play_max_nodes": 0,
  "movetime_ms": 0,
  "score_field_mode": "constant_zero_no_search",
  "label_depth_argument": 4,
  "label_depth_positional_arg_ignored": True,
  "sample_one_in": 4,
  "quiet_only": False,
  "pv_extract": 0,
  "random_open_plies": int(sys.argv[11]),
  "explore_epsilon_percent": int(sys.argv[12]),
  "explore_decay_plies": int(sys.argv[13]),
  "drop_post_epsilon": False,
  "drop_plycap": True,
  "terminate_at_exact_egdb": True,
  "tb_relabel": False,
  "material_adjudication": False,
  "pair_openings": True,
  "holdout_mod_by_opening": int(sys.argv[14]),
  "base_seed": int(sys.argv[15]),
  "design": {
    "kind": "l2_first_triage",
    "swept_factor": "fit_l2",
    "recipe": "X_HHH_CONTROL",
    "role": sys.argv[19],
    "baseline_cell": "X_HHH_CONTROL",
  },
  "geometry": "8cf",
  "build_features": {
    "endgame_features": True, "king_mobility": True,
    "scan_parity": True, "tempo_stage": True, "external_egdb": True,
  },
  "bootstrap": {"men": 1, "king": 3, "king_center": 0, "mobility": 0},
  "fit": {
    "target": "wdl", "loss": "logistic", "color_fold": True,
    "tempo_stage": True, "l2": float(sys.argv[16]),
    "max_iter": int(sys.argv[17]), "chunk": int(sys.argv[18]),
    "warm_start": "G2_from_G1_only", "parent_anchor": False,
  },
  "frontier_game_percent": 0,
  "external_teacher_inputs": 0,
  "search_params_scope": "play",
  "search_params": spec,
  "search_params_map": params,
  "search_params_count": len(params),
  "search_params_overrides": {
    key: int(value) for key, value in
    (token.split("=", 1) for token in sys.argv[6].split(","))
  },
  "search_params_sha256": sys.argv[5],
  "search_params_inherited_defaults": False,
  "automatic_next_job": None,
}
Path(sys.argv[1]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
python3 -m py_compile \
  tools/selfplay_frontier.py \
  jobs/tools/aggregate_l3_exploration.py \
  pattern_jass/tools/train.py \
  pattern_jass/tools/train_stream.py \
  pattern_jass/tools/make_bootstrap_eval.py
python3 jobs/tests/test_selfplay_frontier.py > "$W/test-frontier.log" 2>&1 \
  || die "selfplay frontier tests failed"
python3 jobs/tests/test_l3_exploration_metrics.py > "$W/test-mf-metrics.log" 2>&1 \
  || die "C3-MF exploration metric tests failed"
python3 tools/test_prior_train.py > "$W/test-warm-start.log" 2>&1 \
  || die "warm-start tests failed"

# Freeze the small 8cf geometry before building. The runner owns this
# detached worktree, so generated source changes cannot affect another job.
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
NPAT="$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"
[ "$NPAT" -eq 4251528 ] || die "8cf geometry mismatch: n_pat=$NPAT"

# Runner pins one immutable SHA. Verify the performance-critical sources in the
# worktree are exactly those of that SHA, then assert the known NPS guards.
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
PER_SHARD=$(( (FRESH + NSHARDS - 1) / NSHARDS ))

for generation in $(seq 1 "$NGEN"); do
  case "$generation" in
    1|2) PLAY_DEPTH=8 ;;
    *)   PLAY_DEPTH=10 ;;
  esac
  say "--- G$generation/$NGEN arm=$ARM play=d$PLAY_DEPTH l2=$L2 pilot=$(basename "$PILOT") ---"
  pids=()
  merge_args=()
  start_monitor "$generation"
  for shard in $(seq 0 $((NSHARDS - 1))); do
    data="$W/g${generation}.s${shard}.jnnw"
    meta="$W/g${generation}.s${shard}.jsm"
    log="$W/g${generation}.s${shard}.log"
    seed=$((BASE_SEED + generation * 10000 + shard))
    timeout "$SHARD_TIMEOUT" "$J" --gen-data-wdl \
      "$PER_SHARD" "$data" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$seed" \
      --nnue "$PILOT" \
      --search-params-play "$L3_SEARCH_PARAMS" \
      --wdl-zero-score \
      --random-open-plies "$RANDOM_OPEN_PLIES" \
      --explore-eps "$EXPLORE_EPS" \
      --explore-decay-plies "$EXPLORE_DECAY_PLIES" \
      --pair-openings \
      --drop-plycap \
      --sample-meta-out "$meta" > "$log" 2>&1 &
    pids+=("$!")
    merge_args+=(--pair "$data" "$meta")
    if [ "${#pids[@]}" -ge "$PAR_GEN" ]; then
      run_pids "G$generation generation batch" "${pids[@]}"
      pids=()
    fi
  done
  [ "${#pids[@]}" -eq 0 ] || run_pids "G$generation generation" "${pids[@]}"
  stop_monitor
  for log in "$W/g${generation}.s"*.log; do
    grep -q 'label_score_searches=0' "$log" \
      || die "G$generation did not prove zero score-label searches: $log"
  done

  python3 tools/selfplay_frontier.py merge \
    "${merge_args[@]}" \
    --out-data "$W/g${generation}.raw.jnnw" \
    --out-meta "$W/g${generation}.raw.jsm" \
    --manifest "$ART/g${generation}-merge.json" \
    > "$W/g${generation}-merge.log" 2>&1
  python3 jobs/tools/aggregate_l3_exploration.py \
    --log "$W"/g${generation}.s*.log \
    --expected-random-open "$RANDOM_OPEN_PLIES" \
    --expected-eps "$EXPLORE_EPS" \
    --expected-decay "$EXPLORE_DECAY_PLIES" \
    --manifest "$ART/g${generation}-exploration.json" \
    > "$W/g${generation}-exploration.log" 2>&1
  python3 tools/selfplay_frontier.py profile \
    --data "$W/g${generation}.raw.jnnw" \
    --meta "$W/g${generation}.raw.jsm" \
    --manifest "$ART/g${generation}-profile.json" \
    > "$W/g${generation}-profile.log" 2>&1
  python3 - "$ART/g${generation}-profile.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
sources = payload["source_records"]
if sources.get("frontier", 0) != 0:
    raise SystemExit("C3-MF profile contains forbidden frontier records")
if sources.get("standard", 0) != payload["records"]:
    raise SystemExit("C3-MF profile provenance does not cover every record")
PY
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
  # starts the optimiser at zero; G2 continues numerically from G1.
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

  PILOT="$W/g${generation}.pjtw"
  say "G$generation complete: holdout=$HOLDOUT_COUNT frontier=off l2=$L2"
done

python3 - "$ART" "$NGEN" <<'PY'
import hashlib, json, re, sys
from pathlib import Path
root = Path(sys.argv[1])
ngen = int(sys.argv[2])
payload = json.loads((root / "l3-run-config.json").read_text(encoding="utf-8"))
payload.update({
  "scientific_status": "complete_mf_screen_cell",
  "screen_only": True,
  "promotion_authorized": False,
  "training_sources": ["selfplay_terminal_wdl"],
  "forbidden_sources_used": [],
  "deep_relabel": False,
  "material_adjudication": False,
  "mmto": False,
  "parent_anchor": False,
  "plycap_policy": "drop_game_samples",
})
for generation in range(1, ngen + 1):
  for kind in ("exploration", "profile"):
    path = root / f"g{generation}-{kind}.json"
    if not path.is_file():
      raise SystemExit(f"missing G{generation} {kind} diagnostics")
    payload.setdefault("diagnostic_sha256", {})[path.name] = hashlib.sha256(
      path.read_bytes()).hexdigest()
for path in sorted(root.glob("g*.pjtw.gz")):
  if not re.fullmatch(r"g[1-9][0-9]*\.pjtw\.gz", path.name):
    continue
  payload.setdefault("champion_sha256", {})[path.name] = hashlib.sha256(
      path.read_bytes()).hexdigest()
if len(payload.get("champion_sha256", {})) != ngen:
  raise SystemExit("missing generation model artifacts")
(root / "l3-pure-manifest.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

say "=== L3-PURE $L3_EXPERIMENT $L3_VARIANT (L2=$L2) complete; candidate is not promoted ==="
