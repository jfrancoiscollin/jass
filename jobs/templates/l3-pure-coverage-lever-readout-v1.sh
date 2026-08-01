#!/usr/bin/env bash
# L3-PURE — independent treatment-vs-control readout for a coverage-lever A/B.
#
# The opening pool is generated after training with a distinct pinned seed.
# Q00 and native counters are summed before score/Elo/CI95. No promotion and no
# continuation are authorized by this job.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${TRAIN_PREFIX:?}"; : "${EXPECTED_TRAIN_JOB:?}"
: "${EXPECTED_COVERAGE_LEVER:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/force"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/stage.txt"
: > "$RES"
echo preflight > "$STAGE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }

NOPEN=1500
OPENING_CANDIDATES=2000
OPENING_SEED=27182818
GAMES_PER_VIEW=$((NOPEN * 2))
NSH_GATE=12
PAR_GATE=12
FORCE_DEPTH=9
MOVETIME=0.1
CACHE_MB=128
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'lever=%s\n' "$EXPECTED_COVERAGE_LEVER"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        for f in "$ART"/force/*.json; do
          [ -e "$f" ] || continue
          printf 'done_%s\n' "$(basename "$f" .json)"
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
  rm -rf "$W/build8" "$IN" "$GEOM" "$W"/gate-* 2>/dev/null || true
  rm -f "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

stage preflight
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 8000 ] ||
  die "need 8 GiB free"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
monitor

stage fetch-and-authenticate-arms
python3 jobs/tools/fetch_result_files.py --prefix "$TRAIN_PREFIX" \
  --expected-state completed \
  --file artefacts/JASS_CONTROL_SUMMARY.json=training.json \
  --file artefacts/control.pjtw.gz=control.pjtw.gz \
  --file artefacts/treatment.pjtw.gz=treatment.pjtw.gz \
  --file artefacts/control.jnnw.gz=control.jnnw.gz \
  --file artefacts/treatment.jnnw.gz=treatment.jnnw.gz \
  --file artefacts/opening-exclusions.fen.gz=opening-exclusions.fen.gz \
  --out-dir "$IN" --report "$ART/verified-training.json" \
  > "$W/fetch-training.log" 2>&1
python3 - "$ART/verified-training.json" "$IN/training.json" \
  "$EXPECTED_TRAIN_JOB" "$EXPECTED_COVERAGE_LEVER" "$EXPECTED_CODE_SHA" <<'PY'
import json
import sys
verified = json.load(open(sys.argv[1]))
summary = json.load(open(sys.argv[2]))
if verified.get("job_id") != sys.argv[3] or verified.get("result_state") != "completed":
    raise SystemExit("training source identity/state mismatch")
if summary.get("verdict") != "L3_PURE_COVERAGE_LEVER_ARMS_READY":
    raise SystemExit("training verdict mismatch")
if summary.get("coverage_lever") != sys.argv[4]:
    raise SystemExit("coverage lever mismatch")
if summary.get("code_sha") != sys.argv[5]:
    raise SystemExit("readout must use the exact training code SHA")
if summary.get("promotion_authorized") is not False:
    raise SystemExit("training promotion guard drift")
if summary.get("automatic_next_job") is not None:
    raise SystemExit("training automatic continuation drift")
for arm in ("control", "treatment"):
    if summary.get("arms", {}).get(arm, {}).get("fit", {}).get("converged") is not True:
        raise SystemExit(f"{arm} fit did not converge")
PY
gunzip -c "$IN/control.pjtw.gz" > "$W/control.pjtw"
gunzip -c "$IN/treatment.pjtw.gz" > "$W/treatment.pjtw"
python3 - "$IN/training.json" "$W/control.pjtw" "$W/treatment.pjtw" <<'PY'
import hashlib
import json
import pathlib
import sys
summary = json.load(open(sys.argv[1]))
for arm, path in zip(("control", "treatment"), map(pathlib.Path, sys.argv[2:4])):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = summary["arms"][arm]["model_sha256"]
    if actual != expected:
        raise SystemExit(f"{arm} model hash drift: {actual} != {expected}")
PY

stage build-8cf-engine
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j8 --target jass jass_tests > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"

stage generate-fresh-independent-openings
"$J8" --gen-opening-pool "$OPENING_CANDIDATES" "$W/opening-candidates.fen" \
  8 32 20 "$OPENING_SEED" > "$W/openings.log" 2>&1
python3 - "$W/opening-candidates.fen" "$IN/control.jnnw.gz" \
  "$IN/treatment.jnnw.gz" "$IN/opening-exclusions.fen.gz" \
  "$W/readout-openings.fen" \
  "$ART/readout-opening-disjointness.json" "$NOPEN" "$OPENING_SEED" <<'PY'
import gzip
import hashlib
import json
import pathlib
import struct
import sys

sys.path.insert(0, "jobs/tools")
from conversion_teacher import board_key

candidates_path, control_path, treatment_path, exclusions_path, output_path, report_path = map(
    pathlib.Path, sys.argv[1:7])
expected, seed = map(int, sys.argv[7:9])
candidates = [
    row for line in candidates_path.read_text().splitlines()
    if (row := line.split("#", 1)[0].strip())
]
if len(candidates) != len(set(candidates)):
    raise SystemExit("opening generator emitted duplicates")
candidate_keys = {board_key(row): row for row in candidates}
overlap = set()
source_counts = {}
for source in (control_path, treatment_path):
    with gzip.open(source, "rb") as stream:
        header = stream.read(8)
        if len(header) != 8 or header[:4] != b"JNNW":
            raise SystemExit(f"{source}: invalid JNNW header")
        count = struct.unpack_from("<I", header, 4)[0]
        source_counts[source.name] = count
        for _ in range(count):
            record = stream.read(38)
            if len(record) != 38:
                raise SystemExit(f"{source}: truncated JNNW")
            if record[:33] in candidate_keys:
                overlap.add(record[:33])
        if stream.read(1):
            raise SystemExit(f"{source}: trailing JNNW bytes")
with gzip.open(exclusions_path, "rt", encoding="utf-8") as stream:
    exclusion_rows = [
        row for line in stream
        if (row := line.split("#", 1)[0].strip())
    ]
for row in exclusion_rows:
    key = board_key(row)
    if key in candidate_keys:
        overlap.add(key)
selected = [row for row in candidates if board_key(row) not in overlap][:expected]
if len(selected) != expected:
    raise SystemExit(
        f"only {len(selected)} candidates disjoint from sampled training positions")
output_path.write_text("\n".join(selected) + "\n")
payload = {
    "schema": 1,
    "generator_seed": seed,
    "candidate_records": len(candidates),
    "excluded_candidate_positions": len(overlap),
    "selected_records": len(selected),
    "disjoint_from_sampled_training_positions": True,
    "disjoint_from_external_opening_pool": True,
    "external_opening_exclusions": len(exclusion_rows),
    "training_source_records": source_counts,
    "pool_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
}
report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
NPOS=$(awk '{sub(/#.*/,""); gsub(/^[ \t]+|[ \t]+$/,""); if (length) n++}
             END {print n+0}' "$W/readout-openings.fen")
