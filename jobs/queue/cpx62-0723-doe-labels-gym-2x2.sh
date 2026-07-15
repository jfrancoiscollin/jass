#!/usr/bin/env bash
# id: cpx62-0723-doe-labels-gym-2x2
# description: DOE 2x2 causal L3 sur corpus strictement apparié.
# Facteur A = labels base on-policy d9 vs d14+EGDB ; facteur B = gymnase normal G1 vs fortement pondéré G4.
# Les 4 cellules partagent exactement les mêmes positions uniques et le même ordre de base. G4 ne fait que répéter
# les mêmes positions gymnase. Les labels adjud ne changent QUE le byte WDL ; score/features/positions restent identiques.
# Mesures : 4 gates vs bootstrap, conversion WDL-grounded sur témoin d14+EGDB figé, 4 contrastes directs et interaction.
# Correctifs 0721/0722 : shards contigus réassemblés dans l'ordre, aucun shard incomplet toléré, dédup positions,
# exclusion dure base∩gym, hashes/SHAs/manifeste, outils develop pinnés. AUCUN NNUE. AUCUN bake.
set -uo pipefail
cd /root/jass

JOB_ID=cpx62-0723-doe-labels-gym-2x2
exec 9>/root/.jass-0723.lock
if ! flock -n 9; then echo "ABORT 0723 : instance deja active"; exit 0; fi

NCPU=$(nproc)
export TMPDIR=/root/jass/.compile-tmp
mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/$JOB_ID/artefacts"
ARTREL="jobs/results/$JOB_ID/artefacts"
W=/root/cw-0723
GEOM=/root/jass-geom32-0723
rm -rf "$W" "$GEOM"
mkdir -p "$W" "$ART"
RES="$W/RESULTS.txt"
: > "$RES"
say(){ echo "$@" | tee -a "$RES"; }
die(){ say "ABORT: $*"; restore_src 2>/dev/null || true; exit 1; }

DFA=$(df -Pm /root | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 5000 ] || { echo "ABORT disque <5Go"; exit 3; }

FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0715-d1-ablation/artefacts/corpus_T1.jnnw.gz
EVALSTRAT=jobs/results/ccx33-0718-mine-tip/artefacts/conv_self_eval_strat_v2.fen
GYMPOOL=jobs/results/ccx33-0718-mine-tip/artefacts/conversion_pool_train_v2.fen

N_TARGET=${N_TARGET:-120000}
GYM_W=${GYM_W:-4}
CONV_PER_PAL=${CONV_PER_PAL:-200}
ARB_DEPTH=${ARB_DEPTH:-14}
ANCHOR=${ANCHOR:-0.05}
MAXIT=${MAXIT:-60}
CHUNK=${CHUNK:-1000000}
CONV_DEPTH=${CONV_DEPTH:-10}
NOPEN=${NOPEN:-300}
PAIRS=${PAIRS:-2}
DEPTH=${DEPTH:-9}
QS=${QS:-qs_forcing_depth=6,qs_promo_depth=6}
NSH=$NCPU
RELABEL_TIMEOUT=${RELABEL_TIMEOUT:-3600}
PLAY_TIMEOUT=${PLAY_TIMEOUT:-7000}

commit_to_main(){
  local ab="$1" rel="$2" msg="$3"
  for attempt in 1 2 3 4 5; do
    git fetch origin main --quiet 2>/dev/null || true
    local idx="/root/.ti.$$.$RANDOM"
    rm -f "$idx"
    GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null || return 1
    local blob tree commit
    blob=$(git hash-object -w "$ab") || return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$blob" "$rel"
    tree=$(GIT_INDEX_FILE="$idx" git write-tree) || return 1
    commit=$(printf '%s\n' "$msg" | git commit-tree "$tree" -p origin/main) || return 1
    if git push origin "$commit:main" 2>/dev/null; then rm -f "$idx"; return 0; fi
    rm -f "$idx"
    sleep $((attempt*4))
  done
  return 1
}

