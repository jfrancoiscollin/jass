#!/usr/bin/env bash
# L3-PURE — causal fit: UNIFORM_REPLAY vs HARD_REPLAY.
#
# One common fresh 1M corpus is generated once.  Each arm adds 1M records from
# the same immutable historical train partition, selected either uniformly or
# by failed_conversion.  Both fits share a bit-identical fresh holdout tail.
# This job trains and authenticates two models; it plays no strength match.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${ENGINE_REFERENCE_SHA:?}"
: "${PREFLIGHT_PREFIX:?}"; : "${EXPECTED_PREFLIGHT_JOB:?}"
: "${EXPECTED_PREFLIGHT_ATTEMPT:?}"; : "${EXPECTED_PREFLIGHT_CODE_SHA:?}"
: "${HISTORY_PREFIX:?}"; : "${EXPECTED_HISTORY_JOB:?}"
: "${EXPECTED_HISTORY_ATTEMPT:?}"; : "${EXPECTED_HISTORY_CODE_SHA:?}"
: "${EXPECTED_HISTORY_STATE:?}"; : "${HISTORY_DATA_ARTEFACT:?}"
: "${HISTORY_META_ARTEFACT:?}"; : "${HISTORY_SPLIT_ARTEFACT:?}"
: "${HISTORY_ARM:?}"
: "${PARENT_PREFIX:?}"; : "${EXPECTED_PARENT_JOB:?}"; : "${PARENT_ARTEFACT:?}"
: "${PARENT_MODEL_SHA:?}"; : "${PARENT_NAME:?}"; : "${FRESH_POLICY:?}"

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

FRESH_RECORDS=${FRESH_RECORDS:-1000000}
REPLAY_RECORDS=${REPLAY_RECORDS:-1000000}
SHARDS=${SHARDS:-6}
LABEL_DEPTH=4
PLAY_DEPTH=8
MAXPLIES=260
EXPLORE_EPS=8
EXPLORE_DECAY=60
TOPK=3
EXPLORE_MARGIN=50
BASE_SEED=32452843
SPLIT_SEED=577215
HOLDOUT_MOD=10
UNIFORM_REPLAY_SEED=3141592
GEN_TIMEOUT=${GEN_TIMEOUT:-3600}
FIT_TIMEOUT=${FIT_TIMEOUT:-5400}
L2=3e-5
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
CHUNK=20000
NUMPY_VERSION=${NUMPY_VERSION:-1.26.4}
SCIPY_VERSION=${SCIPY_VERSION:-1.14.1}
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
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        awk '
          /positions$/ { done[FILENAME]=$4; total[FILENAME]=$6 }
          END {
            for (k in done) { d += done[k]; t += total[k] }
            if (t > 0) printf "fresh_positions=%d/%d (%.1f%%)\n",d,t,100*d/t
          }' "$W"/fresh-s*.log 2>/dev/null || true
        for arm in control treatment; do
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

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$FRESH_RECORDS" -eq 1000000 ] || die "causal contract requires 1M fresh"
[ "$REPLAY_RECORDS" -eq 1000000 ] || die "causal contract requires 1M replay"
[ "$SHARDS" -eq 6 ] || die "causal contract requires six fresh producers"
[ "$PLAY_DEPTH" -eq 8 ] || die "causal contract requires d8"
[ "$SPLIT_SEED" -eq 577215 ] || die "split seed drift"
[ "$HOLDOUT_MOD" -eq 10 ] || die "holdout ratio drift"
[[ "$NUMPY_VERSION" =~ ^[0-9]+([.][0-9]+){2}$ ]] ||
  die "NUMPY_VERSION must be an explicit x.y.z pin"
[[ "$SCIPY_VERSION" =~ ^[0-9]+([.][0-9]+){2}$ ]] ||
  die "SCIPY_VERSION must be an explicit x.y.z pin"
[ "$FRESH_POLICY" = uniform ] || [ "$FRESH_POLICY" = topk3 ] ||
  die "FRESH_POLICY must be uniform or topk3"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ "$(nproc)" -ge 12 ] || die "HOME requires at least 12 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 22000 ] ||
  die "need 22 GiB free"
