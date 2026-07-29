#!/usr/bin/env bash
# L3-PURE — produce a large post-fix UNIFORM source for hard-replay mining.
#
# This is a data-only job.  It reproduces the UNIFORM arm policy from
# home-1017 at larger volume from the authenticated TURNOVER champion.  It
# does not mine, fit, evaluate, promote, or schedule a continuation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${PARENT_TRAIN_PREFIX:?}"
: "${EXPECTED_PARENT_TRAIN_JOB:?}"; : "${EXPECTED_PARENT_ATTEMPT:?}"
: "${EXPECTED_PARENT_CODE_SHA:?}"; : "${PARENT_ARTEFACT:?}"
: "${PARENT_MODEL_SHA:?}"; : "${PARENT_NAME:?}"

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

SOURCE_RECORDS=${SOURCE_RECORDS:-40000000}
SHARDS=${SHARDS:-6}
LABEL_DEPTH=4
PLAY_DEPTH=8
MAXPLIES=260
EXPLORE_EPS=8
EXPLORE_DECAY=60
BASE_SEED=31415926
SPLIT_SEED=577215
HOLDOUT_MOD=10
RATE_D8=9804
GEN_TIMEOUT=${GEN_TIMEOUT:-72000}
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
        awk -v el="$elapsed" '
          /positions$/ { done[FILENAME] = $4; total[FILENAME] = $6 }
          END {
            for (k in done) { d += done[k]; t += total[k] }
            if (t > 0) {
              printf "uniform_positions=%d/%d (%.1f%%)\n", d, t, 100*d/t
              if (d > 0 && el > 0)
                printf "uniform_eta_remaining_min=%d\n", el*(t-d)/d
            }
          }' "$W"/uniform-s*.log 2>/dev/null || true
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
  rm -rf "$W/build" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm 2>/dev/null || true
  restore_src
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
[ "$SOURCE_RECORDS" -eq 40000000 ] ||
  die "large-source contract requires exactly 40M records"
[ "$SHARDS" -eq 6 ] || die "HOME contract requires six producers"
[ "$PLAY_DEPTH" -eq 8 ] || die "source must remain d8"
[ "$(nproc)" -ge 12 ] || die "HOME requires at least 12 logical CPUs"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -ge 20000 ] || die "need 20 GiB free, got ${DFA}M"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"

PER_SHARD=$(( (SOURCE_RECORDS + SHARDS - 1) / SHARDS ))
HEALTHY_MIN=$(( (PER_SHARD + RATE_D8 - 1) / RATE_D8 ))
say "  source: $SOURCE_RECORDS post-fix UNIFORM records from $PARENT_NAME"
say "  sizing: $SHARDS producers x <=$PER_SHARD records; healthy ETA ~${HEALTHY_MIN} min"
say "  timeout: ${GEN_TIMEOUT}s; mining yield planning buffer=17.8%"
cat > "$ART/generation-plan.txt" <<EOF
policy=uniform
source_records=$SOURCE_RECORDS
shards=$SHARDS
records_per_shard_ceiling=$PER_SHARD
play_depth=$PLAY_DEPTH
label_depth=$LABEL_DEPTH
rate_d8_records_per_min_per_shard=$RATE_D8
healthy_eta_min=$HEALTHY_MIN
generation_timeout_s=$GEN_TIMEOUT
base_seed=$BASE_SEED
split_seed=$SPLIT_SEED
holdout_mod=$HOLDOUT_MOD
max_concurrent_producers=$SHARDS
promotion=false
automatic_next_job=null
EOF
monitor

phase pull-and-assert-pinned-sources
for f in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp \
         src/movegen.cpp src/movegen.hpp src/main.cpp \
         src/selfplay_exploration.hpp; do
  git show "$EXPECTED_CODE_SHA:$f" > "$f" ||
    die "cannot pull $f from $EXPECTED_CODE_SHA"
done
grep -q "root_is_drawn" src/search.cpp ||
  { restore_src; die "engine predates drawn-root fix"; }
grep -q "split_selfplay_rngs" src/main.cpp ||
  { restore_src; die "engine lacks split self-play RNGs"; }

