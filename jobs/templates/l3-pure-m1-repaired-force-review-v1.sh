#!/usr/bin/env bash
# Repaired-engine force and exact-corpus 8cf coverage review for M1.
# Diagnostic selection only: no confirmation, promotion, or continuation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${M1_PREFIX:?}"; : "${C0_PREFIX:?}"; : "${MATRIX_PREFIX:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/force" "$ART/coverage"
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
  rm -rf "$W/build8" "$W/build32" "$W/baseline-code" "$IN" "$GEOM"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

MODELS=(F500 F2M R2M)
NOPEN=200; NSH_GATE=8; FORCE_DEPTH=9; MOVETIME=0.1; CACHE_MB=128
BASELINE_CODE_SHA="038a2001854f2805bc0045acd56c617826e5ff15"
C0_SHA="13d9463f32d3378e8ce800c01590a93abcaeaca8ac50fcbbc6c6a79263b090be"
F500_SHA="e3239b094037d5ef220234ef39f0383a254f412afa362f899b3e4e49c1a5f135"
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

jnnw_count(){
  python3 - "$1" <<'PY'
import struct,sys
raw=open(sys.argv[1],"rb").read(8)
if len(raw)!=8 or raw[:4]!=b"JNNW":
    raise SystemExit("invalid JNNW header")
print(struct.unpack("<I",raw[4:])[0])
PY
}
wait_all(){
  local label="$1"; shift; local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail workers failed"
}

stage fetch-and-verify-immutable-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$MATRIX_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=repaired-matrix.json \
  --out-dir "$IN" --report "$ART/verified-repaired-matrix.json" \
  > "$W/fetch-matrix.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$C0_PREFIX" \
  --file artefacts/g3.pjtw.gz=c0.pjtw.gz \
  --file artefacts/g1-selfplay.jnnw.gz=hist-g1.jnnw.gz \
  --file artefacts/g2-selfplay.jnnw.gz=hist-g2.jnnw.gz \
  --file artefacts/g3-selfplay.jnnw.gz=hist-g3.jnnw.gz \
  --file artefacts/l3-pure-manifest.json=c0-manifest.json \
  --out-dir "$IN" --report "$ART/verified-c0.json" > "$W/fetch-c0.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f500.pjtw.gz=f500.pjtw.gz \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/r2m.pjtw.gz=r2m.pjtw.gz \
  --file artefacts/common-fresh-500k.jnnw.gz=common.jnnw.gz \
  --file artefacts/extra-fresh-1500k.jnnw.gz=extra.jnnw.gz \
  --file artefacts/m1-arm-contract.json=m1-arm-contract.json \
  --file artefacts/m1-training-summary.json=m1-training-summary.json \
  --out-dir "$IN" --report "$ART/verified-m1.json" > "$W/fetch-m1.log" 2>&1
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1

gunzip -c "$IN/c0.pjtw.gz" > "$W/C0.pjtw"
gunzip -c "$IN/f500.pjtw.gz" > "$W/F500.pjtw"
gunzip -c "$IN/f2m.pjtw.gz" > "$W/F2M.pjtw"
gunzip -c "$IN/r2m.pjtw.gz" > "$W/R2M.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/common.jnnw.gz" > "$W/common.jnnw"
gunzip -c "$IN/extra.jnnw.gz" > "$W/extra.jnnw"
for g in 1 2 3; do
  gunzip -c "$IN/hist-g${g}.jnnw.gz" > "$W/hist-g${g}.jnnw"
done
cp "$IN/m1-training-summary.json" "$ART/m1-training-summary.json"
cp "$IN/m1-arm-contract.json" "$ART/m1-arm-contract.json"

for spec in \
  "C0:$C0_SHA" "F500:$F500_SHA" "F2M:$F2M_SHA" "R2M:$R2M_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  got="$(sha256sum "$W/$name.pjtw"|awk '{print $1}')"
  [ "$got" = "$want" ] || die "$name hash drift got=$got"
done
python3 - "$IN/repaired-matrix.json" "$IN/m1-training-summary.json" \
  "$IN/m1-arm-contract.json" "$IN/c0-manifest.json" <<'PY'
import json,sys
matrix,training,contract,c0=(json.load(open(p)) for p in sys.argv[1:])
if matrix.get("verdict")!="M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW":
    raise SystemExit("repaired matrix verdict mismatch")
if training.get("verdict")!="M1_TRAINING_SCREEN_READY":
    raise SystemExit("M1 training verdict mismatch")
if contract.get("same_parent") is not True or contract.get("same_common_500k") is not True:
    raise SystemExit("M1 common-parent contract mismatch")
if contract.get("r2m_exact_history")!="C0_G1_G2_G3":
    raise SystemExit("R2M replay contract mismatch")
