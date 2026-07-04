#!/usr/bin/env bash
# id: cpx62-0579-famine-curve-v2
# description: E1 v2 PROPRE (JFC) — learning-curve 8cf vs 32cf avec VAL SET FIXE (corrige le defaut v1 : val sets
# differents par volume). Protocole correct : un val de 400k FIGE (memes positions pour tous les volumes), train sur
# sous-ensembles croissants {0.5,1,1.5,2}M du RESTE (disjoint du val), fit --holdout-frac calcule pour que la queue =
# exactement ce val fixe. => courbe d'apprentissage propre (le volume aide-t-il ?) ET comparaison 8cf-vs-32cf a val
# identique. Fit from-scratch (prior gen1=32cf incompatible 8cf). chunk reduit 500k (fix OOM 32cf@2M v1). Code depuis
# DEVELOP (--holdout-frac + variant v3). GATE : 8cf <= 32cf @2M => famine ; 32cf << 8cf => encodage. VERDICT job-side.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0579-famine-curve-v2/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0579-famine-curve-v2/artefacts"
W=/root/cw-faminev2; rm -rf "$W"; mkdir -p "$W"
REGEN_GZ=jobs/results/cpx62-0566-regen-mix-oncoin/artefacts/corpus-regen-mix2M.jnnw.gz
COMBO_SRC=jobs/results/ccx33-0464-master-combo-mining/artefacts/combos.jnnw
L2=3e-5; MAXIT=25; CHUNK=500000; VAL=400000
RANK="$W/rank.tsv"; : > "$RANK"; LOG="$W/run.log"; note(){ echo "$@" | tee -a "$LOG"; }

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

note "=== E1 v2 famine curve (val fixe $VAL) — HEAD main $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:pattern_jass/tools/gen_patterns.py > pattern_jass/tools/gen_patterns.py
grep -q 'holdout-frac' pattern_jass/tools/train_stream.py || { note "ABORT holdout-frac absent"; exit 5; }
note "  code develop : $(git show origin/develop --oneline -1|cat)"

cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { note "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"

GEOM8="$W/geom8"; GEOM32="$W/geom32"; mkdir -p "$GEOM8" "$GEOM32"; TOOLS="$(pwd)/pattern_jass/tools"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v3 >"$W/emit3.log" 2>&1 || true
cp pattern_jass/tools/patterns.py "$GEOM8/patterns.py"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >"$W/emit4.log" 2>&1 || true
cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
N8=$(PYTHONPATH="$GEOM8:$TOOLS" python3 -c "import patterns;print(patterns.NUM_PATTERNS)" 2>"$W/i8.log")
N32=$(PYTHONPATH="$GEOM32:$TOOLS" python3 -c "import patterns;print(patterns.NUM_PATTERNS)" 2>"$W/i32.log")
note "  geom : 8cf=$N8 32cf=$N32"
[ "$N8" = 8 ] && [ "$N32" = 32 ] || { note "ABORT geom $N8/$N32 : $(tail -1 "$W/emit3.log") | $(tail -1 "$W/i8.log")"; exit 7; }

# --- pool shuffle ; VAL = 400k figes (tete) ; REST = le reste ---
git show "origin/main:$REGEN_GZ" | gunzip > "$W/regen.jnnw" || { note "ABORT corpus"; exit 4; }
git show "origin/main:$COMBO_SRC" > "$W/combos.jnnw" 2>/dev/null || : > "$W/combos.jnnw"
python3 - "$W/regen.jnnw" "$W/combos.jnnw" "$W/pool.jnnw" <<'PY'
import struct,sys,random
random.seed(777); REC=38; recs=[]
for p in sys.argv[1:3]:
    try: b=open(p,'rb').read()
    except: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]
    for i in range(n): recs.append(b[8+i*REC:8+(i+1)*REC])
random.shuffle(recs)
open(sys.argv[3],'wb').write(b'JNNW'+struct.pack('<I',len(recs))+b''.join(recs))
print(len(recs))
PY
POOLN=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pool.jnnw','rb').read(8)[4:8])[0])")
note "  pool=$POOLN (val fixe=$VAL ; train dispo=$((POOLN-VAL)))"

# construit DATA_v = [train (REST[0:V])] ++ [VAL (pool[0:VAL])] ; queue = val => frac=VAL/(V+VAL)
mkdata(){ python3 - "$W/pool.jnnw" "$1" "$VAL" "$2" <<'PY'
import struct,sys
pool=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',pool[4:8])[0]; REC=38; body=pool[8:]
V=int(sys.argv[2]); VALN=int(sys.argv[3]); out=sys.argv[4]
val=body[0:VALN*REC]                       # 400k figes
train=body[VALN*REC:(VALN+V)*REC]          # V positions du reste (disjoint du val)
recs=train+val                             # val en QUEUE
tot=len(recs)//REC
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+recs)
print(tot)
PY
}
fit_ll(){ local geom="$1" data="$2" feat="$3" frac="$4" out="$5"
  JASS_PATTERNS_DIR="$geom" python3 pattern_jass/tools/train_stream.py --data "$data" --feat "$feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --prune-min-visits 1 --holdout-frac "$frac" --out "$out" 2>&1
}