restore_src(){
  git checkout -- src pattern_jass/src tools/calibrate_vs_scan.py tools/jass_vs_jass_arch.py \
    pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py \
    pattern_jass/tools/make_bootstrap_eval.py 2>/dev/null || true
}

relabel_strict(){ # input output prefix timeout
  local input="$1" output="$2" prefix="$3" timeout_s="$4"
  python3 jobs/tools/jnnw_doe.py split --input "$input" --prefix "$W/${prefix}_src" --shards "$NSH" >>"$RES"
  local pids=()
  for s in $(seq 0 $((NSH-1))); do
    local tag
    tag=$(printf '%03d' "$s")
    timeout "$timeout_s" "$J" --deep-relabel "$W/${prefix}_src.$tag.jnnw" "$W/${prefix}_rel.$tag.jnnw" \
      "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb 2048 >"$W/${prefix}_rel.$tag.log" 2>&1 &
    pids+=($!)
  done
  local failed=0
  for pid in "${pids[@]}"; do wait "$pid" || failed=$((failed+1)); done
  [ "$failed" -eq 0 ] || die "$prefix: $failed relabel shards failed/timed out"
  local expected
  expected=$(python3 - "$input" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); print(struct.unpack('<I',b[4:8])[0])
PY
)
  python3 jobs/tools/jnnw_doe.py merge --prefix "$W/${prefix}_rel" --source-prefix "$W/${prefix}_src" \
    --shards "$NSH" --expected "$expected" --output "$W/${prefix}_raw_rel.jnnw" >>"$RES" || die "$prefix merge/order verification"
  python3 jobs/tools/jnnw_doe.py normalize-labels --reference "$input" --relabeled "$W/${prefix}_raw_rel.jnnw" \
    --output "$output" | tee -a "$RES" || die "$prefix label normalization"
}

fit_cell(){ # name corpus
  local name="$1" data="$2"
  "$J" --dump-eval-features "$data" "$W/feat_$name" >"$W/dump_$name.log" 2>&1 || return 1
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    python3 pattern_jass/tools/wdl_finetune.py --champion "$W/bootstrap.pjtw" --data "$data" \
      --feat "$W/feat_$name" --out "$W/cand_$name.pjtw" --tools pattern_jass/tools \
      --anchor "$ANCHOR" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" \
      --verify-jass "$J" --verify-n 80 >"$W/fit_$name.log" 2>&1
}

measure_conversion(){ # name pattern -> stdout "conv n"
  local name="$1" pattern="$2" pids=()
  for s in $(seq 0 $((NSH-1))); do
    timeout "$PLAY_TIMEOUT" python3 jobs/tools/conv_fixed_wdl.py --jass "$J" --pattern "$pattern" \
      --defender-pattern "$W/gen2.pjtw" --pool-jnnw "$W/conv_eval.jnnw" \
      --calibrate-tool tools/calibrate_vs_scan.py --depth "$CONV_DEPTH" --max-plies 260 \
      --shard "$s" --nshards "$NSH" --out "$W/conv_${name}.$s.json" >"$W/conv_${name}.$s.log" 2>&1 &
    pids+=($!)
  done
  local failed=0
  for pid in "${pids[@]}"; do wait "$pid" || failed=$((failed+1)); done
  [ "$failed" -eq 0 ] || { echo "conversion $name: $failed shards failed" >&2; return 1; }
  python3 - "$W/conv_${name}.json" "$W" "$name" <<'PY'
import glob,json,sys
out,w,name=sys.argv[1:]
agg={"n_pos":0,"n_win":0,"n_draw":0,"n_loss":0,"n_errors":0,"n_skipped_draw_label":0}
for p in glob.glob(f"{w}/conv_{name}.*.json"):
    j=json.load(open(p))
    for k in agg: agg[k]+=int(j.get(k,0))
agg["conv"]=agg["n_win"]/agg["n_pos"] if agg["n_pos"] else None
json.dump(agg,open(out,'w'),indent=2)
if agg["n_errors"] or agg["n_skipped_draw_label"]:
    raise SystemExit(f"conversion integrity failure: {agg}")
print(f"{agg['conv']:.6f} {agg['n_pos']}")
PY
}

