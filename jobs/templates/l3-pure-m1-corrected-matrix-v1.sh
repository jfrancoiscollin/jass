#!/usr/bin/env bash
# Corrected retrospective M1 matrix on the immutable stable 0954 JNNW gauge.
# Diagnostic only: no promotion and no automatic continuation.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${GAUGE_PREFIX:?}"; : "${C0_PREFIX:?}"; : "${P1_PREFIX:?}"
: "${M1_PREFIX:?}"; : "${ABLATION_PREFIX:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$IN" "$ART/conversion"
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
  rm -rf "$W/build8" "$W/build32" "$IN"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

NSH_CONV=4; PAR_MODEL_GROUPS=2; CONV_DEPTH=10; CACHE_MB=128
NOPEN=200; NSH_GATE=8; PAR_GATE=2; FORCE_DEPTH=9; MOVETIME=0.1
TARGET_PER_STRATUM=300; BOOTSTRAP_SAMPLES=200000; MATRIX_SEED=955001
MODELS=(C0 P1 F500 F2M R2M AB_MAT AB_KING AB_EXTRAS)
STRATA=(p3_mince p4_egal)
C0_SHA="13d9463f32d3378e8ce800c01590a93abcaeaca8ac50fcbbc6c6a79263b090be"
P1_SHA="93c76031be3a039aa08eec4a1d3166321d93d602ca78a139509f8c6e90de5e86"
F500_SHA="e3239b094037d5ef220234ef39f0383a254f412afa362f899b3e4e49c1a5f135"
F2M_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
R2M_SHA="1e089a88fa3d65807d66819ed4fa01effcd8a9b18518650e748a292e77556bdf"
AB_MAT_SHA="ef85876c7aca9bb91c63c62d0175cd5ccd18b146b3e516148c9cd162057b0bdc"
AB_KING_SHA="522022e361dca85ba1fe102bd370e5efda773199ca50ca1e37a09b5ff3fe877d"
AB_EXTRAS_SHA="c86da4bd7ce2d2cb9e1b73ccec9785a770d4727c51b875a03fe9e6edd865ba94"
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"
OLD_GAUGE_SHA="e5e20043a1c32916548f76fd1ff430efa1f1a2156ceefca6c3c8470dfb9b9c72"
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

