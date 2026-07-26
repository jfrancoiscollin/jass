#!/usr/bin/env bash
# L3-PURE: staged independent readout of the fixed-corpus TURNOVER L2 screen.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${TRAIN_PREFIX:?}"; : "${EXPECTED_TRAIN_JOB:?}"
: "${EXPECTED_L2_1E5_MODEL_SHA256:?}"; : "${EXPECTED_L2_1E4_MODEL_SHA256:?}"
: "${PREFLIGHT_PREFIX:?}"; : "${EXPECTED_PREFLIGHT_JOB:?}"
: "${EXPECTED_OPENING_SHA256:?}"; : "${TURNOVER_TRAIN_PREFIX:?}"
: "${EXPECTED_TURNOVER_TRAIN_JOB:?}"; : "${TURNOVER_EVAL_PREFIX:?}"
: "${EXPECTED_TURNOVER_EVAL_JOB:?}"; : "${TURNOVER_CONFIRM_PREFIX:?}"
: "${EXPECTED_TURNOVER_CONFIRM_JOB:?}"; : "${M1_PREFIX:?}"
: "${EXPECTED_M1_JOB:?}"; : "${CHAMPION_PREFIX:?}"
: "${EXPECTED_CHAMPION_JOB:?}"; : "${GAUGE_PREFIX:?}"; : "${MATRIX_PREFIX:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/force" "$ART/conversion"
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
  [ -z "$MON" ] || {
    kill "$MON" 2>/dev/null
    wait "$MON" 2>/dev/null
  }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8" "$W/build32" "$W/build32fixed" \
    "$W/fixed-defender-code" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.pjtw "$W"/*.jnnw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

NOPEN=500
OPENING_SEED=1836313
NSH_GATE=16
PAR_GATE=4
FORCE_DEPTH=9
MOVETIME=0.1
NSH_CONV=4
CONV_DEPTH=10
TARGET_PER_STRATUM=300
CACHE_MB=128
BOOTSTRAP_SAMPLES=200000
F2M_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
TURNOVER_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
GEN2_GZ_SHA="01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"
MATRIX_CODE_SHA="eacd90ab02b26f0619438ff1f65527d250d3c629"
CHAMPION_CODE_SHA="0c1e04a9574fcd87977f62fe5bd6d71c60c72265"
FIXED_DEFENDER_CODE_SHA="038a2001854f2805bc0045acd56c617826e5ff15"
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
monitor

jnnw_count(){ python3 - "$1" <<'PY'
import struct
import sys
raw = open(sys.argv[1], "rb").read(8)
if len(raw) != 8 or raw[:4] != b"JNNW":
    raise SystemExit("invalid JNNW header")
print(struct.unpack("<I", raw[4:])[0])
PY
}
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
python3 jobs/tools/fetch_result_files.py --prefix "$TRAIN_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=l2-training.json \
  --file artefacts/turnover-l2-1e5.pjtw.gz=L2_1E5.pjtw.gz \
  --file artefacts/turnover-l2-1e4.pjtw.gz=L2_1E4.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-l2-training.json" \
  > "$W/fetch-l2-training.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=l2-preflight.json \
  --file artefacts/turnover-l2-eval-openings.fen=l2-eval-openings.fen \
  --file artefacts/turnover-l2-eval-openings.json=l2-openings.json \
  --out-dir "$IN" --report "$ART/verified-l2-preflight.json" \
  > "$W/fetch-l2-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-training.json \
  --file artefacts/turnover1to1.pjtw.gz=TURNOVER.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-turnover-training.json" \
  > "$W/fetch-turnover-training.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_EVAL_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-evaluation.json \
  --file artefacts/conversion/TURNOVER-p3_mince.json=TURNOVER-p3_mince.json \
  --file artefacts/conversion/TURNOVER-p4_egal.json=TURNOVER-p4_egal.json \
  --out-dir "$IN" --report "$ART/verified-turnover-evaluation.json" \
  > "$W/fetch-turnover-evaluation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_CONFIRM_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-confirmation.json \
  --out-dir "$IN" --report "$ART/verified-turnover-confirmation.json" \
  > "$W/fetch-turnover-confirmation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=F2M.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-f2m.json" > "$W/fetch-f2m.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$CHAMPION_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=champion-benchmark.json \
  --out-dir "$IN" --report "$ART/verified-champion.json" \
  > "$W/fetch-champion.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --out-dir "$IN" --report "$ART/verified-gauge.json" > "$W/fetch-gauge.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$MATRIX_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m1-matrix.json \
  --out-dir "$IN" --report "$ART/verified-m1-matrix.json" \
  > "$W/fetch-matrix.log" 2>&1
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-gen2.log" 2>&1

