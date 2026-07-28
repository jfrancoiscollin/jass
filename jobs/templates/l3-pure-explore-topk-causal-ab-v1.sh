#!/usr/bin/env bash
# L3-PURE — causal A/B of self-play exploration: UNIFORM vs TOPK3.
#
# The two arms differ only in the move selected when epsilon exploration fires:
#   A UNIFORM: draw uniformly from every legal move.
#   B TOPK3:   draw from the best three moves within 50 cp of the best.
#
# Both arms use the same parent, warm start, 2 M fresh records, d8, Q00,
# geometry, L2, opening seeds, split seed and replay share (zero). Independent
# RNG streams keep later openings paired when TOPK3 consumes extra random draws.
#
# This job trains and authenticates two models. It does not measure strength,
# promote a model or schedule a continuation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"
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
SHARDS=${SHARDS:-6}
LABEL_DEPTH=4
PLAY_DEPTH=8
MAXPLIES=260
EXPLORE_EPS=8
EXPLORE_DECAY=60
TOPK=3
EXPLORE_MARGIN=50
BASE_SEED=2718281
SPLIT_SEED=577215
HOLDOUT_MOD=10
RATE_D8=9804
TOPK_COST_PCT=121
GEN_TIMEOUT_UNIFORM=${GEN_TIMEOUT_UNIFORM:-4500}
GEN_TIMEOUT_TOPK=${GEN_TIMEOUT_TOPK:-5400}
FIT_TIMEOUT=${FIT_TIMEOUT:-7200}
L2=3e-5
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
CHUNK=20000
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  (
    local t0; t0=$(date +%s)
    while true; do
      {
        local elapsed; elapsed=$(( ($(date +%s) - t0) / 60 ))
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$elapsed"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in uniform topk3; do
          awk -v a="$arm" -v el="$elapsed" '
            /positions$/ { done[FILENAME] = $4; total[FILENAME] = $6 }
            END {
              for (k in done) { d += done[k]; t += total[k] }
              if (t > 0) {
                printf "%s_positions=%d/%d (%.1f%%)\n", a, d, t, 100*d/t
                if (d > 0 && el > 0)
                  printf "%s_eta_remaining_min=%d\n", a, el*(t-d)/d
              }
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

restore_src(){ git checkout -- src/ 2>/dev/null || true; }
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
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

# Runtime and authorization preflight.
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$RECORDS" -eq 2000000 ] || die "causal contract requires 2M records per arm"
[ "$SHARDS" -eq 6 ] || die "causal contract requires 6 shards per arm"
[ "$PLAY_DEPTH" -eq 8 ] || die "causal contract requires d8 only"
NCPU=$(nproc)
[ "$NCPU" -ge 12 ] || die "HOME requires at least 12 logical CPUs, got $NCPU"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -ge 20000 ] || die "need 20 GiB free, got ${DFA}M"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"

PER_SHARD=$(( (RECORDS + SHARDS - 1) / SHARDS ))
UNIFORM_HEALTHY_MIN=$(( (PER_SHARD + RATE_D8 - 1) / RATE_D8 ))
TOPK_HEALTHY_MIN=$(( (UNIFORM_HEALTHY_MIN * TOPK_COST_PCT + 99) / 100 ))
say "  sizing : nproc=$NCPU; 2 arms x $SHARDS shards; $RECORDS records/arm; d$PLAY_DEPTH"
say "  sizing : $PER_SHARD records/shard; ~${UNIFORM_HEALTHY_MIN} min UNIFORM; ~${TOPK_HEALTHY_MIN} min TOPK3"
TOTAL_HEALTHY_MIN=$((UNIFORM_HEALTHY_MIN + TOPK_HEALTHY_MIN))
say "  sizing : sequential arms, at most $SHARDS producers; generation ETA ~${TOTAL_HEALTHY_MIN} min"
say "  sizing : timeouts ${GEN_TIMEOUT_UNIFORM}s/${GEN_TIMEOUT_TOPK}s"
cat > "$ART/generation-plan.txt" <<EOF
arms=uniform,topk3
records_per_arm=$RECORDS
shards_per_arm=$SHARDS
play_depth=$PLAY_DEPTH
records_per_shard_ceiling=$PER_SHARD
rate_d8_records_per_min_per_shard=$RATE_D8
topk_cost_factor=1.21
uniform_healthy_min=$UNIFORM_HEALTHY_MIN
topk3_healthy_min=$TOPK_HEALTHY_MIN
total_healthy_min=$TOTAL_HEALTHY_MIN
uniform_timeout_s=$GEN_TIMEOUT_UNIFORM
topk3_timeout_s=$GEN_TIMEOUT_TOPK
scheduling=sequential_arms
max_concurrent_producers=$SHARDS
EOF
monitor

phase pull-and-assert-pinned-sources
for f in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp \
         src/movegen.cpp src/movegen.hpp src/main.cpp \
         src/selfplay_exploration.hpp; do
  git show "$EXPECTED_CODE_SHA:$f" > "$f" ||
    die "cannot pull $f from $EXPECTED_CODE_SHA"
done
grep -q "g_emasks" src/scan_eval.cpp ||
  { restore_src; die "archi: scan_eval without g_emasks"; }
grep -q "has_any_capture" src/search.cpp ||
  { restore_src; die "archi: search without has_any_capture"; }
grep -q "has_any_capture" src/movegen.cpp ||
  { restore_src; die "archi: movegen without has_any_capture"; }
grep -q "root_is_drawn" src/search.cpp ||
  { restore_src; die "engine predates drawn-root fix"; }
grep -q "split_selfplay_rngs" src/main.cpp ||
  { restore_src; die "engine lacks split self-play RNGs"; }
grep -q "select_topk_exploration_move" src/main.cpp ||
  { restore_src; die "main does not use the PR 384 helper"; }
say "  architecture guard passed at pinned SHA"

phase fetch-and-authenticate-parent
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_TRAIN_PREFIX" \
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
say "  parent authenticated: $PARENT_NAME $PARENT_MODEL_SHA"

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
say "  build, tests and 8cf witness passed"

gen_arm(){
  local arm="$1" timeout_s="$2"; shift 2
  local base=$((RECORDS / SHARDS)) rem=$((RECORDS % SHARDS))
  local count shard failed=0 pid rc idx
  local pids=()
  local shards=()
  : > "$ART/producer-exits-$arm.txt"
  for shard in $(seq 0 $((SHARDS - 1))); do
    count="$base"; [ "$shard" -lt "$rem" ] && count=$((count + 1))
    timeout "$timeout_s" "$J" --gen-data-wdl "$count" \
      "$W/$arm-s$shard.jnnw" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" \
      $((BASE_SEED + shard)) \
      --nnue "$W/PARENT.pjtw" --search-params-play "$Q00" --wdl-zero-score \
      --random-open-plies 8 --explore-eps "$EXPLORE_EPS" \
      --explore-decay-plies "$EXPLORE_DECAY" --split-selfplay-rngs "$@" \
      --pair-openings --drop-plycap --sample-meta-out "$W/$arm-s$shard.jsm" \
      < /dev/null > "$W/$arm-s$shard.log" 2>&1 &
    pids+=("$!")
    shards+=("$shard")
  done
  for idx in "${!pids[@]}"; do
    pid="${pids[$idx]}"
    shard="${shards[$idx]}"
    if wait "$pid"; then rc=0; else rc=$?; fi
    printf 'arm=%s shard=%s pid=%s rc=%s timeout_s=%s\n' \
      "$arm" "$shard" "$pid" "$rc" "$timeout_s" |
      tee -a "$ART/producer-exits-$arm.txt"
    [ "$rc" -eq 0 ] || failed=$((failed + 1))
  done
  [ "$failed" -eq 0 ] || die "$arm generation: $failed producer failures"
}

phase generate-paired-arms-sequential
say "  resource guard: UNIFORM then TOPK3; max concurrent producers=$SHARDS"
gen_arm uniform "$GEN_TIMEOUT_UNIFORM"
gen_arm topk3 "$GEN_TIMEOUT_TOPK" \
  --explore-topk "$TOPK" --explore-margin "$EXPLORE_MARGIN"

for arm in uniform topk3; do
  for log in "$W/$arm"-s*.log; do
    grep -q 'label_score_searches=0' "$log" ||
      die "score-label search in $log"
  done
  grep '^EXPLORATION' "$W/$arm"-s*.log > "$ART/exploration-$arm.txt"
done

python3 - "$W" "$ART" "$RECORDS" "$PLAY_DEPTH" <<'PY'
import json
import pathlib
import struct
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
expected, play_depth = map(int, sys.argv[3:5])

def count_records(path):
    raw = path.read_bytes()[:8]
    if len(raw) != 8 or raw[:4] != b"JNNW":
        raise SystemExit(f"{path}: invalid JNNW header")
    return struct.unpack_from("<I", raw, 4)[0]

def counters(arm):
    out = {}
    for line in (art / f"exploration-{arm}.txt").read_text().splitlines():
        for token in line.split():
            key, sep, value = token.partition("=")
            if sep and value.lstrip("-").isdigit():
                out.setdefault(key, set()).add(int(value))
    return out

for arm in ("uniform", "topk3"):
    total = sum(count_records(p) for p in sorted(w.glob(f"{arm}-s*.jnnw")))
    if total != expected:
        raise SystemExit(f"{arm}: {total} records, expected {expected}")
    c = counters(arm)
    if c.get("split_selfplay_rngs") != {1}:
        raise SystemExit(f"{arm}: split RNGs inactive: {c.get('split_selfplay_rngs')}")
    ranked = sum(c.get("topk_ranked_plies", {0}))
    if arm == "uniform" and ranked != 0:
        raise SystemExit(f"UNIFORM ranked {ranked} plies")
    if arm == "topk3":
        if ranked <= 0:
            raise SystemExit("TOPK3 ranked zero plies")
        if c.get("topk_rank_depth") != {play_depth - 1}:
            raise SystemExit(f"TOPK3 rank depth drift: {c.get('topk_rank_depth')}")
        if sum(c.get("margin_singleton_plies", {0})) <= 0:
            raise SystemExit("TOPK3 margin never constrained the cap")
(art / "paired-generation-check.json").write_text(json.dumps({
    "schema": 1, "records_per_arm": expected, "play_depth": play_depth,
    "opening_seed_base": 2718281, "split_selfplay_rngs": True,
    "same_shard_seeds": True, "topk_rank_depth": play_depth - 1,
    "ok": True,
}, indent=2, sort_keys=True) + "\n")
PY
say "  paired generation guards passed"

phase merge-split-cover-fit
for arm in uniform topk3; do
  pairs=()
  for shard in $(seq 0 $((SHARDS - 1))); do
    pairs+=(--pair "$W/$arm-s$shard.jnnw" "$W/$arm-s$shard.jsm")
  done
  python3 tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested \
    --out-data "$W/$arm.raw.jnnw" --out-meta "$W/$arm.raw.jsm" \
    --manifest "$ART/$arm-merge.json" > "$W/$arm-merge.log" 2>&1
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

python3 - "$ART/uniform-split.json" "$ART/topk3-split.json" \
  "$ART/paired-split-check.json" <<'PY'
import json
import sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
for key in ("split_unit", "holdout_mod", "seed", "tail_is_holdout"):
    if a.get(key) != b.get(key):
        raise SystemExit(f"split mismatch for {key}: {a.get(key)} != {b.get(key)}")
for arm, manifest in (("uniform", a), ("topk3", b)):
    for key in ("train_openings", "holdout_openings", "train_records",
                "holdout_records"):
        if int(manifest.get(key, 0)) <= 0:
            raise SystemExit(f"{arm}: split manifest has non-positive {key}")

# With equal record budgets, the exploration policy can change game lengths and
# therefore the number of openings required to reach the target. Opening counts
# are a downstream treatment outcome, not a split parameter to force equal.
payload = {
    "schema": 1,
    "same_split_contract": True,
    "compared_contract_keys": [
        "split_unit", "holdout_mod", "seed", "tail_is_holdout",
    ],
    "opening_counts_are_treatment_outcomes": True,
    "uniform": {
        key: a[key] for key in (
            "train_openings", "holdout_openings",
            "train_records", "holdout_records",
        )
    },
    "topk3": {
        key: b[key] for key in (
            "train_openings", "holdout_openings",
            "train_records", "holdout_records",
        )
    },
}
with open(sys.argv[3], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

for arm in uniform topk3; do
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
say "  both fits converged"

phase publish-certificate
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" "$RECORDS" \
  "$PLAY_DEPTH" "$EXPLORE_EPS" "$EXPLORE_DECAY" "$TOPK" "$EXPLORE_MARGIN" \
  "$PARENT_NAME" "$PARENT_MODEL_SHA" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha = sys.argv[3]
records, depth, eps, decay, topk, margin = map(int, sys.argv[4:10])
parent_name, parent_sha = sys.argv[10:12]

def summed_counters(arm):
    keys = ("eps_events", "eps_changed_best", "play_plies", "games",
            "topk_ranked_plies", "margin_singleton_plies",
            "topk_duplicate_candidates")
    out = {k: 0 for k in keys}
    for line in (art / f"exploration-{arm}.txt").read_text().splitlines():
        for token in line.split():
            key, sep, value = token.partition("=")
            if key in out and sep:
                out[key] += int(value)
    out["eps_rate_pct"] = (
        round(100.0 * out["eps_events"] / out["play_plies"], 3)
        if out["play_plies"] else None)
    out["changed_best_share"] = (
        round(out["eps_changed_best"] / out["eps_events"], 3)
        if out["eps_events"] else None)
    return out

arms = {}
for arm in ("uniform", "topk3"):
    cov = json.load(open(art / f"{arm}-coverage.json"))
    opt = json.load(open(art / f"{arm}-optimizer.json"))
    wdl = json.load(open(art / f"{arm}-corpus-wdl.json"))
    log = (w / f"fit-{arm}.log").read_text(errors="replace")
    match = re.search(r"HOLDOUT_LOGLOSS[ =:]+([0-9.]+)", log)
    arms[arm] = {
        "model_sha256": hashlib.sha256((w / f"{arm}.pjtw").read_bytes()).hexdigest(),
        "exploration": summed_counters(arm),
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
            "holdout_logloss": float(match.group(1)) if match else None,
        },
    }

payload = {
    "schema": 2,
    "verdict": "L3_PURE_TOPK_CAUSAL_AB_ARMS_READY",
    "code_sha": code_sha,
    "parent": {"name": parent_name, "model_sha256": parent_sha},
    "primary_contrast": "TOPK3 minus UNIFORM",
    "design": {
        "single_factor": "epsilon move policy: all legal vs top-3 within 50 cp",
        "identical_across_arms": [
            "parent", "warm start", "records", "replay share", "play depth",
            "label depth", "Q00", "geometry", "L2", "opening seeds",
            "split seed", "split self-play RNG mode",
        ],
        "records_per_arm": records,
        "replay_share_pct": 0,
        "play_depth": depth,
        "label_depth": 4,
        "explore_eps": eps,
        "explore_decay_plies": decay,
        "topk": topk,
        "explore_margin": margin,
        "ranking_depth": depth - 1,
        "split_selfplay_rngs": True,
    },
    "arms": arms,
    "holdout_loss_is_diagnostic_only": True,
    "readout_required": (
        "TOPK3 vs UNIFORM on 1500 fresh paired openings, both colours, "
        "Q00 and native views, n=6000 summed before Elo"
    ),
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__L3_PURE_TOPK_CAUSAL_AB_ARMS_READY").write_text(
    "L3_PURE_TOPK_CAUSAL_AB_ARMS_READY\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
for arm, result in arms.items():
    print(f"  {arm}: model={result['model_sha256']} "
          f"coverage={result['coverage']['visited_pct']}% "
          f"draw={result['wdl']['shares']['draw']} "
          f"converged={result['fit']['converged']}")
PY
phase complete
say "L3_PURE_TOPK_CAUSAL_AB_ARMS_READY promotion=false automatic_next_job=null"
