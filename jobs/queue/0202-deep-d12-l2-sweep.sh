#!/usr/bin/env bash
# id: 0202-deep-d12-l2-sweep
# description: SWEEP12 — affiner cycle-1. 0200 a confirmé le levier deep (d12
# relabel = 0.306 vs v15 à l2=3e-4) MAIS n'a testé que 2 l2, et 1e-4 s'est
# EFFONDRÉ (d9=0) : la cible score-deep (range ±30000, std ~5470) est sensible
# à la régularisation. On balaie l2 plus large et plus HAUT (≥3e-4) sur le MÊME
# sp-d12.jnnw (déjà sur le runner, pas de relabel) pour trouver le vrai plafond
# de cycle-1 — ce modèle deviendra le GÉNÉRATEUR de cycle-2.
#
#   Bench rapide (v15 d9 + Scan d9) sur les 5 l2 → full bench (mt/hc) du gagnant.
#
# expected_duration: ~1-1.5 h (5 fits 1M + benchs d9 ; pas de relabel/génération).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/0202-deep-d12-l2-sweep/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
RELAB=/root/jass/jobs/results/0200-selfplay-deep-relabel-d12/artefacts.src/sp-d12.jnnw
FEAT=/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src/sp.feat
[ -f "$RELAB" ] || { echo "ABORT: sp-d12.jnnw de 0200 introuvable"; exit 3; }
[ -f "$FEAT" ]  || { echo "ABORT: sp.feat de 0196 introuvable"; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
echo "=== reuse $(ls -lh "$RELAB"|awk '{print $5}') deep-d12 data ==="

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

SCAN_DIR=/root/jass/.scan; SCAN="$SCAN_DIR/scan_linux"
[ -x "$SCAN" ] || { git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" 2>/dev/null && chmod +x "$SCAN/scan_linux" 2>/dev/null; SCAN="$SCAN_DIR/scan_linux"; }

rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
jrate(){ grep -oE 'Jass score rate:\s*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+'|head -1; }
v15d9(){ ./build-prod/jass --benchmark-scan-eval "$1.pjtw" "$V15" 9 6 1 0 "" 64 >"$1-v15d9.log" 2>&1; }
scand9(){ [ -x "$SCAN" ] && python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN" \
            --jass-pattern "$1.pjtw" --depth 9 --pairs 8 --jass-threads 1 >"$1-scand9.log" 2>&1 || true; }
train(){ # <tag> <l2>
  python3 pattern_jass/tools/train.py --data "$RELAB" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --score-drop 4900 --l2 "$2" --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$1.pjtw" >"$ART/$1-train.log" 2>&1
  [ -f "$ART/$1.pjtw" ] && { v15d9 "$ART/$1"; scand9 "$ART/$1"; } || echo "  ABORT train $1"; }

echo "=== sweep l2 (deep-d12 data) : v15 d9 + Scan d9 ==="
declare -A R
for pair in "l2_3e-4 3e-4" "l2_6e-4 6e-4" "l2_1e-3 1e-3" "l2_3e-3 3e-3" "l2_1e-2 1e-2"; do
  set -- $pair
  train "$1" "$2"
  r=$(rate "$ART/$1-v15d9.log"); R[$1]=${r:-0}
  echo "  l2=$2 : v15 d9=$r   Scan d9=$(jrate "$ART/$1-scand9.log")"
done

# meilleur par v15-d9 → full bench (mt + hc)
BEST=$(for k in "${!R[@]}"; do echo "${R[$k]} $k"; done | sort -rn | head -1 | awk '{print $2}')
echo "=== gagnant=$BEST → full bench (mt + hc) ==="
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/$BEST-v15mt.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" hc 8 6 1 0 "" 64 >"$ART/$BEST-hc.log" 2>&1

echo; echo "=========================================================="
echo "   0202 SWEEP12 (l2 sur deep-d12) — VERDICT"
for k in l2_3e-4 l2_6e-4 l2_1e-3 l2_3e-3 l2_1e-2; do
  echo "  $k : v15 d9=$(rate "$ART/$k-v15d9.log")   Scan d9=$(jrate "$ART/$k-scand9.log")"
done
echo "  GAGNANT $BEST : v15 d9=$(rate "$ART/$BEST-v15d9.log")  mt=$(rate "$ART/$BEST-v15mt.log")  hc=$(rate "$ART/$BEST-hc.log")  | Scan d9=$(jrate "$ART/$BEST-scand9.log")"
echo "  ANCRES vs v15 : 0200 best (l2=3e-4)=0.306 ; champion=0.39 ; WDL=0.22"
echo "  → meilleur l2 > 0.306 = plafond cycle-1 relevé → ce modèle = générateur cycle-2."
echo "  → si tous ≈ 0 vs Scan = confirme la distance ; cycle-2 testera le compounding vs v15."
echo "=========================================================="