for spec in \
  "verified-l2-training.json:$EXPECTED_TRAIN_JOB" \
  "verified-l2-preflight.json:$EXPECTED_PREFLIGHT_JOB" \
  "verified-turnover-training.json:$EXPECTED_TURNOVER_TRAIN_JOB" \
  "verified-turnover-evaluation.json:$EXPECTED_TURNOVER_EVAL_JOB" \
  "verified-turnover-confirmation.json:$EXPECTED_TURNOVER_CONFIRM_JOB" \
  "verified-f2m.json:$EXPECTED_M1_JOB" \
  "verified-champion.json:$EXPECTED_CHAMPION_JOB"; do
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

for model in L2_1E5 L2_1E4 TURNOVER F2M; do
  gunzip -c "$IN/$model.pjtw.gz" > "$W/$model.pjtw"
done
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"
cp "$IN/l2-eval-openings.fen" "$W/open-eval.fen"
cp "$IN/l2-openings.json" "$ART/independent-openings-manifest.json"
for stratum in p3_mince p4_egal; do
  cp "$IN/TURNOVER-$stratum.json" "$ART/conversion/TURNOVER-$stratum.json"
done

[ "$(sha256sum "$W/L2_1E5.pjtw" | awk '{print $1}')" = \
  "$EXPECTED_L2_1E5_MODEL_SHA256" ] || die "L2_1E5 model hash drift"
[ "$(sha256sum "$W/L2_1E4.pjtw" | awk '{print $1}')" = \
  "$EXPECTED_L2_1E4_MODEL_SHA256" ] || die "L2_1E4 model hash drift"
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_SHA" ] ||
  die "TURNOVER model hash drift"
[ "$(sha256sum "$W/F2M.pjtw" | awk '{print $1}')" = "$F2M_SHA" ] ||
  die "F2M model hash drift"
[ "$(sha256sum "$IN/gen2.pjtw.gz" | awk '{print $1}')" = "$GEN2_GZ_SHA" ] ||
  die "Gen2 model hash drift"
for spec in "p3_mince:$P3_GAUGE_SHA" "p4_egal:$P4_GAUGE_SHA"; do
  name="${spec%%:*}"
  want="${spec#*:}"
  [ "$(sha256sum "$W/$name.jnnw" | awk '{print $1}')" = "$want" ] ||
    die "$name gauge hash drift"
  [ "$(jnnw_count "$W/$name.jnnw")" -eq "$TARGET_PER_STRATUM" ] ||
    die "$name gauge count drift"
done

python3 - "$IN" "$ART" "$EXPECTED_L2_1E5_MODEL_SHA256" \
  "$EXPECTED_L2_1E4_MODEL_SHA256" "$EXPECTED_OPENING_SHA256" <<'PY'
import json
import sys
from pathlib import Path

src, art = map(Path, sys.argv[1:3])
sha_1e5, sha_1e4, opening_sha = sys.argv[3:]
training = json.load(open(src / "l2-training.json"))
preflight = json.load(open(src / "l2-preflight.json"))
turnover = json.load(open(src / "turnover-training.json"))
turnover_eval = json.load(open(src / "turnover-evaluation.json"))
confirmation = json.load(open(src / "turnover-confirmation.json"))
champion = json.load(open(src / "champion-benchmark.json"))
matrix = json.load(open(src / "m1-matrix.json"))
if (
    training.get("verdict") != "TURNOVER_L2_TRAINING_SCREEN_READY"
    or training.get("arms", {}).get("L2_1E5", {}).get("model_sha256") != sha_1e5
    or training.get("arms", {}).get("L2_1E4", {}).get("model_sha256") != sha_1e4
    or training.get("arms", {}).get("L2_1E5", {}).get("optimizer", {}).get(
        "success"
    )
    is not True
    or training.get("arms", {}).get("L2_1E4", {}).get("optimizer", {}).get(
        "success"
    )
    is not True
    or training.get("evaluation_authorized") is not True
    or training.get("promotion_authorized") is not False
    or training.get("automatic_next_job") is not None
    or training.get("control", {}).get("source_code_sha")
    != "336bb98451a205266d6646c4d801027af4b30294"
):
    raise SystemExit("L2 training certificate mismatch")