git diff --quiet "$ENGINE_REFERENCE_SHA" HEAD -- src pattern_jass/tools ||
  die "engine/trainer semantics changed since the pinned parent recipe"
say "  design: 1M common fresh + 1M replay per arm; fresh_policy=$FRESH_POLICY"
say "  design: only historical replay selection differs"
say "  resources: six producers once, then two sequential 2M fits"
monitor

phase fetch-and-authenticate-preflight
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=hard-preflight.json \
  --file artefacts/hard-replay.jnnw.gz=hard-replay.jnnw.gz \
  --file artefacts/hard-replay.jsm.gz=hard-replay.jsm.gz \
  --file artefacts/hard-mining-manifest.json=hard-mining-manifest.json \
  --out-dir "$IN" --report "$ART/verified-hard-preflight.json" \
  > "$W/fetch-hard-preflight.log" 2>&1
python3 - "$ART/verified-hard-preflight.json" "$IN/hard-preflight.json" \
  "$EXPECTED_PREFLIGHT_JOB" "$EXPECTED_PREFLIGHT_ATTEMPT" \
  "$EXPECTED_PREFLIGHT_CODE_SHA" \
  "$REPLAY_RECORDS" "$EXPECTED_HISTORY_JOB" "$EXPECTED_HISTORY_ATTEMPT" \
  "$EXPECTED_HISTORY_CODE_SHA" "$EXPECTED_HISTORY_STATE" "$HISTORY_ARM" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

report = json.load(open(sys.argv[1]))
summary = json.load(open(sys.argv[2]))
job, attempt, code_sha, records = sys.argv[3], sys.argv[4], sys.argv[5], int(sys.argv[6])
source = summary.get("source", {})
if (
    report.get("job_id") != job
    or report.get("attempt_id") != attempt
    or report.get("code_sha") != code_sha
    or report.get("result_state") != "completed"
    or summary.get("verdict") != "L3_PURE_HARD_REPLAY_CATALOGUE_READY"
    or summary.get("code_sha") != code_sha
    or summary.get("selection", {}).get("records") != records
    or summary.get("training_authorized") is not True
    or summary.get("promotion_authorized") is not False
    or summary.get("automatic_next_job") is not None
    or source.get("job_id") != sys.argv[7]
    or source.get("attempt_id") != sys.argv[8]
    or source.get("code_sha") != sys.argv[9]
    or source.get("state") != sys.argv[10]
    or source.get("arm") != sys.argv[11]
):
    raise SystemExit("hard replay preflight certificate mismatch")
for name in ("hard-replay.jnnw.gz", "hard-replay.jsm.gz"):
    digest = hashlib.sha256((Path(sys.argv[2]).parent / name).read_bytes()).hexdigest()
    if summary.get("outputs", {}).get(name) != digest:
        raise SystemExit(f"hard replay compressed hash mismatch for {name}")
PY
gunzip -c "$IN/hard-replay.jnnw.gz" > "$W/hard-replay.jnnw"
gunzip -c "$IN/hard-replay.jsm.gz" > "$W/hard-replay.jsm"

phase fetch-and-authenticate-history
python3 jobs/tools/fetch_result_files.py --prefix "$HISTORY_PREFIX" \
  --expected-state "$EXPECTED_HISTORY_STATE" \
  --file "artefacts/$HISTORY_DATA_ARTEFACT=history.jnnw.gz" \
  --file "artefacts/$HISTORY_META_ARTEFACT=history.jsm.gz" \
  --file "artefacts/$HISTORY_SPLIT_ARTEFACT=source-split.json" \
  --out-dir "$IN" --report "$ART/verified-history-source.json" \
  > "$W/fetch-history.log" 2>&1
