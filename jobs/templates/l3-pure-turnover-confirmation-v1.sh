#!/usr/bin/env bash
# Independent high-N confirmation of the L3-PURE 1:1 temporal-turnover signal.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${TURNOVER_TRAIN_PREFIX:?}"; : "${TURNOVER_EVAL_PREFIX:?}"
: "${M2_PREFIX:?}"; : "${F2M_PREFIX:?}"
: "${EXPECTED_TURNOVER_TRAIN_JOB:?}"; : "${EXPECTED_TURNOVER_EVAL_JOB:?}"
: "${EXPECTED_M2_JOB:?}"; : "${EXPECTED_F2M_JOB:?}"
: "${EXPECTED_OPENING_SHA256:?}"; : "${EXPECTED_CANDIDATE_OPENING_SHA256:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$IN" "$ART/force"
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
  (while true; do
    {
      date -Is
      printf 'stage=%s\n' "$(cat "$STAGE")"
      awk '/MemTotal:/{total=$2}/MemAvailable:/{available=$2}
        END{printf "mem_total_mb=%d\nmem_available_mb=%d\n",total/1024,available/1024}' \
        /proc/meminfo
      ps -eo pid,ppid,rss,pcpu,stat,comm --sort=-rss | head -n 18
    } > "$PROG.tmp"
    mv "$PROG.tmp" "$PROG"
    cp "$PROG" "$ART/PROGRESS.txt"
    sleep 60
  done) & MON="$!"
}
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || kill "$MON" 2>/dev/null
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -name '*.log' -type f -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8" "$IN"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

NOPEN=1000
PRIOR_NOPEN=500
OPENING_CANDIDATES=4000
PRIOR_OPENING_CANDIDATES=2000
OPENING_SEED=11235813
NSH_GATE=16
PAR_GATE=4
FORCE_DEPTH=9
MOVETIME=0.1
CACHE_MB=128
TURNOVER_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
M2_SHA="75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
F2M_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
TURNOVER_CORPUS_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
TURNOVER_META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
TURNOVER_CODE_SHA="336bb98451a205266d6646c4d801027af4b30294"
PRIOR_TURNOVER_OPENINGS_SHA="6ebd2a5ecd79d5e11fc35100c00babb33c98c47843a7b9aadbed7eaef2b6930d"
M2_OPENINGS_SHA="9a0e46be89655ada7317440e3539b8583ab3d7fe83e400475ae817e77396313c"
D10_OPENINGS_SHA="e41ae3875368112a99d3de2a1e6e40aa8d4d94d5cb66ed5280999a7a4e612965"
D12_OPENINGS_SHA="0f7af083406063719717190cab7f983bee6d0f49b552f42ca4d05d81dce7cf7f"
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
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
git diff --quiet "$CHAMPION_CODE_SHA" HEAD -- src pattern_jass/tools ||
  die "engine semantics changed since the symmetric F2M benchmark"
monitor

stage fetch-and-verify-immutable-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/m2.pjtw.gz=turnover.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-training.json \
  --out-dir "$IN" --report "$ART/verified-turnover-training.json" \
  > "$W/fetch-turnover-training.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_EVAL_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=turnover-evaluation.json \
  --file artefacts/independent-openings-manifest.json=turnover-openings.json \
  --file work/open-eval.fen=prior-turnover-independent.fen \
  --out-dir "$IN" --report "$ART/verified-turnover-evaluation.json" \
  > "$W/fetch-turnover-evaluation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M2_PREFIX" \
  --file artefacts/m2.pjtw.gz=m2.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-m2.json" \
  > "$W/fetch-m2.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$F2M_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-f2m.json" \
  > "$W/fetch-f2m.log" 2>&1

gunzip -c "$IN/turnover.pjtw.gz" > "$W/TURNOVER.pjtw"
gunzip -c "$IN/m2.pjtw.gz" > "$W/M2.pjtw"
gunzip -c "$IN/f2m.pjtw.gz" > "$W/F2M.pjtw"
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_SHA" ] ||
  die "TURNOVER model hash drift"
[ "$(sha256sum "$W/M2.pjtw" | awk '{print $1}')" = "$M2_SHA" ] ||
  die "M2 model hash drift"
[ "$(sha256sum "$W/F2M.pjtw" | awk '{print $1}')" = "$F2M_SHA" ] ||
  die "F2M model hash drift"
[ "$(sha256sum "$IN/prior-turnover-independent.fen" | awk '{print $1}')" = \
  "$PRIOR_TURNOVER_OPENINGS_SHA" ] || die "prior TURNOVER opening pool hash drift"

python3 - "$ART/verified-turnover-training.json" \
  "$ART/verified-turnover-evaluation.json" "$ART/verified-m2.json" \
  "$ART/verified-f2m.json" "$IN/turnover-training.json" \
  "$IN/turnover-evaluation.json" "$IN/turnover-openings.json" \
  "$EXPECTED_TURNOVER_TRAIN_JOB" "$EXPECTED_TURNOVER_EVAL_JOB" \
  "$EXPECTED_M2_JOB" "$EXPECTED_F2M_JOB" <<'PY'
import json
import sys