jnnw_count(){ python3 - "$1" <<'PY'
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
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --file artefacts/holdout-provenance.json=gauge-provenance.json \
  --file artefacts/p3_mince-stability.json=p3-stability.json \
  --file artefacts/p4_egal-stability.json=p4-stability.json \
  --out-dir "$IN" --report "$ART/verified-corrected-gauge.json" \
  > "$W/fetch-gauge.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$C0_PREFIX" \
  --file artefacts/g3.pjtw.gz=c0.pjtw.gz --out-dir "$IN" \
  --report "$ART/verified-c0.json" > "$W/fetch-c0.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$P1_PREFIX" \
  --file artefacts/g4.pjtw.gz=p1.pjtw.gz \
  --file artefacts/l3-pure-p1-manifest.json=p1-manifest.json \
  --out-dir "$IN" --report "$ART/verified-p1.json" > "$W/fetch-p1.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f500.pjtw.gz=f500.pjtw.gz \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/r2m.pjtw.gz=r2m.pjtw.gz \
  --file artefacts/m1-training-summary.json=m1-training-summary.json \
  --out-dir "$IN" --report "$ART/verified-m1.json" > "$W/fetch-m1.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$ABLATION_PREFIX" \
  --file work/AB_MAT.pjtw=ab-mat.pjtw \
  --file work/AB_KING.pjtw=ab-king.pjtw \
  --file work/AB_EXTRAS.pjtw=ab-extras.pjtw \
  --file artefacts/ablation-manifest.json=ablation-manifest.json \
  --out-dir "$IN" --report "$ART/verified-ablations.json" \
  > "$W/fetch-ablations.log" 2>&1

gunzip -c "$IN/c0.pjtw.gz" > "$W/C0.pjtw"
gunzip -c "$IN/p1.pjtw.gz" > "$W/P1.pjtw"
gunzip -c "$IN/f500.pjtw.gz" > "$W/F500.pjtw"
gunzip -c "$IN/f2m.pjtw.gz" > "$W/F2M.pjtw"
gunzip -c "$IN/r2m.pjtw.gz" > "$W/R2M.pjtw"
cp "$IN/ab-mat.pjtw" "$W/AB_MAT.pjtw"
cp "$IN/ab-king.pjtw" "$W/AB_KING.pjtw"
cp "$IN/ab-extras.pjtw" "$W/AB_EXTRAS.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"

for spec in \
  "C0:$C0_SHA" "P1:$P1_SHA" "F500:$F500_SHA" "F2M:$F2M_SHA" \
  "R2M:$R2M_SHA" "AB_MAT:$AB_MAT_SHA" "AB_KING:$AB_KING_SHA" \
  "AB_EXTRAS:$AB_EXTRAS_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  got="$(sha256sum "$W/$name.pjtw"|awk '{print $1}')"
  [ "$got" = "$want" ] || die "$name hash drift got=$got"
done
for spec in "p3_mince:$P3_GAUGE_SHA" "p4_egal:$P4_GAUGE_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  got="$(sha256sum "$W/$name.jnnw"|awk '{print $1}')"
  [ "$got" = "$want" ] || die "$name gauge hash drift got=$got"
  [ "$(jnnw_count "$W/$name.jnnw")" -eq "$TARGET_PER_STRATUM" ] ||
    die "$name gauge count drift"
done
cp "$IN/gauge-provenance.json" "$ART/corrected-gauge-provenance.json"
cp "$IN/p3-stability.json" "$ART/p3_mince-stability.json"
cp "$IN/p4-stability.json" "$ART/p4_egal-stability.json"
cp "$IN/p1-manifest.json" "$ART/p1-manifest.json"
cp "$IN/m1-training-summary.json" "$ART/m1-training-summary.json"
cp "$IN/ablation-manifest.json" "$ART/ablation-manifest.json"

python3 - "$ART/gauge-invalidation-register.json" "$OLD_GAUGE_SHA" \
  "$P3_GAUGE_SHA" "$P4_GAUGE_SHA" "$GAUGE_PREFIX" <<'PY'
import json,sys
from pathlib import Path
out,old,p3,p4,prefix=sys.argv[1:]
payload={
 "schema":1,
 "incident":"black men and kings were swapped by rec_to_fen",
 "bugfix_commit":"8efd1c45dd5355db0a4825d7fd9a48fa3704db8c",
 "invalidated_gauge":{
   "sha256":old,
   "source_job":"ccx33-0718-mine-tip",
   "source_path":"artefacts/conv_self_eval_strat_v2.fen",
   "source_blob":"ff359c28c6e6ccdc491635141a2167ea0fe896be"},
 "superseded_readouts":[
   "home-0945-l3-pure-m1-eval-v1 conversion",
   "home-0949-l3-pure-m1-causal-ablation-v1 conversion",
   "all conversion readouts derived from the invalidated FEN gauge"],
 "not_invalidated":[
   "M0 direct force triangle",
   "C0/P1/M1 model weights",
   "AB_MAT/AB_KING/AB_EXTRAS weight constructions"],
 "replacement":{
   "source_job":"home-0954-l3-pure-m1-abextras-validation-v5",
   "source_prefix":prefix,
   "format":"JNNW, selected directly from certified records",
   "p3_mince_sha256":p3,
   "p4_egal_sha256":p4,
   "records_per_stratum":300}}
Path(out).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
PY

stage build-exact-8cf-and-32cf
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j4 --target jass > "$W/build8.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
J8="$W/build8/jass"; J32="$W/build32/jass"

run_conv(){
  local model="$1" stratum="$2" pool="$3"
  local pids=() inputs=() shard out
  for shard in $(seq 0 $((NSH_CONV-1))); do
    out="$W/$model-$stratum-$shard.json"; inputs+=("$out")
    timeout 14400 python3 jobs/tools/conv_fixed_wdl.py \
      --jass "$J8" --defender-jass "$J32" \
      --pattern "$W/$model.pjtw" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$Q00" --defender-search-params "$Q00" \
      --pool-jnnw "$pool" --depth "$CONV_DEPTH" --max-plies 260 \
      --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
      > "$W/$model-$stratum-$shard.log" 2>&1 & pids+=("$!")
  done
  wait_all "$model/$stratum conversion" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
    --expected-shards "$NSH_CONV" --expected-records "$TARGET_PER_STRATUM" \
    --max-error-rate 0.08 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$model-$stratum.json" \
    > "$W/$model-$stratum-aggregate.log" 2>&1
}
run_model_batches(){
  local stratum="$1" pool="$2"; local pids=() model
  for model in "${MODELS[@]}"; do
    run_conv "$model" "$stratum" "$pool" & pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR_MODEL_GROUPS" ]; then
      wait_all "$stratum model batch" "${pids[@]}"; pids=()
    fi
  done
  [ "${#pids[@]}" -eq 0 ] || wait_all "$stratum model batch" "${pids[@]}"
}

stage corrected-fixed-defender-matrix
for stratum in "${STRATA[@]}"; do
  run_model_batches "$stratum" "$W/$stratum.jnnw"
done

stage preregistered-paired-selection
python3 jobs/tools/l3_corrected_conversion_matrix.py \
  --conversion-dir "$ART/conversion" --models "${MODELS[@]}" \
  --strata "${STRATA[@]}" --baseline C0 --primary-stratum p4_egal \
  --preservation-stratum p3_mince --bootstrap-samples "$BOOTSTRAP_SAMPLES" \
  --seed "$MATRIX_SEED" --out "$ART/corrected-matrix-preselection.json"
CANDIDATE="$(python3 - "$ART/corrected-matrix-preselection.json" <<'PY'
import json,sys
value=json.load(open(sys.argv[1])).get("selected_challenger_for_force_review")
print(value or "")
PY
)"
printf '%s\n' "${CANDIDATE:-NONE}" > "$ART/force-review-candidate.txt"