match_patterns(){ # label patternA patternB -> stdout "rate n elo lo hi"
  local label="$1" pa="$2" pb="$3" pids=()
  for s in $(seq 0 $((NSH-1))); do
    timeout "$PLAY_TIMEOUT" python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$pa" \
      --jass-b "$J" --pattern-b "$pb" --search-params-a "$QS" --search-params-b "$QS" \
      --depth "$DEPTH" --pairs "$PAIRS" --max-plies 180 --shard "$s" --nshards "$NSH" \
      --quiet --openings-file "$W/open.fen" >"$W/match_${label}.$s.log" 2>&1 &
    pids+=($!)
  done
  local failed=0
  for pid in "${pids[@]}"; do wait "$pid" || failed=$((failed+1)); done
  [ "$failed" -eq 0 ] || { echo "match $label: $failed shards failed" >&2; return 1; }
  python3 - "$W/match_${label}.json" "$W" "$label" <<'PY'
import glob,json,math,sys
out,w,label=sys.argv[1:]
a=d=b=0
for p in glob.glob(f"{w}/match_{label}.*.log"):
    for line in open(p,errors='replace'):
        if line.startswith('RESULT'):
            _,x,y,z=line.split(); a+=int(x); d+=int(y); b+=int(z)
n=a+d+b
if not n: raise SystemExit('no RESULT games')
r=(a+0.5*d)/n
vals2=(a+0.25*d)/n
var=max(0.0,vals2-r*r)
se=math.sqrt(var/n)
lo=max(0.0,r-1.96*se); hi=min(1.0,r+1.96*se)
elo=-400*math.log10(1/r-1) if 0<r<1 else (9999 if r==1 else -9999)
j={"wins_a":a,"draws":d,"wins_b":b,"n":n,"rate_a":r,"elo_a":elo,"ci95_rate":[lo,hi]}
json.dump(j,open(out,'w'),indent=2)
print(f"{r:.6f} {n} {elo:.2f} {lo:.6f} {hi:.6f}")
PY
}

say "=== DOE 2x2 LABELS × GYMNASE — HEAD $(git log --oneline -1 | cat) — NCPU=$NCPU df=${DFA}Mo ==="
say "  config: base=$N_TARGET gym G1/G$GYM_W conv=${CONV_PER_PAL}/palier gate=${NOPEN} openings×${PAIRS} pairs"

python3 jobs/tests/test_jnnw_doe.py | tee -a "$RES" || die "unit tests jnnw_doe"
python3 jobs/tests/test_conv_fixed_wdl.py | tee -a "$RES" || die "unit tests conv_fixed_wdl"
python3 -m py_compile jobs/tools/jnnw_doe.py jobs/tools/conv_fixed_wdl.py || die "py_compile jobs tools"

git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || die "fetch develop"
DEVSHA=$(git rev-parse origin/develop)
MAINSHA=$(git rev-parse origin/main)
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f" || die "copy develop $f"; done
for f in tools/calibrate_vs_scan.py tools/jass_vs_jass_arch.py pattern_jass/tools/wdl_finetune.py \
         pattern_jass/tools/train_stream.py pattern_jass/tools/make_bootstrap_eval.py; do
  git show "origin/develop:$f" > "$f" || die "$f absent de develop"
done
say "  source pin: main=$MAINSHA develop=$DEVSHA"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "egdb databases not found"
export JASS_EGDB_PATH="$EGDIR"

