#!/usr/bin/env bash
# Independent validation of the M1 AB_EXTRAS diagnostic candidate.
# Generates a candidate-blind P3/P4 holdout from fixed C0 play, evaluates
# conversion and general force, and never promotes or continues automatically.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${C0_PREFIX:?}"; : "${M1_PREFIX:?}"; : "${ABLATION_PREFIX:?}"
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

TOTAL_GAMES="${HOLDOUT_GAMES:-12000}"
GEN_DEPTH=10; GEN_MAX_PLIES=220; GEN_MIN_PIECES=36
GEN_SEED=950027; NSH_GEN=8; PAR_GEN=8; GEN_TIMEOUT=14400
TARGET_PER_STRATUM=300; N_CAND_MAX=60000
NSH_CONV=4; CONV_DEPTH=10; ARB_DEPTH=14; CACHE_MB=128
NOPEN=200; NSH_GATE=8; PAR_GATE=2; FORCE_DEPTH=9; MOVETIME=0.1
C0_SHA="13d9463f32d3378e8ce800c01590a93abcaeaca8ac50fcbbc6c6a79263b090be"
F500_SHA="e3239b094037d5ef220234ef39f0383a254f412afa362f899b3e4e49c1a5f135"
AB_SHA="c86da4bd7ce2d2cb9e1b73ccec9785a770d4727c51b875a03fe9e6edd865ba94"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
MODELS=(C0 F500 AB_EXTRAS)

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(tr ',' '\n' <<<"$Q00"|wc -l)" -eq 63 ] || die "Q00 drift"
[ "$((TOTAL_GAMES % NSH_GEN))" -eq 0 ] || die "TOTAL_GAMES must divide NSH_GEN"
GAMES_PER_SHARD=$((TOTAL_GAMES / NSH_GEN))
monitor

jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
b=open(sys.argv[1],"rb").read(8)
if len(b)!=8 or b[:4]!=b"JNNW": raise SystemExit(2)
print(struct.unpack("<I",b[4:])[0])
PY
}
merge_jnnw(){ python3 - "$1" "$2" <<'PY'
import glob,re,struct,sys
out,prefix=sys.argv[1:]
def key(path):
    m=re.search(r"\.(\d+)$",path); return int(m.group(1)) if m else 10**9
files=sorted(glob.glob(prefix+"*"),key=key)
if not files: raise SystemExit("no JNNW shards")
body=bytearray(); total=0
for path in files:
    raw=open(path,"rb").read()
    if raw[:4]!=b"JNNW": raise SystemExit(f"{path}: invalid JNNW")
    n=struct.unpack_from("<I",raw,4)[0]
    if len(raw)!=8+n*38: raise SystemExit(f"{path}: truncated JNNW")
    total+=n; body+=raw[8:]
open(out,"wb").write(b"JNNW"+struct.pack("<I",total)+body)
print(total)
PY
}
wait_all(){
  local label="$1"; shift; local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail workers failed"
}

stage fetch-immutable-models-and-seeds
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$C0_PREFIX" \
  --file artefacts/g3.pjtw.gz=c0.pjtw.gz --out-dir "$IN" \
  --report "$ART/verified-c0.json" > "$W/fetch-c0.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f500.pjtw.gz=f500.pjtw.gz --out-dir "$IN" \
  --report "$ART/verified-f500.json" > "$W/fetch-f500.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$ABLATION_PREFIX" \
  --file work/AB_EXTRAS.pjtw=ab-extras.pjtw --out-dir "$IN" \
  --report "$ART/verified-ab-extras.json" > "$W/fetch-ab.log" 2>&1
gunzip -c "$IN/c0.pjtw.gz" > "$W/C0.pjtw"
gunzip -c "$IN/f500.pjtw.gz" > "$W/F500.pjtw"
cp "$IN/ab-extras.pjtw" "$W/AB_EXTRAS.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/seeds.jnnw.gz" > "$W/seeds.jnnw"
for spec in "C0:$C0_SHA" "F500:$F500_SHA" "AB_EXTRAS:$AB_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  got="$(sha256sum "$W/$name.pjtw"|awk '{print $1}')"
  [ "$got" = "$want" ] || die "$name hash drift got=$got"
done

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

stage generate-candidate-blind-c0-holdout
pids=()
for shard in $(seq 0 $((NSH_GEN-1))); do
  timeout "$GEN_TIMEOUT" python3 tools/scan_selfplay_gen.py \
    --jass "$J8" --player-jass-bin "$J8" --player-pattern "$W/C0.pjtw" \
    --seeds "$W/seeds.jnnw" --out "$W/sp.$shard" --games "$GAMES_PER_SHARD" \
    --max-plies "$GEN_MAX_PLIES" --min-pieces "$GEN_MIN_PIECES" \
    --sample-every 1 --depth "$GEN_DEPTH" --seed "$GEN_SEED" \
    --nshards "$NSH_GEN" --shard "$shard" \
    > "$W/sp.$shard.log" 2>&1 & pids+=("$!")
  if [ "${#pids[@]}" -ge "$PAR_GEN" ]; then
    wait_all generation "${pids[@]}"; pids=()
  fi
