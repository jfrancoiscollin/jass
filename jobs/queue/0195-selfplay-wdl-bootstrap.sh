#!/usr/bin/env bash
# id: 0195-selfplay-wdl-bootstrap
# description: RECETTE SCAN — étape 2 : self-play (MOVETIME). 0194 a montré que
# la régression logistique (le vrai objectif de Scan) s'effondre sur notre
# master WDL (0.22 vs champion 0.47) car les parties du master sont FAIBLES :
# 18.6% de nulles là où le self-play fort fait ~90%. Le WDL encode du jeu
# faible. Parade = générer NOS parties avec notre meilleure éval (champion 0.47)
# au MOVETIME (comme Scan), puis fitter la logistique dessus.
#
#   Preuve préliminaire : self-play à 20ms (éval embarquée) donne déjà 59% de
#   nulles vs 18.6% du master → parties bien plus fortes.
#
# Design : on contrôle le CONFOND volume-de-données en fittant aussi la
# logistique sur un SOUS-ÉCHANTILLON du master de MÊME TAILLE. Si self-play >>
# master-même-taille, c'est la QUALITÉ des parties qui compte (pas le volume).
#   réfs : 0194 logistic/master-1.4M=0.22 ; champion distill-score=0.47/0.38.
#   > 0.22 et ↗ 0.47 = bootstrap marche → itérer (étape 3).
#
# expected_duration: ~3-4 h (génération movetime 50ms + distills).
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0195-selfplay-wdl-bootstrap/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT clean; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
bench(){ ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 9  6 1 0   "" 64 >"$1-v15d9.log" 2>&1
         ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 64 4 1 300 "" 64 >"$1-v15mt.log" 2>&1
         ./build-prod/jass --benchmark-scan-eval "$1.pjtw" hc    8  6 1 0   "" 64 >"$1-hc.log"    2>&1; }
draws(){ python3 - "$1" <<'PY'
import sys,struct
f=open(sys.argv[1],'rb'); assert f.read(4)==b'JNNW'; n=struct.unpack('<I',f.read(4))[0]
w=d=l=0
for _ in range(n):
    f.read(37); v=struct.unpack('<b',f.read(1))[0]
    w+=v>0; l+=v<0; d+=v==0
print(f"n={n} win={w} draw={d} loss={l} draws={100*d/(n or 1):.1f}%")
PY
}

# ----------------------------------------------------------------------------
# 1) champion (distill score Scan-d10) = générateur self-play
# ----------------------------------------------------------------------------
echo "=== distill champion (générateur) ==="
./build-prod/jass --dump-eval-features "$CLEAN" "$ART/champ.feat" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$ART/champ.feat" \
  --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
  --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/champ.pjtw" >"$ART/champ-train.log" 2>&1
[ -f "$ART/champ.pjtw" ] || { echo "ABORT champ distill"; tail -15 "$ART/champ-train.log"; exit 7; }
bench "$ART/champ"
echo "  champion : v15 d9=$(rate "$ART/champ-v15d9.log")  mt=$(rate "$ART/champ-v15mt.log")  hc=$(rate "$ART/champ-hc.log")"

# ----------------------------------------------------------------------------
# 2) self-play MOVETIME 50ms (play_depth=64 = simple plafond). PILOTE d'abord
#    (taux de nulles = diagnostic n°1), puis 4 shards × 40k = 160k.
# ----------------------------------------------------------------------------
MT=50
echo "=== self-play PILOTE (6k, movetime=${MT}ms) — TAUX DE NULLES ==="
./build-prod/jass --gen-data-wdl 6000 "$ART/sp-pilot.jnnw" 4 64 200 1 --nnue "$ART/champ.pjtw" --movetime $MT >"$ART/sp-pilot.log" 2>&1
echo "  pilote: $(draws "$ART/sp-pilot.jnnw")   (master faible=18.6% ; embarquée@20ms=59%)"

echo "=== self-play GROS JEU (4×40k=160k, movetime=${MT}ms) ==="
for s in 1 2 3 4; do
  ./build-prod/jass --gen-data-wdl 40000 "$ART/sp-$s.jnnw" 4 64 200 $((10+s)) --nnue "$ART/champ.pjtw" --movetime $MT >"$ART/sp-$s.log" 2>&1 &
