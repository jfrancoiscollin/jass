#!/usr/bin/env bash
# L3-PURE REPLAY75: deterministic full-corpus, runtime and evaluation-pool preflight.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${TURNOVER_CONFIRM_PREFIX:?}"
: "${EXPECTED_TURNOVER_CONFIRM_JOB:?}"; : "${M1_PREFIX:?}"
: "${EXPECTED_M1_JOB:?}"; : "${M2_PREFIX:?}"; : "${EXPECTED_M2_JOB:?}"
: "${REPLAY25_PREFLIGHT_PREFIX:?}"; : "${EXPECTED_REPLAY25_PREFLIGHT_JOB:?}"
: "${L2_PREFLIGHT_PREFIX:?}"; : "${EXPECTED_L2_PREFLIGHT_JOB:?}"
: "${L2_CONFIRM_PREFLIGHT_PREFIX:?}"; : "${EXPECTED_L2_CONFIRM_PREFLIGHT_JOB:?}"

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
F2M_CORPUS_SHA="15261c89bd6520e17c03bcf2843b226600ff334130656aab7b1a1f2d1ca03248"
F2M_META_SHA="6b12a940128033652afe578c61e48c8570ba4db14cb4cde363d56d4bdcdf2d7f"
M2_MODEL_SHA="75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
M2_CORPUS_SHA="ee8d685cea331940403da82830d7b4cc045fe50acc1e5764d23f0467d4f7ffb8"
M2_META_SHA="42b184456375bb581192651262f3981879bd04e5ee3162a6186883c2f8f66729"
TURNOVER_MODEL_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
CHAMPION_CODE_SHA="0c1e04a9574fcd87977f62fe5bd6d71c60c72265"
MIX_SEED=832040
SPLIT_SEED=577215
OPENING_SEED=3141593
OPENING_CANDIDATES=5000
NOPEN=1250
TOTAL_RECORDS=2000000
PARENT_RECORDS=1500000
FRESH_RECORDS=500000

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

phase fetch-and-authenticate-completed-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_CONFIRM_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-confirmation.json \
  --file artefacts/turnover-confirmation.json=turnover-confirmation-detail.json \
  --file artefacts/independent-openings-manifest.json=turnover-confirm-openings.json \
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
  > "$W/fetch-confirmation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$REPLAY25_PREFLIGHT_PREFIX" \
  --file artefacts/replay25-eval-openings.fen=prior-replay25.fen \
  --out-dir "$IN" --report "$ART/verified-replay25-preflight.json" \
  > "$W/fetch-prior-replay25.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$L2_PREFLIGHT_PREFIX" \
  --file artefacts/turnover-l2-eval-openings.fen=prior-turnover-l2.fen \
  --out-dir "$IN" --report "$ART/verified-l2-preflight.json" \
  > "$W/fetch-prior-l2.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$L2_CONFIRM_PREFLIGHT_PREFIX" \
  --file artefacts/turnover-l2-confirm-openings.fen=prior-l2-confirm.fen \
  --out-dir "$IN" --report "$ART/verified-l2-confirm-preflight.json" \
  > "$W/fetch-prior-l2-confirm.log" 2>&1

for spec in \
  "verified-replay25-preflight.json:$EXPECTED_REPLAY25_PREFLIGHT_JOB" \
  "verified-l2-preflight.json:$EXPECTED_L2_PREFLIGHT_JOB" \
  "verified-l2-confirm-preflight.json:$EXPECTED_L2_CONFIRM_PREFLIGHT_JOB"; do
  report="${spec%%:*}"
  job="${spec#*:}"
  python3 - "$ART/$report" "$job" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
PY
done
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/common-fresh-500k.jnnw.gz=f2m-common.jnnw.gz \
  --file artefacts/common-fresh-500k.jsm.gz=f2m-common.jsm.gz \
  --file artefacts/extra-fresh-1500k.jnnw.gz=f2m-extra.jnnw.gz \
  --file artefacts/extra-fresh-1500k.jsm.gz=f2m-extra.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m1-training.json \
  --out-dir "$IN" --report "$ART/verified-m1-source.json" \
  > "$W/fetch-m1.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M2_PREFIX" \
  --file artefacts/m2.pjtw.gz=m2.pjtw.gz \
  --file artefacts/m2-fresh-2m.jnnw.gz=m2.jnnw.gz \
  --file artefacts/m2-fresh-2m.jsm.gz=m2.jsm.gz \
  --file artefacts/m2-corpus-contract.json=m2-corpus-contract.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m2-training.json \
  --out-dir "$IN" --report "$ART/verified-m2-source.json" \
  > "$W/fetch-m2.log" 2>&1