say "=== build jass develop-pinned + EGDB ==="
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 || die "cmake"
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "EGDB not enabled"
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || die "build jass"
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || die "geometry NUM_PATTERNS=$NP"
mkdir -p "$GEOM"
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"

git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || die "gen2 artifact"
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/bootstrap.pjtw" --like "$W/gen2.pjtw" >"$W/bootstrap.log" 2>&1 || die "bootstrap"
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/full.jnnw" || die "T1 corpus"
git show "origin/main:$GYMPOOL" > "$W/gym_pool.fen" || die "gym pool"
git show "origin/main:$EVALSTRAT" > "$W/conv_eval_full.fen" || die "conv eval"
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"
[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "openings n != $NOPEN"

say "=== prepare unique, disjoint base and deeply labelled gym/eval ==="
python3 jobs/tools/jnnw_doe.py fen-to-jnnw --input "$W/gym_pool.fen" --output "$W/gym_raw.jnnw" | tee -a "$RES" || die "gym FEN pack/dedup"
python3 jobs/tools/jnnw_doe.py sample --input "$W/full.jnnw" --output "$W/base_onp.jnnw" --count "$N_TARGET" \
  --exclude-fen "$W/gym_pool.fen" | tee -a "$RES" || die "base sampling"
relabel_strict "$W/base_onp.jnnw" "$W/base_adj.jnnw" base "$RELABEL_TIMEOUT"
relabel_strict "$W/gym_raw.jnnw" "$W/gym_adj.jnnw" gym "$RELABEL_TIMEOUT"
python3 jobs/tools/jnnw_doe.py assert-decisive --input "$W/gym_adj.jnnw" | tee -a "$RES" || die "gym not decisive"

python3 jobs/tools/jnnw_doe.py subset-fen --input "$W/conv_eval_full.fen" --output "$W/conv_eval.fen" \
  --per-group "$CONV_PER_PAL" | tee -a "$RES" || die "conv subset"
python3 jobs/tools/jnnw_doe.py fen-to-jnnw --input "$W/conv_eval.fen" --output "$W/conv_eval_raw.jnnw" | tee -a "$RES" || die "conv FEN pack"
relabel_strict "$W/conv_eval_raw.jnnw" "$W/conv_eval.jnnw" conv "$RELABEL_TIMEOUT"
python3 jobs/tools/jnnw_doe.py assert-decisive --input "$W/conv_eval.jnnw" | tee -a "$RES" || die "conv eval not decisive"

python3 jobs/tools/jnnw_doe.py build-cells --base-onp "$W/base_onp.jnnw" --base-adj "$W/base_adj.jnnw" \
  --gym "$W/gym_adj.jnnw" --gym-mult "$GYM_W" --out-dir "$W/cells" --manifest "$ART/corpus_manifest.json" \
  | tee -a "$RES" || die "build cells"
python3 jobs/tools/jnnw_doe.py verify-cells --out-dir "$W/cells" --manifest "$ART/corpus_manifest.json" \
  | tee -a "$RES" || die "verify cells"

python3 - "$ART/corpus_manifest.json" "$MAINSHA" "$DEVSHA" "$N_TARGET" "$GYM_W" "$CONV_PER_PAL" <<'PY'
import json,sys
p,main,dev,n,g,c=sys.argv[1:]
j=json.load(open(p)); j.update({"main_sha":main,"develop_sha":dev,"n_target":int(n),"gym_weight_high":int(g),"conv_per_palier":int(c)})
json.dump(j,open(p,'w'),indent=2)
PY

say "=== fit 4 cells ==="
CELLS=(onp_g1 adj_g1 "onp_g$GYM_W" "adj_g$GYM_W")
for cell in "${CELLS[@]}"; do
  data="$W/cells/$cell.jnnw"
  n=$(python3 - "$data" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); print(struct.unpack('<I',b[4:8])[0])
PY
)
  say "  fit $cell N=$n"
  fit_cell "$cell" "$data" || die "fit $cell: $(tail -2 "$W/fit_$cell.log" | tr '\n' ' ')"