[ "$NPOS" -eq "$NOPEN" ] || die "opening pool count drift: $NPOS != $NOPEN"
python3 jobs/tools/validate_opening_pool.py \
  --pool "$W/readout-openings.fen" --expected "$NOPEN" \
  --generator-seed "$OPENING_SEED" --out "$ART/readout-openings-manifest.json" \
  > "$W/validate-openings.log" 2>&1
cp "$W/readout-openings.fen" "$ART/readout-openings.fen"

run_gate(){
  local view="$1"
  local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 10800 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J8" \
    --pattern-a "$W/treatment.pjtw" --pattern-b "$W/control.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/readout-openings.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 9000 --game-timeout 180 \
    --work-dir "$W/gate-$view" \
    --out "$ART/force/force-$view-treatment-vs-control.json" \
    > "$W/force-$view.log" 2>&1
}

stage play-both-views
for view in q00 native; do
  stage "view-$view-${GAMES_PER_VIEW}-games"
  if run_gate "$view"; then
    say "view $view completed"
  else
    say "view $view FAILED rc=$?; final verdict will be inconclusive"
  fi
done

stage publish-readout
python3 - "$ART" "$IN/training.json" "$EXPECTED_CODE_SHA" \
  "$EXPECTED_COVERAGE_LEVER" "$GAMES_PER_VIEW" "$OPENING_SEED" <<'PY'