(
    train_report,
    eval_report,
    m2_report,
    f2m_report,
    training,
    evaluation,
    openings,
) = (json.load(open(path)) for path in sys.argv[1:8])
expected_jobs = sys.argv[8:12]
for report, job, label in zip(
    (train_report, eval_report, m2_report, f2m_report),
    expected_jobs,
    ("TURNOVER training", "TURNOVER evaluation", "M2", "F2M"),
):
    if report.get("result_state") != "completed" or report.get("job_id") != job:
        raise SystemExit(f"{label} source identity/state mismatch")
if (
    train_report.get("code_sha")
    != "336bb98451a205266d6646c4d801027af4b30294"
    or eval_report.get("code_sha")
    != "336bb98451a205266d6646c4d801027af4b30294"
    or training.get("model_sha256")
    != "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
    or training.get("training_corpus_sha256")
    != "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
    or training.get("training_meta_sha256")
    != "acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
    or training.get("experiment_variant") != "TURNOVER_1_1"
    or training.get("training_records") != 2_000_000
):
    raise SystemExit("TURNOVER immutable training certificate mismatch")
if (
    evaluation.get("verdict") != "TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW"
    or evaluation.get("recommendation") != "independent_turnover_confirmation"
    or evaluation.get("all_guardrails_pass") is not True
    or evaluation.get("promotion_authorized") is not False
    or evaluation.get("automatic_next_job") is not None
    or evaluation.get("training_summary", {}).get("model_sha256")
    != training.get("model_sha256")
):
    raise SystemExit("TURNOVER source evaluation certificate mismatch")
if (
    openings.get("records") != 500
    or openings.get("unique_records") != 500
    or openings.get("overlap_records") != 0
    or openings.get("generator_seed") != 732_051
    or openings.get("sha256")
    != "6ebd2a5ecd79d5e11fc35100c00babb33c98c47843a7b9aadbed7eaef2b6930d"
):
    raise SystemExit("TURNOVER source opening certificate mismatch")
PY

python3 -m py_compile jobs/tools/l3_turnover_confirmation.py
python3 -m unittest jobs.tests.test_l3_turnover_confirmation \
  > "$W/test-turnover-confirmation.log" 2>&1

stage build-and-test-8cf
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf \
  > "$W/gen8.log" 2>&1
grep -q "g_emasks" src/scan_eval.cpp || die "8cf build lacks g_emasks"
grep -q "has_any_capture" src/search.cpp || die "search lacks capture guard"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j4 --target jass jass_tests \
  > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
