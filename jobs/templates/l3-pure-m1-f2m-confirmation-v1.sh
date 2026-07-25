#!/usr/bin/env bash
# Independent powered F2M confirmation after repaired M1 review.
# No training and no automatic promotion/continuation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${M1_PREFIX:?}"; : "${C0_PREFIX:?}"; : "${MATRIX_PREFIX:?}"
: "${REVIEW_PREFIX:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$IN" "$ART/force"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/stage.txt"
: > "$RES"; echo preflight > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
MON=""
monitor(){
  (while true; do
    { date -Is; printf 'stage=%s\n' "$(cat "$STAGE")"; } > "$PROG.tmp"
    mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 60
  done) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
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

NOPEN=500; NSH_GATE=16; FORCE_DEPTH=9; MOVETIME=0.1; CACHE_MB=128
OPENING_SEED=173205
C0_SHA="13d9463f32d3378e8ce800c01590a93abcaeaca8ac50fcbbc6c6a79263b090be"
F2M_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
R2M_SHA="1e089a88fa3d65807d66819ed4fa01effcd8a9b18518650e748a292e77556bdf"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(tr ',' '\n' <<<"$Q00"|wc -l)" -eq 63 ] || die "Q00 drift"
monitor

wait_all(){
  local label="$1"; shift; local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail workers failed"
}

stage fetch-and-verify-selection
python3 jobs/tools/fetch_result_files.py --prefix "$REVIEW_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=repaired-review.json \
  --out-dir "$IN" --report "$ART/verified-repaired-review.json" \
  > "$W/fetch-review.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$MATRIX_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=repaired-matrix.json \
  --out-dir "$IN" --report "$ART/verified-repaired-matrix.json" \
  > "$W/fetch-matrix.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$C0_PREFIX" \
  --file artefacts/g3.pjtw.gz=c0.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-c0.json" > "$W/fetch-c0.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/r2m.pjtw.gz=r2m.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-m1.json" > "$W/fetch-m1.log" 2>&1
gunzip -c "$IN/c0.pjtw.gz" > "$W/C0.pjtw"
gunzip -c "$IN/f2m.pjtw.gz" > "$W/F2M.pjtw"
gunzip -c "$IN/r2m.pjtw.gz" > "$W/R2M.pjtw"
for spec in "C0:$C0_SHA" "F2M:$F2M_SHA" "R2M:$R2M_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  got="$(sha256sum "$W/$name.pjtw"|awk '{print $1}')"
  [ "$got" = "$want" ] || die "$name hash drift got=$got"
done
python3 - "$IN/repaired-review.json" "$IN/repaired-matrix.json" <<'PY'
import json,sys
review,matrix=(json.load(open(p)) for p in sys.argv[1:])
if review.get("verdict")!="M1_REPAIRED_FORCE_COVERAGE_REVIEW_READY":
    raise SystemExit("0963 review verdict mismatch")
if review.get("selected_m1_arm_for_confirmation")!="F2M":
    raise SystemExit("0963 did not select F2M")
if review.get("eligible_arms",[None])[0]!="F2M":
    raise SystemExit("F2M is not top-ranked")
if matrix.get("verdict")!="M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW":
    raise SystemExit("0962 matrix verdict mismatch")
if "F2M" not in matrix.get("m1_arms_passing_floor",[]):
    raise SystemExit("F2M conversion floor missing")
PY

stage build-and-test-repaired-engine
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j4 --target jass jass_tests > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "equivalent king-capture paths were not deduplicated"
[ "$("$J8" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
  die "tablebase-draw witness legal moves mismatch"

stage independent-opening-pool
"$J8" --gen-opening-pool 768 "$W/prior-reinforcement.fen" 8 32 20 271828 \
  > "$W/open-prior-reinforcement.log" 2>&1
"$J8" --gen-opening-pool 128 "$W/prior-meta-screen.fen" 8 32 20 161803 \
  > "$W/open-prior-screen.log" 2>&1
"$J8" --gen-opening-pool 256 "$W/prior-meta-confirm.fen" 8 32 20 141421 \
  > "$W/open-prior-confirm.log" 2>&1
"$J8" --gen-opening-pool "$NOPEN" "$W/open-confirm.fen" 8 32 20 "$OPENING_SEED" \
  > "$W/open-confirm.log" 2>&1
python3 jobs/tools/validate_opening_pool.py \
  --pool "$W/open-confirm.fen" --expected "$NOPEN" \
  --exclude data/dilf_combinations.fen \
  --exclude "$W/prior-reinforcement.fen" \
  --exclude "$W/prior-meta-screen.fen" \
  --exclude "$W/prior-meta-confirm.fen" \
  --generator-seed "$OPENING_SEED" \
  --out "$ART/independent-openings-manifest.json" \
  > "$W/validate-openings.log" 2>&1
sha256sum "$W/open-confirm.fen" > "$ART/independent-openings.sha256"

run_gate(){
  local view="$1" opponent="$2" parallel="$3"; local jb="$W/$opponent.pjtw"
  local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass "$J8" --pattern-a "$W/F2M.pjtw" --pattern-b "$jb" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-confirm.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$parallel" \
    --timeout 10800 --game-timeout 180 \
    --work-dir "$W/gate-$view-F2M-$opponent" \
    --out "$ART/force/force-$view-F2M-vs-$opponent.json" \
    > "$W/force-$view-F2M-$opponent.log" 2>&1
}
run_wave(){
  local view="$1" parallel="$2"; local pids=()
  run_gate "$view" C0 "$parallel" & pids+=("$!")
  run_gate "$view" R2M "$parallel" & pids+=("$!")
  wait_all "$view confirmation wave" "${pids[@]}"
}

stage independent-q00-confirmation
run_wave q00 4
stage independent-native-confirmation
run_wave native 4

stage aggregate-human-review
python3 jobs/tools/l3_f2m_independent_confirmation.py \
  --review "$IN/repaired-review.json" --matrix "$IN/repaired-matrix.json" \
  --force-dir "$ART/force" \
  --opening-manifest "$ART/independent-openings-manifest.json" \
  --out "$ART/f2m-independent-confirmation.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" > "$W/aggregate.log" 2>&1
VERDICT="$(python3 - "$ART/f2m-independent-confirmation.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["verdict"])
PY
)"
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE \
  > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL \
  > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "$VERDICT promotion=false automatic_next_job=null"