done
[ "${#pids[@]}" -eq 0 ] || wait_all generation "${pids[@]}"
merge_jnnw "$W/fresh.jnnw" "$W/sp." > "$W/merge.log"

stage mine-and-certify-independent-p3-p4
python3 tools/mine_conversion_pool.py extract --corpus "$W/fresh.jnnw" \
  --out "$W/p3p4-candidates.jnnw" --n-cand "$N_CAND_MAX" \
  --max-over 3 --val-margin-max 1 > "$W/extract.log"
[ "$(jnnw_count "$W/p3p4-candidates.jnnw")" -gt 0 ] ||
  die "no fresh P3/P4 candidates"
"$J32" --deep-relabel "$W/p3p4-candidates.jnnw" "$W/p3p4-certified.jnnw" \
  "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB" > "$W/relabel.log" 2>&1
: > "$W/empty.fen"
python3 tools/mine_conversion_pool.py filter \
  --certified "$W/p3p4-certified.jnnw" --thermo "$IN/gauge.fen" \
  --eval-set-in "$W/empty.fen" --value-adv --eval-n 0 \
  --out-pool "$W/certified-pool.fen" --out-eval "$W/unused-eval.fen" \
  --manifest "$ART/certification-manifest.json" > "$W/filter.log"
python3 tools/mine_conversion_pool.py carve --pool "$W/certified-pool.fen" \
  --per-palier "$TARGET_PER_STRATUM" --holdout-only \
  --out-eval "$ART/independent-gauge.fen" \
  --out-train "$W/unused-train.fen" \
  --manifest "$ART/independent-gauge-manifest.json" > "$W/carve.log"
python3 - "$ART/independent-gauge-manifest.json" "$TARGET_PER_STRATUM" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); target=int(sys.argv[2])
c=p["eval_par_palier"]
for s in ("p3_mince","p4_egal"):
    if c.get(s,0)!=target:
        raise SystemExit(f"{s}: need {target}, got {c.get(s,0)}")
PY
python3 jobs/tools/split_stratified_fen.py \
  --input "$ART/independent-gauge.fen" --out-dir "$W/strata" \
  --manifest "$ART/gauge-strata.json" --required-strata p3_mince p4_egal \
  > "$W/split.log" 2>&1
for stratum in p3_mince p4_egal; do
  python3 jobs/tools/jnnw_doe.py fen-to-jnnw \
    --input "$W/strata/$stratum.fen" --output "$W/$stratum.raw.jnnw" >/dev/null
  "$J32" --deep-relabel "$W/$stratum.raw.jnnw" "$W/$stratum.rel.jnnw" \
    "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB" \
    > "$W/$stratum-relabel.log" 2>&1
  python3 jobs/tools/jnnw_doe.py keep-decisive \
    --input "$W/$stratum.rel.jnnw" --output "$W/$stratum.dec.jnnw" >/dev/null
  [ "$(jnnw_count "$W/$stratum.dec.jnnw")" -eq "$TARGET_PER_STRATUM" ] ||
    die "$stratum lost decisive labels on replay"
done
python3 - "$ART" "$W/fresh.jnnw" "$W/p3p4-candidates.jnnw" \
  "$W/p3_mince.dec.jnnw" "$W/p4_egal.dec.jnnw" "$GEN_SEED" \
  "$TOTAL_GAMES" <<'PY'
import hashlib,json,sys
from pathlib import Path
art=Path(sys.argv[1]); names=("fresh","candidates","p3","p4")
paths=map(Path,sys.argv[2:6])
payload={"schema":1,"blind_to_candidates":True,"generator_model":"C0",
 "generation_seed":int(sys.argv[6]),"total_games":int(sys.argv[7]),
 "old_gauge_excluded":True,
 "sha256":{n:hashlib.sha256(p.read_bytes()).hexdigest()
           for n,p in zip(names,paths)}}
(art/"holdout-provenance.json").write_text(
 json.dumps(payload,indent=2,sort_keys=True)+"\n")
PY

run_conv(){
  local model="$1" stratum="$2" pool="$3" expected="$4"
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
    --expected-shards "$NSH_CONV" --expected-records "$expected" \
    --max-error-rate 0.08 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$model-$stratum.json" \
    > "$W/$model-$stratum-aggregate.log" 2>&1
}

