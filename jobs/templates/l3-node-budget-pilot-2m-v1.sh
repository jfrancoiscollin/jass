#!/usr/bin/env bash
# L3 experimental screen: fixed-depth self-play versus variable node budgets.
#
# The two decision arms are bounded to 2 M fresh records in total:
#   - DEPTH: 1 M records, historical d8 play search;
#   - NODES: 1 M records, deterministic weighted budgets sampled per move.
# Three discarded 6 k canaries, plus at most one feedback confirmation, add
# at most 24 k calibration records.
#
# Both arms use the same PRIORTIGHT parent, seeds, openings, exploration,
# training recipe and hardware. A target-box calibration rescales the proposed
# node distribution using wall time only. A confirmation must land within the
# preregistered cost window before either 1 M arm is generated; if coarse
# quantization misses once, one measured feedback rescale is allowed.
#
# The job produces two authenticated models. It does not play the strength gate,
# promote either model or schedule a continuation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
IN="$JASS_RESULT_DIR/inputs"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/.stage"
: > "$RES"
: > "$PROG"
echo start > "$STAGE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

PARENT_PREFIX="${PARENT_PREFIX:-r2:jass-data/runs/cpx62-1159-l3-prior-tight-refit-v1/20260802T171908Z-646f1149}"
EXPECTED_PARENT_JOB="${EXPECTED_PARENT_JOB:-cpx62-1159-l3-prior-tight-refit-v1}"
PARENT_ARTEFACT="${PARENT_ARTEFACT:-exact.pjtw.gz}"
PARENT_SHA256="${PARENT_SHA256:-2bbe1733ca0976ce4934131f83178a9e3757b5bc7a9b5a3bdbc41984781dfec7}"
PARENT_NAME=PRIORTIGHT

RECORDS_PER_ARM="${RECORDS_PER_ARM:-1000000}"
SHARDS="${SHARDS:-6}"
CAL_RECORDS="${CAL_RECORDS:-6000}"
CAL_SHARDS="${CAL_SHARDS:-6}"
LABEL_DEPTH=4
PLAY_DEPTH=8
MAXPLIES=260
BASE_SEED=2718281
CAL_BASE_SEED=3141592
SPLIT_SEED=577215
HOLDOUT_MOD=10
EXPLORE_EPS=8
EXPLORE_DECAY=60
RAW_NODE_SPEC="5000:10,20000:25,80000:35,300000:20,1200000:10"
RAW_NODE_MEAN=213500
CAL_TIMEOUT="${CAL_TIMEOUT:-3600}"
GEN_TIMEOUT_DEPTH="${GEN_TIMEOUT_DEPTH:-7200}"
GEN_TIMEOUT_NODES="${GEN_TIMEOUT_NODES:-10800}"
FIT_TIMEOUT="${FIT_TIMEOUT:-21600}"

L2=3e-5
MAXIT=5000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-4
CHUNK=20000

Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  (
    local t0
    t0=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in depth nodes; do
          awk -v a="$arm" '
            /positions$/ { done[FILENAME]=$4; total[FILENAME]=$6 }
            END {
              for (k in done) { d += done[k]; t += total[k] }
              if (t > 0) {
                printf "%s_positions=%d/%d (%.1f%%)\n", a, d, t, 100*d/t
              }
            }' "$W"/"$arm"-s*.log 2>/dev/null || true
          [ -f "$W/fit-$arm.log" ] &&
            printf 'fit_%s_lines=%s\n' "$arm" "$(wc -l < "$W/fit-$arm.log")"
        done
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done
  ) &
  MON="$!"
}

restore_src(){ git checkout -- src/ pattern_jass/ 2>/dev/null || true; }
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
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.jsonl 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$RECORDS_PER_ARM" -eq 1000000 ] ||
  die "pilot contract requires 1M records per arm"
[ "$((2 * RECORDS_PER_ARM))" -eq 2000000 ] ||
  die "pilot contract requires exactly 2M fresh records total"
[ "$SHARDS" -eq 6 ] && [ "$CAL_SHARDS" -eq 6 ] ||
  die "HOME contract requires six producers"
[ "$CAL_RECORDS" -ge 6000 ] ||
  die "calibration requires at least 6000 records per cell"
[ "$PLAY_DEPTH" -eq 8 ] || die "depth control must remain d8"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"

