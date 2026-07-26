#!/usr/bin/env bash
# L3-PURE REPLAY25: independent force, conversion and coverage readout.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${TRAIN_PREFIX:?}"; : "${EXPECTED_TRAIN_JOB:?}"
: "${EXPECTED_CANDIDATE_MODEL_SHA256:?}"; : "${EXPECTED_CANDIDATE_CORPUS_SHA256:?}"
: "${PREFLIGHT_PREFIX:?}"; : "${EXPECTED_PREFLIGHT_JOB:?}"
: "${TURNOVER_TRAIN_PREFIX:?}"; : "${EXPECTED_TURNOVER_TRAIN_JOB:?}"
: "${TURNOVER_EVAL_PREFIX:?}"; : "${EXPECTED_TURNOVER_EVAL_JOB:?}"
: "${TURNOVER_CONFIRM_PREFIX:?}"; : "${EXPECTED_TURNOVER_CONFIRM_JOB:?}"
: "${M2_PREFIX:?}"; : "${EXPECTED_M2_JOB:?}"
: "${M2_EVAL_PREFIX:?}"; : "${EXPECTED_M2_EVAL_JOB:?}"
: "${M1_PREFIX:?}"; : "${EXPECTED_M1_JOB:?}"
: "${CHAMPION_PREFIX:?}"; : "${EXPECTED_CHAMPION_JOB:?}"
: "${GAUGE_PREFIX:?}"; : "${MATRIX_PREFIX:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM" \
  "$ART/force" "$ART/conversion" "$ART/coverage"
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
OPENING_SEED=1836311
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
M2_SHA="75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
M2_CORPUS_SHA="ee8d685cea331940403da82830d7b4cc045fe50acc1e5764d23f0467d4f7ffb8"
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
  --file artefacts/replay25.pjtw.gz=replay25.pjtw.gz \
  --file artefacts/replay25.jnnw.gz=replay25.jnnw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=replay25-training.json \
  --out-dir "$IN" --report "$ART/verified-replay25-training.json" \
  > "$W/fetch-replay25.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=replay25-preflight.json \
  --file artefacts/replay25-eval-openings.fen=replay25-eval-openings.fen \
  --file artefacts/replay25-eval-openings.json=replay25-openings.json \
  --out-dir "$IN" --report "$ART/verified-replay25-preflight.json" \
  > "$W/fetch-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/turnover1to1.pjtw.gz=turnover.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-training.json \
  --out-dir "$IN" --report "$ART/verified-turnover-training.json" \
  > "$W/fetch-turnover-training.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_EVAL_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-evaluation.json \
  --file artefacts/conversion/TURNOVER-p3_mince.json=TURNOVER-p3_mince.json \
  --file artefacts/conversion/TURNOVER-p4_egal.json=TURNOVER-p4_egal.json \
  --file artefacts/conversion/M2-p3_mince.json=M2-p3_mince.json \
  --file artefacts/conversion/M2-p4_egal.json=M2-p4_egal.json \
  --file artefacts/conversion/F2M-p3_mince.json=F2M-p3_mince.json \
  --file artefacts/conversion/F2M-p4_egal.json=F2M-p4_egal.json \
  --file artefacts/coverage/TURNOVER-coverage.json=TURNOVER-coverage.json \
  --file artefacts/coverage/M2-coverage.json=M2-coverage.json \
  --file artefacts/coverage/F2M-coverage.json=F2M-coverage.json \
  --out-dir "$IN" --report "$ART/verified-turnover-evaluation.json" \
  > "$W/fetch-turnover-evaluation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_CONFIRM_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-confirmation.json \
  --out-dir "$IN" --report "$ART/verified-turnover-confirmation.json" \
  > "$W/fetch-turnover-confirmation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M2_PREFIX" \
  --file artefacts/m2.pjtw.gz=m2.pjtw.gz \
  --file artefacts/m2-fresh-2m.jnnw.gz=m2.jnnw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m2-training.json \
  --out-dir "$IN" --report "$ART/verified-m2-training.json" \
  > "$W/fetch-m2.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M2_EVAL_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m2-evaluation.json \
  --out-dir "$IN" --report "$ART/verified-m2-evaluation.json" \
  > "$W/fetch-m2-evaluation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
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
  "verified-replay25-training.json:$EXPECTED_TRAIN_JOB" \
  "verified-replay25-preflight.json:$EXPECTED_PREFLIGHT_JOB" \
  "verified-turnover-training.json:$EXPECTED_TURNOVER_TRAIN_JOB" \
  "verified-turnover-evaluation.json:$EXPECTED_TURNOVER_EVAL_JOB" \
  "verified-turnover-confirmation.json:$EXPECTED_TURNOVER_CONFIRM_JOB" \
  "verified-m2-training.json:$EXPECTED_M2_JOB" \
  "verified-m2-evaluation.json:$EXPECTED_M2_EVAL_JOB" \
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