if (
    preflight.get("verdict") != "TURNOVER_L2_PREFLIGHT_READY"
    or preflight.get("evaluation_openings", {}).get("seed") != 1_836_313
    or preflight.get("evaluation_openings", {}).get("sha256") != opening_sha
    or preflight.get("control_source_code_sha")
    != "336bb98451a205266d6646c4d801027af4b30294"
    or preflight.get("jnnw_sha256")
    != "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
):
    raise SystemExit("L2 preflight certificate mismatch")
if (
    turnover.get("model_sha256")
    != "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
    or turnover.get("code_sha")
    != "336bb98451a205266d6646c4d801027af4b30294"
    or turnover_eval.get("verdict")
    != "TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW"
    or confirmation.get("verdict")
    != "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW"
    or confirmation.get("all_guardrails_pass") is not True
    or champion.get("verdict") != "F2M_NEW_GENERAL_CHAMPION_HUMAN_REVIEW"
    or champion.get("recommended_general_champion") != "F2M"
    or matrix.get("verdict") != "M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW"
):
    raise SystemExit("control certificate mismatch")
for name in ("verified-gauge.json", "verified-m1-matrix.json"):
    if json.load(open(art / name)).get("result_state") != "completed":
        raise SystemExit(f"{name}: source is not completed")
fixed = json.load(open(art / "verified-fixed-inputs.json"))
gen2 = [item for item in fixed.get("objects", []) if item.get("role") == "gen2_pattern"]
if (
    fixed.get("state") != "verified"
    or len(gen2) != 1
    or gen2[0].get("sha256")
    != "01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"
):
    raise SystemExit("fixed Gen2 input certificate mismatch")
PY

python3 -m py_compile jobs/tools/l3_turnover_l2_evaluation.py
python3 -m unittest jobs.tests.test_l3_turnover_l2_evaluation \
  > "$W/test-l2-evaluation.log" 2>&1
for source in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp \
  src/movegen.cpp src/movegen.hpp; do
  git show "${EXPECTED_CODE_SHA}:$source" > "$source"
done
grep -q "g_emasks" src/scan_eval.cpp || die "8cf build lacks g_emasks"
grep -q "has_any_capture" src/search.cpp || die "search lacks capture guard"
grep -q "has_any_capture" src/movegen.cpp || die "movegen lacks capture guard"
git diff --quiet "$CHAMPION_CODE_SHA" HEAD -- src pattern_jass/tools ||
  die "engine semantics changed since symmetric champion benchmark"
git diff --quiet "$MATRIX_CODE_SHA" HEAD -- src pattern_jass/tools ||
  die "attacker semantics changed since repaired conversion matrix"

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

stage verify-independent-opening-pool
[ "$(sha256sum "$W/open-eval.fen" | awk '{print $1}')" = \
  "$EXPECTED_OPENING_SHA256" ] || die "L2 opening pool hash drift"
[ "$(wc -l < "$W/open-eval.fen")" -eq "$NOPEN" ] ||
  die "L2 opening pool count drift"

run_gate(){
  local view="$1"
  local arm="$2"
  local opponent="$3"
  local jb="$J8"
  local pattern="$W/TURNOVER.pjtw"
  local args=()
  [ "$opponent" = F2M ] && pattern="$W/F2M.pjtw"
  [ "$opponent" = GEN2 ] && { jb="$J32"; pattern="$W/GEN2.pjtw"; }
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$jb" \
    --pattern-a "$W/$arm.pjtw" --pattern-b "$pattern" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 10800 --game-timeout 180 \
    --work-dir "$W/gate-$view-$arm-$opponent" \
    --out "$ART/force/force-$view-$arm-vs-$opponent.json" \
    > "$W/force-$view-$arm-$opponent.log" 2>&1
}

for view in q00 native; do
  stage "primary-$view-vs-turnover"
  pids=()
  for arm in L2_1E5 L2_1E4; do
    run_gate "$view" "$arm" TURNOVER &
    pids+=("$!")
  done
  wait_all "$view primary wave" "${pids[@]}"
done

python3 - "$ART/force" "$W/eligible-arms.txt" <<'PY'
import json
import sys
from pathlib import Path