stage disk-and-host-guards
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -ge 20000 ] || die "need 20 GiB free, got ${DFA:-0} MiB"
NCPU=$(nproc)
[ "$NCPU" -ge 12 ] || die "HOME requires at least 12 logical CPUs, got $NCPU"
say "  host: nproc=$NCPU disk_free_mib=$DFA"
say "  design: 2 arms x $RECORDS_PER_ARM records; six sequential producers"
monitor

stage fetch-and-authenticate-priortight
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_PREFIX" \
  --file "artefacts/$PARENT_ARTEFACT=parent.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-parent.json" \
  --expected-state completed > "$W/fetch-parent.log" 2>&1 ||
  die "parent fetch failed"
python3 - "$ART/verified-parent.json" "$EXPECTED_PARENT_JOB" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit("parent source identity/state mismatch")
PY
gunzip -c "$IN/parent.pjtw.gz" > "$W/PARENT.pjtw"
[ "$(sha256sum "$W/PARENT.pjtw" | awk '{print $1}')" = "$PARENT_SHA256" ] ||
  die "PRIORTIGHT hash drift"
say "  parent authenticated: $PARENT_NAME $PARENT_SHA256"

stage build-and-test
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1 ||
  { restore_src; die "8cf generation failed"; }
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  { restore_src; die "8cf geometry drift"; }
grep -q "node_budget_weighted" src/main.cpp ||
  { restore_src; die "engine lacks explicit weighted node budgets"; }