phase fetch-and-authenticate-parent
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_TRAIN_PREFIX" \
  --file "artefacts/$PARENT_ARTEFACT=PARENT.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-parent.json" \
  > "$W/fetch-parent.log" 2>&1
python3 - "$ART/verified-parent.json" "$EXPECTED_PARENT_TRAIN_JOB" \
  "$EXPECTED_PARENT_ATTEMPT" "$EXPECTED_PARENT_CODE_SHA" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if (
    report.get("job_id") != sys.argv[2]
    or report.get("attempt_id") != sys.argv[3]
    or report.get("code_sha") != sys.argv[4]
    or report.get("result_state") != "completed"
):
    raise SystemExit("parent source identity/state mismatch")
PY
gunzip -c "$IN/PARENT.pjtw.gz" > "$W/PARENT.pjtw"
[ "$(sha256sum "$W/PARENT.pjtw" | awk '{print $1}')" = "$PARENT_MODEL_SHA" ] ||
  die "parent model hash drift"

phase build-and-test
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

phase generate-large-uniform-source
base=$((SOURCE_RECORDS / SHARDS))
rem=$((SOURCE_RECORDS % SHARDS))
pids=()
shards=()
: > "$ART/producer-exits-uniform.txt"
for shard in $(seq 0 $((SHARDS - 1))); do
  count="$base"; [ "$shard" -lt "$rem" ] && count=$((count + 1))
  timeout "$GEN_TIMEOUT" "$J" --gen-data-wdl "$count" \
    "$W/uniform-s$shard.jnnw" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" \
    $((BASE_SEED + shard)) \
    --nnue "$W/PARENT.pjtw" --search-params-play "$Q00" --wdl-zero-score \
    --random-open-plies 8 --explore-eps "$EXPLORE_EPS" \
    --explore-decay-plies "$EXPLORE_DECAY" --split-selfplay-rngs \
    --pair-openings --drop-plycap --sample-meta-out "$W/uniform-s$shard.jsm" \
    < /dev/null > "$W/uniform-s$shard.log" 2>&1 &
  pids+=("$!")
  shards+=("$shard")
done
failed=0
for idx in "${!pids[@]}"; do
  pid="${pids[$idx]}"
  shard="${shards[$idx]}"
  if wait "$pid"; then rc=0; else rc=$?; fi
  printf 'arm=uniform shard=%s pid=%s rc=%s timeout_s=%s\n' \
    "$shard" "$pid" "$rc" "$GEN_TIMEOUT" |
    tee -a "$ART/producer-exits-uniform.txt"
  [ "$rc" -eq 0 ] || failed=$((failed + 1))
done
[ "$failed" -eq 0 ] || die "uniform generation: $failed producer failures"
for log in "$W"/uniform-s*.log; do
  grep -q 'label_score_searches=0' "$log" || die "score-label search in $log"
done
grep '^EXPLORATION' "$W"/uniform-s*.log > "$ART/exploration-uniform.txt"

python3 - "$W" "$ART" "$SOURCE_RECORDS" "$PLAY_DEPTH" <<'PY'
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

total = sum(count_records(path) for path in sorted(w.glob("uniform-s*.jnnw")))
if total != expected:
    raise SystemExit(f"UNIFORM: {total} records, expected {expected}")
counters = {}
for line in (art / "exploration-uniform.txt").read_text().splitlines():
    for token in line.split():
        key, sep, value = token.partition("=")
        if sep and value.lstrip("-").isdigit():
            counters.setdefault(key, set()).add(int(value))
if counters.get("split_selfplay_rngs") != {1}:
    raise SystemExit(f"split RNGs inactive: {counters.get('split_selfplay_rngs')}")
if sum(counters.get("topk_ranked_plies", {0})) != 0:
    raise SystemExit("UNIFORM unexpectedly ranked TOPK plies")
