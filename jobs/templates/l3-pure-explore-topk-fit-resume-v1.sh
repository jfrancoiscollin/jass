#!/usr/bin/env bash
# L3-PURE — resume the two fits from authenticated home-1017 corpora.
#
# This job performs no self-play. It fetches the immutable failed 1017 result,
# verifies the four corpus hashes and source identity, deterministically rebuilds
# the opening-level split, then fits UNIFORM and TOPK3 with the preregistered
# common recipe. It does not measure strength or promote either arm.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${SOURCE_PREFIX:?}"; : "${EXPECTED_SOURCE_JOB:?}"
: "${EXPECTED_SOURCE_ATTEMPT:?}"; : "${EXPECTED_SOURCE_CODE_SHA:?}"
: "${UNIFORM_JNNW_GZ_SHA:?}"; : "${UNIFORM_JSM_GZ_SHA:?}"
: "${TOPK3_JNNW_GZ_SHA:?}"; : "${TOPK3_JSM_GZ_SHA:?}"
: "${PARENT_TRAIN_PREFIX:?}"; : "${EXPECTED_PARENT_TRAIN_JOB:?}"
: "${PARENT_ARTEFACT:?}"; : "${PARENT_MODEL_SHA:?}"; : "${PARENT_NAME:?}"

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

HOLDOUT_MOD=10
SPLIT_SEED=577215
L2=3e-5
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
CHUNK=20000
FIT_TIMEOUT=${FIT_TIMEOUT:-5400}
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
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in uniform topk3; do
          [ -f "$W/fit-$arm.log" ] &&
            printf 'fit_%s_lines=%s\n' "$arm" "$(wc -l < "$W/fit-$arm.log")"
          [ -f "$ART/$arm-optimizer.json" ] &&
            printf 'fit_%s_optimizer_report=present\n' "$arm"
        done
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
  restore_src
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
NCPU=$(nproc)
[ "$NCPU" -ge 12 ] || die "HOME requires at least 12 logical CPUs, got $NCPU"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -ge 20000 ] || die "need 20 GiB free, got ${DFA}M"
say "  sizing: nproc=$NCPU; zero self-play; two sequential 2M fits"
say "  runtime anchor: home-0966bis fit 2M ~=33 min; ETA 75-95 min total"
say "  per-fit timeout=${FIT_TIMEOUT}s"
monitor

phase pull-and-assert-pinned-sources
for f in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp \
         src/movegen.cpp src/movegen.hpp src/main.cpp \
         src/selfplay_exploration.hpp; do
  git show "$EXPECTED_CODE_SHA:$f" > "$f" ||
    die "cannot pull $f from $EXPECTED_CODE_SHA"
done
grep -q "g_emasks" src/scan_eval.cpp || die "archi: scan_eval without g_emasks"
grep -q "has_any_capture" src/search.cpp || die "archi: search without has_any_capture"
grep -q "has_any_capture" src/movegen.cpp || die "archi: movegen without has_any_capture"
grep -q "root_is_drawn" src/search.cpp || die "engine predates drawn-root fix"
say "  architecture guard passed at pinned SHA"

phase fetch-and-authenticate-1017
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_PREFIX" \
  --expected-state failed \
  --file artefacts/uniform.jnnw.gz=uniform.jnnw.gz \
  --file artefacts/uniform.jsm.gz=uniform.jsm.gz \
  --file artefacts/topk3.jnnw.gz=topk3.jnnw.gz \
  --file artefacts/topk3.jsm.gz=topk3.jsm.gz \
  --file artefacts/uniform-split.json=source-uniform-split.json \
  --file artefacts/topk3-split.json=source-topk3-split.json \
  --file artefacts/uniform-corpus-wdl.json=uniform-corpus-wdl.json \
  --file artefacts/topk3-corpus-wdl.json=topk3-corpus-wdl.json \
  --file artefacts/uniform-coverage.json=uniform-coverage.json \
  --file artefacts/topk3-coverage.json=topk3-coverage.json \
  --file artefacts/paired-generation-check.json=paired-generation-check.json \
  --out-dir "$IN" --report "$ART/verified-1017-inputs.json" \
  > "$W/fetch-1017.log" 2>&1