grep -q "split_selfplay_rngs" src/main.cpp ||
  { restore_src; die "engine lacks split self-play RNGs"; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests > "$W/build.log" 2>&1
ctest --test-dir "$W/build" --output-on-failure > "$W/ctest.log" 2>&1
J="$W/build/jass"
[ -x "$J" ] || { restore_src; die "build produced no executable"; }
restore_src
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/PARENT.pjtw" \
  > "$W/load-parent.log" 2>&1
grep -q '^ready' "$W/load-parent.log" || die "PRIORTIGHT is not loadable"
say "  build, tests and parent load passed"

stage python-runtime
python3 -m venv "$W/venv"
if "$W/venv/bin/python" -m pip install --disable-pip-version-check \
     --only-binary=:all: numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1; then
  PINSTACK=historical
else
  "$W/venv/bin/python" -m pip install --disable-pip-version-check \
    --only-binary=:all: numpy scipy >> "$W/pip.log" 2>&1 ||
    die "pip installation failed"
  PINSTACK=current
fi
NPV=$("$W/venv/bin/python" -c 'import numpy,scipy;print(numpy.__version__,scipy.__version__)')
printf '{"stack":"%s","numpy_scipy":"%s"}\n' "$PINSTACK" "$NPV" \
  > "$ART/numeric-stack.json"
env PYTHONPATH="$GEOM:pattern_jass/tools" "$W/venv/bin/python" \
  pattern_jass/tools/test_exact_fold.py -v > "$W/exact-fold-selftest.log" 2>&1 ||
  die "exact-fold self-tests failed"
say "  Python stack and exact-fold self-tests passed"

LAST_ELAPSED_MS=0
gen_arm(){
  local prefix="$1" records="$2" shards="$3" timeout_s="$4"
  local seed_base="$5" mode="$6" node_spec="${7:-}"
  local base=$((records / shards)) rem=$((records % shards))
  local shard count pid rc failed=0 idx
  local pids=() shard_ids=()
  local start_ns end_ns
  : > "$ART/producer-exits-$prefix.txt"
  start_ns=$(date +%s%N)
  for shard in $(seq 0 $((shards - 1))); do
    count="$base"
    [ "$shard" -lt "$rem" ] && count=$((count + 1))
    args=(
      timeout "$timeout_s" "$J" --gen-data-wdl "$count"
      "$W/$prefix-s$shard.jnnw" "$LABEL_DEPTH" "$PLAY_DEPTH"
      "$MAXPLIES" "$((seed_base + shard))"
      --nnue "$W/PARENT.pjtw" --search-params-play "$Q00"
      --wdl-zero-score --random-open-plies 8 --explore-eps "$EXPLORE_EPS"
      --explore-decay-plies "$EXPLORE_DECAY" --split-selfplay-rngs
      --pair-openings --drop-plycap
      --sample-meta-out "$W/$prefix-s$shard.jsm"
    )
    if [ "$mode" = nodes ]; then
      args+=(
        --search-limit nodes --node-budget-weighted "$node_spec"
        --node-budget-sample-per move
        --node-budget-log "$W/$prefix-s$shard.jsonl"
      )
    elif [ "$mode" != depth ]; then
      die "invalid generation mode $mode"
    fi
    "${args[@]}" < /dev/null > "$W/$prefix-s$shard.log" 2>&1 &
    pids+=("$!")
    shard_ids+=("$shard")
  done
  for idx in "${!pids[@]}"; do
    pid="${pids[$idx]}"
    shard="${shard_ids[$idx]}"
    if wait "$pid"; then rc=0; else rc=$?; fi
    printf 'prefix=%s shard=%s pid=%s rc=%s timeout_s=%s\n' \
      "$prefix" "$shard" "$pid" "$rc" "$timeout_s" |
      tee -a "$ART/producer-exits-$prefix.txt"
    [ "$rc" -eq 0 ] || failed=$((failed + 1))
  done
  end_ns=$(date +%s%N)
  LAST_ELAPSED_MS=$(( (end_ns - start_ns) / 1000000 ))
  [ "$LAST_ELAPSED_MS" -gt 0 ] || LAST_ELAPSED_MS=1
  [ "$failed" -eq 0 ] || die "$prefix generation: $failed producer failures"
  for log in "$W"/"$prefix"-s*.log; do
    grep -q 'label_score_searches=0' "$log" ||
      die "score-label search found in $log"
    grep -q 'split_selfplay_rngs=1' "$log" ||
      die "split RNGs inactive in $log"
  done
  python3 - "$W" "$prefix" "$records" <<'PY'
import pathlib
import struct
import sys
w = pathlib.Path(sys.argv[1])
prefix = sys.argv[2]
expected = int(sys.argv[3])
total = 0
for path in sorted(w.glob(f"{prefix}-s*.jnnw")):
    raw = path.read_bytes()[:8]
    if len(raw) != 8 or raw[:4] != b"JNNW":
        raise SystemExit(f"{path}: invalid JNNW header")
    total += struct.unpack_from("<I", raw, 4)[0]
if total != expected:
    raise SystemExit(f"{prefix}: {total} records, expected {expected}")
PY
  say "  $prefix: records=$records elapsed_ms=$LAST_ELAPSED_MS"
}

summarize_node_logs(){
  local prefix="$1" out="$2"
  python3 - "$W" "$prefix" "$out" <<'PY'
import collections
import json
import pathlib
import sys
w = pathlib.Path(sys.argv[1])
prefix = sys.argv[2]
out = pathlib.Path(sys.argv[3])
searches = games = nodes = budgets = aborted = elapsed_ms = 0
buckets = collections.Counter()
manifests = []
for path in sorted(w.glob(f"{prefix}-s*.jsonl")):
    first = last = None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            first = event if first is None else first
            last = event
            kind = event.get("event")
            if kind == "selfplay_search":
                searches += 1
                nodes += int(event["nodes_used"])
                budget = int(event["nodes_budget"])
                budgets += budget
                elapsed_ms += float(event["search_time_ms"])
                aborted += int(bool(event["aborted_iteration"]))
                buckets[budget] += 1
            elif kind == "selfplay_game":
                games += 1
    if not first or first.get("event") != "node_budget_manifest":
        raise SystemExit(f"{path}: manifest missing")
    if not last or last.get("event") != "node_budget_summary":
        raise SystemExit(f"{path}: final summary missing")
    manifests.append(first)
if not manifests:
    raise SystemExit(f"{prefix}: no node logs")
policy = {
    key: manifests[0][key]
    for key in ("distribution", "sample_per", "sampler_version", "values")
}
for manifest in manifests[1:]:
    for key in ("distribution", "sample_per", "sampler_version", "values"):
        if manifest[key] != manifests[0][key]:
            raise SystemExit(f"{prefix}: manifest drift for {key}")
payload = {
    "schema": 1,
    "prefix": prefix,
    "shards": len(manifests),
    "searches": searches,
    "games": games,
    "nodes_used_total": nodes,
    "budget_requested_total": budgets,
    "nodes_used_mean": nodes / searches if searches else 0,
    "budget_mean": budgets / searches if searches else 0,
    "aggregate_nodes_used_over_budget": nodes / budgets if budgets else 0,
    "search_time_ms_total": elapsed_ms,
    "nps": nodes * 1000 / elapsed_ms if elapsed_ms else 0,
    "aborted_iterations": aborted,
    "buckets": dict(sorted(buckets.items())),
    "policy": policy,
}
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
}

stage calibrate-raw-distribution
gen_arm cal-depth "$CAL_RECORDS" "$CAL_SHARDS" "$CAL_TIMEOUT" \
  "$CAL_BASE_SEED" depth
CAL_DEPTH_MS="$LAST_ELAPSED_MS"
gen_arm cal-nodes-raw "$CAL_RECORDS" "$CAL_SHARDS" "$CAL_TIMEOUT" \
  "$CAL_BASE_SEED" nodes "$RAW_NODE_SPEC"
CAL_RAW_MS="$LAST_ELAPSED_MS"
summarize_node_logs cal-nodes-raw "$ART/calibration-raw-node-summary.json"

scale_node_spec(){
python3 - "$1" "$2" "$3" "$4" <<'PY'
from decimal import Decimal, ROUND_HALF_UP
import json
import sys
depth_ms, node_ms = map(int, sys.argv[1:3])
raw_spec = sys.argv[3]
out = sys.argv[4]
if depth_ms <= 0 or node_ms <= 0:
    raise SystemExit("non-positive calibration duration")
scale = Decimal(depth_ms) / Decimal(node_ms)
if not Decimal("0.005") <= scale <= Decimal("5.00"):
    raise SystemExit(f"required scale {scale} outside safe [0.005, 5.00]")
merged = {}
for token in raw_spec.split(","):
    nodes_s, weight_s = token.split(":")
    raw_nodes, weight = int(nodes_s), int(weight_s)
    if raw_nodes <= 0 or weight <= 0:
        raise SystemExit("node spec must contain positive nodes and weights")
    scaled = int(
        (Decimal(raw_nodes) * scale / Decimal(1000)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    ) * 1000
    scaled = max(1000, scaled)
    merged[scaled] = merged.get(scaled, 0) + weight
spec = ",".join(f"{nodes}:{weight}" for nodes, weight in sorted(merged.items()))
raw_mean = sum(
    int(token.split(":")[0]) * int(token.split(":")[1])
    for token in raw_spec.split(",")
) / sum(int(token.split(":")[1]) for token in raw_spec.split(","))
mean = sum(nodes * weight for nodes, weight in merged.items()) / sum(merged.values())
payload = {
    "schema": 1,
    "method": "target_box_wall_time_ratio",
    "depth_elapsed_ms": depth_ms,
    "raw_nodes_elapsed_ms": node_ms,
    "raw_nodes_over_depth_time": node_ms / depth_ms,
    "scale": float(scale),
    "raw_spec": raw_spec,
    "raw_requested_mean": raw_mean,
    "scaled_spec": spec,
    "scaled_requested_mean": mean,
    "rounding": "nearest_1000_then_merge_equal_buckets",
    "safe_scale_interval": [0.005, 5.00],
}
with open(out, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
print(spec)
PY
}

write_calibration_cost(){
python3 - "$1" "$2" "$3" "$4" "$5" "$6" <<'PY'
import json
import sys
depth_ms, raw_ms, confirm_ms, records = map(int, sys.argv[1:5])
node_spec, out = sys.argv[5:7]
ratio = confirm_ms / depth_ms
payload = {
    "schema": 1,
    "records_per_cell": records,
    "depth_elapsed_ms": depth_ms,
    "raw_nodes_elapsed_ms": raw_ms,
    "confirmed_nodes_elapsed_ms": confirm_ms,
    "raw_nodes_over_depth_time": raw_ms / depth_ms,
    "confirmed_nodes_over_depth_time": ratio,
    "confirmed_node_spec": node_spec,
    "accepted_interval": [0.75, 1.35],
    "accepted": 0.75 <= ratio <= 1.35,
}
with open(out, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
print(1 if payload["accepted"] else 0)
PY
}

SCALED_NODE_SPEC=$(scale_node_spec "$CAL_DEPTH_MS" "$CAL_RAW_MS" \
  "$RAW_NODE_SPEC" "$ART/calibration-scale-initial.json") ||
  die "raw calibration cannot be safely rescaled"
[ -n "$SCALED_NODE_SPEC" ] || die "scaled node distribution is empty"
say "  calibrated node distribution: $SCALED_NODE_SPEC"

stage confirm-calibrated-cost
gen_arm cal-nodes-confirm "$CAL_RECORDS" "$CAL_SHARDS" "$CAL_TIMEOUT" \
  "$CAL_BASE_SEED" nodes "$SCALED_NODE_SPEC"
CAL_CONFIRM_MS="$LAST_ELAPSED_MS"
summarize_node_logs cal-nodes-confirm "$ART/calibration-confirm-node-summary.json"
CONFIRM_ACCEPTED=$(write_calibration_cost "$CAL_DEPTH_MS" "$CAL_RAW_MS" \
  "$CAL_CONFIRM_MS" "$CAL_RECORDS" "$SCALED_NODE_SPEC" \
  "$ART/calibration-cost-initial.json")

if [ "$CONFIRM_ACCEPTED" = 1 ]; then
  cp "$ART/calibration-scale-initial.json" "$ART/calibration-scale.json"
  cp "$ART/calibration-cost-initial.json" "$ART/calibration-cost.json"
else
  stage refine-calibrated-cost-once
  REFINED_NODE_SPEC=$(scale_node_spec "$CAL_DEPTH_MS" "$CAL_CONFIRM_MS" \
    "$SCALED_NODE_SPEC" "$ART/calibration-scale.json") ||
    die "feedback calibration cannot be safely rescaled"
  [ -n "$REFINED_NODE_SPEC" ] || die "refined node distribution is empty"
  [ "$REFINED_NODE_SPEC" != "$SCALED_NODE_SPEC" ] ||
    die "feedback calibration cannot change the quantized distribution"
  SCALED_NODE_SPEC="$REFINED_NODE_SPEC"
  say "  feedback-calibrated node distribution: $SCALED_NODE_SPEC"
  gen_arm cal-nodes-refined "$CAL_RECORDS" "$CAL_SHARDS" "$CAL_TIMEOUT" \
    "$CAL_BASE_SEED" nodes "$SCALED_NODE_SPEC"
  CAL_CONFIRM_MS="$LAST_ELAPSED_MS"
  summarize_node_logs cal-nodes-refined \
    "$ART/calibration-refined-node-summary.json"
  CONFIRM_ACCEPTED=$(write_calibration_cost "$CAL_DEPTH_MS" "$CAL_RAW_MS" \
    "$CAL_CONFIRM_MS" "$CAL_RECORDS" "$SCALED_NODE_SPEC" \
    "$ART/calibration-cost.json")
  [ "$CONFIRM_ACCEPTED" = 1 ] ||
    die "feedback-calibrated cost remains outside [0.75, 1.35]"
fi
say "  target-box cost confirmation passed"
rm -f "$W"/cal-*.jnnw "$W"/cal-*.jsm "$W"/cal-*.jsonl

stage generate-depth-1m
gen_arm depth "$RECORDS_PER_ARM" "$SHARDS" "$GEN_TIMEOUT_DEPTH" \
  "$BASE_SEED" depth
FULL_DEPTH_MS="$LAST_ELAPSED_MS"

stage generate-nodes-1m
gen_arm nodes "$RECORDS_PER_ARM" "$SHARDS" "$GEN_TIMEOUT_NODES" \
  "$BASE_SEED" nodes "$SCALED_NODE_SPEC"
FULL_NODES_MS="$LAST_ELAPSED_MS"
summarize_node_logs nodes "$ART/node-budget-summary.json"
(cd "$W" && tar -czf "$ART/node-budget-telemetry.tar.gz" nodes-s*.jsonl)

stage merge-split-and-diagnostics
for arm in depth nodes; do
  pairs=()
  for shard in $(seq 0 $((SHARDS - 1))); do
    pairs+=(--pair "$W/$arm-s$shard.jnnw" "$W/$arm-s$shard.jsm")
  done
  python3 tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested \
    --out-data "$W/$arm.raw.jnnw" --out-meta "$W/$arm.raw.jsm" \
    --manifest "$ART/$arm-merge.json" > "$W/$arm-merge.log" 2>&1 ||
    die "$arm merge failed"
  python3 tools/selfplay_frontier.py split \
    --data "$W/$arm.raw.jnnw" --meta "$W/$arm.raw.jsm" \
    --out-data "$W/$arm.fit.jnnw" --out-meta "$W/$arm.fit.jsm" \
    --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
    --manifest "$ART/$arm-split.json" > "$W/$arm-split.log" 2>&1 ||
    die "$arm split failed"
  env PYTHONPATH="$GEOM:pattern_jass/tools" "$W/venv/bin/python" \
    jobs/tools/l3_bucket_visits.py --data "$W/$arm.raw.jnnw" \
    --out "$ART/$arm-coverage.json" > "$W/$arm-coverage.log" 2>&1 ||
    die "$arm coverage failed"
  python3 jobs/tools/assert_corpus_wdl.py --data "$W/$arm.raw.jnnw" \
    --out "$ART/$arm-corpus-wdl.json" > "$W/$arm-wdl.log" 2>&1 ||
    die "$arm WDL canary failed"
  gzip -n -c "$W/$arm.raw.jnnw" > "$ART/$arm.jnnw.gz"
  gzip -n -c "$W/$arm.raw.jsm" > "$ART/$arm.jsm.gz"
done

python3 - "$ART/depth-split.json" "$ART/nodes-split.json" \
  "$ART/paired-split-check.json" <<'PY'
import json
import sys
a, b = (json.load(open(path)) for path in sys.argv[1:3])
for key in ("split_unit", "holdout_mod", "seed", "tail_is_holdout"):
    if a.get(key) != b.get(key):
        raise SystemExit(f"split mismatch for {key}")
for name, manifest in (("depth", a), ("nodes", b)):
    for key in ("train_openings", "holdout_openings",
                "train_records", "holdout_records"):
        if int(manifest.get(key, 0)) <= 0:
            raise SystemExit(f"{name}: non-positive {key}")
payload = {
    "schema": 1,
    "paired_seed_schedule": True,
    "split_contract_equal": True,
    "depth": {k: a[k] for k in (
        "train_openings", "holdout_openings", "train_records", "holdout_records"
    )},
    "nodes": {k: b[k] for k in (
        "train_openings", "holdout_openings", "train_records", "holdout_records"
    )},
}
with open(sys.argv[3], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

fit_arm(){
  local arm="$1"
  local hold
  hold=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' \
    "$ART/$arm-split.json")
  [ "$hold" -gt 0 ] || die "$arm holdout is empty"
  stage "dump-features-$arm"
  "$J" --dump-eval-features "$W/$arm.fit.jnnw" "$W/$arm.feat" \
    > "$W/$arm-features.log" 2>&1 || die "$arm feature dump failed"
  K=$(python3 -c 'import struct,sys; f=open(sys.argv[1],"rb"); assert f.read(4)==b"FEAT"; print(struct.unpack("<II",f.read(8))[1])' \
    "$W/$arm.feat")
  [ "$K" -eq 120 ] || die "$arm extras K=$K expected 120"
  stage "fit-$arm"
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    PYTHONUNBUFFERED=1 \
    timeout "$FIT_TIMEOUT" "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
      --data "$W/$arm.fit.jnnw" --feat "$W/$arm.feat" \
      --out "$W/$arm.pjtw" --target wdl --loss logistic \
      --exact-fold --tempo-stage --prior-mean "$W/PARENT.pjtw" \
      --prior-decay 0 --holdout-count "$hold" \
      --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
      --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
      --prune --optimizer-report "$ART/$arm-optimizer.json" \
      > "$W/fit-$arm.log" 2> "$W/fit-$arm-time.log"
  fit_rc=$?
  set -e
  [ "$fit_rc" -eq 0 ] || die "$arm fit failed rc=$fit_rc"
  [ -s "$W/$arm.pjtw" ] || die "$arm fit produced no model"
  python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("success") else 1)' \
    "$ART/$arm-optimizer.json" || die "$arm optimizer did not converge"
  gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  say "  $arm fit converged"
}

fit_arm depth
fit_arm nodes

stage publish-certificate
python3 - "$W" "$ART" "$EXPECTED_CODE_SHA" "$PARENT_SHA256" \
  "$RECORDS_PER_ARM" "$FULL_DEPTH_MS" "$FULL_NODES_MS" \
  "$SCALED_NODE_SPEC" <<'PY'
import hashlib
import json
import pathlib
import re
import sys
w, art = map(pathlib.Path, sys.argv[1:3])
code_sha, parent_sha = sys.argv[3:5]
records, depth_ms, nodes_ms = map(int, sys.argv[5:8])
node_spec = sys.argv[8]
arms = {}
for arm in ("depth", "nodes"):
    optimizer = json.load(open(art / f"{arm}-optimizer.json"))
    coverage = json.load(open(art / f"{arm}-coverage.json"))
    wdl = json.load(open(art / f"{arm}-corpus-wdl.json"))
    fit_log = (w / f"fit-{arm}.log").read_text(errors="replace")
    match = re.search(r"HOLDOUT_LOGLOSS[ =:]+([0-9.]+)", fit_log)
    arms[arm] = {
        "model_sha256": hashlib.sha256((w / f"{arm}.pjtw").read_bytes()).hexdigest(),
        "optimizer": {
            "success": optimizer.get("success"),
            "iterations": optimizer.get("iterations", optimizer.get("nit")),
            "gradient_inf_norm": optimizer.get("gradient_inf_norm"),
        },
        "holdout_logloss": float(match.group(1)) if match else None,
        "wdl": wdl,
        "coverage": {
            "visited_buckets": coverage["coverage"]["visited_buckets"],
            "visited_pct": 100.0 * coverage["coverage"]["coverage_fraction"],
            "gini": coverage["concentration"]["gini"],
        },
    }
node_summary = json.load(open(art / "node-budget-summary.json"))
calibration = json.load(open(art / "calibration-cost.json"))
scale = json.load(open(art / "calibration-scale.json"))
payload = {
    "schema": 1,
    "verdict": "L3_NODE_BUDGET_PILOT_ARMS_READY",
    "code_sha": code_sha,
    "parent": {"name": "PRIORTIGHT", "model_sha256": parent_sha},
    "primary_contrast": "NODES minus DEPTH",
    "design": {
        "single_factor": "play search limit: historical depth 8 versus deterministic weighted nodes",
        "fresh_records_total": 2 * records,
        "records_per_arm": records,
        "play_depth_control": 8,
        "node_budget_sample_per": "move",
        "node_budget_sampler_version": 1,
        "node_budget_spec": node_spec,
        "opening_seed_base": 2718281,
        "split_seed": 577215,
        "split_selfplay_rngs": True,
        "explore_eps": 8,
        "explore_decay_plies": 60,
        "training": {
            "fold": "exact",
            "prior_mean": "PRIORTIGHT",
            "prior_decay": 0,
            "l2": "3e-5",
            "lbfgs_gtol": "1e-4",
        },
    },
    "target_box_calibration": {
        "scale": scale,
        "confirmation": calibration,
        "full_generation_elapsed_ms": {
            "depth": depth_ms,
            "nodes": nodes_ms,
            "nodes_over_depth": nodes_ms / depth_ms if depth_ms else None,
        },
    },
    "node_budget_telemetry": node_summary,
    "arms": arms,
    "models_byte_identical": (
        (w / "depth.pjtw").read_bytes() == (w / "nodes.pjtw").read_bytes()
    ),
    "required_readout": (
        "NODES versus DEPTH on fresh paired openings, both colours, "
        "Q00 and native views; holdout is diagnostic only"
    ),
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__L3_NODE_BUDGET_PILOT_ARMS_READY").write_text(
    "L3_NODE_BUDGET_PILOT_ARMS_READY\n"
)
(art / "PROMOTION_AUTHORIZED__FALSE").write_text(
    "PROMOTION_AUTHORIZED__FALSE\n"
)
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text(
    "AUTOMATIC_NEXT_JOB__NULL\n"
)
print(
    f"depth={arms['depth']['model_sha256']} "
    f"nodes={arms['nodes']['model_sha256']} "
    f"full_cost_ratio={nodes_ms / depth_ms:.3f}"
)
PY
say "L3_NODE_BUDGET_PILOT_ARMS_READY promotion=false automatic_next_job=null"
