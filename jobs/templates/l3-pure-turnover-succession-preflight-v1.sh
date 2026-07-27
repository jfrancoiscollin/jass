#!/usr/bin/env bash
# L3-PURE: preflight for the TURNOVER champion-succession gate.
#
# Authenticates the home-0993 certificate that established TURNOVER over F2M,
# then builds and certifies a fresh independent opening pool disjoint from the
# fourteen pools already spent.
#
# No fit, no generation, no promotion. It authorises exactly one follow-up: the
# succession gate, which alone may recommend a champion change to human review.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${DOSE_READOUT_PREFIX:?}"
: "${EXPECTED_DOSE_READOUT_JOB:?}"; : "${DOSE_PREFLIGHT_PREFIX:?}"
: "${EXPECTED_DOSE_PREFLIGHT_JOB:?}"; : "${L2_CONFIRM_PREFLIGHT_PREFIX:?}"
: "${EXPECTED_L2_CONFIRM_PREFLIGHT_JOB:?}"; : "${TURNOVER_TRAIN_PREFIX:?}"
: "${EXPECTED_TURNOVER_TRAIN_JOB:?}"; : "${TURNOVER_CONFIRM_PREFIX:?}"
: "${EXPECTED_TURNOVER_CONFIRM_JOB:?}"; : "${REPLAY25_PREFLIGHT_PREFIX:?}"
: "${EXPECTED_REPLAY25_PREFLIGHT_JOB:?}"; : "${L2_PREFLIGHT_PREFIX:?}"
: "${EXPECTED_L2_PREFLIGHT_JOB:?}"; : "${M1_PREFIX:?}"
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

NOPEN=1500
OPENING_CANDIDATES=6000
OPENING_SEED=1618034
CACHE_MB=128
TURNOVER_MODEL_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
F2M_MODEL_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
L2_CONFIRM_POOL_SHA="71dc575eb6930718b1f2762c4adcd1db479b2c41abbbf00b417772e7d6f53043"
DOSE_POOL_SHA="17544078f6e32ec714302dc71aa68c97b34f572fd3205a376b2c868a40095148"
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
python3 jobs/tools/fetch_result_files.py --prefix "$DOSE_READOUT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=dose-readout.json \
  --out-dir "$IN" --report "$ART/verified-dose-readout.json" \
  > "$W/fetch-dose-readout.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$DOSE_PREFLIGHT_PREFIX" \
  --file artefacts/replay75-eval-openings.fen=prior-replay75.fen \
  --out-dir "$IN" --report "$ART/verified-dose-preflight.json" \
  > "$W/fetch-dose-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$L2_CONFIRM_PREFLIGHT_PREFIX" \
  --file artefacts/turnover-l2-confirm-openings.fen=prior-l2-confirm.fen \
  --out-dir "$IN" --report "$ART/verified-l2-confirm-preflight.json" \
  > "$W/fetch-prior-l2-confirm.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$L2_PREFLIGHT_PREFIX" \
  --file artefacts/turnover-l2-eval-openings.fen=prior-turnover-l2.fen \
  --out-dir "$IN" --report "$ART/verified-l2-preflight.json" \
  > "$W/fetch-prior-l2.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$REPLAY25_PREFLIGHT_PREFIX" \
  --file artefacts/replay25-eval-openings.fen=prior-replay25.fen \
  --out-dir "$IN" --report "$ART/verified-replay25-preflight.json" \
  > "$W/fetch-prior-replay25.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-training.json \
  --file artefacts/turnover1to1.pjtw.gz=TURNOVER.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-turnover-training.json" \
  > "$W/fetch-turnover-training.log" 2>&1
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
  "verified-dose-readout.json:$EXPECTED_DOSE_READOUT_JOB" \
  "verified-dose-preflight.json:$EXPECTED_DOSE_PREFLIGHT_JOB" \
  "verified-l2-confirm-preflight.json:$EXPECTED_L2_CONFIRM_PREFLIGHT_JOB" \
  "verified-l2-preflight.json:$EXPECTED_L2_PREFLIGHT_JOB" \
  "verified-replay25-preflight.json:$EXPECTED_REPLAY25_PREFLIGHT_JOB" \
  "verified-turnover-training.json:$EXPECTED_TURNOVER_TRAIN_JOB" \
  "verified-turnover-confirmation.json:$EXPECTED_TURNOVER_CONFIRM_JOB" \
  "verified-m1-source.json:$EXPECTED_M1_JOB"; do
  report="${spec%%:*}"
  job="${spec#*:}"
  python3 - "$ART/$report" "$job" <<'XPY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
XPY
done

python3 - "$IN/dose-readout.json" "$IN/turnover-training.json" \
  "$TURNOVER_MODEL_SHA" "$F2M_MODEL_SHA" <<'XPY'
import json
import sys

readout = json.load(open(sys.argv[1]))
training = json.load(open(sys.argv[2]))
turnover_sha, f2m_sha = sys.argv[3:]

if readout.get("champion_question") != "TURNOVER50_BEATS_F2M_CHAMPION_REVIEW":
    raise SystemExit("dose readout did not establish TURNOVER over F2M")
if readout.get("promotion_authorized") is not False:
    raise SystemExit("dose readout must not authorise promotion")
if readout.get("automatic_next_job") is not None:
    raise SystemExit("dose readout must not chain automatically")
cell = readout.get("combined_force", {}).get("TURNOVER_vs_F2M", {})
checks = readout.get("combined_checks", {}).get("TURNOVER_vs_F2M", {})
if int(cell.get("n", 0)) != 5000:
    raise SystemExit("champion cell is not the preregistered 5000 games")