stage independent-fixed-defender-conversion
for stratum in p3_mince p4_egal; do
  pids=()
  for model in "${MODELS[@]}"; do
    run_conv "$model" "$stratum" "$W/$stratum.dec.jnnw" \
      "$TARGET_PER_STRATUM" & pids+=("$!")
  done
  wait_all "$stratum model groups" "${pids[@]}"
done

stage general-force-gates
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
    --pattern-a "$W/AB_EXTRAS.pjtw" --pattern-b "$W/$opponent.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open.fen" "${args[@]}" --pairs 1 \
    --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" --timeout 14400 \
    --work-dir "$W/gate-$view-$opponent" \
    --out "$ART/force-$view-AB_EXTRAS-vs-$opponent.json" \
    > "$W/force-$view-$opponent.log" 2>&1
}
pids=()
run_force q00 C0 & pids+=("$!")
run_force native C0 & pids+=("$!")
run_force q00 GEN2 & pids+=("$!")
wait_all force-gates "${pids[@]}"

stage aggregate-independent-verdict
python3 - "$ART" <<'PY'
import json,sys
from pathlib import Path
import numpy as np
art=Path(sys.argv[1]); models=("C0","F500","AB_EXTRAS")
strata=("p3_mince","p4_egal")
def load(m,s): return json.load(open(art/"conversion"/f"{m}-{s}.json"))
def positions(doc):
    return {int(r["index"]):r["result"] for r in doc["position_results"]
            if r["result"] in ("win","loss")}
def paired(cand,base,seed):
    c,b=positions(cand),positions(base); ids=sorted(set(c)&set(b))
    d=np.array([int(c[i]=="win")-int(b[i]=="win") for i in ids])
    counts=np.array([(d==-1).sum(),(d==0).sum(),(d==1).sum()])
    rng=np.random.default_rng(seed)
    boot=rng.multinomial(len(d),counts/counts.sum(),size=200000)
    bd=(boot[:,2]-boot[:,0])/len(d)
    return {"n_common":len(d),"candidate_rate":float(np.mean([c[i]=="win" for i in ids])),
      "baseline_rate":float(np.mean([b[i]=="win" for i in ids])),
      "delta":float(d.mean()),"ci_low":float(np.quantile(bd,.025)),
      "ci_high":float(np.quantile(bd,.975)),
      "loss_to_win":int((d==1).sum()),"win_to_loss":int((d==-1).sum())}
conversion={m:{s:{k:load(m,s)[k] for k in
 ("n_pos","n_win","n_draw","n_loss","conversion")} for s in strata}
 for m in models}
paired_out={s:{
 "vs_C0":paired(load("AB_EXTRAS",s),load("C0",s),950100+i),
 "vs_F500":paired(load("AB_EXTRAS",s),load("F500",s),950200+i)}
 for i,s in enumerate(strata)}
force={}
for view,opp in (("q00","C0"),("native","C0"),("q00","GEN2")):
    p=json.load(open(art/f"force-{view}-AB_EXTRAS-vs-{opp}.json"))
    force[f"{view}_vs_{opp}"]={k:p[k] for k in
      ("n","wins_a","draws","wins_b","rate","elo","ci_low","ci_high")}
primary=paired_out["p4_egal"]["vs_F500"]
p3=paired_out["p3_mince"]["vs_F500"]
strength=("confirmed" if primary["ci_low"]>0 else
          "directional" if primary["delta"]>0 else "not_replicated")
payload={"schema":1,"verdict":"AB_EXTRAS_INDEPENDENT_VALIDATION_READY_HUMAN_REVIEW",
 "evidence_strength":strength,
 "pre_registered_readout":{
   "primary":"P4 paired delta AB_EXTRAS vs F500",
   "confirmed_recovery":"primary bootstrap CI low > 0",
   "directional_recovery":"primary delta > 0 but CI crosses 0",
   "p3_preservation":"P3 paired CI high >= 0"},
 "p3_preserved":p3["ci_high"]>=0,
 "conversion":conversion,"paired_comparisons":paired_out,"force":force,
 "promotion_authorized":False,"automatic_next_job":None}
(art/"abextras-independent-validation.json").write_text(
 json.dumps(payload,indent=2,sort_keys=True)+"\n")
(art/"JASS_CONTROL_SUMMARY.json").write_text(
 json.dumps(payload,indent=2,sort_keys=True)+"\n")
(art/"VERDICT__AB_EXTRAS_INDEPENDENT_VALIDATION_READY_HUMAN_REVIEW").write_text(
 "AB_EXTRAS_INDEPENDENT_VALIDATION_READY_HUMAN_REVIEW\n")
(art/"PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art/"AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
PY
stage complete
say "AB_EXTRAS_INDEPENDENT_VALIDATION_READY_HUMAN_REVIEW promotion=false"