done
wait
python3 - "$ART" <<'PY'
import struct,glob,os,sys
art=sys.argv[1]; outp=os.path.join(art,"sp-all.jnnw"); REC=38
shards=sorted(glob.glob(os.path.join(art,"sp-[0-9].jnnw")))
tot=0; body=bytearray()
for s in shards:
    b=open(s,'rb').read(); assert b[:4]==b'JNNW'; n=struct.unpack('<I',b[4:8])[0]
    tot+=n; body+=b[8:8+n*REC]
out=open(outp,'wb'); out.write(b'JNNW'); out.write(struct.pack('<I',tot)); out.write(body); out.close()
print("merged",tot,"->",outp)
PY
echo "  gros jeu: $(draws "$ART/sp-all.jnnw")"
NSP=$(python3 -c "import struct;print(struct.unpack('<I',open('$ART/sp-all.jnnw','rb').read(8)[4:8])[0])")

# ----------------------------------------------------------------------------
# 2b) CONTRÔLE volume : sous-échantillon du master de MÊME TAILLE (NSP)
# ----------------------------------------------------------------------------
echo "=== sous-échantillon master (N=$NSP) pour contrôler le volume ==="
python3 - "$CLEAN" "$ART/master-sub.jnnw" "$NSP" <<'PY'
import sys,struct,random
src,dst,N=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); assert b[:4]==b'JNNW'; n=struct.unpack('<I',b[4:8])[0]
idx=list(range(n)); random.Random(0).shuffle(idx); idx=sorted(idx[:N])
out=open(dst,'wb'); out.write(b'JNNW'); out.write(struct.pack('<I',len(idx)))
for i in idx: out.write(b[8+i*REC:8+(i+1)*REC])
out.close(); print("subsampled",len(idx))
PY

# ----------------------------------------------------------------------------
# 3) logistique-WDL : self-play (sweep l2) + master-même-taille (l2=1e-4)
# ----------------------------------------------------------------------------
train_logistic(){ # <data.jnnw> <tag> <l2>
  ./build-prod/jass --dump-eval-features "$1" "$ART/$2.feat" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$ART/$2.feat" \
    --loss logistic --l2 $3 --max-iter 200 --scale 1000 --out "$ART/$2.pjtw" >"$ART/$2-train.log" 2>&1
  [ -f "$ART/$2.pjtw" ] && bench "$ART/$2" || echo "  ABORT train $2"; }

for L in 1e-5 1e-4 1e-3; do
  echo "=== logistic self-play, l2=$L ==="; train_logistic "$ART/sp-all.jnnw" "sp$L" $L
  echo "  l2=$L : v15 d9=$(rate "$ART/sp$L-v15d9.log")  mt=$(rate "$ART/sp$L-v15mt.log")  hc=$(rate "$ART/sp$L-hc.log")"
done
echo "=== logistic master-même-taille (contrôle), l2=1e-4 ==="; train_logistic "$ART/master-sub.jnnw" "subm" 1e-4
echo "  master-sub : v15 d9=$(rate "$ART/subm-v15d9.log")  mt=$(rate "$ART/subm-v15mt.log")  hc=$(rate "$ART/subm-hc.log")"

echo; echo "=========================================================="
echo "        0195 SELF-PLAY WDL (recette Scan étape 2) — VERDICT"
echo "  champion générateur : v15 d9=$(rate "$ART/champ-v15d9.log")  mt=$(rate "$ART/champ-v15mt.log")"
echo "  self-play draws     : $(draws "$ART/sp-all.jnnw")"
for L in 1e-5 1e-4 1e-3; do
  echo "  self-play  l2=$L   : v15 d9=$(rate "$ART/sp$L-v15d9.log")  mt=$(rate "$ART/sp$L-v15mt.log")  hc=$(rate "$ART/sp$L-hc.log")"
done
echo "  master-sub l2=1e-4  : v15 d9=$(rate "$ART/subm-v15d9.log")  mt=$(rate "$ART/subm-v15mt.log")  hc=$(rate "$ART/subm-hc.log")"
echo "  réfs : 0194 master-1.4M=0.22 d9 ;  champion distill=0.47 d9 / 0.38 mt"
echo "  → self-play >> master-sub (même taille) = la QUALITÉ des parties paie."
echo "  → self-play ↗ vers/au-delà de 0.47 = bootstrap marche → ITÉRER (étape 3)."
echo "  → self-play ≈ master-sub ≈ 0.22 = générateur faible / classe linéaire saturée."
echo "=========================================================="
