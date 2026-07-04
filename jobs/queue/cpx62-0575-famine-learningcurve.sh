#!/usr/bin/env bash
# id: cpx62-0575-famine-learningcurve
# description: E1 — LEARNING-CURVE 8cf vs 32cf (juge de paix de la these FAMINE, briefing JFC). Prediction falsifiable :
# a petit volume, le modele 4x plus petit (8cf = 8 bandes verticales = sous-ensemble Scan) fitte MIEUX (log-loss holdout
# plus basse) que le gros (32cf noye par sa traine affamee). REPONSE = log-loss HOLDOUT (20% queue held-out, jamais vue
# au fit) par volume {0.5M,1M,2M}. Fit FROM-SCRATCH pour les deux (le prior gen1 est 32cf => incompatible 8cf, et
# from-scratch est LA comparaison equitable du pouvoir de fit). Corpus SHUFFLE avant le split (holdout = queue). Code
# depuis DEVELOP (regle JFC) : --holdout-frac (train_stream) + variant v3 (gen_patterns), overlay au runtime.
# GATE : 8cf <= 32cf en log-loss @2M => FAMINE PROUVEE => E2 (tir volume). 32cf << 8cf @2M => encodage, PAS de tir.
# VERDICT job-side. AUCUN NNUE, AUCUNE distillation.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0575-famine-learningcurve/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0575-famine-learningcurve/artefacts"
W=/root/cw-famine; rm -rf "$W"; mkdir -p "$W"
REGEN_GZ=jobs/results/cpx62-0566-regen-mix-oncoin/artefacts/corpus-regen-mix2M.jnnw.gz
COMBO_SRC=jobs/results/ccx33-0464-master-combo-mining/artefacts/combos.jnnw
L2=3e-5; MAXIT=25; CHUNK=1000000; HOLD=0.2
RANK="$W/rank.tsv"; : > "$RANK"; LOG="$W/run.log"; note(){ echo "$@" | tee -a "$LOG"; }

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

note "=== E1 famine learning-curve — HEAD main $(git log --oneline -1|cat) ==="
# --- overlay du CODE depuis develop (regle JFC : code sur develop, job opere sur main) ---
git fetch origin develop --quiet 2>/dev/null || true
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:pattern_jass/tools/gen_patterns.py > pattern_jass/tools/gen_patterns.py
note "  code develop overlay : $(git show origin/develop --oneline -1|cat)"
grep -q 'holdout-frac' pattern_jass/tools/train_stream.py || { note "ABORT: holdout-frac absent (develop pas overlay)"; exit 5; }

# --- build jass (main, 32cf) pour le dump extras (extras = pattern-independant) ---
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { note "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"

# --- patterns.py 8cf et 32cf dans des GEOM dirs (emit ecrit dans le repo => on copie puis restaure) ---
GEOM8="$W/geom8"; GEOM32="$W/geom32"; mkdir -p "$GEOM8" "$GEOM32"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v3 >/dev/null 2>&1 || true
cp pattern_jass/tools/patterns.py "$GEOM8/patterns.py"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
N8=$(JASS_PATTERNS_DIR="$GEOM8" python3 -c "import patterns;print(patterns.NUM_PATTERNS)" 2>/dev/null)
N32=$(JASS_PATTERNS_DIR="$GEOM32" python3 -c "import patterns;print(patterns.NUM_PATTERNS)" 2>/dev/null)
note "  geom : 8cf NUM_PATTERNS=$N8 ; 32cf NUM_PATTERNS=$N32"
[ "$N8" = 8 ] && [ "$N32" = 32 ] || { note "ABORT: geom counts $N8/$N32 != 8/32"; exit 7; }

# --- pool = regen + combos, SHUFFLE (pour que la queue held-out soit representative) ---
git show "origin/main:$REGEN_GZ" | gunzip > "$W/regen.jnnw" || { note "ABORT corpus"; exit 4; }
git show "origin/main:$COMBO_SRC" > "$W/combos.jnnw" 2>/dev/null || : > "$W/combos.jnnw"
python3 - "$W/regen.jnnw" "$W/combos.jnnw" "$W/pool.jnnw" <<'PY'
import struct,sys,random
random.seed(12345); REC=38; recs=[]
for p in sys.argv[1:3]:
    try: b=open(p,'rb').read()
    except: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]
    for i in range(n): recs.append(b[8+i*REC:8+(i+1)*REC])
random.shuffle(recs)
with open(sys.argv[3],'wb') as f:
    f.write(b'JNNW'); f.write(struct.pack('<I',len(recs)))
    for r in recs: f.write(r)