[ "$("$J8" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
  die "tablebase-root witness failed"

stage reconstruct-all-prior-opening-pools
for spec in \
  "prior-reinforcement:768:271828" \
  "prior-meta-screen:128:161803" \
  "prior-meta-confirm:256:141421" \
  "prior-f2m-confirm:500:173205" \
  "prior-f2m-gen2:500:223607"; do
  name="${spec%%:*}"
  rest="${spec#*:}"
  count="${rest%%:*}"
  seed="${rest#*:}"
  "$J8" --gen-opening-pool "$count" "$W/$name.fen" 8 32 20 "$seed" \
    > "$W/open-$name.log" 2>&1
done

"$J8" --gen-opening-pool "$PRIOR_OPENING_CANDIDATES" \
  "$W/prior-m2-candidates.fen" 8 32 20 244949 \
  > "$W/open-prior-m2.log" 2>&1
python3 jobs/tools/select_independent_opening_pool.py \
  --candidates "$W/prior-m2-candidates.fen" --expected "$PRIOR_NOPEN" \
  --exclude data/dilf_combinations.fen \
  --exclude "$W/prior-reinforcement.fen" \
  --exclude "$W/prior-meta-screen.fen" \
  --exclude "$W/prior-meta-confirm.fen" \
  --exclude "$W/prior-f2m-confirm.fen" \
  --exclude "$W/prior-f2m-gen2.fen" \
  --generator-seed 244949 --out "$W/prior-m2-independent.fen" \
  --manifest "$W/prior-m2-independent.json" \
  > "$W/select-prior-m2.log" 2>&1
[ "$(sha256sum "$W/prior-m2-independent.fen" | awk '{print $1}')" = \
  "$M2_OPENINGS_SHA" ] || die "reconstructed M2 opening pool hash drift"

"$J8" --gen-opening-pool "$PRIOR_OPENING_CANDIDATES" \
  "$W/prior-d10-candidates.fen" 8 32 20 314159 \
  > "$W/open-prior-d10.log" 2>&1
python3 jobs/tools/select_independent_opening_pool.py \
  --candidates "$W/prior-d10-candidates.fen" --expected "$PRIOR_NOPEN" \
  --exclude data/dilf_combinations.fen \
  --exclude "$W/prior-reinforcement.fen" \
  --exclude "$W/prior-meta-screen.fen" \
  --exclude "$W/prior-meta-confirm.fen" \
  --exclude "$W/prior-f2m-confirm.fen" \
  --exclude "$W/prior-f2m-gen2.fen" \
  --exclude "$W/prior-m2-independent.fen" \
  --generator-seed 314159 --out "$W/prior-d10-independent.fen" \
  --manifest "$W/prior-d10-independent.json" \
  > "$W/select-prior-d10.log" 2>&1
[ "$(sha256sum "$W/prior-d10-independent.fen" | awk '{print $1}')" = \
  "$D10_OPENINGS_SHA" ] || die "reconstructed D10 opening pool hash drift"

"$J8" --gen-opening-pool "$PRIOR_OPENING_CANDIDATES" \
  "$W/prior-d12-candidates.fen" 8 32 20 424243 \
  > "$W/open-prior-d12.log" 2>&1
python3 jobs/tools/select_independent_opening_pool.py \
  --candidates "$W/prior-d12-candidates.fen" --expected "$PRIOR_NOPEN" \
  --exclude data/dilf_combinations.fen \
  --exclude "$W/prior-reinforcement.fen" \
  --exclude "$W/prior-meta-screen.fen" \
  --exclude "$W/prior-meta-confirm.fen" \
  --exclude "$W/prior-f2m-confirm.fen" \
  --exclude "$W/prior-f2m-gen2.fen" \
  --exclude "$W/prior-m2-independent.fen" \
  --exclude "$W/prior-d10-independent.fen" \
  --generator-seed 424243 --out "$W/prior-d12-independent.fen" \
  --manifest "$W/prior-d12-independent.json" \
  > "$W/select-prior-d12.log" 2>&1
[ "$(sha256sum "$W/prior-d12-independent.fen" | awk '{print $1}')" = \
  "$D12_OPENINGS_SHA" ] || die "reconstructed D12 opening pool hash drift"

stage select-independent-confirmation-pool
cp "$IN/prior-turnover-independent.fen" "$W/prior-turnover-independent.fen"
"$J8" --gen-opening-pool "$OPENING_CANDIDATES" \
  "$W/open-candidates.fen" 8 32 20 "$OPENING_SEED" \
  > "$W/open-candidates.log" 2>&1
python3 jobs/tools/select_independent_opening_pool.py \
  --candidates "$W/open-candidates.fen" --expected "$NOPEN" \
  --exclude data/dilf_combinations.fen \
  --exclude "$W/prior-reinforcement.fen" \
  --exclude "$W/prior-meta-screen.fen" \
  --exclude "$W/prior-meta-confirm.fen" \
  --exclude "$W/prior-f2m-confirm.fen" \
  --exclude "$W/prior-f2m-gen2.fen" \
  --exclude "$W/prior-m2-independent.fen" \
  --exclude "$W/prior-d10-independent.fen" \
  --exclude "$W/prior-d12-independent.fen" \
  --exclude "$W/prior-turnover-independent.fen" \
  --generator-seed "$OPENING_SEED" --out "$W/open-eval.fen" \
  --manifest "$ART/independent-openings-manifest.json" \
  > "$W/select-openings.log" 2>&1
[ "$(sha256sum "$W/open-eval.fen" | awk '{print $1}')" = \
  "$EXPECTED_OPENING_SHA256" ] || die "confirmation opening pool hash drift"
[ "$(sha256sum "$W/open-candidates.fen" | awk '{print $1}')" = \
  "$EXPECTED_CANDIDATE_OPENING_SHA256" ] ||
  die "confirmation candidate opening pool hash drift"

wait_all(){
  local label="$1"
  shift
  local fail=0 pid
  for pid in "$@"; do
    wait "$pid" || fail=$((fail+1))
  done
  [ "$fail" -eq 0 ] || die "$label: $fail workers failed"
}
run_gate(){
  local view="$1" opponent="$2"
  local pattern="$W/$opponent.pjtw"
  local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J8" \
    --pattern-a "$W/TURNOVER.pjtw" --pattern-b "$pattern" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 18000 --game-timeout 180 \
    --work-dir "$W/gate-$view-TURNOVER-$opponent" \
    --out "$ART/force/force-$view-TURNOVER-vs-$opponent.json" \
    > "$W/force-$view-TURNOVER-$opponent.log" 2>&1
}

stage force-q00-2000-games-per-cell
run_gate q00 M2 & p_m2=$!
run_gate q00 F2M & p_f2m=$!
wait_all "Q00 confirmation wave" "$p_m2" "$p_f2m"

stage force-native-2000-games-per-cell
run_gate native M2 & p_m2=$!
run_gate native F2M & p_f2m=$!
wait_all "native confirmation wave" "$p_m2" "$p_f2m"

stage aggregate-preregistered-confirmation
python3 jobs/tools/l3_turnover_confirmation.py \
  --force-dir "$ART/force" \
  --previous-evaluation "$IN/turnover-evaluation.json" \
  --opening-manifest "$ART/independent-openings-manifest.json" \
  --expected-opening-seed "$OPENING_SEED" \
  --expected-opening-sha256 "$EXPECTED_OPENING_SHA256" \
  --expected-candidate-sha256 "$EXPECTED_CANDIDATE_OPENING_SHA256" \
  --out "$ART/turnover-confirmation.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" \
  > "$W/aggregate.log" 2>&1
VERDICT="$(python3 - "$ART/turnover-confirmation.json" <<'PY'
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