gunzip -c "$IN/replay25.pjtw.gz" > "$W/REPLAY25.pjtw"
gunzip -c "$IN/replay25.jnnw.gz" > "$W/REPLAY25.jnnw"
gunzip -c "$IN/turnover.pjtw.gz" > "$W/TURNOVER.pjtw"
gunzip -c "$IN/m2.pjtw.gz" > "$W/M2.pjtw"
gunzip -c "$IN/m2.jnnw.gz" > "$W/M2.jnnw"
gunzip -c "$IN/f2m.pjtw.gz" > "$W/F2M.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"
cp "$IN/replay25-eval-openings.fen" "$W/open-eval.fen"
cp "$IN/replay25-openings.json" "$ART/independent-openings-manifest.json"
for model in TURNOVER M2 F2M; do
  cp "$IN/$model-p3_mince.json" "$ART/conversion/$model-p3_mince.json"
  cp "$IN/$model-p4_egal.json" "$ART/conversion/$model-p4_egal.json"
  cp "$IN/$model-coverage.json" "$ART/coverage/$model-coverage.json"
done

[ "$(sha256sum "$W/REPLAY25.pjtw" | awk '{print $1}')" = \
  "$EXPECTED_CANDIDATE_MODEL_SHA256" ] || die "REPLAY25 model hash drift"
[ "$(sha256sum "$W/REPLAY25.jnnw" | awk '{print $1}')" = \
  "$EXPECTED_CANDIDATE_CORPUS_SHA256" ] || die "REPLAY25 corpus hash drift"
[ "$(jnnw_count "$W/REPLAY25.jnnw")" -eq 2000000 ] ||
  die "REPLAY25 corpus count drift"
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_SHA" ] ||
  die "TURNOVER model hash drift"
[ "$(sha256sum "$W/M2.pjtw" | awk '{print $1}')" = "$M2_SHA" ] ||
  die "M2 model hash drift"
[ "$(sha256sum "$W/M2.jnnw" | awk '{print $1}')" = "$M2_CORPUS_SHA" ] ||
  die "M2 corpus hash drift"
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

python3 - "$IN" "$ART" "$EXPECTED_CANDIDATE_MODEL_SHA256" \
  "$EXPECTED_CANDIDATE_CORPUS_SHA256" <<'PY'
import json
import sys
from pathlib import Path

src, art = map(Path, sys.argv[1:3])
model_sha, corpus_sha = sys.argv[3:]
training = json.load(open(src / "replay25-training.json"))
preflight = json.load(open(src / "replay25-preflight.json"))
turnover_training = json.load(open(src / "turnover-training.json"))
turnover_evaluation = json.load(open(src / "turnover-evaluation.json"))
turnover_confirmation = json.load(open(src / "turnover-confirmation.json"))
m2_training = json.load(open(src / "m2-training.json"))
m2_evaluation = json.load(open(src / "m2-evaluation.json"))
champion = json.load(open(src / "champion-benchmark.json"))
matrix = json.load(open(src / "m1-matrix.json"))
if (
    training.get("verdict") != "REPLAY25_TRAINING_SCREEN_READY"
    or training.get("model_sha256") != model_sha
    or training.get("training_corpus_sha256") != corpus_sha
    or training.get("training_meta_sha256") != preflight.get("jsm_sha256")
    or training.get("historical_replay_records") != 500_000
    or training.get("fresh_records") != 1_500_000
    or training.get("evaluation_authorized") is not True
    or training.get("promotion_authorized") is not False
    or training.get("automatic_next_job") is not None
):
    raise SystemExit("REPLAY25 training certificate mismatch")
if (
    preflight.get("verdict") != "REPLAY25_PREFLIGHT_READY"
    or preflight.get("jnnw_sha256") != corpus_sha
    or preflight.get("evaluation_openings", {}).get("seed") != 1_836_311
    or preflight.get("evaluation_openings", {}).get("sha256")
    != "a0af38e81ea457b5f95a12d3166b7103e922627c4771d6351057de1ad7ced2c2"
):
    raise SystemExit("REPLAY25 preflight certificate mismatch")
if (
    turnover_training.get("model_sha256")
    != "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
    or turnover_evaluation.get("verdict")
    != "TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW"
    or turnover_confirmation.get("verdict")
    != "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW"
    or turnover_confirmation.get("all_guardrails_pass") is not True
    or m2_training.get("model_sha256")
    != "75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
    or m2_evaluation.get("verdict") != "M2_PLATEAU_OR_REGRESSION_REVIEW"
    or m2_evaluation.get("all_guardrails_pass") is not True
):
    raise SystemExit("M2/TURNOVER control certificate mismatch")
if (
    champion.get("verdict") != "F2M_NEW_GENERAL_CHAMPION_HUMAN_REVIEW"
    or champion.get("recommended_general_champion") != "F2M"
    or matrix.get("verdict") != "M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW"
):
    raise SystemExit("champion/matrix certificate mismatch")
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

python3 -m py_compile jobs/tools/l3_replay25_evaluation.py
python3 -m unittest jobs.tests.test_l3_replay25_evaluation \
  > "$W/test-replay25-evaluation.log" 2>&1
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

