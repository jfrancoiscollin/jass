#!/usr/bin/env bash
# L3-PURE M1 evaluation: common force and fixed-defender conversion.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${M1_PREFIX:?}"; : "${C0_PREFIX:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$IN" "$ART/conversion"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/stage.txt"
: > "$RES"; echo preflight > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
MON=""
monitor(){ (while true; do { date -Is; printf 'stage=%s\n' "$(cat "$STAGE")"; } > "$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 60; done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; [ -z "$MON" ] || kill "$MON" 2>/dev/null; cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"; (cd "$W" && find . -name '*.log' -type f -print0|tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null||true; rm -rf "$W/build8" "$W/build32" "$IN"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

NOPEN=200; NSH_GATE=8; PAR_GATE=2; DEPTH=9; MOVETIME=0.1
NSH_CONV=4; CONV_DEPTH=10; ARB_DEPTH=14; CACHE_MB=128
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
MODELS=(F500 F2M R2M); ALL=(C0 F500 F2M R2M)

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(tr ',' '\n' <<<"$Q00"|wc -l)" -eq 63 ] || die "Q00 drift"
monitor

stage fetch-verified-models
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$C0_PREFIX" \
  --file artefacts/g3.pjtw.gz=c0.pjtw.gz --out-dir "$IN" \
  --report "$ART/verified-c0.json" > "$W/fetch-c0.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f500.pjtw.gz=f500.pjtw.gz \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/r2m.pjtw.gz=r2m.pjtw.gz \
  --file artefacts/m1-training-summary.json=training-summary.json \
  --out-dir "$IN" --report "$ART/verified-m1.json" > "$W/fetch-m1.log" 2>&1
gunzip -c "$IN/c0.pjtw.gz" > "$W/C0.pjtw"
gunzip -c "$IN/f500.pjtw.gz" > "$W/F500.pjtw"
gunzip -c "$IN/f2m.pjtw.gz" > "$W/F2M.pjtw"
gunzip -c "$IN/r2m.pjtw.gz" > "$W/R2M.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
cp "$IN/training-summary.json" "$ART/m1-training-summary.json"

stage build-8cf-and-32cf
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"; export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1; cmake --build "$W/build8" -j4 --target jass > "$W/build8.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1; cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
J8="$W/build8/jass"; J32="$W/build32/jass"
awk -v limit="$NOPEN" '/^[[:space:]]*#/ {next} {sub(/#.*/,""); if(NF){print;n++;if(n>=limit)exit}}' data/dilf_combinations.fen > "$W/open.fen"
[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "opening pool short"

run_gate_group(){
  local view="$1" opponent="$2"; local pids=() model args=()
  [ "$view" = q00 ] && args=(--depth "$DEPTH") || args=(--movetime "$MOVETIME")
  for model in "${MODELS[@]}"; do
    jb="$J8"; [ "$opponent" = GEN2 ] && jb="$J32"
    timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
      --jass-a "$J8" --jass-b "$jb" --pattern-a "$W/$model.pjtw" --pattern-b "$W/$opponent.pjtw" \
      --search-params-a "$Q00" --search-params-b "$Q00" --openings-file "$W/open.fen" \
      "${args[@]}" --pairs 1 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" --timeout 10800 \
      --work-dir "$W/gate-$view-$model-$opponent" --out "$ART/force-$view-$model-vs-$opponent.json" \
      > "$W/force-$view-$model-$opponent.log" 2>&1 & pids+=("$!")
  done
  fail=0; for pid in "${pids[@]}"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$view/$opponent gate failure"
}
stage force-q00-vs-c0
run_gate_group q00 C0
stage force-native-vs-c0
run_gate_group native C0
stage force-q00-vs-gen2
run_gate_group q00 GEN2

jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
b=open(sys.argv[1],"rb").read(8); print(struct.unpack("<I",b[4:])[0])
PY
}
run_conv(){
  local model="$1" stratum="$2" pool="$3" expected="$4"; local pids=() inputs=() shard out
  for shard in $(seq 0 $((NSH_CONV-1))); do
    out="$W/$model-$stratum-$shard.json"; inputs+=("$out")
    timeout 10800 python3 jobs/tools/conv_fixed_wdl.py --jass "$J8" --defender-jass "$J32" \
      --pattern "$W/$model.pjtw" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$Q00" --defender-search-params "$Q00" --pool-jnnw "$pool" \
      --depth "$CONV_DEPTH" --max-plies 260 --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
      > "$W/$model-$stratum-$shard.log" 2>&1 & pids+=("$!")
  done
  fail=0; for pid in "${pids[@]}"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$model/$stratum conversion failure"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" --expected-shards "$NSH_CONV" \
    --expected-records "$expected" --max-error-rate 0.08 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$model-$stratum.json" > "$W/$model-$stratum-aggregate.log" 2>&1
}

stage fixed-defender-conversion
python3 jobs/tools/split_stratified_fen.py --input "$IN/gauge.fen" --out-dir "$W/strata" --manifest "$ART/gauge-strata.json" > "$W/split.log" 2>&1
for stratum in p1_net p2_moyen p3_mince p4_egal; do
  python3 jobs/tools/jnnw_doe.py fen-to-jnnw --input "$W/strata/$stratum.fen" --output "$W/$stratum.raw.jnnw" >/dev/null
  "$J32" --deep-relabel "$W/$stratum.raw.jnnw" "$W/$stratum.rel.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB" > "$W/$stratum-relabel.log" 2>&1
  python3 jobs/tools/jnnw_doe.py keep-decisive --input "$W/$stratum.rel.jnnw" --output "$W/$stratum.dec.jnnw" >/dev/null
  expected="$(jnnw_count "$W/$stratum.dec.jnnw")"; [ "$expected" -gt 0 ] || die "$stratum empty"
  for model in "${ALL[@]}"; do run_conv "$model" "$stratum" "$W/$stratum.dec.jnnw" "$expected"; done
done

stage aggregate
python3 - "$ART" <<'PY'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); models=("F500","F2M","R2M"); all_models=("C0",)+models
force={}
for m in models:
    force[m]={}
    for view,opp in (("q00","C0"),("native","C0"),("q00","GEN2")):
        p=json.load(open(art/f"force-{view}-{m}-vs-{opp}.json"))
        force[m][f"{view}_vs_{opp}"]={k:p[k] for k in ("n","wins_a","draws","wins_b","rate","elo","ci_low","ci_high")}
conversion={}
for m in all_models:
    conversion[m]={}
    for s in ("p1_net","p2_moyen","p3_mince","p4_egal"):
        p=json.load(open(art/"conversion"/f"{m}-{s}.json"))
        conversion[m][s]={k:p[k] for k in ("n_pos","n_win","n_draw","n_loss","conversion")}
payload={"schema":1,"verdict":"M1_EVALUATION_READY_HUMAN_REVIEW","force":force,
 "fixed_defender_conversion":conversion,"promotion_authorized":False,"automatic_next_job":None}
(art/"m1-evaluation.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
(art/"JASS_CONTROL_SUMMARY.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
(art/"VERDICT__M1_EVALUATION_READY_HUMAN_REVIEW").write_text("M1_EVALUATION_READY_HUMAN_REVIEW\n")
(art/"PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art/"AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
PY
stage complete
say "M1_EVALUATION_READY_HUMAN_REVIEW promotion=false"