done

say "=== cell metrics: WDL-grounded conversion + gate vs bootstrap ==="
for cell in "${CELLS[@]}"; do
  metrics=$(measure_conversion "$cell" "$W/cand_$cell.pjtw") || die "conversion metric $cell"
  read -r conv cn <<<"$metrics"
  metrics=$(match_patterns "gate_$cell" "$W/cand_$cell.pjtw" "$W/bootstrap.pjtw") || die "gate $cell"
  read -r rate gn elo lo hi <<<"$metrics"
  say "CELL $cell conv=$conv conv_n=$cn gate_rate=$rate gate_n=$gn gate_elo=$elo gate_ci=[$lo,$hi]"
done

say "=== direct factorial contrasts (A named first) ==="
metrics=$(match_patterns label_g1 "$W/cand_adj_g1.pjtw" "$W/cand_onp_g1.pjtw") || die "contrast label_g1"
read -r r n e lo hi <<<"$metrics"
say "CONTRAST label_g1 A=adj_g1 B=onp_g1 rate=$r n=$n elo=$e ci=[$lo,$hi]"
metrics=$(match_patterns "label_g$GYM_W" "$W/cand_adj_g$GYM_W.pjtw" "$W/cand_onp_g$GYM_W.pjtw") || die "contrast label_g$GYM_W"
read -r r n e lo hi <<<"$metrics"
say "CONTRAST label_g$GYM_W A=adj_g$GYM_W B=onp_g$GYM_W rate=$r n=$n elo=$e ci=[$lo,$hi]"
metrics=$(match_patterns gym_onp "$W/cand_onp_g$GYM_W.pjtw" "$W/cand_onp_g1.pjtw") || die "contrast gym_onp"
read -r r n e lo hi <<<"$metrics"
say "CONTRAST gym_onp A=onp_g$GYM_W B=onp_g1 rate=$r n=$n elo=$e ci=[$lo,$hi]"
metrics=$(match_patterns gym_adj "$W/cand_adj_g$GYM_W.pjtw" "$W/cand_adj_g1.pjtw") || die "contrast gym_adj"
read -r r n e lo hi <<<"$metrics"
say "CONTRAST gym_adj A=adj_g$GYM_W B=adj_g1 rate=$r n=$n elo=$e ci=[$lo,$hi]"

say "=== DOE VERDICT ==="
python3 - "$RES" "$ART/doe_manifest.json" "$ART/corpus_manifest.json" "$GYM_W" <<'PY' | tee -a "$RES"
import json,re,sys
res,out,corpus,gymw=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4])
txt=open(res).read()
cell_re=re.compile(r"CELL (\S+) conv=([\d.]+) conv_n=(\d+) gate_rate=([\d.]+) gate_n=(\d+) gate_elo=([+-]?[\d.]+) gate_ci=\[([\d.]+),([\d.]+)\]")
con_re=re.compile(r"CONTRAST (\S+) A=(\S+) B=(\S+) rate=([\d.]+) n=(\d+) elo=([+-]?[\d.]+) ci=\[([\d.]+),([\d.]+)\]")
cells={m.group(1):{"conv":float(m.group(2)),"conv_n":int(m.group(3)),"gate_rate":float(m.group(4)),"gate_n":int(m.group(5)),"gate_elo":float(m.group(6)),"gate_ci":[float(m.group(7)),float(m.group(8))]} for m in cell_re.finditer(txt)}
contrasts={m.group(1):{"a":m.group(2),"b":m.group(3),"rate":float(m.group(4)),"n":int(m.group(5)),"elo":float(m.group(6)),"ci":[float(m.group(7)),float(m.group(8))]} for m in con_re.finditer(txt)}
required_cells={"onp_g1","adj_g1",f"onp_g{gymw}",f"adj_g{gymw}"}
required_con={"label_g1",f"label_g{gymw}","gym_onp","gym_adj"}
if set(cells)!=required_cells or set(contrasts)!=required_con:
    raise SystemExit(f"incomplete DOE cells={sorted(cells)} contrasts={sorted(contrasts)}")
