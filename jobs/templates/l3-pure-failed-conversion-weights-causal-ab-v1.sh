#!/usr/bin/env bash
# L3-PURE — fit-only causal A/B for bounded failed-conversion sample weights.
#
# Both arms replay the exact immutable TURNOVER corpus and opening-level split.
# CONTROL supplies an all-ones vector, which must take train_stream's legacy
# sw_all=None path and reproduce the historical TURNOVER model byte-for-byte.
# TREATMENT changes only failed-conversion train-row weights from 1 to 2.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${SOURCE_PREFIX:?}"; : "${EXPECTED_SOURCE_JOB:?}"
: "${EXPECTED_SOURCE_ATTEMPT:?}"; : "${EXPECTED_SOURCE_CODE_SHA:?}"
: "${SOURCE_CORPUS_SHA:?}"; : "${SOURCE_META_SHA:?}"; : "${SOURCE_MODEL_SHA:?}"
: "${M1_PREFIX:?}"; : "${EXPECTED_M1_JOB:?}"; : "${EXPECTED_M1_ATTEMPT:?}"
: "${EXPECTED_M1_CODE_SHA:?}"; : "${F2M_MODEL_SHA:?}"

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

FAILED_WEIGHT=2
HOLDOUT_MOD=10
SPLIT_SEED=577215
L2=3e-5
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
CHUNK=20000
FIT_TIMEOUT=${FIT_TIMEOUT:-5400}
MIN_TREATMENT_ESS_FRACTION=0.80
MON=""