python3 - "$IN" "$ART" "$EXPECTED_TURNOVER_CONFIRM_JOB" \
  "$EXPECTED_M1_JOB" "$EXPECTED_M2_JOB" "$TURNOVER_MODEL_SHA" \
  "$M2_MODEL_SHA" "$M2_CORPUS_SHA" "$M2_META_SHA" <<'PY'
import json
import sys
from pathlib import Path

src, art = map(Path, sys.argv[1:3])
(
    confirmation_job,
    m1_job,
    m2_job,
    turnover_model_sha,
    m2_model_sha,
    m2_corpus_sha,
    m2_meta_sha,
) = sys.argv[3:]

for name, expected_job in (
    ("verified-turnover-confirmation.json", confirmation_job),
    ("verified-m1-source.json", m1_job),
    ("verified-m2-source.json", m2_job),
):
    report = json.load(open(art / name))
    if report.get("job_id") != expected_job or report.get("result_state") != "completed":
        raise SystemExit(f"{name}: source identity/state mismatch")

confirmation = json.load(open(src / "turnover-confirmation.json"))
detail = json.load(open(src / "turnover-confirmation-detail.json"))
allowed = {
    "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW",
    "TURNOVER_DIRECTION_REPLICATED_REVIEW",
}
if (
    confirmation != detail
    or confirmation.get("verdict") not in allowed
    or confirmation.get("all_guardrails_pass") is not True
    or confirmation.get("promotion_authorized") is not False
    or confirmation.get("automatic_next_job") is not None
    or confirmation.get("protocol", {}).get("candidate") != "TURNOVER_1_1"
    or confirmation.get("previous_evaluation_certificate", {}).get("model_sha256")
    != turnover_model_sha
    or confirmation.get("fresh_force", {}).get("q00_vs_M2", {}).get("n") != 2000
    or confirmation.get("fresh_force", {}).get("q00_vs_M2", {}).get("rate")
    != 0.53775
    or confirmation.get("fresh_force", {}).get("q00_vs_F2M", {}).get("rate")
    != 0.5035
    or confirmation.get("pooled_checks", {}).get("M2", {}).get("q00", {}).get(
        "superiority_established"
    )
    is not True
    or confirmation.get("pooled_checks", {}).get("F2M", {}).get("q00", {}).get(
        "regression_not_established"
    )
    is not True
):
    raise SystemExit("turnover confirmation does not authorize REPLAY75 preflight")

m1 = json.load(open(src / "m1-training.json"))
m2 = json.load(open(src / "m2-training.json"))
m2_contract = json.load(open(src / "m2-corpus-contract.json"))
if (
    m1.get("verdict") != "M1_TRAINING_SCREEN_READY"
    or m1.get("arms", {}).get("F2M", {}).get("model_sha256")
    != "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
):
    raise SystemExit("F2M training certificate mismatch")
if (
    m2.get("verdict") != "M2_TRAINING_SCREEN_READY"
    or m2.get("model_sha256") != m2_model_sha
    or m2.get("training_corpus_sha256") != m2_corpus_sha
    or m2.get("fresh_only") is not True
    or m2.get("training_records") != 2_000_000
    or m2_contract.get("jnnw_sha256") != m2_corpus_sha
    or m2_contract.get("jsm_sha256") != m2_meta_sha
    or m2_contract.get("historical_replay_records") != 0
    or m2_contract.get("starts") != "standard"
    or m2_contract.get("top3") is not False
    or m2_contract.get("role_reweight_v2") is not False
    or m2_contract.get("geometry") != "8cf"
    or m2_contract.get("search") != "Q00"
):
    raise SystemExit("M2 source certificate mismatch")
PY

phase reconstruct-certified-source-corpora
gunzip -c "$IN/f2m.pjtw.gz" > "$W/f2m.pjtw"
gunzip -c "$IN/m2.pjtw.gz" > "$W/m2.pjtw"
[ "$(sha256sum "$W/f2m.pjtw" | awk '{print $1}')" = "$F2M_MODEL_SHA" ] ||
  die "F2M model hash drift"
