#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# L3-PURE long-lineage P1: frozen baseline recipe, G1-G4 from material G0.
# This runner trains only. It never promotes a model or chains an evaluation job.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_JOB_ID:?runner v3 must provide JASS_JOB_ID}"
: "${EXPECTED_CODE_SHA:?pin the merged jass SHA in the GitOps job}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$GEOM"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

L3_EXPERIMENT="L3-PURE-P1"
L3_VARIANT="FROZEN_BASELINE"
NGEN="${NGEN:-4}"
FRESH="${FRESH:-500000}"
NSHARDS="${NSHARDS:-8}"
PAR_GEN="${PAR_GEN:-8}"
PLAY_DEPTH="${PLAY_DEPTH:-8}"
MAXPLIES="${MAXPLIES:-260}"
LABEL_DEPTH="${LABEL_DEPTH:-4}"
RANDOM_OPEN_PLIES="${RANDOM_OPEN_PLIES:-8}"
EXPLORE_EPS="${EXPLORE_EPS:-8}"
EXPLORE_DECAY_PLIES="${EXPLORE_DECAY_PLIES:-60}"
HOLDOUT_MOD="${HOLDOUT_MOD:-10}"
BASE_SEED="${BASE_SEED:-271828}"
MAXIT="${MAXIT:-25}"
L2="${L2:-3e-5}"
CHUNK="${CHUNK:-500000}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-21600}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
FRONTIER_FRAC="${FRONTIER_FRAC:-0}"

EXPECTED_SEARCH_OVERRIDES="qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
L3_SEARCH_OVERRIDES="${L3_SEARCH_OVERRIDES:-$EXPECTED_SEARCH_OVERRIDES}"
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
readonly L3_EXPERIMENT L3_VARIANT EXPECTED_SEARCH_OVERRIDES
readonly L3_SEARCH_OVERRIDES L3_BASE_SEARCH_PARAMS L3_SEARCH_PARAMS

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
        printf 'generation=%s/%s phase=P1 depth=%s\n' "$generation" "$NGEN" "$PLAY_DEPTH"
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

say "=== $JASS_JOB_ID — $L3_EXPERIMENT $L3_VARIANT ==="
[ -z "$(git branch --show-current)" ] || die "runner code worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "$NGEN" -eq 4 ] || die "P1 requires exactly G1-G4"
[ "$FRESH" -eq 500000 ] || die "P1 requires 500000 fresh records/generation"
[ "$NSHARDS" -eq 8 ] || die "P1 requires NSHARDS=8"
[ "$PAR_GEN" -eq 8 ] || die "P1 requires PAR_GEN=8"
[ "$PLAY_DEPTH" -eq 8 ] || die "P1 requires d8 for all four generations"
[ "$MAXPLIES" -eq 260 ] || die "P1 requires MAXPLIES=260"
[ "$LABEL_DEPTH" -eq 4 ] || die "ignored label-depth positional argument must remain 4"
[ "$RANDOM_OPEN_PLIES" -eq 8 ] || die "P1 freezes random-open-plies=8"
[ "$EXPLORE_EPS" -eq 8 ] || die "P1 freezes epsilon=8"
[ "$EXPLORE_DECAY_PLIES" -eq 60 ] || die "P1 freezes decay=60"
[ "$HOLDOUT_MOD" -eq 10 ] || die "P1 requires holdout-mod=10"
[ "$BASE_SEED" -eq 271828 ] || die "P1 primary lineage seed is 271828"
[ "$MAXIT" -eq 25 ] || die "P1 requires max-iter=25"
[ "$L2" = 3e-5 ] || die "P1 freezes L2=3e-5"
[ "$CHUNK" -eq 500000 ] || die "P1 requires chunk=500000"
[ "$FRONTIER_FRAC" -eq 0 ] || die "P1 forbids frontier records"
[ "$L3_SEARCH_OVERRIDES" = "$EXPECTED_SEARCH_OVERRIDES" ] || die "P1 requires Q00"
NPROC="$(nproc)"
[ "$NSHARDS" -le "$NPROC" ] || die "NSHARDS=$NSHARDS exceeds nproc=$NPROC"
MEM_MB="$(awk '/MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo)"
[ "${MEM_MB:-0}" -ge 30000 ] || die "P1 is approved only for the 32 GiB cpx62 runner"
FREE_MB="$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')"
[ "${FREE_MB:-0}" -ge 20000 ] || die "less than 20 GiB free on result filesystem"
say "preflight: sha=$EXPECTED_CODE_SHA nproc=$NPROC mem_mb=$MEM_MB free_mb=$FREE_MB nshards=$NSHARDS timeout=${SHARD_TIMEOUT}s"