stage build-and-test-repaired-engines
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
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
mkdir -p "$W/fixed-defender-code"
git archive "$FIXED_DEFENDER_CODE_SHA" | tar -x -C "$W/fixed-defender-code"
(cd "$W/fixed-defender-code" &&
  python3 pattern_jass/tools/gen_patterns.py --emit --variant v4) \
  > "$W/gen32fixed.log" 2>&1
cmake -S "$W/fixed-defender-code" -B "$W/build32fixed" $FLAGS \
  > "$W/cmake32fixed.log" 2>&1
cmake --build "$W/build32fixed" -j4 --target jass > "$W/build32fixed.log" 2>&1
J8="$W/build8/jass"
J32="$W/build32/jass"
J32FIXED="$W/build32fixed/jass"
for jass in "$J8" "$J32"; do
  [ "$("$jass" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
    die "king-capture witness failed"
  [ "$("$jass" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
    die "tablebase-root witness failed"
done

stage verify-independent-opening-pool
[ "$(sha256sum "$W/open-eval.fen" | awk '{print $1}')" = \
  "a0af38e81ea457b5f95a12d3166b7103e922627c4771d6351057de1ad7ced2c2" ] ||
  die "REPLAY25 opening pool hash drift"
[ "$(wc -l < "$W/open-eval.fen")" -eq "$NOPEN" ] ||
  die "REPLAY25 opening pool count drift"

stage exact-corpus-coverage
env PYTHONPATH="$GEOM:pattern_jass/tools" \
  python3 jobs/tools/l3_bucket_visits.py --data "$W/REPLAY25.jnnw" \
  --out "$ART/coverage/REPLAY25-coverage.json" \
  > "$W/coverage-REPLAY25.log" 2>&1

run_gate(){
  local view="$1"
  local opponent="$2"
  local jb="$J8"
  local pattern="$W/F2M.pjtw"
  local args=()
  [ "$opponent" = GEN2 ] && { jb="$J32"; pattern="$W/GEN2.pjtw"; }
  [ "$opponent" = M2 ] && pattern="$W/M2.pjtw"
  [ "$opponent" = TURNOVER ] && pattern="$W/TURNOVER.pjtw"
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$jb" \
    --pattern-a "$W/REPLAY25.pjtw" --pattern-b "$pattern" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 10800 --game-timeout 180 \
    --work-dir "$W/gate-$view-REPLAY25-$opponent" \
    --out "$ART/force/force-$view-REPLAY25-vs-$opponent.json" \
    > "$W/force-$view-REPLAY25-$opponent.log" 2>&1
}
for view in q00 native; do
  stage "force-$view"
  pids=()
  for opponent in M2 TURNOVER F2M GEN2; do
    run_gate "$view" "$opponent" &
    pids+=("$!")
  done
  wait_all "$view force wave" "${pids[@]}"
done

run_conv(){
  local stratum="$1"
  local pool="$2"
  local pids=() inputs=() shard out
  for shard in $(seq 0 $((NSH_CONV-1))); do
    out="$W/REPLAY25-$stratum-$shard.json"
    inputs+=("$out")
    timeout 14400 python3 jobs/tools/conv_fixed_wdl.py \
      --jass "$J8" --defender-jass "$J32FIXED" \
      --pattern "$W/REPLAY25.pjtw" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$Q00" --defender-search-params "$Q00" \
      --pool-jnnw "$pool" --depth "$CONV_DEPTH" --max-plies 260 \
      --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
      > "$W/REPLAY25-$stratum-$shard.log" 2>&1 &
    pids+=("$!")
  done
  wait_all "REPLAY25/$stratum conversion" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
    --expected-shards "$NSH_CONV" --expected-records "$TARGET_PER_STRATUM" \
    --max-error-rate 0.08 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/REPLAY25-$stratum.json" \
    > "$W/REPLAY25-$stratum-aggregate.log" 2>&1
}
stage corrected-fixed-defender-conversion
run_conv p3_mince "$W/p3_mince.jnnw"
run_conv p4_egal "$W/p4_egal.jnnw"

stage aggregate-preregistered-verdict
python3 jobs/tools/l3_replay25_evaluation.py \
  --force-dir "$ART/force" \
  --conversion-dir "$ART/conversion" \
  --coverage-dir "$ART/coverage" \
  --training-summary "$IN/replay25-training.json" \
  --preflight "$IN/replay25-preflight.json" \
  --turnover-training "$IN/turnover-training.json" \
  --turnover-evaluation "$IN/turnover-evaluation.json" \
  --turnover-confirmation "$IN/turnover-confirmation.json" \
  --m2-training "$IN/m2-training.json" \
  --m2-evaluation "$IN/m2-evaluation.json" \
  --opening-manifest "$ART/independent-openings-manifest.json" \
  --expected-opening-seed "$OPENING_SEED" \
  --expected-opening-sha256 \
    "a0af38e81ea457b5f95a12d3166b7103e922627c4771d6351057de1ad7ced2c2" \
  --bootstrap-samples "$BOOTSTRAP_SAMPLES" \
  --out "$ART/replay25-evaluation.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" \
  > "$W/aggregate.log" 2>&1
VERDICT="$(python3 - "$ART/replay25-evaluation.json" <<'PY'
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
