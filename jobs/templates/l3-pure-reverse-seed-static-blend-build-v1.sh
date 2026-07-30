#!/usr/bin/env bash
# Build and certify one fixed 50/50 PJTW blend:
# TURNOVER champion + the positive reverse-seed treatment.
#
# This job performs no training and no force selection.  It authenticates the
# two immutable parents, blends once, and checks static-evaluation linearity on
# a fixed legal probe.  It cannot promote or launch a readout.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${CHAMPION_PREFIX:?}"; : "${CHAMPION_JOB:?}"
: "${CHAMPION_ATTEMPT:?}"; : "${CHAMPION_CODE_SHA:?}"; : "${CHAMPION_SHA:?}"
: "${REVERSE_ARMS_PREFIX:?}"; : "${REVERSE_ARMS_JOB:?}"
: "${REVERSE_ARMS_ATTEMPT:?}"; : "${REVERSE_ARMS_CODE_SHA:?}"
: "${REVERSE_READOUT_PREFIX:?}"; : "${REVERSE_READOUT_JOB:?}"
: "${REVERSE_READOUT_ATTEMPT:?}"; : "${REVERSE_READOUT_CODE_SHA:?}"
: "${REVERSE_CONTROL_SHA:?}"; : "${REVERSE_TREATMENT_SHA:?}"

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
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
MON=""
monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
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
  rm -rf "$W/build8" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.pjtw "$W"/probe.fen 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

ALPHA_CHAMPION="${ALPHA_CHAMPION:-0.5}"
PROBE_POSITIONS="${PROBE_POSITIONS:-64}"
MAX_STATIC_RESIDUAL="${MAX_STATIC_RESIDUAL:-8.0}"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$ALPHA_CHAMPION" = 0.5 ] || die "alpha drift"
[ "$PROBE_POSITIONS" -eq 64 ] || die "probe-size drift"
[ "$MAX_STATIC_RESIDUAL" = 8.0 ] || die "probe-tolerance drift"
[ "$(nproc)" -ge 16 ] || die "CPX62 requires at least 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 8000 ] ||
  die "need 8 GiB free"
monitor

stage local-tests
python3 -m py_compile tools/blend_pjtw.py \
  jobs/tools/l3_static_blend_probe.py \
  jobs/tools/l3_static_blend_readout.py
python3 jobs/tests/test_blend_pjtw.py > "$W/test-blend.log" 2>&1 ||
  die "blend unit tests red"
python3 jobs/tests/test_l3_static_blend_probe.py \
  > "$W/test-probe.log" 2>&1 || die "probe unit tests red"
python3 jobs/tests/test_l3_static_blend_readout.py \
  > "$W/test-readout.log" 2>&1 || die "readout unit tests red"

stage fetch-and-authenticate-parents
python3 jobs/tools/fetch_result_files.py --prefix "$CHAMPION_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=champion-summary.json \
  --file artefacts/turnover1to1.pjtw.gz=champion.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-champion.json" \
  > "$W/fetch-champion.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$REVERSE_ARMS_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=reverse-arms-summary.json \
  --file artefacts/treatment.pjtw.gz=reverse-treatment.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-reverse-arms.json" \
  > "$W/fetch-reverse-arms.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$REVERSE_READOUT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=reverse-readout-summary.json \
  --out-dir "$IN" --report "$ART/verified-reverse-readout.json" \
  > "$W/fetch-reverse-readout.log" 2>&1

python3 - "$ART/verified-champion.json" "$ART/verified-reverse-arms.json" \
  "$ART/verified-reverse-readout.json" "$IN/reverse-arms-summary.json" \
  "$IN/reverse-readout-summary.json" <<'PY'
import json
import os
import sys

champion_report, arms_report, readout_report, arms, readout = (
    json.load(open(path, encoding="utf-8")) for path in sys.argv[1:6]
)

def require(condition, message):
    if not condition:
        raise SystemExit(message)

for report, identity, label in (
    (
        champion_report,
        (
            os.environ["CHAMPION_JOB"],
            os.environ["CHAMPION_ATTEMPT"],
            os.environ["CHAMPION_CODE_SHA"],
        ),
        "champion",
    ),
    (
        arms_report,
        (
            os.environ["REVERSE_ARMS_JOB"],
            os.environ["REVERSE_ARMS_ATTEMPT"],
            os.environ["REVERSE_ARMS_CODE_SHA"],
        ),
        "reverse arms",
    ),
    (
        readout_report,
        (
            os.environ["REVERSE_READOUT_JOB"],
            os.environ["REVERSE_READOUT_ATTEMPT"],
            os.environ["REVERSE_READOUT_CODE_SHA"],
        ),
        "reverse readout",
    ),
):
    require(
        report.get("job_id") == identity[0]
        and report.get("attempt_id") == identity[1]
        and report.get("code_sha") == identity[2]
        and report.get("result_state") == "completed"
        and report.get("exit_code") == 0,
        f"{label} identity/state mismatch",
    )

