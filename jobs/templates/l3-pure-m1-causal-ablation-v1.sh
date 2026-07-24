#!/usr/bin/env bash
# L3-PURE M1 causal diagnostic: isolate which F500 dense-weight block drives
# the P3/P4 trade-off. Diagnostic only; never promotes or continues.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${M1_PREFIX:?}"; : "${C0_PREFIX:?}"; : "${M1_EVAL_PREFIX:?}"
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

NSH_CONV=4; CONV_DEPTH=10; ARB_DEPTH=14; CACHE_MB=128
P3_SHA="050b2e4f4336f2a6d27ff0a6e4aac535a8dd8007f45f9586c7dbfec1aa652f29"
P4_SHA="70cfe5d56544b14ff1d61e0abfd00db40d9298e072c64de982e669cfaea6a221"
C0_SHA="13d9463f32d3378e8ce800c01590a93abcaeaca8ac50fcbbc6c6a79263b090be"
F500_SHA="e3239b094037d5ef220234ef39f0383a254f412afa362f899b3e4e49c1a5f135"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
ARMS=(AB_MAT AB_KING AB_EXTRAS)

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

stage fetch-verified-inputs
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$C0_PREFIX" \
  --file artefacts/g3.pjtw.gz=c0.pjtw.gz --out-dir "$IN" \
  --report "$ART/verified-c0.json" > "$W/fetch-c0.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f500.pjtw.gz=f500.pjtw.gz --out-dir "$IN" \
  --report "$ART/verified-f500.json" > "$W/fetch-f500.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_EVAL_PREFIX" \
  --file artefacts/conversion/C0-p3_mince.json=baseline-C0-p3_mince.json \
  --file artefacts/conversion/C0-p4_egal.json=baseline-C0-p4_egal.json \
  --file artefacts/conversion/F500-p3_mince.json=baseline-F500-p3_mince.json \
  --file artefacts/conversion/F500-p4_egal.json=baseline-F500-p4_egal.json \
  --out-dir "$IN" --report "$ART/verified-baseline-results.json" \
  > "$W/fetch-baselines.log" 2>&1
gunzip -c "$IN/c0.pjtw.gz" > "$W/C0.pjtw"
gunzip -c "$IN/f500.pjtw.gz" > "$W/F500.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
[ "$(sha256sum "$W/C0.pjtw"|awk '{print $1}')" = "$C0_SHA" ] ||
  die "C0 hash drift"
[ "$(sha256sum "$W/F500.pjtw"|awk '{print $1}')" = "$F500_SHA" ] ||
  die "F500 hash drift"

stage construct-weight-ablations
python3 - "$W/C0.pjtw" "$W/F500.pjtw" "$W" "$ART/ablation-manifest.json" <<'PY'
import hashlib,json,struct,sys
from pathlib import Path
c0p,f5p,outdir,manifest=map(Path,sys.argv[1:])
c0=bytearray(c0p.read_bytes()); f5=bytearray(f5p.read_bytes())
def head(raw):
    return struct.unpack_from("<IIIII",raw,0)
hc,hf=head(c0),head(f5)
if hc != hf:
    raise SystemExit(f"header mismatch C0={hc} F500={hf}")
magic,version,scale,npat,next_=hf
if magic != 0x57544A50 or (version&0xff) not in (3,4) or next_ != 120:
    raise SystemExit(f"unsupported PJTW header {hf}")
extmg=20+8*npat; exteg=extmg+4*next_
arms={"AB_MAT":range(116,120),"AB_KING":range(106,120),
      "AB_EXTRAS":range(0,120)}
payload={"schema":1,"source":"F500","donor":"C0","header":{
    "version_word":version,"scale":scale,"n_pattern":npat,"n_extra":next_},
    "arms":{}}
for name,indices in arms.items():
    dst=bytearray(f5)
    idx=list(indices)
    for base in (extmg,exteg):
        for i in idx:
            dst[base+4*i:base+4*(i+1)]=c0[base+4*i:base+4*(i+1)]
    allowed=set()
    for base in (extmg,exteg):
        for i in idx:
            allowed.update(range(base+4*i,base+4*(i+1)))
    bad=[i for i,(a,b) in enumerate(zip(dst,f5)) if a!=b and i not in allowed]
    if bad:
        raise SystemExit(f"{name}: bytes changed outside declared block")
    path=outdir/f"{name}.pjtw"; path.write_bytes(dst)
    payload["arms"][name]={"restored_extra_indices":idx,
      "sha256":hashlib.sha256(dst).hexdigest(),
      "changed_bytes":sum(a!=b for a,b in zip(dst,f5))}
manifest.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
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

jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
b=open(sys.argv[1],"rb").read(8); print(struct.unpack("<I",b[4:])[0])
PY
}
run_conv(){
  local model="$1" stratum="$2" pool="$3" expected="$4"
  local pids=() inputs=() shard out
  for shard in $(seq 0 $((NSH_CONV-1))); do
    out="$W/$model-$stratum-$shard.json"; inputs+=("$out")
    timeout 10800 python3 jobs/tools/conv_fixed_wdl.py \
      --jass "$J8" --defender-jass "$J32" \
      --pattern "$W/$model.pjtw" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$Q00" --defender-search-params "$Q00" \
      --pool-jnnw "$pool" --depth "$CONV_DEPTH" --max-plies 260 \
      --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
      > "$W/$model-$stratum-$shard.log" 2>&1 & pids+=("$!")
  done
  fail=0
  for pid in "${pids[@]}"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$model/$stratum conversion failure"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
    --expected-shards "$NSH_CONV" --expected-records "$expected" \
    --max-error-rate 0.08 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$model-$stratum.json" \
    > "$W/$model-$stratum-aggregate.log" 2>&1
}