import json
import math
import pathlib
import sys

art = pathlib.Path(sys.argv[1])
training = json.load(open(sys.argv[2]))
code_sha, lever = sys.argv[3:5]
per_view, opening_seed = map(int, sys.argv[5:7])

views = {}
for view in ("q00", "native"):
    path = art / "force" / f"force-{view}-treatment-vs-control.json"
    views[view] = json.load(open(path)) if path.exists() else None
missing = [name for name, data in views.items() if data is None]
short = [name for name, data in views.items()
         if data is not None and data.get("n", 0) < int(0.9 * per_view)]

wins = sum(data["wins_a"] for data in views.values() if data)
draws = sum(data["draws"] for data in views.values() if data)
losses = sum(data["wins_b"] for data in views.values() if data)
n = wins + draws + losses
rate = (wins + 0.5 * draws) / n if n else None
if rate is not None:
    variance = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(variance / n)
    lo = max(0.0, rate - 1.96 * se)
    hi = min(1.0, rate + 1.96 * se)
else:
    lo = hi = None

def elo(value):
    return -400 * math.log10(1 / value - 1) if value and value < 1 else None

if missing or short:
    verdict = "L3_PURE_COVERAGE_LEVER_READOUT_INCONCLUSIVE_CELL_FAILED"
elif lo > 0.5:
    verdict = "L3_PURE_COVERAGE_LEVER_TREATMENT_GAIN_ESTABLISHED"
elif hi < 0.5:
    verdict = "L3_PURE_COVERAGE_LEVER_TREATMENT_REGRESSION_ESTABLISHED"
else:
    verdict = "L3_PURE_COVERAGE_LEVER_FLAT_OR_UNDERPOWERED"

coverage = {
    arm: training["arms"][arm]["coverage"] for arm in ("control", "treatment")
}
payload = {
    "schema": 1,
    "verdict": verdict,
    "coverage_lever": lever,
    "code_sha": code_sha,
    "matchup": "treatment vs control",
    "opening_pool": {
        "count": 1500,
        "seed": opening_seed,
        "sha256": json.load(
            open(art / "readout-opening-disjointness.json"))["pool_sha256"],
        "fresh_independent_generator_stream": True,
        "disjoint_from_sampled_training_positions": True,
    },
    "views_summed": {
        "wins_treatment": wins, "draws": draws, "wins_control": losses,
        "n": n,
        "rate": round(rate, 6) if rate is not None else None,
        "ci95": ([round(lo, 6), round(hi, 6)] if rate is not None else None),
        "elo": round(elo(rate), 2) if elo(rate) is not None else None,
        "elo_ci95": ([round(elo(lo), 1), round(elo(hi), 1)]
                     if elo(lo) is not None and elo(hi) is not None else None),
    },
    "per_view": views,
    "coverage_from_training": coverage,
    "coverage_delta_treatment_minus_control": {
        "visited_pct": round(
            coverage["treatment"]["visited_pct"] - coverage["control"]["visited_pct"], 3),
        "gini": round(
            coverage["treatment"]["gini"] - coverage["control"]["gini"], 6),
        "buckets_ge_10": (
            coverage["treatment"]["buckets_ge_10"] -
            coverage["control"]["buckets_ge_10"]),
        "buckets_ge_100": (
            coverage["treatment"]["buckets_ge_100"] -
            coverage["control"]["buckets_ge_100"]),
    },
    "holdout_loss_used_for_selection": False,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "coverage-lever-readout.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / f"VERDICT__{verdict}").write_text(verdict + "\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
print(f"lever={lever} n={n} {wins}-{draws}-{losses} rate={rate} "
      f"ci95={[lo, hi]} verdict={verdict}")
PY
stage complete
say "L3_PURE_COVERAGE_LEVER_READOUT_READY lever=$EXPECTED_COVERAGE_LEVER promotion=false automatic_next_job=null"