conv_label_g1=cells['adj_g1']['conv']-cells['onp_g1']['conv']
conv_label_hi=cells[f'adj_g{gymw}']['conv']-cells[f'onp_g{gymw}']['conv']
conv_gym_onp=cells[f'onp_g{gymw}']['conv']-cells['onp_g1']['conv']
conv_gym_adj=cells[f'adj_g{gymw}']['conv']-cells['adj_g1']['conv']
conv_interaction=conv_gym_adj-conv_gym_onp
elo_inter_label=contrasts[f'label_g{gymw}']['elo']-contrasts['label_g1']['elo']
elo_inter_gym=contrasts['gym_adj']['elo']-contrasts['gym_onp']['elo']
summary={"corpus_manifest":json.load(open(corpus)),"cells":cells,"direct_contrasts":contrasts,
 "effects":{"conv_label_g1":conv_label_g1,"conv_label_high":conv_label_hi,"conv_gym_onp":conv_gym_onp,"conv_gym_adj":conv_gym_adj,"conv_interaction":conv_interaction,
            "elo_interaction_label_difference":elo_inter_label,"elo_interaction_gym_difference":elo_inter_gym}}
json.dump(summary,open(out,'w'),indent=2,ensure_ascii=False)
print(f"  effet LABEL à G1      : conv {conv_label_g1:+.4f} | direct Elo {contrasts['label_g1']['elo']:+.1f}")
print(f"  effet LABEL à G{gymw}      : conv {conv_label_hi:+.4f} | direct Elo {contrasts[f'label_g{gymw}']['elo']:+.1f}")
print(f"  effet GYMNASE sous ONP: conv {conv_gym_onp:+.4f} | direct Elo {contrasts['gym_onp']['elo']:+.1f}")
print(f"  effet GYMNASE sous ADJ: conv {conv_gym_adj:+.4f} | direct Elo {contrasts['gym_adj']['elo']:+.1f}")
print(f"  interaction conv      : {conv_interaction:+.4f}")
print(f"  interaction Elo       : label-diff {elo_inter_label:+.1f} | gym-diff {elo_inter_gym:+.1f}")
combo=cells[f'adj_g{gymw}']
if combo['gate_ci'][0] >= 0.48 and conv_gym_adj >= 0.02 and contrasts['gym_adj']['elo'] > 0:
    print(f"  => ✓ COMBINAISON ADJ+G{gymw} PROMETTEUSE : gate non-inférieur, conversion monte sous ADJ, contraste direct positif. Confirmer à N supérieur avant campagne.")
elif conv_interaction >= 0.02 and elo_inter_label > 10 and elo_inter_gym > 10:
    print("  => ~ INTERACTION POSITIVE mais cellule combinée pas encore admise contre bootstrap : tuner poids gym/ancre, pas scaler aveuglément.")
else:
    print("  => ✗ PAS D'INTERACTION UTILE démontrée : ne pas lancer la campagne combinée ; reconsidérer poids gym ou point de départ.")
PY

commit_to_main "$ART/corpus_manifest.json" "$ARTREL/corpus_manifest.json" "0723 DOE corpus manifest strict matched" >/dev/null 2>&1 || say "  ⚠ commit corpus manifest"
commit_to_main "$ART/doe_manifest.json" "$ARTREL/doe_manifest.json" "0723 DOE metrics and interaction manifest" >/dev/null 2>&1 || say "  ⚠ commit DOE manifest"
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0723 FIN DOE 2x2 labels x gym G1/G$GYM_W" && say "  ✓ RESULTS committé" || say "  ⚠ commit RESULTS"
say "=== 0723 FINI ==="
rm -rf "$W" "$GEOM"
