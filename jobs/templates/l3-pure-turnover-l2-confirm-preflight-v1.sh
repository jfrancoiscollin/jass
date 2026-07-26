#!/usr/bin/env bash
# L3-PURE: preflight for the independent confirmation of the L2_1E5 arm.
#
# Authenticates the home-0987 directional certificate and the immutable models
# it names, then builds and certifies a fresh independent opening pool disjoint
# from every pool used so far, including the L2 screen pool itself.
#
# No fit, no generation, no promotion. It authorises exactly one follow-up: the
# confirmation readout.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${SCREEN_EVAL_PREFIX:?}"
: "${EXPECTED_SCREEN_EVAL_JOB:?}"; : "${SCREEN_PREFLIGHT_PREFIX:?}"
: "${EXPECTED_SCREEN_PREFLIGHT_JOB:?}"; : "${TRAIN_PREFIX:?}"
: "${EXPECTED_TRAIN_JOB:?}"; : "${TURNOVER_TRAIN_PREFIX:?}"
: "${EXPECTED_TURNOVER_TRAIN_JOB:?}"; : "${TURNOVER_CONFIRM_PREFIX:?}"
: "${EXPECTED_TURNOVER_CONFIRM_JOB:?}"; : "${REPLAY25_PREFLIGHT_PREFIX:?}"
: "${EXPECTED_REPLAY25_PREFLIGHT_JOB:?}"; : "${M1_PREFIX:?}"
: "${EXPECTED_M1_JOB:?}"

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
MON=""
monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
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
  rm -f "$W"/*.pjtw "$W"/*.jnnw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

NOPEN=1000
OPENING_CANDIDATES=4000
OPENING_SEED=2718281
CACHE_MB=128
CANDIDATE_MODEL_SHA="27cf9bedf20d00bbcc106a52ad183990f8df131362c4590fc319cc708464ff49"
CONTROL_MODEL_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
F2M_MODEL_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
SCREEN_OPENING_SHA="e7b89a5e3feade8919c8a498f424084deb0a2128c1712c9ca0a9547cf22b6df2"
CHAMPION_CODE_SHA="0c1e04a9574fcd87977f62fe5bd6d71c60c72265"

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
[ "$(awk '/MemAvailable:/{print int($2/1024)}' /proc/meminfo)" -ge 3500 ] ||
  die "need 3.5 GiB available RAM"
git diff --quiet "$CHAMPION_CODE_SHA" HEAD -- src pattern_jass/tools ||
  die "engine semantics changed since the repaired champion gate"
monitor

phase fetch-and-authenticate-trigger
python3 jobs/tools/fetch_result_files.py --prefix "$SCREEN_EVAL_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=screen-evaluation.json \
  --out-dir "$IN" --report "$ART/verified-screen-evaluation.json" \
  > "$W/fetch-screen-evaluation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$SCREEN_PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=screen-preflight.json \
  --file artefacts/turnover-l2-eval-openings.fen=prior-turnover-l2.fen \
  --out-dir "$IN" --report "$ART/verified-screen-preflight.json" \
  > "$W/fetch-screen-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TRAIN_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=l2-training.json \
  --file artefacts/turnover-l2-1e5.pjtw.gz=L2_1E5.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-l2-training.json" \
  > "$W/fetch-l2-training.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-training.json \
  --file artefacts/turnover1to1.pjtw.gz=CONTROL.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-turnover-training.json" \
  > "$W/fetch-turnover-training.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$REPLAY25_PREFLIGHT_PREFIX" \
  --file artefacts/replay25-eval-openings.fen=prior-replay25.fen \
  --out-dir "$IN" --report "$ART/verified-replay25-preflight.json" \
  > "$W/fetch-replay25-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_CONFIRM_PREFIX" \
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
  --file artefacts/f2m.pjtw.gz=F2M.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-m1-source.json" \
  > "$W/fetch-m1.log" 2>&1

for spec in \
  "verified-screen-evaluation.json:$EXPECTED_SCREEN_EVAL_JOB" \
  "verified-screen-preflight.json:$EXPECTED_SCREEN_PREFLIGHT_JOB" \
  "verified-l2-training.json:$EXPECTED_TRAIN_JOB" \
  "verified-turnover-training.json:$EXPECTED_TURNOVER_TRAIN_JOB" \
  "verified-replay25-preflight.json:$EXPECTED_REPLAY25_PREFLIGHT_JOB" \
  "verified-turnover-confirmation.json:$EXPECTED_TURNOVER_CONFIRM_JOB" \
  "verified-m1-source.json:$EXPECTED_M1_JOB"; do
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

python3 - "$IN/screen-evaluation.json" "$CANDIDATE_MODEL_SHA" \
  "$CONTROL_MODEL_SHA" "$F2M_MODEL_SHA" "$SCREEN_OPENING_SHA" <<'PY'
import json
import sys

screen = json.load(open(sys.argv[1]))
candidate_sha, control_sha, f2m_sha, pool_sha = sys.argv[2:]
training = screen.get("training_summary", {})
guard = screen.get("guardrails", {}).get("L2_1E5", {})
if screen.get("verdict") != "TURNOVER_L2_SCREEN_DIRECTIONAL_CONFIRMATION_REVIEW":
    raise SystemExit("screen verdict is not the directional certificate")
if screen.get("recommendation") != "independent_confirmation_of_directional_l2_arms":
    raise SystemExit("screen recommendation mismatch")
if screen.get("directional_arms") != ["L2_1E5"] or screen.get("confirmed_leads") != []:
    raise SystemExit("screen directional arm set mismatch")
if screen.get("recommended_l2_arm") != "L2_1E5":
    raise SystemExit("screen recommended arm mismatch")
if screen.get("promotion_authorized") is not False:
    raise SystemExit("screen must not authorise promotion")
if screen.get("automatic_next_job") is not None:
    raise SystemExit("screen must not chain automatically")
if guard.get("all_pass") is not True or not all(guard.get("checks", {}).values()):
    raise SystemExit("screen guardrails did not all pass")
if training.get("arms", {}).get("L2_1E5", {}).get("model_sha256") != candidate_sha:
    raise SystemExit("candidate model identity drift")
if training.get("control", {}).get("model_sha256") != control_sha:
    raise SystemExit("control model identity drift")
if training.get("parent_model_sha256") != f2m_sha:
    raise SystemExit("parent identity drift")
if screen.get("opening_manifest", {}).get("sha256") != pool_sha:
    raise SystemExit("screen opening-pool identity drift")
for view in ("q00", "native"):
    if screen["primary_checks"]["L2_1E5"][view] != {
        "positive_point_estimate": True,
        "superiority_established": False,
        "regression_not_established": True,
    }:
        raise SystemExit("screen primary checks are not directional")
PY
say "  trigger ✓ : home-0987 directionnel, L2_1E5 seul bras, garde-fous verts"

phase verify-immutable-models
for model in L2_1E5 CONTROL F2M; do
  gunzip -c "$IN/$model.pjtw.gz" > "$W/$model.pjtw"
done
[ "$(sha256sum "$W/L2_1E5.pjtw" | awk '{print $1}')" = "$CANDIDATE_MODEL_SHA" ] ||
  die "L2_1E5 model hash drift"
[ "$(sha256sum "$W/CONTROL.pjtw" | awk '{print $1}')" = "$CONTROL_MODEL_SHA" ] ||
  die "control model hash drift"
[ "$(sha256sum "$W/F2M.pjtw" | awk '{print $1}')" = "$F2M_MODEL_SHA" ] ||
  die "F2M model hash drift"
[ "$(sha256sum "$IN/prior-turnover-l2.fen" | awk '{print $1}')" = \
  "$SCREEN_OPENING_SHA" ] || die "screen opening pool hash drift"

phase build-and-test-8cf-engine
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
cmake --build "$W/build8" -j4 --target jass jass_tests > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J="$W/build8/jass"
[ "$("$J" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
[ "$("$J" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
  die "tablebase-root witness failed"

phase independent-confirmation-pool
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
  --generator-seed "$OPENING_SEED"
)
python3 jobs/tools/select_independent_opening_pool.py "${opening_args[@]}" \
  --out "$ART/turnover-l2-confirm-openings.fen" \
  --manifest "$ART/turnover-l2-confirm-openings.json" \
  > "$W/select-openings-a.log" 2>&1
opening_args[1]="$W/open-candidates-b.fen"
python3 jobs/tools/select_independent_opening_pool.py "${opening_args[@]}" \
  --out "$W/turnover-l2-confirm-openings-repeat.fen" \
  --manifest "$W/turnover-l2-confirm-openings-repeat.json" \
  > "$W/select-openings-b.log" 2>&1
cmp -s "$ART/turnover-l2-confirm-openings.fen" \
  "$W/turnover-l2-confirm-openings-repeat.fen" ||
  die "selected confirmation pool is not byte-identical"
[ "$(wc -l < "$ART/turnover-l2-confirm-openings.fen")" -eq "$NOPEN" ] ||
  die "confirmation pool count drift"
[ "$(sha256sum "$ART/turnover-l2-confirm-openings.fen" | awk '{print $1}')" != \
  "$SCREEN_OPENING_SHA" ] || die "confirmation pool equals the screen pool"

phase publish-preflight-certificate
python3 - "$W" "$ART" "$EXPECTED_CODE_SHA" "$EXPECTED_SCREEN_EVAL_JOB" \
  "$OPENING_SEED" "$CANDIDATE_MODEL_SHA" "$CONTROL_MODEL_SHA" \
  "$F2M_MODEL_SHA" <<'PY'
import hashlib
import json
import os
import pathlib
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha, trigger_job, seed = sys.argv[3:6]
candidate_sha, control_sha, f2m_sha = sys.argv[6:]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


openings = json.loads((art / "turnover-l2-confirm-openings.json").read_text())
if openings.get("overlap_records") != 0:
    raise SystemExit("confirmation pool overlaps a prior pool")
if openings.get("records") != 1000 or openings.get("unique_records") != 1000:
    raise SystemExit("confirmation pool is not 1000 unique openings")

payload = {
    "schema": 1,
    "verdict": "TURNOVER_L2_CONFIRM_PREFLIGHT_READY",
    "code_sha": code_sha,
    "trigger": {"job": trigger_job, "verdict": "TURNOVER_L2_SCREEN_DIRECTIONAL_CONFIRMATION_REVIEW"},
    "experiment_variant": "TURNOVER_1_1_L2_CONFIRMATION",
    "candidate": "L2_1E5",
    "candidate_l2": 1e-05,
    "candidate_model_sha256": candidate_sha,
    "causal_control": "L2_3E5_CONTROL",
    "control_model_sha256": control_sha,
    "champion": "F2M",
    "champion_model_sha256": f2m_sha,
    "confirmation_openings": {
        "seed": int(seed),
        "sha256": sha(art / "turnover-l2-confirm-openings.fen"),
        "candidate_sha256": sha(w / "open-candidates-a.fen"),
        "manifest": openings,
    },
    "resource_preflight": {
        "nproc": os.cpu_count(),
        "home_confirmation_eta_minutes": [80, 110],
        "games_per_cell": 2000,
        "cells": 4,
    },
    "new_generation_performed": False,
    "external_teacher_inputs": 0,
    "confirmation_authorized": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "turnover-l2-confirm-preflight.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__TURNOVER_L2_CONFIRM_PREFLIGHT_READY").write_text(
    "TURNOVER_L2_CONFIRM_PREFLIGHT_READY\n"
)
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
print("pool_sha256=" + payload["confirmation_openings"]["sha256"])
print("candidate_sha256=" + payload["confirmation_openings"]["candidate_sha256"])
PY
say "  pool indépendant ✓ : $(sha256sum "$ART/turnover-l2-confirm-openings.fen" | awk '{print $1}')"
say "  candidats ✓ : $(sha256sum "$W/open-candidates-a.fen" | awk '{print $1}')"
phase complete
say "TURNOVER_L2_CONFIRM_PREFLIGHT_READY confirmation=true promotion=false automatic_next_job=null"