print(f"  pool shuffle : {len(recs)} positions")
PY
POOLN=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pool.jnnw','rb').read(8)[4:8])[0])")
note "  pool = $POOLN positions (shuffle)"

subsample(){ python3 - "$W/pool.jnnw" "$1" "$2" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; K=min(int(sys.argv[3]),n)
with open(sys.argv[2],'wb') as f:
    f.write(b'JNNW'); f.write(struct.pack('<I',K))
    f.write(b[8:8+K*REC])   # deja shuffle => prefixe = echantillon aleatoire
print(K)
PY
}
fit_holdout(){ local geom="$1" data="$2" feat="$3" out="$4"
  JASS_PATTERNS_DIR="$geom" python3 pattern_jass/tools/train_stream.py --data "$data" --feat "$feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --prune-min-visits 1 --holdout-frac "$HOLD" --out "$out" 2>&1
}

note ""; note "=== fits (from-scratch, holdout=$HOLD) ==="
for VOL in 500000 1000000 2000000; do
  DAT="$W/d_$VOL.jnnw"; subsample "$DAT" "$VOL" >/dev/null
  FEAT="$W/f_$VOL"
  "$J" --dump-eval-features "$DAT" "$FEAT" >"$W/feat_$VOL.log" 2>&1 || { note "  dump feat $VOL FAIL"; continue; }
  for A in 8cf 32cf; do
    G="$GEOM8"; [ "$A" = 32cf ] && G="$GEOM32"
    LL=$(fit_holdout "$G" "$DAT" "$FEAT" "$W/c_${A}_$VOL.pjtw" | tee "$W/fit_${A}_$VOL.log" | grep -oE 'HOLDOUT_LOGLOSS [0-9.]+' | awk '{print $2}')
    [ -z "$LL" ] && LL="NA"
    note "  vol=$VOL arch=$A : holdout_logloss=$LL"
    echo -e "$VOL\t$A\t$LL" >>"$RANK"
    rm -f "$W/c_${A}_$VOL.pjtw"
  done
  rm -f "$FEAT" "$DAT"
done

VERD="$ART/VERDICT.txt"
python3 - "$RANK" > "$VERD" <<'PY'
import sys,collections
rows=[l.strip().split('\t') for l in open(sys.argv[1]) if l.strip()]
d={}
for r in rows:
    if len(r)<3: continue
    vol,arch,ll=r
    try: d[(int(vol),arch)]=float(ll)
    except: d[(int(vol),arch)]=None
print("=== VERDICT E1 famine learning-curve : log-loss HOLDOUT (plus BAS = meilleur) ===")
print(f"  {'volume':>9} {'8cf':>10} {'32cf':>10}  {'gagnant':>8}  {'ecart(32-8)':>12}")
vols=sorted(set(k[0] for k in d))
famine_2M=None
for v in vols:
    a8=d.get((v,'8cf')); a32=d.get((v,'32cf'))
    if a8 is None or a32 is None: print(f"  {v:>9} {str(a8):>10} {str(a32):>10}  (incomplet)"); continue
    win='8cf' if a8<a32 else '32cf'; gap=a32-a8
    print(f"  {v:>9} {a8:>10.5f} {a32:>10.5f}  {win:>8}  {gap:>+12.5f}")
    if v==2000000: famine_2M=(a8<=a32, gap)
print("")
if famine_2M is not None:
    ok,gap=famine_2M
    if ok:
        print(f"=> 8cf <= 32cf a 2M (ecart 32-8 = {gap:+.5f}) : FAMINE PROUVEE.")
        print("   Le gros modele est NOYE par sa traine affamee => le volume aiderait => GO E2 (tir 50-100M).")
    else:
        print(f"=> 32cf << 8cf a 2M (ecart {gap:+.5f}) : la famine N'EST PAS l'histoire => probleme d'ENCODAGE.")
        print("   NE PAS tirer le 100M => retour dump/DOE/oracle.")
print("(Bonus : la pente des courbes vs volume estime le croisement ou 32cf redevient rentable.)")
PY
cat "$VERD" | tee -a "$LOG"
cp "$RANK" "$ART/RANKING.tsv"
# restaure le repo (patterns.py deja en v4 via l'emit ci-dessus ; on remet aussi le code develop tel quel — non committe)
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0575 E1 famine learning-curve : VERDICT job-side (holdout log-loss 8cf vs 32cf)" \
  && note "  VERDICT committe job-side ✓" || note "  ⚠ commit VERDICT echoue"
commit_to_main "$ART/RANKING.tsv" "$ARTREL/RANKING.tsv" "0575 E1 : RANKING job-side" || true
note "=== fin E1 famine learning-curve ==="
