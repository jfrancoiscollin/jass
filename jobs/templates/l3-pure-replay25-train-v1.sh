#!/usr/bin/env bash
# L3-PURE REPLAY25: fit the preflighted 25% historical / 75% recent corpus.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${PREFLIGHT_PREFIX:?}"
: "${EXPECTED_PREFLIGHT_JOB:?}"; : "${M1_PREFIX:?}"; : "${EXPECTED_M1_JOB:?}"
: "${CHAMPION_PREFIX:?}"; : "${EXPECTED_CHAMPION_JOB:?}"
: "${TURNOVER_CONFIRM_PREFIX:?}"; : "${EXPECTED_TURNOVER_CONFIRM_JOB:?}"

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
CHAMPION_CODE_SHA="0c1e04a9574fcd87977f62fe5bd6d71c60c72265"
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
L2=3e-5
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
[ "$(awk '/MemAvailable:/{print int($2/1024)}' /proc/meminfo)" -ge 3500 ] ||
  die "need 3.5 GiB available RAM"
git diff --quiet "$CHAMPION_CODE_SHA" HEAD -- src pattern_jass/tools ||
  die "engine/training semantics changed since the repaired champion gate"
monitor

phase fetch-and-authenticate-preflight
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=replay25-preflight.json \
  --file artefacts/replay25.jnnw.gz=replay25.jnnw.gz \
  --file artefacts/replay25.jsm.gz=replay25.jsm.gz \
  --file artefacts/replay25-mix.json=replay25-mix.json \
  --file artefacts/replay25-split.json=replay25-split.json \
  --file artefacts/replay25-coverage.json=replay25-coverage.json \
  --out-dir "$IN" --report "$ART/verified-preflight-source.json" \
  > "$W/fetch-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m1-training.json \
  --out-dir "$IN" --report "$ART/verified-m1-source.json" \
  > "$W/fetch-m1.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$CHAMPION_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=champion.json \
  --out-dir "$IN" --report "$ART/verified-champion-source.json" \
  > "$W/fetch-champion.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_CONFIRM_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-confirmation.json \
  --out-dir "$IN" --report "$ART/verified-confirmation-source.json" \
  > "$W/fetch-confirmation.log" 2>&1

python3 - "$IN" "$ART" "$EXPECTED_PREFLIGHT_JOB" "$EXPECTED_M1_JOB" \
  "$EXPECTED_CHAMPION_JOB" "$EXPECTED_TURNOVER_CONFIRM_JOB" \
  "$F2M_MODEL_SHA" "$TURNOVER_MODEL_SHA" <<'PY'
import json
import sys
from pathlib import Path

src, art = map(Path, sys.argv[1:3])
(
    preflight_job,
    m1_job,
    champion_job,
    confirmation_job,
    f2m_model_sha,
    turnover_model_sha,
) = sys.argv[3:]
for name, job in (
    ("verified-preflight-source.json", preflight_job),
    ("verified-m1-source.json", m1_job),
    ("verified-champion-source.json", champion_job),
    ("verified-confirmation-source.json", confirmation_job),
):
    report = json.load(open(art / name))
    if report.get("job_id") != job or report.get("result_state") != "completed":
        raise SystemExit(f"{name}: source identity/state mismatch")

preflight = json.load(open(src / "replay25-preflight.json"))
mix = json.load(open(src / "replay25-mix.json"))
split = json.load(open(src / "replay25-split.json"))
coverage = json.load(open(src / "replay25-coverage.json"))
m1 = json.load(open(src / "m1-training.json"))
champion = json.load(open(src / "champion.json"))
confirmation = json.load(open(src / "turnover-confirmation.json"))
if (
    preflight.get("verdict") != "REPLAY25_PREFLIGHT_READY"
    or preflight.get("training_authorized") is not True
    or preflight.get("promotion_authorized") is not False
    or preflight.get("automatic_next_job") is not None
    or preflight.get("experiment_variant") != "REPLAY25_RECENCY75"
    or preflight.get("parent") != "F2M"
    or preflight.get("records") != 2_000_000
    or preflight.get("historical_replay_records") != 500_000
    or preflight.get("fresh_records") != 1_500_000
    or preflight.get("mix_seed") != 618_034
    or preflight.get("split_seed") != 577_215
    or preflight.get("mix_manifest") != mix
    or preflight.get("split_manifest") != split
    or preflight.get("coverage") != coverage
    or preflight.get("runtime", {}).get("numpy") != "1.26.4"
    or preflight.get("runtime", {}).get("scipy") != "1.14.1"
    or preflight.get("mini_fit", {}).get("completed") is not True
):
    raise SystemExit("REPLAY25 preflight certificate mismatch")
