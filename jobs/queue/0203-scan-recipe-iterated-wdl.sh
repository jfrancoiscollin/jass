#!/usr/bin/env bash
# id: 0203-scan-recipe-iterated-wdl
# description: LA VRAIE RECETTE SCAN — boucle WDL ITÉRÉE (enfin). Nos docs
# (SCAN_ARCHITECTURE_NOTES) disent : Scan = self-play DEPUIS ZÉRO + label =
# ISSUE RÉELLE DE PARTIE (WDL, JAMAIS un score d'eval depth-N) + régression
# logistique + ITÉRER quelques cycles. On a pris un mauvais virage : WDL faible
# en 1 cycle (0196=0.22) → on a pivoté vers des labels de SCORE de recherche
# (0200/0202=0.33). Mais le score = DISTILLATION, borné par l'eval qui le génère
# → ne peut PAS compounder (d'où le plateau ~champion). Le WDL (issue réelle) est
# borné par RIEN → le seul label qui peut grimper jusqu'à Scan. Et on n'a JAMAIS
# itéré la boucle : un cycle ne PEUT PAS montrer de compounding.
#
# Ce job teste l'affirmatif : depuis un seed FAIBLE (sous le point fixe), la
# boucle WDL itérée GRIMPE-t-elle ?
#   gen0 = seed matériel-only (logistic l2=3e-2 sur sp-all ≈ matériel, ~0.05).
#   g=1..3 : self-play 300k @ mt30 avec gen{g-1} (8 shards) → WDL → logistic
#            l2=3e-4 → gen{g} ; bench vs v15 d9. gen3 aussi vs Scan d9.
#   Profondeur de jeu = mt30 (= 0196) pour comparabilité : si ça plafonne ~0.22,
#   le prochain test isolera « jeu plus profond relève le point fixe ? ».
#
#   COURBE gen0→1→2→3 monte = la boucle marche (brique = on n'itérait jamais)
#     → scaler (volume + profondeur de jeu + générations).
#   COURBE plate/descend = mécanisme cassé ou features plafonnent → pivot
#     (features plus riches, ou non-linéaire).
#
# expected_duration: ~5 h (3 gens × self-play 300k @mt30 + train/bench).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/0203-scan-recipe-iterated-wdl/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SPALL=/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src/sp-all.jnnw
SPFEAT=/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src/sp.feat
[ -f "$SPALL" ] && [ -f "$SPFEAT" ] || { echo "ABORT: sp-all/sp.feat de 0196 introuvables"; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

SCAN_DIR=/root/jass/.scan; SCAN="$SCAN_DIR/scan_linux"
[ -x "$SCAN" ] || { git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" 2>/dev/null && chmod +x "$SCAN_DIR/scan_linux"; SCAN="$SCAN_DIR/scan_linux"; }

rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
jrate(){ grep -oE 'Jass score rate:\s*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+'|head -1; }
v15d9(){ ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 9 6 1 0 "" 64 >"$1-v15d9.log" 2>&1; }
# logistic WDL fit (cible = issue de partie), recette = 0196 (PAS de material-anchor)
fit_wdl(){ # <data.jnnw> <feat> <out-tag> <l2>
  python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
    --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --out "$3.pjtw" >"$3-train.log" 2>&1; }

# --- gen0 : seed matériel-only (logistic très régularisé sur sp-all) -------
echo "=== gen0 : seed matériel-only (logistic l2=3e-2 sur sp-all) ==="
fit_wdl "$SPALL" "$SPFEAT" "$ART/gen0" 3e-2
[ -f "$ART/gen0.pjtw" ] || { echo "ABORT seed"; tail -10 "$ART/gen0-train.log"; exit 7; }
v15d9 "$ART/gen0"; echo "  gen0 (seed) vs v15 d9 = $(rate "$ART/gen0-v15d9.log")"

# --- boucle WDL itérée -----------------------------------------------------
N=300000; SH=$NCPU; PER=$(( (N + SH - 1) / SH )); MT=30
PREV="$ART/gen0"
for g in 1 2 3; do
  echo "=== gen$g : self-play ${N}@mt${MT} avec gen$((g-1)) ($SH shards) → WDL → logistic ==="
  for s in $(seq 1 "$SH"); do
    $JASS --gen-data-wdl "$PER" "$ART/sp$g-$s.jnnw" 4 64 200 $((g*100+s)) --nnue "$PREV.pjtw" --movetime $MT >"$ART/sp$g-$s.log" 2>&1 &
  done
  wait
  python3 - "$ART" "$g" <<'PY'
import struct,glob,os,sys,re
art=sys.argv[1]; g=sys.argv[2]; REC=38; outp=os.path.join(art,f"sp{g}.jnnw")
shards=sorted(glob.glob(os.path.join(art,f"sp{g}-*.jnnw")),
              key=lambda p:int(re.search(rf"sp{g}-(\d+)\.jnnw",p).group(1)))
tot=0; out=open(outp,'wb'); out.write(b'JNNW'); out.write(struct.pack('<I',0))
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; tot+=n; out.write(b[8:8+n*REC])
out.seek(4); out.write(struct.pack('<I',tot)); out.close(); print("gen",g,"merged",tot)
PY
  $JASS --dump-eval-features "$ART/sp$g.jnnw" "$ART/feat$g" 2>&1 | tail -1
  fit_wdl "$ART/sp$g.jnnw" "$ART/feat$g" "$ART/gen$g" 3e-4
  [ -f "$ART/gen$g.pjtw" ] || { echo "ABORT gen$g train"; tail -10 "$ART/gen$g-train.log"; exit 7; }
  v15d9 "$ART/gen$g"
  echo "  gen$g vs v15 d9 = $(rate "$ART/gen$g-v15d9.log")"
  rm -f "$ART/sp$g-"*.jnnw   # shards (garde sp$g.jnnw mergé)
  PREV="$ART/gen$g"
done

# gen3 vs Scan d9 (ancre absolue)
[ -x "$SCAN" ] && python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN" \
  --jass-pattern "$ART/gen3.pjtw" --depth 9 --pairs 8 --jass-threads 1 >"$ART/gen3-scand9.log" 2>&1 || true

echo; echo "=========================================================="
echo "   0203 BOUCLE WDL ITÉRÉE (vraie recette Scan) — VERDICT"
echo "  COURBE vs v15 d9 :"
echo "    gen0 (seed matériel) = $(rate "$ART/gen0-v15d9.log")"
echo "    gen1                 = $(rate "$ART/gen1-v15d9.log")"
echo "    gen2                 = $(rate "$ART/gen2-v15d9.log")"
echo "    gen3                 = $(rate "$ART/gen3-v15d9.log")   | Scan d9=$(jrate "$ART/gen3-scand9.log" 2>/dev/null)"
echo "  ANCRES : 0196 WDL 1-cycle (depuis champion)=0.22 ; champion=0.39"
echo "  → courbe MONTE (gen0<gen1<gen2<gen3) = la boucle compounde → scaler (volume/profondeur/gens)."
echo "  → courbe PLATE/DESCEND = WDL-mt30 ne grimpe pas dans notre setup → pivot (features/non-linéaire ou jeu plus profond)."
echo "=========================================================="
