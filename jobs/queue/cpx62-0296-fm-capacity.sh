#!/usr/bin/env bash
# id: cpx62-0296-fm-capacity
# description: 1er JOB BRANCHE CAPACITÉ (verdict 0287 : verrou finale = capacité éval linéaire, pas
# couverture). Levier le moins risqué SANS nouveau code : le terme FM (factorization-machine, déjà
# câblé : --fm-rank entraîne un pairwise NON-LINÉAIRE sur le résidu linéaire ; l'éval l'évalue déjà).
# Avec patterns king-aware, la FM capture les interactions ENTRE fenêtres = potentiellement la relation
# roi-roi que le linéaire additif ne peut pas représenter. A/B : même dataset (self-play EGDB-PERFECT,
# champion 0266, depth-8 ; build king-aware+egdb SANS endgame-features = 106, compat champion), bras
# LIN (linéaire) vs bras FM (linéaire+FM rank-8). egdb ON gen, OFF éval. Compare endgame-rois vs Scan.
# FM-rois ≪ LIN-rois → la non-linéarité aide → on pousse (rank, puis MLP). ≈ → FM pairwise insuffisant
# → table king-pair sparse / MLP / MTC.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0296-fm-capacity/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
APP=/root/egdb_extracted/app
SRC=/root/jass/jobs/results/cpx62-0266-kingloop-deepplay/artefacts.src
CHAMP="$SRC/gen8.pjtw"
ls "$APP"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: base egdb absente"; exit 4; }
[ -f "$CHAMP" ] || { echo "ABORT: champion 0266 absent"; exit 3; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1

rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }

# --- dataset partagé : self-play EGDB-PERFECT (~1M, depth-8, champion 0266) ---
EVAL_DEPTH=6; PLAY_DEPTH=8; NPER=1000000; CUM="$ART/data.jnnw"
PER=$(( (NPER + NCPU - 1) / NCPU ))
for s in $(seq 1 "$NCPU"); do
  JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=256 \
    $JASS --gen-data-wdl "$PER" "$ART/d-$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 $((RANDOM)) --nnue "$CHAMP" >"$ART/d-$s.log" 2>&1 &
done; wait
python3 - "$ART/d" "$CUM" <<'PY'
import struct,glob,sys,re
outp,dst=sys.argv[1],sys.argv[2]; REC=38; body=b""; add=0
for s in sorted(glob.glob(outp+"-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1))):
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; add+=n; body+=b[8:8+n*REC]
open(dst,'wb').write(b'JNNW'+struct.pack('<I',add)+body); print(f"data: {add}")
PY
rm -f "$ART"/d-*.jnnw
$JASS --dump-eval-features "$CUM" "$ART/featM" 2>&1 | tail -1

COMMON="--data $CUM --scan-eval --king-patterns --eval-features-file $ART/featM --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --full-fold"
elo(){ local lg="$ART/elo-$1.log"; $JASS --benchmark-scan-eval "$ART/$1.pjtw" hc 9 40 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2) (${W:-0}-${D:-0}-${L:-0})"; }
autopsy(){ local tag="$1"; [ -x "$SCAN_BIN" ] || { echo "(no Scan)"; return; }
  local G="$ART/games-$tag"; mkdir -p "$G"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/$tag.pjtw" --scan-bb-size 0 --movetime 0.5 --pairs 2 --dump-games-dir "$G" >"$ART/scan-$tag.log" 2>&1
  python3 tools/game_autopsy.py --games-dir "$G" --jass /bin/true --scan "$SCAN_BIN" --scan-depth 11 --scan-bb-size 0 --worst 6 --out "$ART/autopsy-$tag.txt" 2>"$ART/autopsy-$tag.err" || echo "(autopsie skip $tag)"
  grep -iE 'late-mid|endgame|deep-eg' "$ART/autopsy-$tag.txt" 2>/dev/null | head -4 | sed 's/^/    /'
}

echo "=== BRAS LIN (linéaire, --lowmem --prune) ==="
python3 pattern_jass/tools/train.py $COMMON --prune --lowmem --out "$ART/lin.pjtw" >"$ART/lin-train.log" 2>&1
[ -f "$ART/lin.pjtw" ] || { echo "ABORT lin"; tail -8 "$ART/lin-train.log"; exit 7; }
EG_LIN=$(grep -oE 'val/phase mse : .*' "$ART/lin-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2)
ELO_LIN=$(elo lin)
echo "=== BRAS FM (linéaire + FM rank-8, full design : no lowmem/prune) ==="
python3 pattern_jass/tools/train.py $COMMON --fm-rank 8 --fm-hash 8192 --l2-fm 1e-3 --out "$ART/fm.pjtw" >"$ART/fm-train.log" 2>&1
[ -f "$ART/fm.pjtw" ] || { echo "ABORT fm"; tail -12 "$ART/fm-train.log"; exit 7; }
FMRED=$(grep -oE 'FM : .*' "$ART/fm-train.log" | head -1)
EG_FM=$(grep -oE 'val/phase mse : .*' "$ART/fm-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2)
ELO_FM=$(elo fm)

echo; echo "=========================================================="
echo "   cpx62-0296 — CAPACITÉ : FM (non-linéaire pairwise) vs LINÉAIRE"
echo "----------------------------------------------------------"
echo "  $FMRED"
echo "  LIN : val_endgame_mse=$EG_LIN  Elo_vs_hc=$ELO_LIN"
echo "  --- autopsie LIN (perte rois par phase vs Scan) ---"; autopsy lin
echo "  FM  : val_endgame_mse=$EG_FM  Elo_vs_hc=$ELO_FM"
echo "  --- autopsie FM (perte rois par phase vs Scan) ---"; autopsy fm
echo "----------------------------------------------------------"
echo "  endgame-rois(FM) ≪ endgame-rois(LIN) → la NON-LINÉARITÉ aide → pousser (rank, puis MLP/king-pair)."
echo "  ≈ égal → FM pairwise insuffisant pour la relation roi-roi → table king-pair sparse / MLP / MTC."
echo "=========================================================="