force_dir = Path(sys.argv[1])
eligible = []
for arm in ("L2_1E5", "L2_1E4"):
    rates = [
        json.load(open(force_dir / f"force-{view}-{arm}-vs-TURNOVER.json"))[
            "rate"
        ]
        for view in ("q00", "native")
    ]
    if all(rate > 0.5 for rate in rates):
        eligible.append(arm)
Path(sys.argv[2]).write_text("".join(f"{arm}\n" for arm in eligible))
PY
mapfile -t ELIGIBLE < "$W/eligible-arms.txt"
cp "$W/eligible-arms.txt" "$ART/eligible-arms.txt"

if [ "${#ELIGIBLE[@]}" -gt 0 ]; then
  stage build-guard-and-fixed-defender-engines
  python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 \
    > "$W/gen32.log" 2>&1
  cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
  cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
  mkdir -p "$W/fixed-defender-code"
  git archive "$FIXED_DEFENDER_CODE_SHA" | tar -x -C "$W/fixed-defender-code"
  (cd "$W/fixed-defender-code" &&
    python3 pattern_jass/tools/gen_patterns.py --emit --variant v4) \
    > "$W/gen32fixed.log" 2>&1
  cmake -S "$W/fixed-defender-code" -B "$W/build32fixed" $FLAGS \
    > "$W/cmake32fixed.log" 2>&1
  cmake --build "$W/build32fixed" -j4 --target jass \
    > "$W/build32fixed.log" 2>&1
  J32="$W/build32/jass"
  J32FIXED="$W/build32fixed/jass"
  for jass in "$J32" "$J32FIXED"; do
    [ "$("$jass" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
      die "guard engine king-capture witness failed"
  done

  for view in q00 native; do
    stage "guard-$view"
    pids=()
    for arm in "${ELIGIBLE[@]}"; do
      for opponent in F2M GEN2; do
        run_gate "$view" "$arm" "$opponent" &
        pids+=("$!")
      done
    done
    wait_all "$view guard wave" "${pids[@]}"
  done

  run_conv(){
    local arm="$1"
    local stratum="$2"
    local pool="$3"
    local pids=() inputs=() shard out
    for shard in $(seq 0 $((NSH_CONV-1))); do
      out="$W/$arm-$stratum-$shard.json"
      inputs+=("$out")
      timeout 14400 python3 jobs/tools/conv_fixed_wdl.py \
        --jass "$J8" --defender-jass "$J32FIXED" \
        --pattern "$W/$arm.pjtw" --defender-pattern "$W/GEN2.pjtw" \
        --search-params "$Q00" --defender-search-params "$Q00" \
        --pool-jnnw "$pool" --depth "$CONV_DEPTH" --max-plies 260 \
        --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
        > "$W/$arm-$stratum-$shard.log" 2>&1 &
      pids+=("$!")
    done
    wait_all "$arm/$stratum conversion" "${pids[@]}"
    python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
      --expected-shards "$NSH_CONV" --expected-records "$TARGET_PER_STRATUM" \
      --max-error-rate 0.08 --stratum "$stratum" --require-position-results \
      --out "$ART/conversion/$arm-$stratum.json" \
      > "$W/$arm-$stratum-aggregate.log" 2>&1
  }
  for stratum in p3_mince p4_egal; do
    stage "conversion-$stratum"
    pids=()
    for arm in "${ELIGIBLE[@]}"; do
      run_conv "$arm" "$stratum" "$W/$stratum.jnnw" &
      pids+=("$!")
    done
    wait_all "$stratum candidate conversions" "${pids[@]}"
  done
fi

stage aggregate-preregistered-verdict
python3 jobs/tools/l3_turnover_l2_evaluation.py \
  --force-dir "$ART/force" \
  --conversion-dir "$ART/conversion" \
  --training-summary "$IN/l2-training.json" \
  --preflight "$IN/l2-preflight.json" \
  --turnover-training "$IN/turnover-training.json" \
  --turnover-confirmation "$IN/turnover-confirmation.json" \
  --opening-manifest "$ART/independent-openings-manifest.json" \
  --expected-opening-seed "$OPENING_SEED" \
  --expected-opening-sha256 "$EXPECTED_OPENING_SHA256" \
  --bootstrap-samples "$BOOTSTRAP_SAMPLES" \
  --out "$ART/turnover-l2-evaluation.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" \
  > "$W/aggregate.log" 2>&1
VERDICT="$(python3 - "$ART/turnover-l2-evaluation.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1]))["verdict"])
PY
)"
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "$VERDICT promotion=false automatic_next_job=null"