CODE_SHA="$(git rev-parse HEAD)"
SEARCH_PARAMS_SHA256="$(printf '%s' "$L3_SEARCH_PARAMS" | sha256sum | awk '{print $1}')"
say "search_fingerprint: scope=play params=$L3_SEARCH_PARAMS sha256=$SEARCH_PARAMS_SHA256"

python3 - "$ART/l3-run-config.json" "$CODE_SHA" "$L3_SEARCH_PARAMS" \
  "$SEARCH_PARAMS_SHA256" "$NGEN" "$FRESH" "$NSHARDS" "$PLAY_DEPTH" \
  "$MAXPLIES" "$RANDOM_OPEN_PLIES" "$EXPLORE_EPS" "$EXPLORE_DECAY_PLIES" \
  "$HOLDOUT_MOD" "$BASE_SEED" "$L2" "$MAXIT" "$CHUNK" <<'PY'
import hashlib, json, sys
from pathlib import Path
(
    out, code_sha, search_spec, search_sha, ngen, fresh, nshards, depth,
    max_plies, random_open, epsilon, decay, holdout_mod, seed, l2, max_iter,
    chunk,
) = sys.argv[1:]
params = dict(token.split("=", 1) for token in search_spec.split(","))
params = {key: int(value) for key, value in params.items()}
assert len(params) == 63
assert hashlib.sha256(search_spec.encode()).hexdigest() == search_sha
assert {key: params[key] for key in (
    "qs_threat_ext", "qs_sacs", "qs_sacs_depth0_only",
    "qs_forcing_depth", "qs_promo_depth",
)} == {
    "qs_threat_ext": 0, "qs_sacs": 0, "qs_sacs_depth0_only": 1,
    "qs_forcing_depth": 0, "qs_promo_depth": 0,
}
recipe = {
    "lineage": "L3-PURE",
    "phase": "P1",
    "variant": "FROZEN_BASELINE",
    "start": "G0_material",
    "generations": int(ngen),
    "positions_per_generation": int(fresh),
    "play_depth_schedule": {f"G{g}": int(depth) for g in range(1, int(ngen) + 1)},
    "geometry": "8cf",
    "bootstrap": {"men": 1, "king": 3, "king_center": 0, "mobility": 0},
    "exploration": {
        "random_open_plies": int(random_open),
        "epsilon_percent": int(epsilon),
        "decay_plies": int(decay),
        "drop_post_epsilon": False,
    },
    "fit": {
        "target": "wdl", "loss": "logistic", "color_fold": True,
        "tempo_stage": True, "l2": float(l2), "max_iter": int(max_iter),
        "chunk": int(chunk), "fresh_corpus_only": True,
        "warm_start": "G2_plus_from_previous_student", "parent_anchor": False,
    },
    "truth": {
        "terminal_wdl_only": True, "exact_egdb_after_natural_reach": True,
        "drop_plycap_game_samples": True, "material_adjudication": False,
        "tb_relabel": False, "deep_relabel": False,
    },
    "search_params": search_spec,
}
recipe_bytes = json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()
payload = {
    "schema": 4,
    "runner_version": 1,
    "experiment": "L3-PURE-P1",
    "variant": "FROZEN_BASELINE",
    "code_sha": code_sha,
    "recipe": recipe,
    "recipe_sha256": hashlib.sha256(recipe_bytes).hexdigest(),
    "nshards": int(nshards),
    "max_plies": int(max_plies),
    "play_max_nodes": 0,
    "movetime_ms": 0,
    "score_field_mode": "constant_zero_no_search",
    "label_depth_argument": 4,
    "label_depth_positional_arg_ignored": True,
    "sample_one_in": 4,
    "quiet_only": False,
    "pv_extract": 0,
    "pair_openings": True,
    "holdout_mod_by_opening": int(holdout_mod),
    "base_seed": int(seed),
    "frontier_game_percent": 0,
    "external_teacher_inputs": 0,
    "search_params_scope": "play",
    "search_params_map": params,
    "search_params_count": len(params),
    "search_params_sha256": search_sha,
    "search_params_inherited_defaults": False,
    "automatic_next_job": None,
}
Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