python3 - "$ART/verified-history-source.json" "$EXPECTED_HISTORY_JOB" \
  "$EXPECTED_HISTORY_ATTEMPT" "$EXPECTED_HISTORY_CODE_SHA" \
  "$EXPECTED_HISTORY_STATE" "$IN/hard-preflight.json" \
  "$IN/history.jnnw.gz" "$IN/history.jsm.gz" "$IN/source-split.json" <<'PY'
import hashlib
import json
import sys

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

report = json.load(open(sys.argv[1]))
if (
    report.get("job_id") != sys.argv[2]
    or report.get("attempt_id") != sys.argv[3]
    or report.get("code_sha") != sys.argv[4]
    or report.get("result_state") != sys.argv[5]
):
    raise SystemExit("historical source identity/state mismatch")
source = json.load(open(sys.argv[6])).get("source", {})
expected = {
    "history.jnnw.gz": source.get("data_gz_sha256"),
    "history.jsm.gz": source.get("meta_gz_sha256"),
}
actual = {row["local_name"]: row["sha256"] for row in report["files"]}
for name, expected_digest in expected.items():
    if actual.get(name) != expected_digest:
        raise SystemExit(f"historical compressed hash mismatch for {name}")
if digest(sys.argv[7]) != expected["history.jnnw.gz"]:
    raise SystemExit("downloaded historical JNNW gzip hash mismatch")
if digest(sys.argv[8]) != expected["history.jsm.gz"]:
    raise SystemExit("downloaded historical JSM1 gzip hash mismatch")
if json.load(open(sys.argv[9])) != source.get("split"):
    raise SystemExit("historical source split differs from preflight certificate")
PY
gunzip -c "$IN/history.jnnw.gz" > "$W/history.raw.jnnw"
gunzip -c "$IN/history.jsm.gz" > "$W/history.raw.jsm"
python3 - "$IN/hard-preflight.json" "$W/history.raw.jnnw" \
  "$W/history.raw.jsm" <<'PY'
import hashlib
import json
import sys

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

source = json.load(open(sys.argv[1]))["source"]
if digest(sys.argv[2]) != source.get("data_sha256"):
    raise SystemExit("historical raw JNNW hash differs from preflight certificate")
if digest(sys.argv[3]) != source.get("meta_sha256"):
    raise SystemExit("historical raw JSM1 hash differs from preflight certificate")
PY
python3 tools/selfplay_frontier.py split \
  --data "$W/history.raw.jnnw" --meta "$W/history.raw.jsm" \
  --out-data "$W/history.fit.jnnw" --out-meta "$W/history.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/history-split.json" > "$W/history-split.log" 2>&1
cmp -s "$IN/source-split.json" "$ART/history-split.json" ||
  die "historical split reproduction drift"

phase fetch-and-authenticate-parent
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_PREFIX" \
  --file "artefacts/$PARENT_ARTEFACT=PARENT.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-parent.json" \
  > "$W/fetch-parent.log" 2>&1
python3 - "$ART/verified-parent.json" "$EXPECTED_PARENT_JOB" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit("parent source identity/state mismatch")
PY
gunzip -c "$IN/PARENT.pjtw.gz" > "$W/PARENT.pjtw"
[ "$(sha256sum "$W/PARENT.pjtw" | awk '{print $1}')" = "$PARENT_MODEL_SHA" ] ||
  die "parent model hash drift"

phase build-and-tests
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: "numpy==$NUMPY_VERSION" "scipy==$SCIPY_VERSION" \
  > "$W/pip.log" 2>&1
"$W/venv/bin/python" - "$ART/python-science-stack.json" \
  "$NUMPY_VERSION" "$SCIPY_VERSION" <<'PY'
import json
import platform
import sys

import numpy
import scipy

expected_numpy, expected_scipy = sys.argv[2:]
if numpy.__version__ != expected_numpy or scipy.__version__ != expected_scipy:
    raise SystemExit(
        "installed science stack differs from explicit pins: "
        f"numpy={numpy.__version__} scipy={scipy.__version__}"
    )
