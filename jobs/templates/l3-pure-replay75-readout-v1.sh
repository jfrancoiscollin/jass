#!/usr/bin/env bash
# L3-PURE: powered readout of the replay dose axis, views summed.
#
# Six cells of 2500 games on the pool certified by home-0991: REPLAY75 against
# the dose-50 arm TURNOVER and against the champion F2M, plus the direct
# TURNOVER/F2M comparison that no run has yet measured at this power.
#
# The two views are SUMMED rather than required to agree separately, per
# docs/experiments/L3_VIEW_AGREEMENT_AND_POWER_20260726.md: n=5000 per matchup
# resolves ~1.4 pp (~10 Elo) instead of the 2.5-3 pp of earlier screens.
#
# Only 8cf engines take part, so no 32cf guard engine and no frozen defender.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${PREFLIGHT_PREFIX:?}"
: "${EXPECTED_PREFLIGHT_JOB:?}"; : "${EXPECTED_OPENING_SHA256:?}"
: "${TRAIN_PREFIX:?}"; : "${EXPECTED_TRAIN_JOB:?}"
: "${EXPECTED_CANDIDATE_MODEL_SHA256:?}"; : "${TURNOVER_TRAIN_PREFIX:?}"
: "${EXPECTED_TURNOVER_TRAIN_JOB:?}"; : "${M1_PREFIX:?}"
: "${EXPECTED_M1_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/force"
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
  rm -f "$W"/*.pjtw "$W"/*.jnnw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

NOPEN=1250
OPENING_SEED=3141593
NSH_GATE=16
PAR_GATE=4
FORCE_DEPTH=9
MOVETIME=0.1
CACHE_MB=128
TURNOVER_MODEL_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
F2M_MODEL_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
CHAMPION_CODE_SHA="0c1e04a9574fcd87977f62fe5bd6d71c60c72265"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

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
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
git diff --quiet "$CHAMPION_CODE_SHA" HEAD -- src pattern_jass/tools ||
  die "engine semantics changed since the repaired champion gate"
monitor

wait_all(){
  local label="$1"
  shift
  local fail=0 pid
  for pid in "$@"; do
    wait "$pid" || fail=$((fail+1))
  done
  [ "$fail" -eq 0 ] || die "$label: $fail workers failed"
}

stage fetch-and-authenticate-immutable-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=dose-preflight.json \
  --file artefacts/replay75-eval-openings.fen=open-eval.fen \
  --file artefacts/replay75-eval-openings.json=openings-manifest.json \
  --out-dir "$IN" --report "$ART/verified-dose-preflight.json" \
  > "$W/fetch-dose-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TRAIN_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=dose-training.json \
  --file artefacts/replay75.pjtw.gz=REPLAY75.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-dose-training.json" \
  > "$W/fetch-dose-training.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/turnover1to1.pjtw.gz=TURNOVER.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-turnover-training.json" \
  > "$W/fetch-turnover-training.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=F2M.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-f2m.json" \
  > "$W/fetch-f2m.log" 2>&1

for spec in \
  "verified-dose-preflight.json:$EXPECTED_PREFLIGHT_JOB" \
  "verified-dose-training.json:$EXPECTED_TRAIN_JOB" \
  "verified-turnover-training.json:$EXPECTED_TURNOVER_TRAIN_JOB" \
  "verified-f2m.json:$EXPECTED_M1_JOB"; do
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

python3 - "$IN/dose-preflight.json" "$IN/dose-training.json" \
  "$EXPECTED_OPENING_SHA256" "$OPENING_SEED" \
  "$EXPECTED_CANDIDATE_MODEL_SHA256" <<'XPY'
import json
import sys

preflight = json.load(open(sys.argv[1]))
training = json.load(open(sys.argv[2]))
pool_sha, seed, candidate_sha = sys.argv[3:]
openings = preflight.get("evaluation_openings", {})
if preflight.get("verdict") != "REPLAY75_PREFLIGHT_READY":
    raise SystemExit("preflight verdict mismatch")
if openings.get("sha256") != pool_sha or openings.get("seed") != int(seed):
    raise SystemExit("certified pool identity drift")
if training.get("verdict") != "REPLAY75_TRAINING_SCREEN_READY":
    raise SystemExit("training verdict mismatch")
if training.get("model_sha256") != candidate_sha:
    raise SystemExit("candidate model identity drift")
if training.get("optimizer_success") is not True:
    raise SystemExit("candidate fit did not converge")
if training.get("historical_replay_records") != 1_500_000:
    raise SystemExit("dose is not 75 percent replay")
if training.get("fresh_records") != 500_000:
    raise SystemExit("dose is not 75 percent replay")
if training.get("promotion_authorized") is not False:
    raise SystemExit("training must not authorise promotion")
XPY

cp "$IN/open-eval.fen" "$W/open-eval.fen"
cp "$IN/openings-manifest.json" "$ART/independent-openings-manifest.json"
for model in REPLAY75 TURNOVER F2M; do
  gunzip -c "$IN/$model.pjtw.gz" > "$W/$model.pjtw"
done
[ "$(sha256sum "$W/REPLAY75.pjtw" | awk '{print $1}')" = \
  "$EXPECTED_CANDIDATE_MODEL_SHA256" ] || die "REPLAY75 model hash drift"
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_MODEL_SHA" ] ||
  die "TURNOVER model hash drift"
[ "$(sha256sum "$W/F2M.pjtw" | awk '{print $1}')" = "$F2M_MODEL_SHA" ] ||
  die "F2M model hash drift"

stage build-and-test-8cf-engine
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
J8="$W/build8/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
[ "$("$J8" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
  die "tablebase-root witness failed"

stage verify-independent-confirmation-pool
[ "$(sha256sum "$W/open-eval.fen" | awk '{print $1}')" = \
  "$EXPECTED_OPENING_SHA256" ] || die "confirmation pool hash drift"
[ "$(wc -l < "$W/open-eval.fen")" -eq "$NOPEN" ] ||
  die "confirmation pool count drift"

run_gate(){
  local view="$1"
  local arm="$2"
  local opponent="$3"
  local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J8" \
    --pattern-a "$W/$arm.pjtw" --pattern-b "$W/$opponent.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 18000 --game-timeout 180 \
    --work-dir "$W/gate-$view-$arm-$opponent" \
    --out "$ART/force/force-$view-$arm-vs-$opponent.json" \
    > "$W/force-$view-$arm-$opponent.log" 2>&1
}

for view in q00 native; do
  stage "dose-$view-2500-games-per-cell"
  pids=()
  for pair in "REPLAY75:TURNOVER" "REPLAY75:F2M" "TURNOVER:F2M"; do
    run_gate "$view" "${pair%%:*}" "${pair#*:}" &
    pids+=("$!")
  done
  wait_all "$view dose wave" "${pids[@]}"
done

stage aggregate-dose-readout
python3 jobs/tools/l3_dose_readout.py \
  --force-dir "$ART/force" \
  --games-per-view $((NOPEN * 2)) \
  --out "$ART/replay75-dose-readout.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" \
  > "$W/aggregate.log" 2>&1
VERDICT="$(python3 - "$ART/replay75-dose-readout.json" <<'XPY'
import json
import sys
print(json.load(open(sys.argv[1]))["verdict"])
XPY
)"
CHAMPION="$(python3 - "$ART/replay75-dose-readout.json" <<'XPY'
import json
import sys
print(json.load(open(sys.argv[1]))["champion_question"])
XPY
)"
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf '%s\n' "$CHAMPION" > "$ART/CHAMPION__$CHAMPION"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "$VERDICT | $CHAMPION | promotion=false automatic_next_job=null"