if (
    m1.get("verdict") != "M1_TRAINING_SCREEN_READY"
    or m1.get("arms", {}).get("F2M", {}).get("model_sha256") != f2m_model_sha
    or champion.get("verdict") != "F2M_NEW_GENERAL_CHAMPION_HUMAN_REVIEW"
    or champion.get("recommended_general_champion") != "F2M"
    or confirmation.get("verdict") != preflight.get("trigger", {}).get("verdict")
    or confirmation.get("all_guardrails_pass") is not True
    or confirmation.get("previous_evaluation_certificate", {}).get("model_sha256")
    != turnover_model_sha
    or confirmation.get("promotion_authorized") is not False
    or confirmation.get("automatic_next_job") is not None
):
    raise SystemExit("parent/trigger certificate mismatch")
PY

phase verify-corpus-and-runtime
gunzip -c "$IN/f2m.pjtw.gz" > "$W/f2m.pjtw"
gunzip -c "$IN/replay25.jnnw.gz" > "$W/replay25.raw.jnnw"
gunzip -c "$IN/replay25.jsm.gz" > "$W/replay25.raw.jsm"
python3 - "$W" "$IN/replay25-preflight.json" "$F2M_MODEL_SHA" <<'PY'
import hashlib
import json
import struct
import sys
from pathlib import Path

w = Path(sys.argv[1])
preflight = json.load(open(sys.argv[2]))
expected_parent = sys.argv[3]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if sha(w / "f2m.pjtw") != expected_parent:
    raise SystemExit("F2M model hash drift")
if (
    sha(w / "replay25.raw.jnnw") != preflight["jnnw_sha256"]
    or sha(w / "replay25.raw.jsm") != preflight["jsm_sha256"]
):
    raise SystemExit("REPLAY25 corpus hash drift")
head = (w / "replay25.raw.jnnw").read_bytes()[:8]
if head[:4] != b"JNNW" or struct.unpack_from("<I", head, 4)[0] != 2_000_000:
    raise SystemExit("REPLAY25 corpus count/header mismatch")
PY
cp "$IN/replay25.jnnw.gz" "$ART/replay25.jnnw.gz"
cp "$IN/replay25.jsm.gz" "$ART/replay25.jsm.gz"
cp "$IN/replay25-mix.json" "$ART/replay25-mix.json"
cp "$IN/replay25-coverage.json" "$ART/replay25-coverage.json"

phase isolated-runtime-build-and-tests
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1
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

phase reproduce-split-by-opening
python3 tools/selfplay_frontier.py split \
  --data "$W/replay25.raw.jnnw" --meta "$W/replay25.raw.jsm" \
  --out-data "$W/replay25.fit.jnnw" --out-meta "$W/replay25.fit.jsm" \
  --holdout-mod 10 --seed 577215 \
  --manifest "$ART/replay25-split.json" > "$W/replay25-split.log" 2>&1
"$W/venv/bin/python" - "$W" "$IN/replay25-preflight.json" \
  "$ART/replay25-split.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

w = Path(sys.argv[1])
preflight = json.load(open(sys.argv[2]))
split = json.load(open(sys.argv[3]))
if split != preflight["split_manifest"]:
    raise SystemExit("REPLAY25 split manifest drift")
if (
    hashlib.sha256((w / "replay25.fit.jnnw").read_bytes()).hexdigest()
    != preflight["split_jnnw_sha256"]
    or hashlib.sha256((w / "replay25.fit.jsm").read_bytes()).hexdigest()
    != preflight["split_jsm_sha256"]
):
    raise SystemExit("REPLAY25 split hash drift")
PY
HOLDOUT="$("$W/venv/bin/python" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' \
  "$ART/replay25-split.json")"
[ "$HOLDOUT" -gt 0 ] || die "REPLAY25 holdout missing"

phase full-feature-dump-and-converged-fit
"$J" --dump-eval-features "$W/replay25.fit.jnnw" "$W/replay25.feat" \
  > "$W/features.log" 2>&1