[ "$(sha256sum "$W/m2.pjtw" | awk '{print $1}')" = "$M2_MODEL_SHA" ] ||
  die "M2 model hash drift"
gunzip -c "$IN/f2m-common.jnnw.gz" > "$W/f2m-common.jnnw"
gunzip -c "$IN/f2m-common.jsm.gz" > "$W/f2m-common.jsm"
gunzip -c "$IN/f2m-extra.jnnw.gz" > "$W/f2m-extra.jnnw"
gunzip -c "$IN/f2m-extra.jsm.gz" > "$W/f2m-extra.jsm"
python3 tools/selfplay_frontier.py merge \
  --pair "$W/f2m-common.jnnw" "$W/f2m-common.jsm" \
  --pair "$W/f2m-extra.jnnw" "$W/f2m-extra.jsm" \
  --renamespace-nested \
  --out-data "$W/f2m.raw.jnnw" --out-meta "$W/f2m.raw.jsm" \
  --manifest "$ART/f2m-reconstruction.json" > "$W/f2m-reconstruction.log" 2>&1
gunzip -c "$IN/m2.jnnw.gz" > "$W/m2.raw.jnnw"
gunzip -c "$IN/m2.jsm.gz" > "$W/m2.raw.jsm"
[ "$(sha256sum "$W/f2m.raw.jnnw" | awk '{print $1}')" = "$F2M_CORPUS_SHA" ] ||
  die "F2M corpus hash drift"
[ "$(sha256sum "$W/f2m.raw.jsm" | awk '{print $1}')" = "$F2M_META_SHA" ] ||
  die "F2M metadata hash drift"
[ "$(sha256sum "$W/m2.raw.jnnw" | awk '{print $1}')" = "$M2_CORPUS_SHA" ] ||
  die "M2 corpus hash drift"
[ "$(sha256sum "$W/m2.raw.jsm" | awk '{print $1}')" = "$M2_META_SHA" ] ||
  die "M2 metadata hash drift"

phase construct-replay75-twice
/usr/bin/time -v -o "$W/mix1.time" python3 tools/selfplay_frontier.py mix \
  --source PARENT "$W/f2m.raw.jnnw" "$W/f2m.raw.jsm" 3 \
  --source FRESH "$W/m2.raw.jnnw" "$W/m2.raw.jsm" 1 \
  --target-records "$TOTAL_RECORDS" --seed "$MIX_SEED" --namespace-openings \
  --out-data "$W/replay75.raw.jnnw" --out-meta "$W/replay75.raw.jsm" \
  --manifest "$ART/replay75-mix.json" > "$W/replay75-mix.log" 2>&1
/usr/bin/time -v -o "$W/mix2.time" python3 tools/selfplay_frontier.py mix \
  --source PARENT "$W/f2m.raw.jnnw" "$W/f2m.raw.jsm" 3 \
  --source FRESH "$W/m2.raw.jnnw" "$W/m2.raw.jsm" 1 \
  --target-records "$TOTAL_RECORDS" --seed "$MIX_SEED" --namespace-openings \
  --out-data "$W/replay75-repeat.jnnw" --out-meta "$W/replay75-repeat.jsm" \
  --manifest "$W/replay75-repeat-mix.json" > "$W/replay75-repeat-mix.log" 2>&1
cmp -s "$W/replay75.raw.jnnw" "$W/replay75-repeat.jnnw" ||
  die "REPLAY75 data reconstruction is not byte-identical"
cmp -s "$W/replay75.raw.jsm" "$W/replay75-repeat.jsm" ||
  die "REPLAY75 metadata reconstruction is not byte-identical"
python3 - "$ART/replay75-mix.json" "$F2M_CORPUS_SHA" "$F2M_META_SHA" \
  "$M2_CORPUS_SHA" "$M2_META_SHA" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1]))