design = arms.get("design", {})
require(
    arms.get("schema") == 1
    and arms.get("verdict") == "L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY"
    and arms.get("code_sha") == os.environ["REVERSE_ARMS_CODE_SHA"]
    and arms.get("primary_contrast")
    == "HARD_SEED_SELFPLAY minus MATCHED_RANDOM_SEED_SELFPLAY"
    and design.get("single_factor") == "seed_root_selection_policy"
    and design.get("same_parent") is True
    and design.get("same_search_policy") is True
    and design.get("same_shard_seeds") is True
    and design.get("same_split_contract") is True
    and design.get("same_fit") is True
    and arms.get("arms", {}).get("control", {}).get("model_sha256")
    == os.environ["REVERSE_CONTROL_SHA"]
    and arms.get("arms", {}).get("treatment", {}).get("model_sha256")
    == os.environ["REVERSE_TREATMENT_SHA"],
    "reverse arms certificate mismatch",
)
summed = readout.get("force_views_summed", {})
require(
    readout.get("schema") == 1
    and readout.get("verdict")
    == "L3_PURE_REVERSE_SEED_ABOVE_MATCHED_CONTROL_IC95"
    and readout.get("code_sha") == os.environ["REVERSE_READOUT_CODE_SHA"]
    and readout.get("models", {}).get("control_sha256")
    == os.environ["REVERSE_CONTROL_SHA"]
    and readout.get("models", {}).get("treatment_sha256")
    == os.environ["REVERSE_TREATMENT_SHA"]
    and summed.get("n") == 6000
    and summed.get("ci95", [0])[0] > 0.5
    and readout.get("scientific_result") is True
    and readout.get("promotion_authorized") is False
    and readout.get("automatic_next_job", "missing") is None,
    "reverse readout evidence mismatch",
)
PY

gunzip -c "$IN/champion.pjtw.gz" > "$W/CHAMPION.pjtw"
gunzip -c "$IN/reverse-treatment.pjtw.gz" > "$W/REVERSE.pjtw"
[ "$(sha256sum "$W/CHAMPION.pjtw" | awk '{print $1}')" = "$CHAMPION_SHA" ] ||
  die "champion hash drift"
[ "$(sha256sum "$W/REVERSE.pjtw" | awk '{print $1}')" = \
  "$REVERSE_TREATMENT_SHA" ] || die "reverse treatment hash drift"

stage build-fixed-blend
python3 tools/blend_pjtw.py \
  --parent-a "$W/CHAMPION.pjtw" --parent-b "$W/REVERSE.pjtw" \
  --alpha-a "$ALPHA_CHAMPION" --out "$W/BLEND50.pjtw" \
  --report "$ART/blend-construction.json" > "$W/blend.log" 2>&1
python3 - "$ART/blend-construction.json" <<'PY'
import json
import os
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
if (
    report.get("mode") != "convex-weight-interpolation"
    or report.get("alpha_a") != 0.5
    or report.get("alpha_b") != 0.5
    or report.get("parent_a_sha256") != os.environ["CHAMPION_SHA"]
    or report.get("parent_b_sha256") != os.environ["REVERSE_TREATMENT_SHA"]
    or report.get("saturation", {}).get("total") != 0
    or report.get("quantization", {}).get("max_abs_error", 99) > 0.5
    or report.get("weights_changed_from_a", 0) <= 0
    or report.get("weights_changed_from_b", 0) <= 0
    or report.get("atomic_write") is not True
):
    raise SystemExit("blend construction certificate mismatch")
PY

stage build-static-probe-engine
for src in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp \
  src/movegen.cpp src/movegen.hpp; do
  git show "$EXPECTED_CODE_SHA:$src" > "$src" ||
    die "cannot pin $src from expected SHA"
done
grep -q "g_emasks" src/scan_eval.cpp ||
  die "arch guard: scan_eval missing g_emasks"
grep -q "has_any_capture" src/search.cpp ||
  die "arch guard: search missing has_any_capture"
