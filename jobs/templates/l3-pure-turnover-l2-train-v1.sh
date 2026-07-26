#!/usr/bin/env bash
# L3-PURE: fit the two preregistered L2 arms on the fixed TURNOVER corpus.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${PREFLIGHT_PREFIX:?}"
: "${EXPECTED_PREFLIGHT_JOB:?}"; : "${TURNOVER_TRAIN_PREFIX:?}"
: "${EXPECTED_TURNOVER_TRAIN_JOB:?}"; : "${M1_PREFIX:?}"
: "${EXPECTED_M1_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
PHASE="$W/phase.txt"
: > "$RES"
echo initializing > "$PHASE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" > "$PHASE"; say "phase=$1"; }

MONITOR_PID=""
monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$PHASE" 2>/dev/null || echo unknown)"
        df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{printf "free_mb=%s\n",$4}'
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MONITOR_PID="$!"
}
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MONITOR_PID" ] || {
    kill "$MONITOR_PID" 2>/dev/null
    wait "$MONITOR_PID" 2>/dev/null
  }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$W/venv" "$IN" "$GEOM" "$W"/*.feat 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

F2M_MODEL_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
TURNOVER_MODEL_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
CHAMPION_CODE_SHA="0c1e04a9574fcd87977f62fe5bd6d71c60c72265"
SPLIT_SEED=577215
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
CHUNK=20000

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 12000 ] ||
  die "need 12 GiB free"
[ "$(awk '/MemAvailable:/{print int($2/1024)}' /proc/meminfo)" -ge 5000 ] ||
  die "need 5 GiB available RAM for two concurrent fits"
git diff --quiet "$CHAMPION_CODE_SHA" HEAD -- src pattern_jass/tools ||
  die "engine/training semantics changed since the repaired champion gate"
monitor

phase fetch-and-authenticate-preflight
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-l2-preflight.json \
  --file artefacts/turnover1to1.jnnw.gz=turnover1to1.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover1to1.jsm.gz \
  --file artefacts/turnover-l2-split.json=turnover-l2-split.json \
  --out-dir "$IN" --report "$ART/verified-l2-preflight.json" \
  > "$W/fetch-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-training.json \
  --file artefacts/turnover1to1.pjtw.gz=turnover1to1-control.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-turnover-training.json" \
  > "$W/fetch-turnover.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m1-training.json \
  --out-dir "$IN" --report "$ART/verified-m1-source.json" \
  > "$W/fetch-m1.log" 2>&1

python3 - "$IN" "$ART" "$EXPECTED_PREFLIGHT_JOB" \
  "$EXPECTED_TURNOVER_TRAIN_JOB" "$EXPECTED_M1_JOB" <<'PY'
import json
import sys
from pathlib import Path

src, art = map(Path, sys.argv[1:3])
for report_name, expected_job in zip(
    (
        "verified-l2-preflight.json",
        "verified-turnover-training.json",
        "verified-m1-source.json",
    ),
    sys.argv[3:],
):
    report = json.load(open(art / report_name))
    if report.get("job_id") != expected_job or report.get("result_state") != "completed":
        raise SystemExit(f"{report_name}: source identity/state mismatch")

preflight = json.load(open(src / "turnover-l2-preflight.json"))
turnover = json.load(open(src / "turnover-training.json"))
m1 = json.load(open(src / "m1-training.json"))
if (
    preflight.get("verdict") != "TURNOVER_L2_PREFLIGHT_READY"
    or preflight.get("training_authorized") is not True
    or preflight.get("promotion_authorized") is not False
    or preflight.get("automatic_next_job") is not None
    or preflight.get("experiment_variant") != "TURNOVER_1_1_L2_SCREEN"
    or preflight.get("l2_levels") != [1e-5, 3e-5, 1e-4]
    or preflight.get("control_l2") != 3e-5
    or preflight.get("control_source_code_sha")
    != "336bb98451a205266d6646c4d801027af4b30294"
    or preflight.get("records") != 2_000_000
    or preflight.get("jnnw_sha256")
    != "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
    or preflight.get("jsm_sha256")
    != "acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
    or preflight.get("runtime", {}).get("numpy") != "1.26.4"
    or preflight.get("runtime", {}).get("scipy") != "1.14.1"
    or preflight.get("resource_preflight", {}).get("max_parallel_fits") != 2
    or turnover.get("model_sha256")
    != "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
    or m1.get("arms", {}).get("F2M", {}).get("model_sha256")
    != "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
):
    raise SystemExit("L2 training source certificate mismatch")