if c0.get("arm")!="A" or c0.get("generations")!=3:
    raise SystemExit("C0 parent manifest mismatch")
PY
[ "$(jnnw_count "$W/common.jnnw")" -eq 500000 ] ||
  die "common fresh corpus count drift"
[ "$(jnnw_count "$W/extra.jnnw")" -eq 1500000 ] ||
  die "extra fresh corpus count drift"

stage build-and-test-repaired-engine
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  die "8cf geometry mismatch"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j4 --target jass jass_tests > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
mkdir -p "$W/baseline-code"
git cat-file -e "$BASELINE_CODE_SHA^{commit}"
git archive "$BASELINE_CODE_SHA" | tar -x -C "$W/baseline-code"
python3 "$W/baseline-code/pattern_jass/tools/gen_patterns.py" \
  --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S "$W/baseline-code" -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
J8="$W/build8/jass"; J32="$W/build32/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "equivalent king-capture paths were not deduplicated"
[ "$("$J8" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
  die "tablebase-draw witness legal moves mismatch"

stage exact-training-corpus-coverage
env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py \
  --data "$W/hist-g1.jnnw" "$W/hist-g2.jnnw" "$W/hist-g3.jnnw" \
  --out "$ART/coverage/C0-coverage.json" > "$W/coverage-C0.log" 2>&1
env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py \
  --data "$W/common.jnnw" \
  --out "$ART/coverage/F500-coverage.json" > "$W/coverage-F500.log" 2>&1
env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py \
  --data "$W/common.jnnw" "$W/extra.jnnw" \
  --out "$ART/coverage/F2M-coverage.json" > "$W/coverage-F2M.log" 2>&1
env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py \
  --data "$W/common.jnnw" "$W/hist-g1.jnnw" "$W/hist-g2.jnnw" "$W/hist-g3.jnnw" \
  --out "$ART/coverage/R2M-coverage.json" > "$W/coverage-R2M.log" 2>&1

awk -v limit="$NOPEN" \
  '/^[[:space:]]*#/ {next} {sub(/#.*/,""); if(NF){print;n++;if(n>=limit)exit}}' \
  data/dilf_combinations.fen > "$W/open.fen"
[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "opening pool short"

run_force_wave(){
  local view="$1" opponent="$2" parallel="$3"; local pids=() model jb
  local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  for model in "${MODELS[@]}"; do
    jb="$J8"; [ "$opponent" = GEN2 ] && jb="$J32"
    timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
      --jass-a "$J8" --jass-b "$jb" \
      --pattern-a "$W/$model.pjtw" --pattern-b "$W/$opponent.pjtw" \
      --search-params-a "$Q00" --search-params-b "$Q00" \
      --openings-file "$W/open.fen" "${args[@]}" --pairs 1 \
      --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$parallel" \
      --timeout 10800 --game-timeout 180 \
      --work-dir "$W/gate-$view-$model-$opponent" \
      --out "$ART/force/force-$view-$model-vs-$opponent.json" \
      > "$W/force-$view-$model-$opponent.log" 2>&1 & pids+=("$!")
  done
  wait_all "$view/$opponent force wave" "${pids[@]}"
}

stage force-q00-vs-c0-and-gen2
run_force_wave q00 C0 1 & p_c0=$!
run_force_wave q00 GEN2 1 & p_gen2=$!
wait_all "Q00 force waves" "$p_c0" "$p_gen2"
stage force-native-vs-c0
run_force_wave native C0 2

stage aggregate-human-review
python3 jobs/tools/l3_repaired_m1_force_review.py \
  --matrix "$IN/repaired-matrix.json" \
  --force-dir "$ART/force" --coverage-dir "$ART/coverage" \
  --training-summary "$IN/m1-training-summary.json" \
  --out "$ART/m1-repaired-force-coverage-review.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" > "$W/aggregate.log" 2>&1
SELECTED="$(python3 - "$ART/m1-repaired-force-coverage-review.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1])).get("selected_m1_arm_for_confirmation") or "NONE")
PY
)"
printf '%s\n' M1_REPAIRED_FORCE_COVERAGE_REVIEW_READY \
  > "$ART/VERDICT__M1_REPAIRED_FORCE_COVERAGE_REVIEW_READY"
printf '%s\n' "SELECTED_M1_ARM_FOR_CONFIRMATION__$SELECTED" \
  > "$ART/SELECTED_M1_ARM_FOR_CONFIRMATION__$SELECTED"
printf '%s\n' CONFIRMATION_AUTHORIZED__FALSE \
  > "$ART/CONFIRMATION_AUTHORIZED__FALSE"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE \
  > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL \
  > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "M1_REPAIRED_FORCE_COVERAGE_REVIEW_READY selected=$SELECTED confirmation=false promotion=false"
