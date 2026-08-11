#!/usr/bin/env bash
# Timing-only HOME preflight for CONTEXT_30 transfer on immutable TURNOVER 2M.
# It generates no self-play, publishes no strength verdict and queues no child.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

TURNOVER_PREFIX="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
L2LOW_PREFIX="r2:jass-data/runs/cpx62-1164-l3-prior-dose-l2-refit-v1/20260803T060626Z-209eb56b"
TURNOVER_JOB="home-0977-l3-pure-turnover1to1-train-v1"
L2LOW_JOB="cpx62-1164-l3-prior-dose-l2-refit-v1"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
L2LOW_SHA="ec47e4b37fc7e95dcb390c0a5eddf207e98c0818c1708636d2df9e85b1d149b4"
EXPECTED_RECORDS=2000000; EXPECTED_HOLDOUT=199204; EXPECTED_EXTRAS=120
SPLIT_SEED=577215; HOLDOUT_MOD=10; MAXIT=25; CHUNK=20000
TARGET_TIMEOUT=3600; FIT_TIMEOUT=2400
VENV="${JASS_L3_NUMERIC_VENV:-/home/jf/.cache/jass-l3-numeric-venv}"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in aligned shuffled; do
          [ -f "$W/fit-$arm.log" ] &&
            printf '%s_fit_lines=%s\n' "$arm" "$(wc -l < "$W/fit-$arm.log")"
        done
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
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
  rm -rf "$W/build" "$IN" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.npy 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-([0-9]+)-l3-conditional-target-transfer-probe-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "post-sizing human GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
NCPU=$(nproc); [ "$NCPU" -eq 16 ] || die "HOME timing contract requires nproc=16"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 10240 ] || die "less than 10 GiB free (${DFA} MiB)"
say "host=$(hostname) nproc=$NCPU free_mb=$DFA mode=timing_only"
monitor

stage fetch-immutable-existing-selfplay-and-parent
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_PREFIX" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" \
  --expected-state completed >"$W/fetch-turnover.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$L2LOW_PREFIX" \
  --file artefacts/control.pjtw.gz=l2low.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-l2low.json" \
  --expected-state completed >"$W/fetch-l2low.log" 2>&1
python3 - "$ART/verified-turnover.json" "$ART/verified-l2low.json" \
  "$TURNOVER_JOB" "$L2LOW_JOB" <<'PY'
import json, sys
for path, expected in ((sys.argv[1], sys.argv[3]), (sys.argv[2], sys.argv[4])):
    row = json.load(open(path))
    if row.get("job_id") != expected or row.get("result_state") != "completed":
        raise SystemExit(f"source identity mismatch: {path}")
PY
gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
gunzip -c "$IN/l2low.pjtw.gz" >"$W/l2low.pjtw"
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = "$TURNOVER_CORPUS_SHA" ] ||
  die "TURNOVER corpus hash drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = "$TURNOVER_META_SHA" ] ||
  die "TURNOVER metadata hash drift"
[ "$(sha256sum "$W/l2low.pjtw" | awk '{print $1}')" = "$L2LOW_SHA" ] ||
  die "L2LOW hash drift"

stage reproduce-opening-level-split
python3 tools/selfplay_frontier.py split \
  --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/turnover.fit.jnnw" --out-meta "$W/turnover.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/split.json" >"$W/split.log" 2>&1