if [ -n "$CANDIDATE" ]; then
  stage force-review-selected-challenger
  awk -v limit="$NOPEN" '/^[[:space:]]*#/ {next} {sub(/#.*/,""); if(NF){print;n++;if(n>=limit)exit}}' \
    data/dilf_combinations.fen > "$W/open.fen"
  [ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "opening pool short"
  run_force(){
    local view="$1" opponent="$2" jb="$J8"; local args=()
    [ "$opponent" = GEN2 ] && jb="$J32"
    [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
      args=(--movetime "$MOVETIME")
    timeout 18000 python3 jobs/tools/run_jass_gate_bounded.py \
      --jass-a "$J8" --jass-b "$jb" \
      --pattern-a "$W/$CANDIDATE.pjtw" --pattern-b "$W/$opponent.pjtw" \
      --search-params-a "$Q00" --search-params-b "$Q00" \
      --openings-file "$W/open.fen" "${args[@]}" --pairs 1 \
      --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" --timeout 14400 \
      --work-dir "$W/gate-$view-$opponent" \
      --out "$ART/force-$view-$CANDIDATE-vs-$opponent.json" \
      > "$W/force-$view-$opponent.log" 2>&1
  }
  pids=()
  run_force q00 C0 & pids+=("$!")
  run_force native C0 & pids+=("$!")
  run_force q00 GEN2 & pids+=("$!")
  wait_all force-review "${pids[@]}"
fi

stage aggregate-corrected-verdict
FINAL_ARGS=()
[ -z "$CANDIDATE" ] || FINAL_ARGS=(--force-dir "$ART")
python3 jobs/tools/l3_corrected_conversion_matrix.py \
  --conversion-dir "$ART/conversion" --models "${MODELS[@]}" \
  --strata "${STRATA[@]}" --baseline C0 --primary-stratum p4_egal \
  --preservation-stratum p3_mince --bootstrap-samples "$BOOTSTRAP_SAMPLES" \
  --seed "$MATRIX_SEED" "${FINAL_ARGS[@]}" \
  --out "$ART/corrected-conversion-matrix.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json"
printf '%s\n' M1_CORRECTED_CONVERSION_MATRIX_READY_HUMAN_REVIEW \
  > "$ART/VERDICT__M1_CORRECTED_CONVERSION_MATRIX_READY_HUMAN_REVIEW"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "M1_CORRECTED_CONVERSION_MATRIX_READY_HUMAN_REVIEW promotion=false candidate=${CANDIDATE:-NONE}"