monitor(){
  (
    local t0; t0=$(date +%s)
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        printf 'disk_free_mb=%s\n' \
          "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in control treatment; do
          [ -f "$W/fit-$arm.log" ] &&
            printf 'fit_%s_lines=%s\n' "$arm" \
              "$(wc -l < "$W/fit-$arm.log")"
          [ -f "$ART/$arm-optimizer.json" ] &&
            printf 'fit_%s_optimizer_report=present\n' "$arm"
          [ -f "$ART/$arm-trainer-weights.json" ] &&
            printf 'fit_%s_weights_report=present\n' "$arm"
        done
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MON="$!"
}

restore_tree(){
  git checkout -- src/ pattern_jass/tools/gen_patterns.py \
    pattern_jass/tools/patterns.py 2>/dev/null || true
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
  restore_tree
  rm -rf "$W/build" "$W/venv" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat "$W"/*.pjtw \
    "$W"/*.npy 2>/dev/null || true
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
[ "${SOURCE_ONLY_IMMUTABLE_TURNOVER:-0}" = 1 ] ||
  die "immutable TURNOVER source guard missing"
[ "${ONE_FACTOR_ONLY:-0}" = 1 ] ||
  die "single-factor guard missing"
[ "${EXTERNAL_TEACHER_INPUTS:-}" = 0 ] ||
  die "external teacher inputs must be zero"
[ "${NO_SELFPLAY_GENERATION:-0}" = 1 ] ||
  die "self-play generation must be disabled"
NCPU=$(nproc)
[ "$NCPU" -ge 12 ] || die "need at least 12 logical CPUs, got $NCPU"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -ge 16000 ] || die "need 16 GiB free, got ${DFA}M"
say "  fit-only DOE: exact TURNOVER 2M; CONTROL w=1; TREATMENT failed=2"
say "  two sequential fits; timeout=${FIT_TIMEOUT}s each; no self-play"
monitor

phase fetch-and-authenticate-turnover-source
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_PREFIX" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --file artefacts/turnover1to1.pjtw.gz=turnover.pjtw.gz \
  --file artefacts/m2-split.json=source-split.json \
  --file artefacts/m2-training-summary.json=source-training.json \
  --file artefacts/m2-corpus-contract.json=source-corpus.json \
  --out-dir "$IN" --report "$ART/verified-turnover-source.json" \
  > "$W/fetch-turnover.log" 2>&1
python3 - "$ART/verified-turnover-source.json" "$EXPECTED_SOURCE_JOB" \
  "$EXPECTED_SOURCE_ATTEMPT" "$EXPECTED_SOURCE_CODE_SHA" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1]))
if (
    report.get("job_id") != sys.argv[2]
    or report.get("attempt_id") != sys.argv[3]
    or report.get("code_sha") != sys.argv[4]
    or report.get("result_state") != "completed"
    or report.get("exit_code") != 0
):
    raise SystemExit("TURNOVER source identity/state mismatch")
PY
gunzip -c "$IN/turnover.jnnw.gz" > "$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" > "$W/turnover.raw.jsm"
gunzip -c "$IN/turnover.pjtw.gz" > "$W/historical-turnover.pjtw"
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = \
  "$SOURCE_CORPUS_SHA" ] || die "TURNOVER corpus hash drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = \
  "$SOURCE_META_SHA" ] || die "TURNOVER metadata hash drift"
[ "$(sha256sum "$W/historical-turnover.pjtw" | awk '{print $1}')" = \
  "$SOURCE_MODEL_SHA" ] || die "TURNOVER model hash drift"
python3 - "$IN/source-split.json" "$IN/source-training.json" \
  "$IN/source-corpus.json" "$EXPECTED_SOURCE_CODE_SHA" "$SOURCE_CORPUS_SHA" \
  "$SOURCE_META_SHA" "$SOURCE_MODEL_SHA" "$HOLDOUT_MOD" "$SPLIT_SEED" <<'PY'
import json
import sys

split, training, corpus = (json.load(open(path)) for path in sys.argv[1:4])
code, data_sha, meta_sha, model_sha = sys.argv[4:8]
holdout_mod, seed = map(int, sys.argv[8:10])
if (
    training.get("verdict") != "M2_TRAINING_SCREEN_READY"
    or training.get("code_sha") != code
    or training.get("model_sha256") != model_sha
    or training.get("training_corpus_sha256") != data_sha
    or training.get("training_meta_sha256") != meta_sha
    or training.get("experiment_variant") != "TURNOVER_1_1"
):
    raise SystemExit("TURNOVER training certificate mismatch")
if (
    corpus.get("jnnw_sha256") != data_sha
    or corpus.get("jsm_sha256") != meta_sha
    or corpus.get("records") != 2_000_000
    or corpus.get("experiment_variant") != "TURNOVER_1_1"
):
    raise SystemExit("TURNOVER corpus contract mismatch")
if (
    split.get("holdout_mod") != holdout_mod
    or split.get("seed") != seed
    or split.get("tail_is_holdout") is not True
    or split.get("records") != 2_000_000
):
    raise SystemExit("TURNOVER split contract mismatch")
PY
say "  immutable TURNOVER corpus/model/split authenticated"

phase fetch-and-authenticate-f2m-warm-start
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/m1-training-summary.json=m1-training.json \
  --out-dir "$IN" --report "$ART/verified-f2m-source.json" \
  > "$W/fetch-f2m.log" 2>&1
python3 - "$ART/verified-f2m-source.json" "$EXPECTED_M1_JOB" \
  "$EXPECTED_M1_ATTEMPT" "$EXPECTED_M1_CODE_SHA" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1]))
if (
    report.get("job_id") != sys.argv[2]
    or report.get("attempt_id") != sys.argv[3]
    or report.get("code_sha") != sys.argv[4]
    or report.get("result_state") != "completed"
    or report.get("exit_code") != 0
):
    raise SystemExit("F2M source identity/state mismatch")
PY
gunzip -c "$IN/f2m.pjtw.gz" > "$W/F2M.pjtw"
[ "$(sha256sum "$W/F2M.pjtw" | awk '{print $1}')" = "$F2M_MODEL_SHA" ] ||
  die "F2M warm-start hash drift"
python3 - "$IN/m1-training.json" "$F2M_MODEL_SHA" <<'PY'
import json
import sys

summary = json.load(open(sys.argv[1]))
if (
    summary.get("verdict") != "M1_TRAINING_SCREEN_READY"
    or summary.get("arms", {}).get("F2M", {}).get("model_sha256") != sys.argv[2]
):
    raise SystemExit("F2M training certificate mismatch")
PY

phase isolated-runtime-tests-and-feature-build
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: numpy==1.26.4 scipy==1.14.1 pytest==8.3.5 \
  > "$W/pip.log" 2>&1
"$W/venv/bin/python" -m unittest \
  jobs.tests.test_l3_failed_conversion_weights \
  > "$W/test-failed-weights.log" 2>&1
"$W/venv/bin/python" -m pytest -q \
  pattern_jass/tests/test_train_stream_sample_weights.py \
  > "$W/test-trainer-weights.log" 2>&1
"$W/venv/bin/python" -m py_compile \
  jobs/tools/l3_failed_conversion_weights.py \
  pattern_jass/tools/train_stream.py
# Reconstruct the historical feature dumper so an all-ones control is a strict
# byte-level reproducibility witness, while the trainer itself remains current.
for source in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp \
  src/movegen.cpp src/movegen.hpp src/main.cpp \
  pattern_jass/tools/gen_patterns.py; do
  git show "$EXPECTED_SOURCE_CODE_SHA:$source" > "$source" ||
    die "cannot reconstruct historical feature source $source"
done
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" "$W/venv/bin/python" -c \
  'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  die "8cf geometry mismatch"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=OFF \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j6 --target jass jass_tests \
  > "$W/build.log" 2>&1
ctest --test-dir "$W/build" --output-on-failure > "$W/ctest.log" 2>&1
J="$W/build/jass"
[ "$("$J" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
say "  sample-weight tests and historical 8cf feature build passed"

phase reproduce-certified-split
python3 tools/selfplay_frontier.py split \
  --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/turnover.fit.jnnw" --out-meta "$W/turnover.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/turnover-split.json" > "$W/split.log" 2>&1
python3 - "$IN/source-split.json" "$ART/turnover-split.json" <<'PY'
import json
import sys

source, reproduced = (json.load(open(path)) for path in sys.argv[1:3])
if source != reproduced:
    raise SystemExit("TURNOVER split reproduction drift")
PY
HOLDOUT=$("$W/venv/bin/python" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' \
  "$ART/turnover-split.json")
[ "$HOLDOUT" -gt 0 ] || die "TURNOVER holdout missing"

phase build-aligned-weight-arms
for arm in control treatment; do
  if [ "$arm" = control ]; then multiplier=1; else multiplier="$FAILED_WEIGHT"; fi
  "$W/venv/bin/python" -m jobs.tools.l3_failed_conversion_weights \
    --data "$W/turnover.fit.jnnw" \
    --split-manifest "$ART/turnover-split.json" \
    --out "$W/$arm.npy" --report "$ART/$arm-weight-construction.json" \
    --failed-weight "$multiplier" --code-sha "$EXPECTED_CODE_SHA" \
    > "$W/build-$arm-weights.log" 2>&1
done
"$W/venv/bin/python" - "$W/control.npy" "$W/treatment.npy" \
  "$ART/control-weight-construction.json" \
  "$ART/treatment-weight-construction.json" \
  "$MIN_TREATMENT_ESS_FRACTION" <<'PY'
import json
import sys

import numpy as np

control = np.load(sys.argv[1], allow_pickle=False, mmap_mode="r")
treatment = np.load(sys.argv[2], allow_pickle=False, mmap_mode="r")
cr, tr = (json.load(open(path)) for path in sys.argv[3:5])
minimum_ess = float(sys.argv[5])
if control.dtype != np.float32 or treatment.dtype != np.float32:
    raise SystemExit("weight dtype drift")
if control.shape != treatment.shape or control.shape != (2_000_000,):
    raise SystemExit("weight alignment/length drift")
if not bool(np.all(control == np.float32(1.0))):
    raise SystemExit("CONTROL is not an all-ones vector")
if cr["train_counts"] != tr["train_counts"]:
    raise SystemExit("weight arms saw different train signal counts")
if tr["train_counts"]["failed_conversion"] <= 0:
    raise SystemExit("TREATMENT has no failed-conversion rows")
if tr["effective_sample_size_before_normalization"]["ess_fraction"] < minimum_ess:
    raise SystemExit("TREATMENT ESS below preregistered floor")
if not bool(np.all(treatment[-tr["split"]["holdout_records"]:] == 1.0)):
    raise SystemExit("TREATMENT holdout weights are not all one")
PY
"$J" --dump-eval-features "$W/turnover.fit.jnnw" "$W/turnover.feat" \
  > "$W/features.log" 2>&1
say "  one shared feature matrix; aligned CONTROL/TREATMENT weights certified"

fit_arm(){
  local arm="$1" max_weight="$2"
  phase "fit-$arm"
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    /usr/bin/time -v timeout "$FIT_TIMEOUT" \
    "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
    --data "$W/turnover.fit.jnnw" --feat "$W/turnover.feat" \
    --out "$W/$arm.pjtw" --target wdl --loss logistic --color-fold \
    --tempo-stage --warm-start "$W/F2M.pjtw" --holdout-count "$HOLDOUT" \
    --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
    --sample-weights "$W/$arm.npy" --weight-normalization mean-train-1 \
    --weight-min 1 --weight-max "$max_weight" \
    --weights-report "$ART/$arm-trainer-weights.json" \
    --optimizer-report "$ART/$arm-optimizer.json" \
    > "$W/fit-$arm.log" 2> "$W/fit-$arm-time.log"
  local rc=$?
  set -e
  [ -s "$W/$arm.pjtw" ] &&
    gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  [ "$rc" -eq 0 ] || die "$arm fit failed rc=$rc"
  grep -q 'HOLDOUT_LOGLOSS' "$W/fit-$arm.log" ||
    die "$arm holdout result missing"
  "$W/venv/bin/python" - "$ART/$arm-optimizer.json" \
    "$ART/$arm-trainer-weights.json" "$arm" <<'PY'
import json
import sys

optimizer = json.load(open(sys.argv[1]))
weights = json.load(open(sys.argv[2]))
arm = sys.argv[3]
if not optimizer.get("success"):
    raise SystemExit(f"{arm}: optimizer did not converge")
if weights["split"]["holdout_weighted"] is not False:
    raise SystemExit(f"{arm}: holdout was weighted")
uniform = weights["optimizer"]["uniform_after_normalization"]
sw_used = weights["optimizer"]["sw_all_used"]
if arm == "control" and (uniform is not True or sw_used is not False):
    raise SystemExit("CONTROL did not take exact legacy unweighted path")
if arm == "treatment" and (uniform is not False or sw_used is not True):
    raise SystemExit("TREATMENT did not activate sample weighting")
PY
  say "  $arm fit converged"
}

fit_arm control 1
[ "$(sha256sum "$W/control.pjtw" | awk '{print $1}')" = "$SOURCE_MODEL_SHA" ] ||
  die "all-ones CONTROL failed byte-level TURNOVER reproduction"
say "  CONTROL reproduces historical TURNOVER model byte-for-byte"
fit_arm treatment "$FAILED_WEIGHT"

phase publish-certificate
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" \
  "$EXPECTED_SOURCE_JOB" "$EXPECTED_SOURCE_ATTEMPT" "$SOURCE_MODEL_SHA" \
  "$F2M_MODEL_SHA" "$FAILED_WEIGHT" "$HOLDOUT" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

w, art = map(Path, sys.argv[1:3])
code, source_job, source_attempt, source_model, warm_start = sys.argv[3:8]
failed_weight = float(sys.argv[8])
holdout = int(sys.argv[9])
arms = {}
for arm, name in (("control", "UNWEIGHTED"), ("treatment", "FAILED_X2")):
    fit_log = (w / f"fit-{arm}.log").read_text(errors="replace")
    match = re.search(r"HOLDOUT_LOGLOSS[ =:]+([0-9.]+)", fit_log)
    arms[name] = {
        "model_sha256": hashlib.sha256(
            (w / f"{arm}.pjtw").read_bytes()
        ).hexdigest(),
        "optimizer": json.load(open(art / f"{arm}-optimizer.json")),
        "weight_construction": json.load(
            open(art / f"{arm}-weight-construction.json")
        ),
        "trainer_weights": json.load(
            open(art / f"{arm}-trainer-weights.json")
        ),
        "holdout_logloss_diagnostic_only": (
            float(match.group(1)) if match else None
        ),
    }
payload = {
    "schema": 1,
    "verdict": "L3_PURE_FAILED_CONVERSION_WEIGHTS_CAUSAL_AB_ARMS_READY",
    "code_sha": code,
    "source": {
        "job_id": source_job,
        "attempt_id": source_attempt,
        "corpus": "immutable TURNOVER 2M",
        "historical_model_sha256": source_model,
    },
    "warm_start": {"name": "F2M", "model_sha256": warm_start},
    "primary_contrast": "FAILED_X2 minus UNWEIGHTED",
    "design": {
        "single_factor": "train_failed_conversion_weight",
        "control_weight": 1.0,
        "treatment_weight": failed_weight,
        "same_records": True,
        "same_opening_split": True,
        "same_feature_matrix": True,
        "same_warm_start": True,
        "same_fit": True,
        "common_holdout_records": holdout,
        "holdout_weighted": False,
        "oversampling": False,
        "control_reproduced_historical_model": (
            arms["UNWEIGHTED"]["model_sha256"] == source_model
        ),
    },
    "arms": arms,
    "external_teacher_inputs": 0,
    "scientific_result": False,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(art / "VERDICT__L3_PURE_FAILED_CONVERSION_WEIGHTS_CAUSAL_AB_ARMS_READY").touch()
(art / "PROMOTION_AUTHORIZED__FALSE").touch()
(art / "AUTOMATIC_NEXT_JOB__NULL").touch()
for name, result in arms.items():
    print(
        f"  {name}: model={result['model_sha256']} "
        f"converged={result['optimizer']['success']} "
        f"sw_all={result['trainer_weights']['optimizer']['sw_all_used']}"
    )
PY
phase complete
say "L3_PURE_FAILED_CONVERSION_WEIGHTS_CAUSAL_AB_ARMS_READY promotion=false automatic_next_job=null"