stage reproduce-frozen-p3-p4
python3 jobs/tools/split_stratified_fen.py --input "$IN/gauge.fen" \
  --out-dir "$W/strata" --manifest "$ART/gauge-strata.json" \
  > "$W/split.log" 2>&1
for stratum in p3_mince p4_egal; do
  python3 jobs/tools/jnnw_doe.py fen-to-jnnw \
    --input "$W/strata/$stratum.fen" --output "$W/$stratum.raw.jnnw" >/dev/null
  "$J32" --deep-relabel "$W/$stratum.raw.jnnw" "$W/$stratum.rel.jnnw" \
    "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB" \
    > "$W/$stratum-relabel.log" 2>&1
  python3 jobs/tools/jnnw_doe.py keep-decisive \
    --input "$W/$stratum.rel.jnnw" --output "$W/$stratum.dec.jnnw" >/dev/null
  expected="$(jnnw_count "$W/$stratum.dec.jnnw")"
  [ "$expected" -gt 0 ] || die "$stratum empty"
  got="$(sha256sum "$W/$stratum.dec.jnnw"|awk '{print $1}')"
  want="$P3_SHA"; [ "$stratum" = p4_egal ] && want="$P4_SHA"
  [ "$got" = "$want" ] || die "$stratum frozen-pool hash drift got=$got"
done

stage causal-conversion-ablations
for model in "${ARMS[@]}"; do
  for stratum in p3_mince p4_egal; do
    run_conv "$model" "$stratum" "$W/$stratum.dec.jnnw" \
      "$(jnnw_count "$W/$stratum.dec.jnnw")"
  done
done

stage paired-readout
for model in C0 F500; do
  for stratum in p3_mince p4_egal; do
    cp "$IN/baseline-$model-$stratum.json" \
      "$ART/conversion/$model-$stratum.json"
  done
done
python3 - "$ART" <<'PY'
import json,sys
from pathlib import Path
import numpy as np
art=Path(sys.argv[1])
arms=("AB_MAT","AB_KING","AB_EXTRAS")
strata=("p3_mince","p4_egal")
def load(model,s):
    return json.load(open(art/"conversion"/f"{model}-{s}.json"))
def pos(doc):
    return {int(r["index"]):r["result"] for r in doc["position_results"]
            if r["result"] in ("win","loss")}
def paired(candidate,baseline,seed):
    ca,ba=pos(candidate),pos(baseline)
    ids=sorted(set(ca)&set(ba))
    d=np.array([(ca[i]=="win")-(ba[i]=="win") for i in ids],dtype=int)
    counts=np.array([(d==-1).sum(),(d==0).sum(),(d==1).sum()])
    rng=np.random.default_rng(seed)
    boot=rng.multinomial(len(d),counts/counts.sum(),size=200000)
    bd=(boot[:,2]-boot[:,0])/len(d)
    return {"n_common":len(d),"candidate_rate":float(np.mean([ca[i]=="win" for i in ids])),
      "baseline_rate":float(np.mean([ba[i]=="win" for i in ids])),
      "delta":float(d.mean()),"ci_low":float(np.quantile(bd,.025)),
      "ci_high":float(np.quantile(bd,.975)),
      "loss_to_win":int((d==1).sum()),"win_to_loss":int((d==-1).sum())}
conversion={}
for m in ("C0","F500")+arms:
    conversion[m]={s:{k:load(m,s)[k] for k in
      ("n_pos","n_win","n_draw","n_loss","conversion")} for s in strata}
comparisons={}
for mi,m in enumerate(arms):
    comparisons[m]={}
    for si,s in enumerate(strata):
        comparisons[m][s]={
          "vs_C0":paired(load(m,s),load("C0",s),91000+mi*10+si),
          "vs_F500":paired(load(m,s),load("F500",s),92000+mi*10+si)}
payload={"schema":1,"verdict":"M1_CAUSAL_ABLATION_READY_HUMAN_REVIEW",
 "question":"Which F500 dense-weight block drives the P3/P4 trade-off?",
 "arms":{
   "AB_MAT":"F500 with extras 116:120 restored from C0",
   "AB_KING":"F500 with extras 106:120 restored from C0",
   "AB_EXTRAS":"F500 with all extras 0:120 restored from C0; patterns retained"},
 "conversion":conversion,"paired_comparisons":comparisons,
 "promotion_authorized":False,"automatic_next_job":None}
(art/"causal-ablation.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
(art/"JASS_CONTROL_SUMMARY.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
(art/"VERDICT__M1_CAUSAL_ABLATION_READY_HUMAN_REVIEW").write_text(
 "M1_CAUSAL_ABLATION_READY_HUMAN_REVIEW\n")
(art/"PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art/"AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
PY
stage complete
say "M1_CAUSAL_ABLATION_READY_HUMAN_REVIEW promotion=false"