python3 - "$ART/verified-1017-inputs.json" "$EXPECTED_SOURCE_JOB" \
  "$EXPECTED_SOURCE_ATTEMPT" "$EXPECTED_SOURCE_CODE_SHA" \
  "$UNIFORM_JNNW_GZ_SHA" "$UNIFORM_JSM_GZ_SHA" \
  "$TOPK3_JNNW_GZ_SHA" "$TOPK3_JSM_GZ_SHA" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1]))
if (
    report.get("job_id") != sys.argv[2]
    or report.get("attempt_id") != sys.argv[3]
    or report.get("code_sha") != sys.argv[4]
    or report.get("result_state") != "failed"
    or report.get("exit_code") != 1
):
    raise SystemExit("1017 source identity/state mismatch")
expected = dict(zip(
    ("uniform.jnnw.gz", "uniform.jsm.gz", "topk3.jnnw.gz", "topk3.jsm.gz"),
    sys.argv[5:9],
))
actual = {item["local_name"]: item["sha256"] for item in report["files"]}
for name, digest in expected.items():
    if actual.get(name) != digest:
        raise SystemExit(f"1017 source hash mismatch for {name}")
PY
for arm in uniform topk3; do
  gunzip -c "$IN/$arm.jnnw.gz" > "$W/$arm.raw.jnnw"
  gunzip -c "$IN/$arm.jsm.gz" > "$W/$arm.raw.jsm"
  cp "$IN/$arm-corpus-wdl.json" "$ART/$arm-corpus-wdl.json"
  cp "$IN/$arm-coverage.json" "$ART/$arm-coverage.json"
done
cp "$IN/paired-generation-check.json" "$ART/paired-generation-check.json"
say "  1017 failed result authenticated; both 2M corpora restored"

phase fetch-and-authenticate-parent
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_TRAIN_PREFIX" \
  --file "artefacts/$PARENT_ARTEFACT=PARENT.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-parent.json" \
  > "$W/fetch-parent.log" 2>&1
python3 - "$ART/verified-parent.json" "$EXPECTED_PARENT_TRAIN_JOB" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit("parent source identity/state mismatch")
PY
gunzip -c "$IN/PARENT.pjtw.gz" > "$W/PARENT.pjtw"
[ "$(sha256sum "$W/PARENT.pjtw" | awk '{print $1}')" = "$PARENT_MODEL_SHA" ] ||
  die "parent model hash drift"

phase build-and-test
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1
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
say "  build, tests and 8cf witness passed"

phase reproduce-splits
for arm in uniform topk3; do
  python3 tools/selfplay_frontier.py split \
    --data "$W/$arm.raw.jnnw" --meta "$W/$arm.raw.jsm" \
    --out-data "$W/$arm.fit.jnnw" --out-meta "$W/$arm.fit.jsm" \
    --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
    --manifest "$ART/$arm-split.json" > "$W/$arm-split.log" 2>&1
done
python3 - "$IN/source-uniform-split.json" "$IN/source-topk3-split.json" \
  "$ART/uniform-split.json" "$ART/topk3-split.json" \
  "$ART/paired-split-check.json" <<'PY'
import json
import sys

su, st, ru, rt = (json.load(open(path)) for path in sys.argv[1:5])
if su != ru or st != rt:
    raise SystemExit("deterministic split reproduction drift")
for key in ("split_unit", "holdout_mod", "seed", "tail_is_holdout"):
    if ru.get(key) != rt.get(key):
        raise SystemExit(f"split contract mismatch for {key}")
for arm, manifest in (("uniform", ru), ("topk3", rt)):
    for key in ("train_openings", "holdout_openings", "train_records",
                "holdout_records"):
        if int(manifest.get(key, 0)) <= 0:
            raise SystemExit(f"{arm}: non-positive {key}")