parent_data, parent_meta, fresh_data, fresh_meta = sys.argv[2:]
sources = {source["label"]: source for source in manifest.get("sources", [])}
if (
    manifest.get("operation") != "weighted_aligned_mix"
    or manifest.get("selection") != "exact_uniform_record_sample_splitmix64_floyd"
    or manifest.get("seed") != 832_040
    or manifest.get("records") != 2_000_000
    or sources.get("PARENT", {}).get("selected_records") != 1_500_000
    or sources.get("FRESH", {}).get("selected_records") != 500_000
    or sources.get("PARENT", {}).get("input_data_sha256") != parent_data
    or sources.get("PARENT", {}).get("input_meta_sha256") != parent_meta
    or sources.get("FRESH", {}).get("input_data_sha256") != fresh_data
    or sources.get("FRESH", {}).get("input_meta_sha256") != fresh_meta
    or manifest.get("opening_id_policy")
    != "source_namespaced_for_independent_temporal_corpora"
    or manifest.get("external_teacher_inputs") != 0
):
    raise SystemExit("REPLAY75 exact mix contract mismatch")
PY
gzip -n -c "$W/replay75.raw.jnnw" > "$ART/replay75.jnnw.gz"
gzip -n -c "$W/replay75.raw.jsm" > "$ART/replay75.jsm.gz"

phase split-by-opening-twice
/usr/bin/time -v -o "$W/split1.time" python3 tools/selfplay_frontier.py split \
  --data "$W/replay75.raw.jnnw" --meta "$W/replay75.raw.jsm" \
  --out-data "$W/replay75.fit.jnnw" --out-meta "$W/replay75.fit.jsm" \
  --holdout-mod 10 --seed "$SPLIT_SEED" \
  --manifest "$ART/replay75-split.json" > "$W/replay75-split.log" 2>&1
/usr/bin/time -v -o "$W/split2.time" python3 tools/selfplay_frontier.py split \
  --data "$W/replay75.raw.jnnw" --meta "$W/replay75.raw.jsm" \
  --out-data "$W/replay75-repeat.fit.jnnw" \
  --out-meta "$W/replay75-repeat.fit.jsm" \
  --holdout-mod 10 --seed "$SPLIT_SEED" \
  --manifest "$W/replay75-repeat-split.json" \
  > "$W/replay75-repeat-split.log" 2>&1
cmp -s "$W/replay75.fit.jnnw" "$W/replay75-repeat.fit.jnnw" ||
  die "REPLAY75 split data is not byte-identical"
cmp -s "$W/replay75.fit.jsm" "$W/replay75-repeat.fit.jsm" ||
  die "REPLAY75 split metadata is not byte-identical"

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
python3 -m py_compile tools/selfplay_frontier.py jobs/tools/l3_bucket_visits.py
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

phase mini-feature-fit-roundtrip
python3 tools/selfplay_frontier.py mix \
  --source PARENT "$W/f2m.raw.jnnw" "$W/f2m.raw.jsm" 3 \
  --source FRESH "$W/m2.raw.jnnw" "$W/m2.raw.jsm" 1 \
  --target-records 20000 --seed "$MIX_SEED" --namespace-openings \
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
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  /usr/bin/time -v -o "$W/mini-fit.time" \
  "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
  --data "$W/mini.fit.jnnw" --feat "$W/mini.feat" --out "$W/mini.pjtw" \
  --target wdl --loss logistic --color-fold --tempo-stage \
  --warm-start "$W/f2m.pjtw" --holdout-count "$HOLDOUT" \
  --l2 3e-5 --max-iter 2 --chunk 20000 --lbfgs-maxcor 20 --lbfgs-gtol 1e-3 \
  > "$W/mini-fit.log" 2>&1
[ -s "$W/mini.pjtw" ] || die "mini-fit output missing"
grep -q 'HOLDOUT_LOGLOSS' "$W/mini-fit.log" || die "mini-fit holdout missing"

phase exact-coverage-and-independent-evaluation-pool
env PYTHONPATH="$GEOM:pattern_jass/tools" \
  /usr/bin/time -v -o "$W/coverage.time" \
  python3 jobs/tools/l3_bucket_visits.py --data "$W/replay75.raw.jnnw" \
  --out "$ART/replay75-coverage.json" > "$W/coverage.log" 2>&1
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
  --exclude "$IN/prior-turnover-l2.fen"
  --exclude "$IN/prior-l2-confirm.fen"
  --generator-seed "$OPENING_SEED"
)
python3 jobs/tools/select_independent_opening_pool.py "${opening_args[@]}" \
  --out "$ART/replay75-eval-openings.fen" \
  --manifest "$ART/replay75-eval-openings.json" \
  > "$W/select-openings-a.log" 2>&1