payload = {
    "schema": 1,
    "python": platform.python_version(),
    "numpy": numpy.__version__,
    "scipy": scipy.__version__,
    "pins_explicit": True,
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
python3 -m py_compile tools/selfplay_frontier.py \
  jobs/tools/l3_hard_replay_assembly.py
python3 -m unittest jobs.tests.test_selfplay_hard_mining \
  jobs.tests.test_l3_hard_replay_assembly \
  > "$W/test-hard-replay.log" 2>&1
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

phase generate-common-fresh
base=$((FRESH_RECORDS / SHARDS))
rem=$((FRESH_RECORDS % SHARDS))
pids=()
shards=()
: > "$ART/producer-exits-fresh.txt"
policy_args=()
if [ "$FRESH_POLICY" = topk3 ]; then
  policy_args=(--explore-topk "$TOPK" --explore-margin "$EXPLORE_MARGIN")
fi
for shard in $(seq 0 $((SHARDS - 1))); do
  count="$base"; [ "$shard" -lt "$rem" ] && count=$((count + 1))
  timeout "$GEN_TIMEOUT" "$J" --gen-data-wdl "$count" \
    "$W/fresh-s$shard.jnnw" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" \
    $((BASE_SEED + shard)) \
    --nnue "$W/PARENT.pjtw" --search-params-play "$Q00" --wdl-zero-score \
    --random-open-plies 8 --explore-eps "$EXPLORE_EPS" \
    --explore-decay-plies "$EXPLORE_DECAY" --split-selfplay-rngs \
    "${policy_args[@]}" --pair-openings --drop-plycap \
    --sample-meta-out "$W/fresh-s$shard.jsm" \
    < /dev/null > "$W/fresh-s$shard.log" 2>&1 &
  pids+=("$!")
  shards+=("$shard")
done
failed=0
for index in "${!pids[@]}"; do
  if wait "${pids[$index]}"; then rc=0; else rc=$?; fi
  printf 'shard=%s pid=%s rc=%s timeout_s=%s\n' \
    "${shards[$index]}" "${pids[$index]}" "$rc" "$GEN_TIMEOUT" |
    tee -a "$ART/producer-exits-fresh.txt"
  [ "$rc" -eq 0 ] || failed=$((failed + 1))
done
[ "$failed" -eq 0 ] || die "fresh generation: $failed producer failures"
grep '^EXPLORATION' "$W"/fresh-s*.log > "$ART/exploration-fresh.txt"
python3 - "$W" "$ART/exploration-fresh.txt" "$FRESH_RECORDS" \
  "$FRESH_POLICY" "$PLAY_DEPTH" <<'PY'
import json
import pathlib
import struct
import sys

w = pathlib.Path(sys.argv[1])
report = pathlib.Path(sys.argv[2])
expected = int(sys.argv[3])
policy = sys.argv[4]
play_depth = int(sys.argv[5])

total = 0
for path in sorted(w.glob("fresh-s*.jnnw")):
    head = path.read_bytes()[:8]
    if len(head) != 8 or head[:4] != b"JNNW":
        raise SystemExit(f"{path}: invalid JNNW header")
    total += struct.unpack_from("<I", head, 4)[0]
if total != expected:
    raise SystemExit(f"fresh record count {total} != {expected}")

counters = {}
for line in report.read_text().splitlines():
    for token in line.split():
        key, sep, value = token.partition("=")
        if sep and value.lstrip("-").isdigit():
            counters.setdefault(key, []).append(int(value))
if not counters.get("split_selfplay_rngs") or set(counters["split_selfplay_rngs"]) != {1}:
    raise SystemExit("fresh generation did not activate split RNGs")
ranked = sum(counters.get("topk_ranked_plies", []))
if policy == "uniform" and ranked != 0:
    raise SystemExit(f"uniform fresh generation ranked {ranked} plies")
if policy == "topk3":
    if ranked <= 0:
        raise SystemExit("topk3 fresh generation ranked zero plies")
    if (
        not counters.get("topk_rank_depth")
        or set(counters["topk_rank_depth"]) != {play_depth - 1}
    ):
        raise SystemExit("topk3 fresh rank-depth drift")
    if sum(counters.get("margin_singleton_plies", [])) <= 0:
        raise SystemExit("topk3 fresh margin never constrained exploration")
payload = {
    "schema": 1,
    "policy": policy,
    "records": total,
    "split_selfplay_rngs": True,
    "topk_ranked_plies": ranked,
    "topk_rank_depth": play_depth - 1 if policy == "topk3" else None,
    "ok": True,
}
(report.parent / "fresh-policy-check.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
pairs=()
for shard in $(seq 0 $((SHARDS - 1))); do
  grep -q 'label_score_searches=0' "$W/fresh-s$shard.log" ||
    die "score-label search in fresh shard $shard"
  pairs+=(--pair "$W/fresh-s$shard.jnnw" "$W/fresh-s$shard.jsm")
done
python3 tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested \
  --out-data "$W/fresh.raw.jnnw" --out-meta "$W/fresh.raw.jsm" \
  --manifest "$ART/fresh-merge.json" > "$W/fresh-merge.log" 2>&1
python3 tools/selfplay_frontier.py split \
  --data "$W/fresh.raw.jnnw" --meta "$W/fresh.raw.jsm" \
  --out-data "$W/fresh.fit.jnnw" --out-meta "$W/fresh.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/fresh-split.json" > "$W/fresh-split.log" 2>&1
python3 jobs/tools/assert_corpus_wdl.py --data "$W/fresh.raw.jnnw" \
  --out "$ART/fresh-corpus-wdl.json" > "$W/fresh-wdl.log" 2>&1 ||
  die "fresh WDL canary failed"
gzip -n -c "$W/fresh.raw.jnnw" > "$ART/fresh-common.jnnw.gz"
gzip -n -c "$W/fresh.raw.jsm" > "$ART/fresh-common.jsm.gz"

phase assemble-causal-fit-corpora
python3 jobs/tools/l3_hard_replay_assembly.py \
  --history-data "$W/history.fit.jnnw" --history-meta "$W/history.fit.jsm" \
  --history-split-manifest "$ART/history-split.json" \
  --fresh-data "$W/fresh.fit.jnnw" --fresh-meta "$W/fresh.fit.jsm" \
  --fresh-split-manifest "$ART/fresh-split.json" \
  --hard-data "$W/hard-replay.jnnw" --hard-meta "$W/hard-replay.jsm" \
  --hard-manifest "$IN/hard-mining-manifest.json" \
  --replay-records "$REPLAY_RECORDS" --fresh-records "$FRESH_RECORDS" \
  --uniform-seed "$UNIFORM_REPLAY_SEED" --code-sha "$EXPECTED_CODE_SHA" \
  --out-control-data "$W/control.fit.jnnw" \
  --out-control-meta "$W/control.fit.jsm" \
  --out-treatment-data "$W/treatment.fit.jnnw" \
  --out-treatment-meta "$W/treatment.fit.jsm" \
  --manifest "$ART/hard-replay-causal-assembly.json" \
  > "$W/assembly.log" 2>&1
HOLDOUT=$("$W/venv/bin/python" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["records"]["common_holdout"])' \
  "$ART/hard-replay-causal-assembly.json")
[ "$HOLDOUT" -gt 0 ] || die "common holdout missing"

phase profile-and-fit-arms
for arm in control treatment; do
  env PYTHONPATH="$GEOM:pattern_jass/tools" \
    python3 jobs/tools/l3_bucket_visits.py --data "$W/$arm.fit.jnnw" \
    --out "$ART/$arm-coverage.json" > "$W/$arm-coverage.log" 2>&1
  "$J" --dump-eval-features "$W/$arm.fit.jnnw" "$W/$arm.feat" \
    > "$W/$arm-features.log" 2>&1
  phase "fit-$arm"
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    /usr/bin/time -v timeout "$FIT_TIMEOUT" \
    "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
    --data "$W/$arm.fit.jnnw" --feat "$W/$arm.feat" --out "$W/$arm.pjtw" \
    --target wdl --loss logistic --color-fold --tempo-stage \
    --warm-start "$W/PARENT.pjtw" --holdout-count "$HOLDOUT" \
    --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
    --optimizer-report "$ART/$arm-optimizer.json" \
    > "$W/fit-$arm.log" 2> "$W/fit-$arm-time.log"
  fit_rc=$?
  set -e
  [ -s "$W/$arm.pjtw" ] && gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  [ "$fit_rc" -eq 0 ] || die "$arm fit failed rc=$fit_rc"
  "$W/venv/bin/python" - "$ART/$arm-optimizer.json" <<'PY' ||
import json
import sys
if not json.load(open(sys.argv[1])).get("success"):
    raise SystemExit(1)
PY
    die "$arm optimiser did not converge"
  gzip -n -c "$W/$arm.fit.jnnw" > "$ART/$arm.jnnw.gz"
  gzip -n -c "$W/$arm.fit.jsm" > "$ART/$arm.jsm.gz"
done

phase publish-certificate
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" "$PARENT_NAME" \
  "$PARENT_MODEL_SHA" "$FRESH_POLICY" "$FRESH_RECORDS" "$REPLAY_RECORDS" \
  "$HOLDOUT" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

w, art = map(Path, sys.argv[1:3])
code_sha, parent_name, parent_sha, fresh_policy = sys.argv[3:7]
fresh_records, replay_records, holdout = map(int, sys.argv[7:10])
assembly = json.load(open(art / "hard-replay-causal-assembly.json"))
science_stack = json.load(open(art / "python-science-stack.json"))
arms = {}
for arm, name in (("control", "UNIFORM_REPLAY"), ("treatment", "HARD_REPLAY")):
    optimizer = json.load(open(art / f"{arm}-optimizer.json"))
    coverage = json.load(open(art / f"{arm}-coverage.json"))
    log = (w / f"fit-{arm}.log").read_text(errors="replace")
    match = re.search(r"HOLDOUT_LOGLOSS[ =:]+([0-9.]+)", log)
    arms[name] = {
        "model_sha256": hashlib.sha256((w / f"{arm}.pjtw").read_bytes()).hexdigest(),
        "optimizer": optimizer,
        "holdout_logloss_diagnostic_only": float(match.group(1)) if match else None,
        "coverage": coverage,
        "corpus_sha256": hashlib.sha256(
            (w / f"{arm}.fit.jnnw").read_bytes()
        ).hexdigest(),
        "meta_sha256": hashlib.sha256(
            (w / f"{arm}.fit.jsm").read_bytes()
        ).hexdigest(),
    }
payload = {
    "schema": 1,
    "verdict": "L3_PURE_HARD_REPLAY_CAUSAL_AB_ARMS_READY",
    "code_sha": code_sha,
    "parent": {"name": parent_name, "model_sha256": parent_sha},
    "primary_contrast": "HARD_REPLAY minus UNIFORM_REPLAY",
    "design": {
        "single_factor": "historical_replay_selection_policy",
        "fresh_policy_common": fresh_policy,
        "fresh_records_per_arm": fresh_records,
        "historical_replay_records_per_arm": replay_records,
        "total_records_per_arm": fresh_records + replay_records,
        "common_holdout_records": holdout,
        "same_parent": True,
        "same_fresh_corpus": True,
        "same_fit": True,
        "same_holdout": True,
    },
    "assembly": assembly,
    "python_science_stack": science_stack,
    "arms": arms,
    "promotion_authorized": False,
    "automatic_next_job": None,
    "external_teacher_inputs": 0,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(art / "VERDICT__L3_PURE_HARD_REPLAY_CAUSAL_AB_ARMS_READY").touch()
(art / "PROMOTION_AUTHORIZED__FALSE").touch()
(art / "AUTOMATIC_NEXT_JOB__NULL").touch()
for name, result in arms.items():
    print(
        f"  {name}: model={result['model_sha256']} "
        f"converged={result['optimizer'].get('success')}"
    )
PY
phase complete
say "L3_PURE_HARD_REPLAY_CAUSAL_AB_ARMS_READY promotion=false automatic_next_job=null"