python3 -m py_compile \
  tools/selfplay_frontier.py \
  jobs/tools/aggregate_l3_exploration.py \
  pattern_jass/tools/train.py \
  pattern_jass/tools/train_stream.py \
  pattern_jass/tools/make_bootstrap_eval.py
python3 jobs/tests/test_selfplay_frontier.py > "$W/test-frontier.log" 2>&1 \
  || die "selfplay frontier tests failed"
python3 jobs/tests/test_l3_exploration_metrics.py > "$W/test-exploration-metrics.log" 2>&1 \
  || die "exploration metric tests failed"
python3 jobs/tests/test_l3_p1_prepared.py > "$W/test-p1-contract.log" 2>&1 \
  || die "P1 contract tests failed"
python3 tools/test_prior_train.py > "$W/test-warm-start.log" 2>&1 \
  || die "warm-start tests failed"

python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
NPAT="$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"
[ "$NPAT" -eq 4251528 ] || die "8cf geometry mismatch: n_pat=$NPAT"

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

python3 pattern_jass/tools/make_bootstrap_eval.py \
  --out "$W/g0-material.pjtw" --n-pat "$NPAT" --n-ext 120 \
  --men 1 --king 3 --king-center 0 --mobility 0 \
  > "$W/g0-material.log" 2>&1
[ -s "$W/g0-material.pjtw" ] || die "material seed missing"
gzip -n -c "$W/g0-material.pjtw" > "$ART/g0-material.pjtw.gz"

PILOT="$W/g0-material.pjtw"
PER_SHARD=$(( (FRESH + NSHARDS - 1) / NSHARDS ))

for generation in $(seq 1 "$NGEN"); do
  say "--- P1 G$generation/$NGEN play=d$PLAY_DEPTH pilot=$(basename "$PILOT") ---"
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
    raise SystemExit("P1 profile contains forbidden frontier records")
if sources.get("standard", 0) != payload["records"]:
    raise SystemExit("P1 profile provenance does not cover every record")
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
  say "G$generation complete: holdout=$HOLDOUT_COUNT frontier=off"
done

python3 - "$ART" "$NGEN" <<'PY'
import hashlib, json, re, sys
from pathlib import Path
root = Path(sys.argv[1])
ngen = int(sys.argv[2])
payload = json.loads((root / "l3-run-config.json").read_text(encoding="utf-8"))
payload.update({
    "scientific_status": "complete_p1_training",
    "phase_complete": "P1",
    "screen_only": False,
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
    for kind in ("merge", "exploration", "profile", "split"):
        path = root / f"g{generation}-{kind}.json"
        if not path.is_file():
            raise SystemExit(f"missing G{generation} {kind} artefact")
        payload.setdefault("diagnostic_sha256", {})[path.name] = hashlib.sha256(
            path.read_bytes()).hexdigest()
for path in sorted(root.glob("g*.pjtw.gz")):
    if not re.fullmatch(r"g[1-9][0-9]*\.pjtw\.gz", path.name):
        continue
    payload.setdefault("student_sha256", {})[path.name] = hashlib.sha256(
        path.read_bytes()).hexdigest()
if len(payload.get("student_sha256", {})) != ngen:
    raise SystemExit("missing generation model artifacts")
(root / "l3-pure-p1-manifest.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

say "=== L3-PURE P1 complete; G1-G4 published, no automatic promotion ==="