opening_args[1]="$W/open-candidates-b.fen"
python3 jobs/tools/select_independent_opening_pool.py "${opening_args[@]}" \
  --out "$W/replay75-eval-openings-repeat.fen" \
  --manifest "$W/replay75-eval-openings-repeat.json" \
  > "$W/select-openings-b.log" 2>&1
cmp -s "$ART/replay75-eval-openings.fen" \
  "$W/replay75-eval-openings-repeat.fen" ||
  die "selected evaluation pool is not byte-identical"

phase publish-preflight-certificate
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" \
  "$EXPECTED_TURNOVER_CONFIRM_JOB" <<'PY'
import hashlib
import json
import os
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha, confirmation_job = sys.argv[3:]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def max_rss(path):
    match = re.search(
        r"Maximum resident set size \(kbytes\):\s*(\d+)",
        path.read_text(),
    )
    return int(match.group(1)) if match else None

mix = json.load(open(art / "replay75-mix.json"))
split = json.load(open(art / "replay75-split.json"))
coverage = json.load(open(art / "replay75-coverage.json"))
openings = json.load(open(art / "replay75-eval-openings.json"))
runtime = json.load(open(art / "python-runtime.json"))
confirmation = json.load(open(w.parent / "inputs" / "turnover-confirmation.json"))
sources = {source["label"]: source for source in mix["sources"]}
if (
    sources["PARENT"]["selected_records"] != 1_500_000
    or sources["FRESH"]["selected_records"] != 500_000
    or split.get("records") != 2_000_000
    or split.get("holdout_records", 0) <= 0
    or split.get("train_records", 0) + split.get("holdout_records", 0)
    != 2_000_000
    or coverage.get("corpus", {}).get("total_records") != 2_000_000
    or openings.get("records") != 1_250
    or openings.get("unique_records") != 1_250
    or openings.get("overlap_records") != 0
    or openings.get("generator_seed") != 3_141_593
):
    raise SystemExit("preflight output contract mismatch")

payload = {
    "schema": 1,
    "verdict": "REPLAY75_PREFLIGHT_READY",
    "code_sha": code_sha,
    "trigger": {
        "job": confirmation_job,
        "verdict": confirmation["verdict"],
        "all_guardrails_pass": confirmation["all_guardrails_pass"],
        "turnover_model_sha256": confirmation[
            "previous_evaluation_certificate"
        ]["model_sha256"],
    },
    "experiment_variant": "REPLAY75_RECENCY75",
    "parent": "F2M",
    "records": 2_000_000,
    "historical_replay_records": 1_500_000,
    "fresh_records": 500_000,
    "mix_seed": 832_040,
    "split_seed": 577_215,
    "jnnw_sha256": sha(w / "replay75.raw.jnnw"),
    "jsm_sha256": sha(w / "replay75.raw.jsm"),
    "split_jnnw_sha256": sha(w / "replay75.fit.jnnw"),
    "split_jsm_sha256": sha(w / "replay75.fit.jsm"),
    "mix_manifest": mix,
    "split_manifest": split,
    "coverage": coverage,
    "evaluation_openings": {
        "seed": 3_141_593,
        "sha256": sha(art / "replay75-eval-openings.fen"),
        "candidate_sha256": sha(w / "open-candidates-a.fen"),
        "manifest": openings,
    },
    "runtime": runtime,
    "mini_fit": {
        "records": 20_000,
        "completed": True,
        "max_iterations": 2,
        "max_rss_kib": max_rss(w / "mini-fit.time"),
    },
    "resource_preflight": {
        "nproc": os.cpu_count(),
        "mix_max_rss_kib": max_rss(w / "mix1.time"),
        "split_max_rss_kib": max_rss(w / "split1.time"),
        "coverage_max_rss_kib": max_rss(w / "coverage.time"),
        "home_training_eta_minutes": [35, 50],
        "home_evaluation_eta_minutes": [80, 115],
    },
    "training_authorized": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "replay75-preflight.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__REPLAY75_PREFLIGHT_READY").write_text(
    "REPLAY75_PREFLIGHT_READY\n"
)
(art / "PROMOTION_AUTHORIZED__FALSE").write_text(
    "PROMOTION_AUTHORIZED__FALSE\n"
)
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
PY
phase complete
say "REPLAY75_PREFLIGHT_READY training=true promotion=false automatic_next_job=null"