payload = {
    "schema": 1,
    "same_split_contract": True,
    "opening_counts_are_treatment_outcomes": True,
    "uniform": ru,
    "topk3": rt,
}
with open(sys.argv[5], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
say "  source splits reproduced byte-for-byte; split contract valid"

for arm in uniform topk3; do
  phase "dump-features-$arm"
  HOLD=$("$W/venv/bin/python" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' \
    "$ART/$arm-split.json")
  [ "$HOLD" -gt 0 ] || die "$arm holdout missing"
  "$J" --dump-eval-features "$W/$arm.fit.jnnw" "$W/$arm.feat" \
    > "$W/$arm-features.log" 2>&1
  phase "fit-$arm"
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    /usr/bin/time -v timeout "$FIT_TIMEOUT" \
    "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
    --data "$W/$arm.fit.jnnw" --feat "$W/$arm.feat" --out "$W/$arm.pjtw" \
    --target wdl --loss logistic --color-fold --tempo-stage \
    --warm-start "$W/PARENT.pjtw" --holdout-count "$HOLD" \
    --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
    --optimizer-report "$ART/$arm-optimizer.json" \
    > "$W/fit-$arm.log" 2> "$W/fit-$arm-time.log"
  FIT_RC=$?
  set -e
  [ -s "$W/$arm.pjtw" ] && gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  [ "$FIT_RC" -eq 0 ] || die "$arm fit failed rc=$FIT_RC"
  grep -q 'HOLDOUT_LOGLOSS' "$W/fit-$arm.log" ||
    die "$arm holdout result missing"
  "$W/venv/bin/python" - "$ART/$arm-optimizer.json" <<'PY' ||
import json
import sys
if not json.load(open(sys.argv[1])).get("success"):
    raise SystemExit(1)
PY
    die "$arm optimiser did not converge"
  say "  $arm fit converged"
done

phase publish-certificate
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" \
  "$EXPECTED_SOURCE_JOB" "$EXPECTED_SOURCE_ATTEMPT" "$PARENT_NAME" \
  "$PARENT_MODEL_SHA" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

w, art = map(Path, sys.argv[1:3])
code_sha, source_job, source_attempt, parent_name, parent_sha = sys.argv[3:8]
arms = {}
for arm in ("uniform", "topk3"):
    optimizer = json.load(open(art / f"{arm}-optimizer.json"))
    split = json.load(open(art / f"{arm}-split.json"))
    coverage = json.load(open(art / f"{arm}-coverage.json"))
    wdl = json.load(open(art / f"{arm}-corpus-wdl.json"))
    log = (w / f"fit-{arm}.log").read_text(errors="replace")
    match = re.search(r"HOLDOUT_LOGLOSS[ =:]+([0-9.]+)", log)
    arms[arm] = {
        "model_sha256": hashlib.sha256((w / f"{arm}.pjtw").read_bytes()).hexdigest(),
        "optimizer": optimizer,
        "split": split,
        "coverage": coverage,
        "wdl": wdl,
        "holdout_logloss_diagnostic_only": (
            float(match.group(1)) if match else None
        ),
    }
payload = {
    "schema": 1,
    "verdict": "L3_PURE_TOPK_CAUSAL_AB_ARMS_READY_FROM_1017_CORPORA",
    "code_sha": code_sha,
    "source": {
        "job_id": source_job,
        "attempt_id": source_attempt,
        "failed_only_after_corpora_and_splits": True,
    },
    "parent": {"name": parent_name, "model_sha256": parent_sha},
    "primary_contrast": "TOPK3 minus UNIFORM",
    "arms": arms,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n"
)
(art / "VERDICT__L3_PURE_TOPK_CAUSAL_AB_ARMS_READY_FROM_1017_CORPORA").touch()
(art / "PROMOTION_AUTHORIZED__FALSE").touch()
(art / "AUTOMATIC_NEXT_JOB__NULL").touch()
for arm, result in arms.items():
    print(
        f"  {arm}: model={result['model_sha256']} "
        f"converged={result['optimizer']['success']}"
    )
PY
phase complete
say "L3_PURE_TOPK_CAUSAL_AB_ARMS_READY_FROM_1017_CORPORA promotion=false automatic_next_job=null"