note ""; note "=== fits (val FIXE $VAL, from-scratch) ==="
for V in 500000 1000000 1500000 2000000; do
  [ $((V+VAL)) -gt "$POOLN" ] && { note "  vol=$V > pool dispo, skip"; continue; }
  DAT="$W/data_$V.jnnw"; mkdata "$V" "$DAT" >/dev/null
  FRAC=$(python3 -c "print($VAL/($V+$VAL))")
  FEAT="$W/feat_$V"
  "$J" --dump-eval-features "$DAT" "$FEAT" >"$W/dump_$V.log" 2>&1 || { note "  dump $V FAIL"; continue; }
  for A in 8cf 32cf; do
    G="$GEOM8"; [ "$A" = 32cf ] && G="$GEOM32"
    fit_ll "$G" "$DAT" "$FEAT" "$FRAC" "$W/c.pjtw" >"$W/fit_${A}_$V.log" 2>&1
    LL=$(grep -oE 'HOLDOUT_LOGLOSS [0-9.]+' "$W/fit_${A}_$V.log" | awk '{print $2}')
    if [ -z "$LL" ]; then LL="NA"; note "  vol=$V $A : NA  ($(tail -1 "$W/fit_${A}_$V.log"|cut -c1-80))"
    else note "  vol=$V $A : holdout_logloss=$LL (frac=$FRAC)"; fi
    echo -e "$V\t$A\t$LL" >>"$RANK"; rm -f "$W/c.pjtw"
  done
  rm -f "$FEAT" "$DAT"
done

VERD="$ART/VERDICT.txt"
python3 - "$RANK" > "$VERD" <<'PY'
import sys
d={}
for l in open(sys.argv[1]):
    r=l.strip().split('\t')
    if len(r)<3: continue
    try: d[(int(r[0]),r[1])]=float(r[2])
    except: d[(int(r[0]),r[1])]=None
print("=== VERDICT E1 v2 famine curve (val FIXE) : holdout log-loss (plus BAS=meilleur) ===")
print(f"  {'train':>9} {'8cf':>10} {'32cf':>10}  {'ecart(32-8)':>12}  {'gagnant':>8}")
vols=sorted(set(k[0] for k in d)); g2=None
for v in vols:
    a8=d.get((v,'8cf')); a32=d.get((v,'32cf'))
    if a8 is None or a32 is None: print(f"  {v:>9} {str(a8):>10} {str(a32):>10}  (incomplet)"); continue
    gap=a32-a8; win='8cf' if a8<a32 else '32cf'
    print(f"  {v:>9} {a8:>10.5f} {a32:>10.5f}  {gap:>+12.5f}  {win:>8}")
    if v==2000000: g2=(a8<=a32,gap)
print("\ncourbe (le volume aide-t-il ? val FIXE => comparable) :")
for a in ('8cf','32cf'):
    xs=[(v,d[(v,a)]) for v in vols if d.get((v,a)) is not None]
    if len(xs)>=2: print(f"  {a:>5} : "+"  ".join(f"{v//1000}k={ll:.5f}" for v,ll in xs)+f"   (delta {xs[-1][1]-xs[0][1]:+.5f})")
print("")
if g2 is not None:
    ok,gap=g2
    if ok: print(f"=> 8cf <= 32cf @2M (ecart {gap:+.5f}) : le gros modele n'aide pas / est <= petit => FAMINE (capacite dormante) => E2 tir volume.")
    else:  print(f"=> 32cf < 8cf @2M (ecart {gap:+.5f}) : le gros modele fitte deja mieux => PAS de famine drowning ; si la courbe est PLATE => saturation => encodage, PAS de tir.")
print("Note : courbe qui DESCEND nettement avec le volume => le volume aide (pro-famine) ; PLATE => sature (anti-tir).")
PY
cat "$VERD" | tee -a "$LOG"; cp "$RANK" "$ART/RANKING.tsv"
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0579 E1 v2 famine curve (val fixe) : VERDICT job-side" \
  && note "  VERDICT committe ✓" || note "  ⚠ commit echoue"
commit_to_main "$ART/RANKING.tsv" "$ARTREL/RANKING.tsv" "0579 E1 v2 : RANKING job-side" || true
note "=== fin E1 v2 ==="