PY

phase reproduce-corpus-split-and-runtime
gunzip -c "$IN/f2m.pjtw.gz" > "$W/f2m.pjtw"
gunzip -c "$IN/turnover1to1-control.pjtw.gz" > "$W/turnover1to1-control.pjtw"
gunzip -c "$IN/turnover1to1.jnnw.gz" > "$W/turnover1to1.raw.jnnw"
gunzip -c "$IN/turnover1to1.jsm.gz" > "$W/turnover1to1.raw.jsm"
[ "$(sha256sum "$W/f2m.pjtw" | awk '{print $1}')" = "$F2M_MODEL_SHA" ] ||
  die "F2M model hash drift"
[ "$(sha256sum "$W/turnover1to1-control.pjtw" | awk '{print $1}')" = \
  "$TURNOVER_MODEL_SHA" ] || die "TURNOVER control model hash drift"
[ "$(sha256sum "$W/turnover1to1.raw.jnnw" | awk '{print $1}')" = \
  "$TURNOVER_CORPUS_SHA" ] || die "TURNOVER corpus hash drift"
[ "$(sha256sum "$W/turnover1to1.raw.jsm" | awk '{print $1}')" = \
  "$TURNOVER_META_SHA" ] || die "TURNOVER metadata hash drift"
python3 tools/selfplay_frontier.py split \
  --data "$W/turnover1to1.raw.jnnw" --meta "$W/turnover1to1.raw.jsm" \
  --out-data "$W/turnover1to1.fit.jnnw" \
  --out-meta "$W/turnover1to1.fit.jsm" \
  --holdout-mod 10 --seed "$SPLIT_SEED" \
  --manifest "$ART/turnover-l2-split.json" > "$W/split.log" 2>&1
cmp -s "$ART/turnover-l2-split.json" "$IN/turnover-l2-split.json" ||
  die "TURNOVER split manifest drift"
PRE_SPLIT_JNNW="$(sha256sum "$W/turnover1to1.fit.jnnw" | awk '{print $1}')"
PRE_SPLIT_JSM="$(sha256sum "$W/turnover1to1.fit.jsm" | awk '{print $1}')"
python3 - "$IN/turnover-l2-preflight.json" "$PRE_SPLIT_JNNW" \
  "$PRE_SPLIT_JSM" <<'PY'
import json
import sys

preflight = json.load(open(sys.argv[1]))
if (
    preflight.get("split_jnnw_sha256") != sys.argv[2]
    or preflight.get("split_jsm_sha256") != sys.argv[3]
):
    raise SystemExit("TURNOVER split hashes drifted")
PY
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1

phase build-and-feature-dump
for source in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp \
  src/movegen.cpp src/movegen.hpp; do
  git show "${EXPECTED_CODE_SHA}:$source" > "$source"