grep -q "has_any_capture" src/movegen.cpp ||
  die "arch guard: movegen missing has_any_capture"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j8 --target jass jass_tests \
  > "$W/build8.log" 2>&1
ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"
[ -x "$J8" ] || die "missing jass probe binary"

awk -v limit="$PROBE_POSITIONS" \
  '!/^#/ && NF {print $1; n++; if (n == limit) exit}' \
  data/dilf_combinations.fen > "$W/probe.fen"
python3 jobs/tools/l3_static_blend_probe.py \
  --jass "$J8" --parent-a "$W/CHAMPION.pjtw" \
  --parent-b "$W/REVERSE.pjtw" --blend "$W/BLEND50.pjtw" \
  --alpha-a "$ALPHA_CHAMPION" --fens "$W/probe.fen" \
  --expected-positions "$PROBE_POSITIONS" \
  --max-abs-residual "$MAX_STATIC_RESIDUAL" \
  --out "$ART/static-linearity-probe.json" > "$W/probe.log" 2>&1

stage publish-certificate
BLEND_SHA="$(sha256sum "$W/BLEND50.pjtw" | awk '{print $1}')"
gzip -n -c "$W/BLEND50.pjtw" > "$ART/blend50.pjtw.gz"
python3 - "$ART/blend-construction.json" \
  "$ART/static-linearity-probe.json" "$ART/JASS_CONTROL_SUMMARY.json" \
  "$BLEND_SHA" <<'PY'
import json
import os
import pathlib
import sys

construction_path, probe_path, out_path = map(pathlib.Path, sys.argv[1:4])
blend_sha = sys.argv[4]
construction = json.load(construction_path.open(encoding="utf-8"))
probe = json.load(probe_path.open(encoding="utf-8"))
payload = {
    "schema": 1,
    "verdict": "L3_PURE_REVERSE_SEED_BLEND50_READY",
    "code_sha": os.environ["EXPECTED_CODE_SHA"],
    "primary_contrast":
    "BLEND50(TURNOVER,REVERSE_SEED) minus TURNOVER",
    "sources": {
        "champion": {
            "job_id": os.environ["CHAMPION_JOB"],
            "attempt_id": os.environ["CHAMPION_ATTEMPT"],
            "code_sha": os.environ["CHAMPION_CODE_SHA"],
            "prefix": os.environ["CHAMPION_PREFIX"],
        },
        "reverse_seed_arms": {
            "job_id": os.environ["REVERSE_ARMS_JOB"],
            "attempt_id": os.environ["REVERSE_ARMS_ATTEMPT"],
            "code_sha": os.environ["REVERSE_ARMS_CODE_SHA"],
            "prefix": os.environ["REVERSE_ARMS_PREFIX"],
        },
        "reverse_seed_readout": {
            "job_id": os.environ["REVERSE_READOUT_JOB"],
            "attempt_id": os.environ["REVERSE_READOUT_ATTEMPT"],
            "code_sha": os.environ["REVERSE_READOUT_CODE_SHA"],
            "prefix": os.environ["REVERSE_READOUT_PREFIX"],
        },
    },
    "models": {
        "champion_sha256": os.environ["CHAMPION_SHA"],
        "reverse_seed_sha256": os.environ["REVERSE_TREATMENT_SHA"],
        "blend_sha256": blend_sha,
    },
    "construction": {
        "mode": "convex-weight-interpolation",
        "single_factor": "static_pjtw_weight_blend",
        "alpha_champion": 0.5,
        "alpha_reverse_seed": 0.5,
        "training_records": 0,
        "self_play_games": 0,
        "report": construction,
    },
    "static_linearity_probe": probe,
    "scientific_result": False,
    "readout_authorized": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
out_path.write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
printf '%s\n' L3_PURE_REVERSE_SEED_BLEND50_READY \
  > "$ART/VERDICT__L3_PURE_REVERSE_SEED_BLEND50_READY"
printf '%s\n' SCIENTIFIC_RESULT__FALSE > "$ART/SCIENTIFIC_RESULT__FALSE"
printf '%s\n' READOUT_AUTHORIZED__TRUE > "$ART/READOUT_AUTHORIZED__TRUE"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE \
  > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
touch "$ART/MODEL_SHA256__BLEND50__$BLEND_SHA"
say "blend_sha256=$BLEND_SHA alpha_champion=0.5 alpha_reverse_seed=0.5"

stage complete
say "L3_PURE_REVERSE_SEED_BLEND50_READY scientific_result=false promotion=false automatic_next_job=null"