if checks.get("superiority_established") is not True:
    raise SystemExit("champion cell does not establish superiority")
if float(cell.get("ci_low", 0)) <= 0.5:
    raise SystemExit("champion cell lower bound does not clear 50 percent")
if training.get("model_sha256") != turnover_sha:
    raise SystemExit("TURNOVER model identity drift")
if training.get("parent_model_sha256") != f2m_sha:
    raise SystemExit("parent identity drift")
if training.get("experiment_variant") != "TURNOVER_1_1":
    raise SystemExit("TURNOVER corpus identity drift")
XPY
say "  trigger ✓ : home-0993 établit TURNOVER > F2M à n=5000"

phase verify-immutable-models
for model in TURNOVER F2M; do
  gunzip -c "$IN/$model.pjtw.gz" > "$W/$model.pjtw"
done
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_MODEL_SHA" ] ||
  die "TURNOVER model hash drift"
[ "$(sha256sum "$W/F2M.pjtw" | awk '{print $1}')" = "$F2M_MODEL_SHA" ] ||
  die "F2M model hash drift"
[ "$(sha256sum "$IN/prior-l2-confirm.fen" | awk '{print $1}')" = \
  "$L2_CONFIRM_POOL_SHA" ] || die "L2 confirmation pool hash drift"
[ "$(sha256sum "$IN/prior-replay75.fen" | awk '{print $1}')" = \
  "$DOSE_POOL_SHA" ] || die "dose pool hash drift"

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
  --exclude "$IN/prior-l2-confirm.fen"
  --exclude "$IN/prior-replay75.fen"
  --generator-seed "$OPENING_SEED"
)
python3 jobs/tools/select_independent_opening_pool.py "${opening_args[@]}" \
  --out "$ART/turnover-succession-openings.fen" \
  --manifest "$ART/turnover-succession-openings.json" \
  > "$W/select-openings-a.log" 2>&1
opening_args[1]="$W/open-candidates-b.fen"
python3 jobs/tools/select_independent_opening_pool.py "${opening_args[@]}" \
  --out "$W/turnover-succession-openings-repeat.fen" \
  --manifest "$W/turnover-succession-openings-repeat.json" \
  > "$W/select-openings-b.log" 2>&1
cmp -s "$ART/turnover-succession-openings.fen" \
  "$W/turnover-succession-openings-repeat.fen" ||
  die "selected confirmation pool is not byte-identical"
[ "$(wc -l < "$ART/turnover-succession-openings.fen")" -eq "$NOPEN" ] ||
  die "confirmation pool count drift"
NEW_POOL_SHA="$(sha256sum "$ART/turnover-succession-openings.fen" | awk '{print $1}')"
for spent in "$L2_CONFIRM_POOL_SHA" "$DOSE_POOL_SHA"; do
  [ "$NEW_POOL_SHA" != "$spent" ] || die "succession pool equals a spent pool"
done

phase publish-preflight-certificate
python3 - "$W" "$ART" "$EXPECTED_CODE_SHA" "$EXPECTED_DOSE_READOUT_JOB" \
  "$OPENING_SEED" "$TURNOVER_MODEL_SHA" "$F2M_MODEL_SHA" <<'XPY'
import hashlib
import json
import os
import pathlib
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha, trigger_job, seed = sys.argv[3:6]
turnover_sha, f2m_sha = sys.argv[6:]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


openings = json.loads((art / "turnover-succession-openings.json").read_text())
if openings.get("overlap_records") != 0:
    raise SystemExit("succession pool overlaps a prior pool")
if openings.get("records") != 1500 or openings.get("unique_records") != 1500:
    raise SystemExit("succession pool is not 1500 unique openings")

payload = {
    "schema": 1,
    "verdict": "TURNOVER_SUCCESSION_PREFLIGHT_READY",
    "code_sha": code_sha,
    "trigger": {
        "job": trigger_job,
        "champion_question": "TURNOVER50_BEATS_F2M_CHAMPION_REVIEW",
    },
    "experiment_variant": "TURNOVER_CHAMPION_SUCCESSION_GATE",
    "candidate": "TURNOVER",
    "candidate_model_sha256": turnover_sha,
    "incumbent": "F2M",
    "incumbent_model_sha256": f2m_sha,
    "historical_reference": "GEN2",
    "succession_openings": {
        "seed": int(seed),
        "sha256": sha(art / "turnover-succession-openings.fen"),
        "candidate_sha256": sha(w / "open-candidates-a.fen"),
        "manifest": openings,
    },
    "resource_preflight": {
        "nproc": os.cpu_count(),
        "home_gate_eta_minutes": [110, 150],
        "games_per_cell_per_view": 3000,
        "force_cells": 4,
        "conversion_strata": 2,
    },
    "new_generation_performed": False,
    "external_teacher_inputs": 0,
    "gate_authorized": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "turnover-succession-preflight.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__TURNOVER_SUCCESSION_PREFLIGHT_READY").write_text(
    "TURNOVER_SUCCESSION_PREFLIGHT_READY\n"
)
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
XPY
say "  pool succession ✓ : $(sha256sum "$ART/turnover-succession-openings.fen" | awk '{print $1}')"
say "  candidats ✓ : $(sha256sum "$W/open-candidates-a.fen" | awk '{print $1}')"
phase complete
say "TURNOVER_SUCCESSION_PREFLIGHT_READY gate=true promotion=false automatic_next_job=null"