read -r RECORDS HOLDOUT < <(python3 - "$ART/split.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); print(d["records"], d["holdout_records"])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] || die "records=$RECORDS"
[ "$HOLDOUT" -eq "$EXPECTED_HOLDOUT" ] || die "holdout=$HOLDOUT"
TRAIN_COUNT=$((RECORDS - HOLDOUT)); [ "$TRAIN_COUNT" -gt 0 ] || die "n=0 train"

stage build-current-production-architecture-and-features
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  die "8cf geometry mismatch"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass >"$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
"$J" --dump-eval-features "$W/turnover.fit.jnnw" "$W/turnover.feat" \
  >"$W/features.log" 2>&1
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/turnover.feat")
[ "$K" -eq "$EXPECTED_EXTRAS" ] || die "architecture guard: extras=$K"

stage persistent-numeric-runtime
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
    numpy==1.26.4 scipy==1.14.1 >"$W/pip-bootstrap-once.log" 2>&1
fi
PY="$VENV/bin/python"
"$PY" -c 'import numpy, scipy; assert numpy.__version__ == "1.26.4"; assert scipy.__version__ == "1.14.1"' ||
  die "persistent numeric venv mismatch"

stage build-aligned-and-marginal-matched-targets
/usr/bin/time -f '%e' -o "$W/targets.seconds" timeout "$TARGET_TIMEOUT" \
  "$PY" jobs/tools/l3_conditional_targets.py \
    --data "$W/turnover.fit.jnnw" --meta "$W/turnover.fit.jsm" \
    --feat "$W/turnover.feat" --train-count "$TRAIN_COUNT" \
    --aligned-out "$W/aligned.npy" --shuffled-out "$W/shuffled.npy" \
    --report "$ART/conditional-targets.json" --alpha 0.30 \
    >"$W/targets.log" 2>&1

fit_probe(){
  local arm="$1"
  /usr/bin/time -f '%e' -o "$W/fit-$arm.seconds" timeout "$FIT_TIMEOUT" \
    env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    "$PY" pattern_jass/tools/train_stream.py \
      --data "$W/turnover.fit.jnnw" --feat "$W/turnover.feat" \
      --out "$W/$arm.pjtw" --target external --target-values "$W/$arm.npy" \
      --targets-report "$ART/$arm-target-consumption.json" \
      --loss logistic --exact-fold --tempo-stage \
      --prior-mean "$W/l2low.pjtw" --prior-decay 0 \
      --holdout-count "$HOLDOUT" --l2 1e-5 --max-iter "$MAXIT" \
      --chunk "$CHUNK" --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune \
      --optimizer-report "$ART/$arm-optimizer.json" \
      >"$W/fit-$arm.log" 2>&1
}
stage paired-25-iteration-fit-timing
set +e
fit_probe aligned & PA=$!
fit_probe shuffled & PS=$!
wait "$PA"; RCA=$?
wait "$PS"; RCS=$?
set -e
[ "$RCA" -eq 0 ] && [ "$RCS" -eq 0 ] || die "timing fit failed aligned=$RCA shuffled=$RCS"

stage timing-report-and-smoke
python3 - "$W" "$ART" "$RECORDS" "$TRAIN_COUNT" "$HOLDOUT" "$NCPU" <<'PY'
import json, os, re, sys
from pathlib import Path
w, art = Path(sys.argv[1]), Path(sys.argv[2])
records, train, holdout, nproc = map(int, sys.argv[3:])
if records == 0 or train == 0:
    raise SystemExit("n=0")
arms = {}
for arm in ("aligned", "shuffled"):
    seconds = float((w / f"fit-{arm}.seconds").read_text().strip())
    optimizer = json.load(open(art / f"{arm}-optimizer.json"))
    iterations = int(optimizer["iterations"])
    if iterations <= 0 or seconds <= 0:
        raise SystemExit(f"invalid timing for {arm}")
    arms[arm] = {
        "seconds": seconds,
        "iterations": iterations,
        "seconds_per_iteration": seconds / iterations,
        "expected_probe_max_iterations": 25,
        "convergence_required_for_probe": False,
    }
targets = json.load(open(art / "conditional-targets.json"))
if targets.get("records") != records or targets.get("feature_width") != 120:
    raise SystemExit("conditional target reporting smoke failed")
report = {
    "schema": "jass.l3_conditional_target_transfer_probe.v1",
    "status": "TIMING_ONLY_READY_FOR_FULL_SIZING",
    "host": "HOME",
    "nproc": nproc,
    "records": records,
    "train_records": train,
    "holdout_records": holdout,
    "target_builder_seconds": float((w / "targets.seconds").read_text().strip()),
    "fit_arms": arms,
    "new_selfplay_generated": False,
    "scientific_strength_verdict": None,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
json.loads((art / "JASS_CONTROL_SUMMARY.json").read_text())
PY
: >"$ART/VERDICT__TIMING_ONLY_READY_FOR_FULL_SIZING"
printf 'PROMOTION_AUTHORIZED__FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n' >"$ART/AUTOMATIC_NEXT_JOB__NULL"
say "TIMING_ONLY_READY_FOR_FULL_SIZING no_new_selfplay=true promotion=false"