(art / "generation-check.json").write_text(json.dumps({
    "schema": 1,
    "records": total,
    "policy": "uniform",
    "play_depth": play_depth,
    "label_depth": 4,
    "base_seed": 31415926,
    "split_selfplay_rngs": True,
    "topk_ranked_plies": 0,
    "ok": True,
}, indent=2, sort_keys=True) + "\n")
PY

phase merge-split-and-canary
pairs=()
for shard in $(seq 0 $((SHARDS - 1))); do
  pairs+=(--pair "$W/uniform-s$shard.jnnw" "$W/uniform-s$shard.jsm")
done
python3 tools/selfplay_frontier.py merge "${pairs[@]}" --renamespace-nested \
  --out-data "$W/uniform.raw.jnnw" --out-meta "$W/uniform.raw.jsm" \
  --manifest "$ART/uniform-merge.json" > "$W/uniform-merge.log" 2>&1
python3 tools/selfplay_frontier.py split \
  --data "$W/uniform.raw.jnnw" --meta "$W/uniform.raw.jsm" \
  --out-data "$W/uniform.fit.jnnw" --out-meta "$W/uniform.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/uniform-split.json" > "$W/uniform-split.log" 2>&1
python3 jobs/tools/assert_corpus_wdl.py --data "$W/uniform.raw.jnnw" \
  --out "$ART/uniform-corpus-wdl.json" > "$W/uniform-wdl.log" 2>&1 ||
  die "UNIFORM WDL canary failed"

phase compress-and-publish-certificate
gzip -n -c "$W/uniform.raw.jnnw" > "$ART/uniform.jnnw.gz"
gzip -n -c "$W/uniform.raw.jsm" > "$ART/uniform.jsm.gz"
python3 - "$W" "$ART" "$EXPECTED_CODE_SHA" "$EXPECTED_JOB_ID" \
  "$SOURCE_RECORDS" "$PARENT_NAME" "$PARENT_MODEL_SHA" <<'PY'
import hashlib
import json
import os
import pathlib
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha, job_id = sys.argv[3:5]
records = int(sys.argv[5])
parent_name, parent_sha = sys.argv[6:8]

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

split = json.load(open(art / "uniform-split.json"))
wdl = json.load(open(art / "uniform-corpus-wdl.json"))
generation = json.load(open(art / "generation-check.json"))
if split.get("records") != records or not generation.get("ok"):
    raise SystemExit("source certificate input mismatch")
arm = {
    "records": records,
    "data_gz_sha256": digest(art / "uniform.jnnw.gz"),
    "meta_gz_sha256": digest(art / "uniform.jsm.gz"),
    "data_raw_sha256": digest(w / "uniform.raw.jnnw"),
    "meta_raw_sha256": digest(w / "uniform.raw.jsm"),
    "split": split,
    "wdl": wdl,
    "generation": generation,
}
payload = {
    "schema": 1,
    "verdict": "L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY",
    "code_sha": code_sha,
    "source_job": job_id,
    "source_attempt": os.environ.get("JASS_ATTEMPT_ID"),
    "source_code_sha": code_sha,
    "parent": {"name": parent_name, "model_sha256": parent_sha},
    "policy": {
        "name": "uniform",
        "depth": 8,
        "label_depth": 4,
        "random_open_plies": 8,
        "explore_eps": 8,
        "explore_decay_plies": 60,
        "split_selfplay_rngs": True,
        "pair_openings": True,
        "drop_plycap": True,
        "post_drawn_root_fix": True,
    },
    "arms": {"uniform": arm},
    "scientific_value": "authenticated historical source only",
    "external_teacher_inputs": 0,
    "promotion": False,
    "automatic_next_job": None,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n"
)
(art / "VERDICT__L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY").touch()
(art / "PROMOTION_AUTHORIZED__FALSE").touch()
(art / "AUTOMATIC_NEXT_JOB__NULL").touch()
(art / f"SHA256__UNIFORM_JNNW_GZ__{arm['data_gz_sha256']}").touch()
(art / f"SHA256__UNIFORM_JSM_GZ__{arm['meta_gz_sha256']}").touch()
PY

say "L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY records=$SOURCE_RECORDS"
say "promotion=false automatic_next_job=null"
