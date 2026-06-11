#!/usr/bin/env bash
# id: 0196-selfplay-wdl-1M
# description: RECETTE SCAN — étape 3 : self-play À L'ÉCHELLE. 0195 a confirmé la
# DIRECTION (parties self-play à 62.8% de nulles vs 18.6% master ; à taille
# égale self-play 0.47 > master-sub 0.33 contre hc) mais 160k AFFAME le modèle
# pattern (haute dim) : contre v15 il s'écroule à 0.05 (< master-1.4M=0.22 de
# 0194, < champion=0.47). Deux écarts au champion : (1) cible logistic-vs-score
# [0194], (2) volume 1.4M→160k [0195]. On retire le #2 ici : ~1M positions
# self-play au movetime 30ms (champion comme générateur), puis logistic.
#
#   Test décisif : logistic-self-play-1M vs ANCRES 0194-logistic-master=0.22 et
#   champion-distill=0.47/0.39. Remonte vers/au-delà de 0.22→0.47 = bootstrap
#   marche → itérer (cycle 2). Plafonne bien sous = classe linéaire saturée
#   → bascule NNUE.
#
#   l2=1e-4 (vainqueur net à 160k) entraîné/benché EN PREMIER pour avoir le
#   chiffre clé même si le job est coupé tard ; sweep {3e-5,3e-4} ensuite.
#   Features dumpées UNE fois et réutilisées sur le sweep. $(nproc) shards.
#
# expected_duration: ~5-8 h (génération 1M @30ms sur tous les cœurs + 3 fits).
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src"; mkdir -p "$ART"
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
# 1) champion (distill score Scan-d10) = générateur — IDENTIQUE à 0195
# ----------------------------------------------------------------------------
echo "=== distill champion (générateur) ==="
./build-prod/jass --dump-eval-features "$CLEAN" "$ART/champ.feat" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$ART/champ.feat" \
  --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
  --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/champ.pjtw" >"$ART/champ-train.log" 2>&1
[ -f "$ART/champ.pjtw" ] || { echo "ABORT champ distill"; tail -15 "$ART/champ-train.log"; exit 7; }
bench "$ART/champ"
echo "  champion : v15 d9=$(rate "$ART/champ-v15d9.log")  mt=$(rate "$ART/champ-v15mt.log")  hc=$(rate "$ART/champ-hc.log")"
rm -f "$ART/champ.feat"   # 600MB, plus besoin

# ----------------------------------------------------------------------------
# 2) self-play MOVETIME 30ms, ~1M positions répartis sur $(nproc) shards
# ----------------------------------------------------------------------------
MT=30; NTOT=1000000; NSH=$NCPU; PER=$(( (NTOT + NSH - 1) / NSH ))
echo "=== self-play 1M : $NSH shards × $PER, movetime=${MT}ms ==="
for s in $(seq 1 "$NSH"); do
  ./build-prod/jass --gen-data-wdl "$PER" "$ART/sp-$s.jnnw" 4 64 200 $((100+s)) --nnue "$ART/champ.pjtw" --movetime $MT >"$ART/sp-$s.log" 2>&1 &
done
wait
python3 - "$ART" <<'PY'
import struct,glob,os,sys
art=sys.argv[1]; outp=os.path.join(art,"sp-all.jnnw"); REC=38
shards=sorted(glob.glob(os.path.join(art,"sp-[0-9]*.jnnw")))
tot=0; out=open(outp,'wb'); out.write(b'JNNW'); out.write(struct.pack('<I',0))
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; tot+=n; out.write(b[8:8+n*REC])
out.seek(4); out.write(struct.pack('<I',tot)); out.close()
print("merged",tot,"->",outp)
PY
echo "  1M self-play: $(draws "$ART/sp-all.jnnw")"

# ----------------------------------------------------------------------------
# 3) features dumpées UNE fois, puis logistic l2=1e-4 (décisif) puis sweep
# ----------------------------------------------------------------------------
echo "=== dump features (une fois) ==="
./build-prod/jass --dump-eval-features "$ART/sp-all.jnnw" "$ART/sp.feat" 2>&1 | tail -1
train_logistic(){ # <tag> <l2>
  python3 pattern_jass/tools/train.py --data "$ART/sp-all.jnnw" --scan-eval --eval-features-file "$ART/sp.feat" \
    --loss logistic --l2 $2 --max-iter 200 --scale 1000 --out "$ART/$1.pjtw" >"$ART/$1-train.log" 2>&1
  [ -f "$ART/$1.pjtw" ] && bench "$ART/$1" || echo "  ABORT train $1"; }

for pair in "sp1e-4 1e-4" "sp3e-5 3e-5" "sp3e-4 3e-4"; do
  set -- $pair
  echo "=== logistic self-play-1M, l2=$2 ==="; train_logistic "$1" "$2"
  echo "  l2=$2 : v15 d9=$(rate "$ART/$1-v15d9.log")  mt=$(rate "$ART/$1-v15mt.log")  hc=$(rate "$ART/$1-hc.log")"
done

echo; echo "=========================================================="
echo "      0196 SELF-PLAY WDL 1M (recette Scan étape 3) — VERDICT"
echo "  champion générateur : v15 d9=$(rate "$ART/champ-v15d9.log")  mt=$(rate "$ART/champ-v15mt.log")"
echo "  self-play 1M draws  : $(draws "$ART/sp-all.jnnw")"
echo "  self-play  l2=1e-4  : v15 d9=$(rate "$ART/sp1e-4-v15d9.log")  mt=$(rate "$ART/sp1e-4-v15mt.log")  hc=$(rate "$ART/sp1e-4-hc.log")"
echo "  self-play  l2=3e-5  : v15 d9=$(rate "$ART/sp3e-5-v15d9.log")  mt=$(rate "$ART/sp3e-5-v15mt.log")  hc=$(rate "$ART/sp3e-5-hc.log")"
echo "  self-play  l2=3e-4  : v15 d9=$(rate "$ART/sp3e-4-v15d9.log")  mt=$(rate "$ART/sp3e-4-v15mt.log")  hc=$(rate "$ART/sp3e-4-hc.log")"
echo "  ANCRES : 0195 self-play-160k l2=1e-4 = 0.056 d9 / 0.47 hc"
echo "           0194 logistic-master-1.4M  = 0.22 d9"
echo "           champion distill           = 0.39 d9 / 0.33 mt / 0.92 hc"
echo "  → 1M ↗ vers/au-delà de 0.22→0.39 = volume était le frein, bootstrap marche → cycle 2."
echo "  → 1M ≈ 160k (toujours ~0.05 vs v15) = ce n'est PAS le volume → classe linéaire saturée → NNUE."
echo "=========================================================="