set +e
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  /usr/bin/time -v timeout 43200 \
  "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
  --data "$W/replay25.fit.jnnw" --feat "$W/replay25.feat" \
  --out "$W/replay25.pjtw" \
  --target wdl --loss logistic --color-fold --tempo-stage \
  --warm-start "$W/f2m.pjtw" --holdout-count "$HOLDOUT" \
  --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
  --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
  --optimizer-report "$ART/replay25-optimizer.json" \
  > "$W/fit.log" 2> "$W/fit.time"
FIT_RC=$?
set -e
if [ -s "$W/replay25.pjtw" ]; then
  gzip -n -c "$W/replay25.pjtw" > "$ART/replay25-checkpoint.pjtw.gz"
fi
[ "$FIT_RC" -eq 0 ] ||
  die "REPLAY25 fit failed rc=$FIT_RC; corpus/checkpoint preserved"
[ -s "$W/replay25.pjtw" ] || die "REPLAY25 model missing"
grep -q 'HOLDOUT_LOGLOSS' "$W/fit.log" || die "REPLAY25 holdout result missing"
"$W/venv/bin/python" - "$ART/replay25-optimizer.json" <<'PY' || die "REPLAY25 optimiser did not converge"
import json
import sys
if not json.load(open(sys.argv[1])).get("success"):
    raise SystemExit(1)
PY
cp "$ART/replay25-checkpoint.pjtw.gz" "$ART/replay25.pjtw.gz"

phase publish-training-screen
"$W/venv/bin/python" - "$W" "$ART" "$IN/replay25-preflight.json" \
  "$EXPECTED_CODE_SHA" "$F2M_MODEL_SHA" "$EXPECTED_PREFLIGHT_JOB" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
preflight = json.load(open(sys.argv[3]))
code_sha, parent_sha, preflight_job = sys.argv[4:]
fit_log = (w / "fit.log").read_text()
timing = (w / "fit.time").read_text()
optimizer = json.load(open(art / "replay25-optimizer.json"))
split = json.load(open(art / "replay25-split.json"))
model_sha = hashlib.sha256((w / "replay25.pjtw").read_bytes()).hexdigest()
payload = {
    "schema": 1,
    "verdict": "REPLAY25_TRAINING_SCREEN_READY",
    "code_sha": code_sha,
    "preflight_job": preflight_job,
    "preflight_code_sha": preflight["code_sha"],
    "trigger_confirmation": preflight["trigger"],
    "experiment_variant": "REPLAY25_RECENCY75",
    "parent": "F2M",
    "parent_model_sha256": parent_sha,
    "model_sha256": model_sha,
    "training_records": 2_000_000,
    "training_corpus_sha256": preflight["jnnw_sha256"],
    "training_meta_sha256": preflight["jsm_sha256"],
    "historical_replay_records": 500_000,
    "fresh_records": 1_500_000,
    "temporal_distribution_records": {
        "parent_f2m": 500_000,
        "fresh_m2": 1_500_000,
    },
    "mix_seed": 618_034,
    "split_seed": 577_215,
    "holdout_records": split["holdout_records"],
    "iterations": int(re.search(r"iters=(\d+)", fit_log).group(1)),
    "holdout_logloss": float(
        re.search(r"HOLDOUT_LOGLOSS\s+([0-9.]+)", fit_log).group(1)
    ),
    "max_rss_kib": int(
        re.search(
            r"Maximum resident set size \(kbytes\):\s*(\d+)",
            timing,
        ).group(1)
    ),
    "optimizer_success": optimizer["success"],
    "new_generation_performed": False,
    "starts": "standard",
    "play_depth": 8,
    "geometry": "8cf",
    "search": "Q00",
    "top3": False,
    "role_reweight_v2": False,
    "external_teacher_inputs": 0,
    "evaluation_authorized": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "replay25-training-summary.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__REPLAY25_TRAINING_SCREEN_READY").write_text(
    "REPLAY25_TRAINING_SCREEN_READY\n"
)
(art / "PROMOTION_AUTHORIZED__FALSE").write_text(
    "PROMOTION_AUTHORIZED__FALSE\n"
)
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
PY
phase complete
say "REPLAY25_TRAINING_SCREEN_READY evaluation=true promotion=false automatic_next_job=null"
