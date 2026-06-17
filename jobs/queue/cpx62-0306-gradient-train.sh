#!/usr/bin/env bash
# id: cpx62-0306-gradient-train
# description: GREFFE le gradient de conversion sur l'éval SATURÉE (0297). A/B propre, même données +
# mêmes features, seule la CIBLE change : BASE = logistic WDL (= régime prod) vs GRAD = logistic
# --target prob (cible graduée hybride proxy+MTC, 0.12/0.04). Mesure si le gradient fait baisser
# endgame-rois vs Scan (l'éval valorise mieux la finale → convertit) sans casser l'Elo global.
# S'auto-enchaîne après 0297 (cumulatif) + 0301 (MTC sur cpx62). egdb OFF aux benchmarks (éval pure).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0306-gradient-train/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app; MTCDB=/root/egdb_mtc/app
SRC=/root/jass/jobs/results/cpx62-0297-saturate-loop/artefacts.src
CUM="$SRC/cumulative.jnnw"
[ -f "$CUM" ] || { echo "ABORT: cumulatif 0297 absent (0297 a échoué ?)"; exit 3; }
ls "$MTCDB"/*.idx_mtc >/dev/null 2>&1 || { echo "ABORT: MTC absent (0301 pas fini ?)"; exit 4; }
ls "$WLD"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: WLD absente"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1

rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_ENDGAME_FEATURES=ON \
      -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
N=$(python3 -c "import struct;print(struct.unpack('<I',open('$CUM','rb').read(8)[4:8])[0])")
echo "cumulatif 0297 = $N positions"

echo "=== relabel gradient (hybride proxy+MTC, défaut 0.12/0.04) ==="
cp "$CUM" "$ART/cum.jnnw"
$JASS --egdb-mtc-relabel "$ART/cum.jnnw" "$WLD" "$MTCDB" "$ART/cum-grad.jnnw" 1024 2>&1 | tail -2
echo "=== features (partagées : positions identiques) ==="
$JASS --dump-eval-features "$ART/cum-grad.jnnw" "$ART/feat" 2>&1 | tail -1

CFOLD="--full-fold --king-patterns"
elo(){ local lg="$ART/elo-$1.log"; $JASS --benchmark-scan-eval "$ART/$1.pjtw" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2) (${W:-0}-${D:-0}-${L:-0})"; }
SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
autopsy(){ local tag="$1"; [ -x "$SCAN_BIN" ] || { echo "(no Scan)"; return; }
  local G="$ART/games-$tag"; mkdir -p "$G"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/$tag.pjtw" --scan-bb-size 0 --movetime 0.5 --pairs 3 --dump-games-dir "$G" >"$ART/scan-$tag.log" 2>&1
  python3 tools/game_autopsy.py --games-dir "$G" --jass /bin/true --scan "$SCAN_BIN" --scan-depth 11 --scan-bb-size 0 --worst 6 --out "$ART/autopsy-$tag.txt" 2>"$ART/autopsy-$tag.err" || echo "(autopsie skip)"
  grep -iE 'late-mid|endgame|deep-eg' "$ART/autopsy-$tag.txt" 2>/dev/null | head -4 | sed 's/^/    /'
  grep -E 'score rate|ELO estimate' "$ART/scan-$tag.log" | tr '\n' ' '; echo
}

echo "=== BASE : logistic WDL (régime prod) ==="
python3 pattern_jass/tools/train.py --data "$ART/cum.jnnw" --scan-eval --eval-features-file "$ART/feat" \
  --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --lowmem $CFOLD --out "$ART/base.pjtw" >"$ART/base-train.log" 2>&1
[ -f "$ART/base.pjtw" ] || { echo "ABORT base"; tail -8 "$ART/base-train.log"; exit 7; }
EGB=$(grep -oE 'val/phase mse : .*' "$ART/base-train.log"|grep -oE 'endgame=[0-9.]+'|head -1|cut -d= -f2); ELB=$(elo base)
echo "  base endgame_mse=$EGB Elo=$ELB"
echo "=== GRAD : logistic --target prob (gradient conversion) ==="
python3 pattern_jass/tools/train.py --data "$ART/cum-grad.jnnw" --scan-eval --eval-features-file "$ART/feat" \
  --loss logistic --target prob --l2 3e-4 --max-iter 200 --scale 1000 --prune --lowmem $CFOLD --out "$ART/grad.pjtw" >"$ART/grad-train.log" 2>&1
[ -f "$ART/grad.pjtw" ] || { echo "ABORT grad"; tail -8 "$ART/grad-train.log"; exit 7; }
EGG=$(grep -oE 'val/phase mse : .*' "$ART/grad-train.log"|grep -oE 'endgame=[0-9.]+'|head -1|cut -d= -f2); ELG=$(elo grad)
echo "  grad endgame_mse=$EGG Elo=$ELG"

echo; echo "=========================================================="
echo "   cpx62-0306 — GRADIENT de conversion greffé sur l'éval saturée 0297 (A/B même données)"
echo "----------------------------------------------------------"
echo "  BASE (WDL)        Elo_vs_hc=$ELB"; echo "  --- autopsie BASE vs Scan ---"; autopsy base
echo "  GRAD (--target prob)  Elo_vs_hc=$ELG"; echo "  --- autopsie GRAD vs Scan ---"; autopsy grad
echo "----------------------------------------------------------"
echo "  endgame-rois(GRAD) < endgame-rois(BASE) + Elo ≈ ou > → le gradient AIDE la finale"
echo "     (l'éval valorise mieux la conversion) → intégrer + sweep conversion autour de 0.12/0.04."
echo "  ≈ égal → le gradient hybride ne transfère pas → reconsidérer (DTW maison / cible plus forte)."
echo "=========================================================="