done
grep -q "g_emasks" src/scan_eval.cpp || die "8cf build lacks g_emasks"
grep -q "has_any_capture" src/search.cpp || die "search lacks capture guard"
grep -q "has_any_capture" src/movegen.cpp || die "movegen lacks capture guard"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" \
  -eq 4251528 ] || die "8cf mismatch"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] ||
  git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl \
    > "$W/clone.log" 2>&1
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB=128
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j4 --target jass > "$W/build.log" 2>&1
J="$W/build/jass"
[ "$("$J" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
[ "$("$J" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
  die "tablebase-root witness failed"
"$J" --dump-eval-features "$W/turnover1to1.fit.jnnw" \
  "$W/turnover1to1.feat" > "$W/features.log" 2>&1
HOLDOUT="$("$W/venv/bin/python" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' \
  "$ART/turnover-l2-split.json")"
[ "$HOLDOUT" -eq 199204 ] || die "TURNOVER holdout drift"

phase fit-two-l2-arms
run_fit(){
  local name="$1"
  local l2="$2"
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    /usr/bin/time -v -o "$W/fit-$name.time" \
    timeout 43200 "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
    --data "$W/turnover1to1.fit.jnnw" \
    --feat "$W/turnover1to1.feat" --out "$W/$name.pjtw" \
    --target wdl --loss logistic --color-fold --tempo-stage \
    --warm-start "$W/f2m.pjtw" --holdout-count "$HOLDOUT" \
    --l2 "$l2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
    --optimizer-report "$ART/$name-optimizer.json" \
    > "$W/fit-$name.log" 2>&1
}
set +e
run_fit turnover-l2-1e5 1e-5 &
PID_1E5=$!
run_fit turnover-l2-1e4 1e-4 &
PID_1E4=$!
wait "$PID_1E5"; RC_1E5=$?
wait "$PID_1E4"; RC_1E4=$?
set -e
for item in "turnover-l2-1e5:$RC_1E5" "turnover-l2-1e4:$RC_1E4"; do
  name="${item%%:*}"
  rc="${item##*:}"
  [ "$rc" -eq 0 ] || die "$name fit failed rc=$rc"
  [ -s "$W/$name.pjtw" ] || die "$name model missing"
  grep -q 'HOLDOUT_LOGLOSS' "$W/fit-$name.log" ||
    die "$name holdout result missing"
  if ! "$W/venv/bin/python" - "$ART/$name-optimizer.json" <<'PY'
import json
import sys
if not json.load(open(sys.argv[1])).get("success"):
    raise SystemExit(1)
PY
  then
    die "$name optimiser did not converge"
  fi
  gzip -n -c "$W/$name.pjtw" > "$ART/$name.pjtw.gz"
done

phase publish-training-screen
"$W/venv/bin/python" - "$W" "$ART" "$IN/turnover-l2-preflight.json" \
  "$EXPECTED_CODE_SHA" "$EXPECTED_PREFLIGHT_JOB" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
preflight = json.load(open(sys.argv[3]))
code_sha, preflight_job = sys.argv[4:]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def arm(name, l2):
    log = (w / f"fit-{name}.log").read_text()
    timing = (w / f"fit-{name}.time").read_text()
    optimizer = json.load(open(art / f"{name}-optimizer.json"))
    return {
        "l2": l2,
        "model_sha256": sha(w / f"{name}.pjtw"),
        "iterations": int(re.search(r"iters=(\d+)", log).group(1)),
        "holdout_logloss": float(
            re.search(r"HOLDOUT_LOGLOSS\s+([0-9.]+)", log).group(1)
        ),
        "max_rss_kib": int(
            re.search(
                r"Maximum resident set size \(kbytes\):\s*(\d+)",
                timing,
            ).group(1)
        ),
        "optimizer": optimizer,
    }

payload = {
    "schema": 1,
    "verdict": "TURNOVER_L2_TRAINING_SCREEN_READY",
    "code_sha": code_sha,
    "preflight_job": preflight_job,
    "preflight_code_sha": preflight["code_sha"],
    "trigger": preflight["trigger"],
    "experiment_variant": "TURNOVER_1_1_L2_SCREEN",
    "parent": "F2M",
    "parent_model_sha256":
        "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2",
    "control": {
        "name": "L2_3E5_CONTROL",
        "l2": 3e-5,
        "source_code_sha": preflight["control_source_code_sha"],
        "model_sha256":
            "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16",
    },
    "arms": {
        "L2_1E5": arm("turnover-l2-1e5", 1e-5),
        "L2_1E4": arm("turnover-l2-1e4", 1e-4),
    },
    "training_records": 2_000_000,
    "training_corpus_sha256": preflight["jnnw_sha256"],
    "training_meta_sha256": preflight["jsm_sha256"],
    "split_jnnw_sha256": preflight["split_jnnw_sha256"],
    "split_jsm_sha256": preflight["split_jsm_sha256"],
    "split_seed": 577_215,
    "holdout_records": 199_204,
    "historical_replay_records": 1_000_000,
    "fresh_records": 1_000_000,
    "new_generation_performed": False,
    "external_teacher_inputs": 0,
    "evaluation_authorized": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "turnover-l2-training-summary.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__TURNOVER_L2_TRAINING_SCREEN_READY").write_text(
    "TURNOVER_L2_TRAINING_SCREEN_READY\n"
)
(art / "PROMOTION_AUTHORIZED__FALSE").write_text(
    "PROMOTION_AUTHORIZED__FALSE\n"
)
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
PY
phase complete
say "TURNOVER_L2_TRAINING_SCREEN_READY evaluation=true promotion=false automatic_next_job=null"
