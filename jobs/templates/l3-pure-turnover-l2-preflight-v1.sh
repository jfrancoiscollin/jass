#!/usr/bin/env bash
# L3-PURE: deterministic L2 screen preflight on the fixed TURNOVER 50/50 corpus.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${REPLAY25_EVAL_PREFIX:?}"
: "${EXPECTED_REPLAY25_EVAL_JOB:?}"; : "${REPLAY25_PREFLIGHT_PREFIX:?}"
: "${EXPECTED_REPLAY25_PREFLIGHT_JOB:?}"; : "${TURNOVER_TRAIN_PREFIX:?}"
: "${EXPECTED_TURNOVER_TRAIN_JOB:?}"; : "${TURNOVER_CONFIRM_PREFIX:?}"
: "${EXPECTED_TURNOVER_CONFIRM_JOB:?}"; : "${M1_PREFIX:?}"
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
  rm -rf "$W/build" "$W/test-build" "$W/venv" "$IN" "$GEOM" \
    "$W"/*.feat 2>/dev/null || true
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
TURNOVER_CODE_SHA="336bb98451a205266d6646c4d801027af4b30294"
CHAMPION_CODE_SHA="0c1e04a9574fcd87977f62fe5bd6d71c60c72265"
SPLIT_SEED=577215
OPENING_SEED=1836313
OPENING_CANDIDATES=2000
NOPEN=500

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
[ "$(awk '/MemAvailable:/{print int($2/1024)}' /proc/meminfo)" -ge 3500 ] ||
  die "need 3.5 GiB available RAM"
git diff --quiet "$CHAMPION_CODE_SHA" HEAD -- src pattern_jass/tools ||
  die "engine/training semantics changed since the repaired champion gate"
monitor

phase fetch-and-authenticate-trigger
python3 jobs/tools/fetch_result_files.py --prefix "$REPLAY25_EVAL_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=replay25-evaluation.json \
  --out-dir "$IN" --report "$ART/verified-replay25-evaluation.json" \
  > "$W/fetch-replay25-evaluation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$REPLAY25_PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=replay25-preflight.json \
  --file artefacts/replay25-eval-openings.fen=prior-replay25.fen \
  --out-dir "$IN" --report "$ART/verified-replay25-preflight.json" \
  > "$W/fetch-replay25-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-training.json \
  --file artefacts/turnover1to1.jnnw.gz=turnover1to1.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover1to1.jsm.gz \
  --file artefacts/turnover1to1.pjtw.gz=turnover1to1.pjtw.gz \
  --file artefacts/m2-split.json=turnover-split.json \
  --out-dir "$IN" --report "$ART/verified-turnover-training.json" \
  > "$W/fetch-turnover-training.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_CONFIRM_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-confirmation.json \
  --file work/prior-reinforcement.fen=prior-reinforcement.fen \
  --file work/prior-meta-screen.fen=prior-meta-screen.fen \
  --file work/prior-meta-confirm.fen=prior-meta-confirm.fen \
  --file work/prior-f2m-confirm.fen=prior-f2m-confirm.fen \
  --file work/prior-f2m-gen2.fen=prior-f2m-gen2.fen \
  --file work/prior-m2-independent.fen=prior-m2-independent.fen \
  --file work/prior-d10-independent.fen=prior-d10-independent.fen \
  --file work/prior-d12-independent.fen=prior-d12-independent.fen \
  --file work/prior-turnover-independent.fen=prior-turnover-independent.fen \
  --file work/open-eval.fen=prior-turnover-confirmation.fen \
  --out-dir "$IN" --report "$ART/verified-turnover-confirmation.json" \
  > "$W/fetch-turnover-confirmation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m1-training.json \
  --out-dir "$IN" --report "$ART/verified-m1-source.json" \
  > "$W/fetch-m1.log" 2>&1

python3 - "$IN" "$ART" "$EXPECTED_REPLAY25_EVAL_JOB" \
  "$EXPECTED_REPLAY25_PREFLIGHT_JOB" "$EXPECTED_TURNOVER_TRAIN_JOB" \
  "$EXPECTED_TURNOVER_CONFIRM_JOB" "$EXPECTED_M1_JOB" <<'PY'
import json
import sys
from pathlib import Path

src, art = map(Path, sys.argv[1:3])
jobs = sys.argv[3:]
reports = (
    "verified-replay25-evaluation.json",
    "verified-replay25-preflight.json",
    "verified-turnover-training.json",
    "verified-turnover-confirmation.json",
    "verified-m1-source.json",
)
for report_name, expected_job in zip(reports, jobs):
    report = json.load(open(art / report_name))
    if report.get("job_id") != expected_job or report.get("result_state") != "completed":
        raise SystemExit(f"{report_name}: source identity/state mismatch")

evaluation = json.load(open(src / "replay25-evaluation.json"))
force = evaluation.get("force", {})
complete_force = all(
    force.get(f"{view}_vs_{opponent}", {}).get("n") == 1_000
    and force.get(f"{view}_vs_{opponent}", {}).get("complete") is True
    for view in ("q00", "native")
    for opponent in ("M2", "TURNOVER", "F2M", "GEN2")
)
if (
    evaluation.get("verdict") != "REPLAY25_DOSE_CLOSED_REVIEW"
    or evaluation.get("promotion_authorized") is not False
    or evaluation.get("automatic_next_job") is not None
    or evaluation.get("protocol", {}).get("candidate") != "REPLAY25_RECENCY75"
    or not complete_force
    or evaluation.get("opening_manifest", {}).get("records") != 500
    or evaluation.get("opening_manifest", {}).get("overlap_records") != 0
    or evaluation.get("primary_checks", {})
    .get("TURNOVER", {})
    .get("q00", {})
    .get("regression_not_established")
    is not False
):
    raise SystemExit("REPLAY25 final result does not authorize the L2 screen")

preflight = json.load(open(src / "replay25-preflight.json"))
turnover = json.load(open(src / "turnover-training.json"))
confirmation = json.load(open(src / "turnover-confirmation.json"))
m1 = json.load(open(src / "m1-training.json"))
if (
    preflight.get("verdict") != "REPLAY25_PREFLIGHT_READY"
    or preflight.get("evaluation_openings", {}).get("seed") != 1_836_311
    or turnover.get("experiment_variant") != "TURNOVER_1_1"
    or turnover.get("code_sha")
    != "336bb98451a205266d6646c4d801027af4b30294"
    or turnover.get("model_sha256")
    != "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
    or turnover.get("training_corpus_sha256")
    != "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
    or turnover.get("training_meta_sha256")
    != "acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
    or turnover.get("training_records") != 2_000_000
    or turnover.get("historical_replay_records") != 1_000_000
    or turnover.get("fresh_records") != 1_000_000
    or turnover.get("parent_model_sha256")
    != "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
    or confirmation.get("verdict") != "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW"
    or confirmation.get("all_guardrails_pass") is not True
    or m1.get("arms", {}).get("F2M", {}).get("model_sha256")
    != "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
):
    raise SystemExit("immutable L2-screen source certificate mismatch")
PY
CONTROL_TEMPLATE="$W/turnover-control-template.sh"
git show "$TURNOVER_CODE_SHA:jobs/templates/l3-pure-m2-train-v1.sh" \
  > "$CONTROL_TEMPLATE"
for setting in \
  "L2=3e-5" \
  "MAXIT=1000" \
  "LBFGS_MAXCOR=20" \
  "LBFGS_GTOL=1e-3" \
  "CHUNK=20000"; do
  grep -Fxq "$setting" "$CONTROL_TEMPLATE" ||
    die "TURNOVER control recipe drift: $setting"
done
grep -Fq -- '--optimizer-report "$ART/m2-optimizer.json"' "$CONTROL_TEMPLATE" ||
  die "TURNOVER control lacks convergence certificate"
grep -Fq 'M2 optimiser did not converge' "$CONTROL_TEMPLATE" ||
  die "TURNOVER control lacks fail-closed optimizer gate"

phase verify-corpus-and-split-twice
gunzip -c "$IN/f2m.pjtw.gz" > "$W/f2m.pjtw"
gunzip -c "$IN/turnover1to1.pjtw.gz" > "$W/turnover1to1.pjtw"
gunzip -c "$IN/turnover1to1.jnnw.gz" > "$W/turnover1to1.raw.jnnw"
gunzip -c "$IN/turnover1to1.jsm.gz" > "$W/turnover1to1.raw.jsm"
[ "$(sha256sum "$W/f2m.pjtw" | awk '{print $1}')" = "$F2M_MODEL_SHA" ] ||
  die "F2M model hash drift"
[ "$(sha256sum "$W/turnover1to1.pjtw" | awk '{print $1}')" = \
  "$TURNOVER_MODEL_SHA" ] || die "TURNOVER model hash drift"
[ "$(sha256sum "$W/turnover1to1.raw.jnnw" | awk '{print $1}')" = \
  "$TURNOVER_CORPUS_SHA" ] || die "TURNOVER corpus hash drift"
[ "$(sha256sum "$W/turnover1to1.raw.jsm" | awk '{print $1}')" = \
  "$TURNOVER_META_SHA" ] || die "TURNOVER metadata hash drift"

/usr/bin/time -v -o "$W/split-a.time" python3 tools/selfplay_frontier.py split \
  --data "$W/turnover1to1.raw.jnnw" --meta "$W/turnover1to1.raw.jsm" \
  --out-data "$W/turnover1to1.fit.jnnw" \
  --out-meta "$W/turnover1to1.fit.jsm" \
  --holdout-mod 10 --seed "$SPLIT_SEED" \
  --manifest "$ART/turnover-l2-split.json" > "$W/split-a.log" 2>&1
/usr/bin/time -v -o "$W/split-b.time" python3 tools/selfplay_frontier.py split \
  --data "$W/turnover1to1.raw.jnnw" --meta "$W/turnover1to1.raw.jsm" \
  --out-data "$W/turnover1to1-repeat.fit.jnnw" \
  --out-meta "$W/turnover1to1-repeat.fit.jsm" \
  --holdout-mod 10 --seed "$SPLIT_SEED" \
  --manifest "$W/turnover-l2-repeat-split.json" > "$W/split-b.log" 2>&1
cmp -s "$W/turnover1to1.fit.jnnw" "$W/turnover1to1-repeat.fit.jnnw" ||
  die "TURNOVER split data is not byte-identical"
cmp -s "$W/turnover1to1.fit.jsm" "$W/turnover1to1-repeat.fit.jsm" ||
  die "TURNOVER split metadata is not byte-identical"
cmp -s "$ART/turnover-l2-split.json" "$IN/turnover-split.json" ||
  die "TURNOVER split manifest drift"
cp "$IN/turnover1to1.jnnw.gz" "$ART/turnover1to1.jnnw.gz"
cp "$IN/turnover1to1.jsm.gz" "$ART/turnover1to1.jsm.gz"

phase isolated-runtime-build-and-tests
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1
"$W/venv/bin/python" - "$ART/python-runtime.json" <<'PY'
import json
import platform
import sys
import numpy
import scipy

json.dump(
    {
        "schema": 1,
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
    },
    open(sys.argv[1], "w"),
    indent=2,
    sort_keys=True,
)
PY
python3 -m py_compile tools/selfplay_frontier.py
python3 jobs/tests/test_selfplay_frontier.py > "$W/test-frontier.log" 2>&1
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
cmake -S . -B "$W/test-build" -DCMAKE_BUILD_TYPE=Release \
  > "$W/cmake-tests.log" 2>&1
cmake --build "$W/test-build" -j4 --target jass_tests \
  > "$W/build-tests.log" 2>&1
ctest --test-dir "$W/test-build" --output-on-failure > "$W/ctest.log" 2>&1
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

phase two-l2-mini-fit-roundtrip
python3 tools/selfplay_frontier.py mix \
  --source TURNOVER "$W/turnover1to1.raw.jnnw" "$W/turnover1to1.raw.jsm" 1 \
  --target-records 20000 --seed 271829 \
  --out-data "$W/mini.raw.jnnw" --out-meta "$W/mini.raw.jsm" \
  --manifest "$W/mini-mix.json" > "$W/mini-mix.log" 2>&1
python3 tools/selfplay_frontier.py split \
  --data "$W/mini.raw.jnnw" --meta "$W/mini.raw.jsm" \
  --out-data "$W/mini.fit.jnnw" --out-meta "$W/mini.fit.jsm" \
  --holdout-mod 10 --seed "$SPLIT_SEED" \
  --manifest "$W/mini-split.json" > "$W/mini-split.log" 2>&1
HOLDOUT="$("$W/venv/bin/python" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' \
  "$W/mini-split.json")"
[ "$HOLDOUT" -gt 0 ] || die "mini holdout missing"
"$J" --dump-eval-features "$W/mini.fit.jnnw" "$W/mini.feat" \
  > "$W/mini-features.log" 2>&1
for spec in L2_1E5:1e-5 L2_1E4:1e-4; do
  name="${spec%%:*}"
  l2="${spec##*:}"
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    /usr/bin/time -v -o "$W/mini-$name.time" \
    "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
    --data "$W/mini.fit.jnnw" --feat "$W/mini.feat" \
    --out "$W/mini-$name.pjtw" \
    --target wdl --loss logistic --color-fold --tempo-stage \
    --warm-start "$W/f2m.pjtw" --holdout-count "$HOLDOUT" \
    --l2 "$l2" --max-iter 2 --chunk 20000 \
    --lbfgs-maxcor 20 --lbfgs-gtol 1e-3 \
    > "$W/mini-$name.log" 2>&1
  [ -s "$W/mini-$name.pjtw" ] || die "$name mini-fit output missing"
  grep -q 'HOLDOUT_LOGLOSS' "$W/mini-$name.log" ||
    die "$name mini-fit holdout missing"
done

phase independent-evaluation-pool
"$J" --gen-opening-pool "$OPENING_CANDIDATES" "$W/open-candidates-a.fen" \
  8 32 20 "$OPENING_SEED" > "$W/open-candidates-a.log" 2>&1
"$J" --gen-opening-pool "$OPENING_CANDIDATES" "$W/open-candidates-b.fen" \
  8 32 20 "$OPENING_SEED" > "$W/open-candidates-b.log" 2>&1
cmp -s "$W/open-candidates-a.fen" "$W/open-candidates-b.fen" ||
  die "opening candidates are not byte-identical"
opening_args=(
  --candidates "$W/open-candidates-a.fen"
  --expected "$NOPEN"
  --exclude data/dilf_combinations.fen
  --exclude "$IN/prior-reinforcement.fen"
  --exclude "$IN/prior-meta-screen.fen"
  --exclude "$IN/prior-meta-confirm.fen"
  --exclude "$IN/prior-f2m-confirm.fen"
  --exclude "$IN/prior-f2m-gen2.fen"
  --exclude "$IN/prior-m2-independent.fen"
  --exclude "$IN/prior-d10-independent.fen"
  --exclude "$IN/prior-d12-independent.fen"
  --exclude "$IN/prior-turnover-independent.fen"
  --exclude "$IN/prior-turnover-confirmation.fen"
  --exclude "$IN/prior-replay25.fen"
  --generator-seed "$OPENING_SEED"
)
python3 jobs/tools/select_independent_opening_pool.py "${opening_args[@]}" \
  --out "$ART/turnover-l2-eval-openings.fen" \
  --manifest "$ART/turnover-l2-eval-openings.json" \
  > "$W/select-openings-a.log" 2>&1
opening_args[1]="$W/open-candidates-b.fen"
python3 jobs/tools/select_independent_opening_pool.py "${opening_args[@]}" \
  --out "$W/turnover-l2-eval-openings-repeat.fen" \
  --manifest "$W/turnover-l2-eval-openings-repeat.json" \
  > "$W/select-openings-b.log" 2>&1
cmp -s "$ART/turnover-l2-eval-openings.fen" \
  "$W/turnover-l2-eval-openings-repeat.fen" ||
  die "selected evaluation pool is not byte-identical"

phase publish-preflight-certificate
"$W/venv/bin/python" - "$W" "$ART" "$IN" "$EXPECTED_CODE_SHA" \
  "$EXPECTED_REPLAY25_EVAL_JOB" <<'PY'
import hashlib
import json
import os
import pathlib
import re
import sys

w, art, inputs = map(pathlib.Path, sys.argv[1:4])
code_sha, trigger_job = sys.argv[4:]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def max_rss(path):
    match = re.search(
        r"Maximum resident set size \(kbytes\):\s*(\d+)",
        path.read_text(),
    )
    return int(match.group(1)) if match else None

split = json.load(open(art / "turnover-l2-split.json"))
runtime = json.load(open(art / "python-runtime.json"))
openings = json.load(open(art / "turnover-l2-eval-openings.json"))
trigger = json.load(open(inputs / "replay25-evaluation.json"))
if (
    split.get("records") != 2_000_000
    or split.get("train_records") != 1_800_796
    or split.get("holdout_records") != 199_204
    or split.get("seed") != 577_215
    or openings.get("records") != 500
    or openings.get("unique_records") != 500
    or openings.get("overlap_records") != 0
    or openings.get("generator_seed") != 1_836_313
):
    raise SystemExit("L2 preflight output contract mismatch")

payload = {
    "schema": 1,
    "verdict": "TURNOVER_L2_PREFLIGHT_READY",
    "code_sha": code_sha,
    "trigger": {
        "job": trigger_job,
        "verdict": trigger["verdict"],
        "all_guardrails_pass": trigger["all_guardrails_pass"],
    },
    "experiment_variant": "TURNOVER_1_1_L2_SCREEN",
    "parent": "F2M",
    "parent_model_sha256":
        "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2",
    "control_model_sha256":
        "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16",
    "control_source_code_sha":
        "336bb98451a205266d6646c4d801027af4b30294",
    "l2_levels": [1e-5, 3e-5, 1e-4],
    "control_l2": 3e-5,
    "records": 2_000_000,
    "historical_replay_records": 1_000_000,
    "fresh_records": 1_000_000,
    "jnnw_sha256": sha(w / "turnover1to1.raw.jnnw"),
    "jsm_sha256": sha(w / "turnover1to1.raw.jsm"),
    "split_jnnw_sha256": sha(w / "turnover1to1.fit.jnnw"),
    "split_jsm_sha256": sha(w / "turnover1to1.fit.jsm"),
    "split_manifest": split,
    "runtime": runtime,
    "mini_fit": {
        "records": 20_000,
        "levels": {
            "L2_1E5": {
                "completed": True,
                "max_rss_kib": max_rss(w / "mini-L2_1E5.time"),
            },
            "L2_1E4": {
                "completed": True,
                "max_rss_kib": max_rss(w / "mini-L2_1E4.time"),
            },
        },
    },
    "evaluation_openings": {
        "seed": 1_836_313,
        "sha256": sha(art / "turnover-l2-eval-openings.fen"),
        "candidate_sha256": sha(w / "open-candidates-a.fen"),
        "manifest": openings,
    },
    "resource_preflight": {
        "nproc": os.cpu_count(),
        "split_max_rss_kib": max_rss(w / "split-a.time"),
        "home_training_eta_minutes": [30, 50],
        "home_evaluation_eta_minutes": [45, 70],
        "max_parallel_fits": 2,
    },
    "new_generation_performed": False,
    "external_teacher_inputs": 0,
    "training_authorized": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "turnover-l2-preflight.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__TURNOVER_L2_PREFLIGHT_READY").write_text(
    "TURNOVER_L2_PREFLIGHT_READY\n"
)
(art / "PROMOTION_AUTHORIZED__FALSE").write_text(
    "PROMOTION_AUTHORIZED__FALSE\n"
)
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
PY
phase complete
say "TURNOVER_L2_PREFLIGHT_READY training=true promotion=false automatic_next_job=null"
