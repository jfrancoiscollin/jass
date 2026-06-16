#!/usr/bin/env bash
# id: cpx62-0291-minibatch-control
# description: CONTRÔLE minibatch vs lowmem (et diagnostic du wedge 0274). Les deux sont du L-BFGS
# PLEIN-BATCH (même optimum) ; ils ne diffèrent QUE par la mémoire : lowmem garde tout le pattern
# sparse + extras bruts en RAM (croît avec le dataset) ; minibatch reconstruit le design par chunk de
# N lignes dans l'objectif (pic RAM ~ taille de chunk). On entraîne le MÊME dataset (cumulatif 0266
# ~5.1M = l'échelle qui a thrashé 0274) + MÊMES features (build prod king-aware + endgame-features),
# une fois --lowmem une fois --minibatch, sous /usr/bin/time -v. On compare : (a) val/phase MSE
# (≈ identique → minibatch EXACT), (b) pic RSS (minibatch ≪ lowmem ?), (c) wall time, (d) Elo vs hc.
# Tranche : minibatch est-il l'outil mémoire exact pour scaler au-delà de lowmem, et lowmem
# thrashait-il vraiment à 5M (cause du wedge 0274) ?
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0291-minibatch-control/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SRC=/root/jass/jobs/results/cpx62-0266-kingloop-deepplay/artefacts.src
GLOBAL="$SRC/cumulative.jnnw"

# --- build prod (king-aware + endgame-features, = éval prod, dump 110 features) ---
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_ENDGAME_FEATURES=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "ENDGAME FEATURES ENABLED" "$ART/cmake.log" || { echo "ABORT: features off"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- dataset : cumulatif 0266 (~5.1M) si présent, sinon génère ~2M ---
if [ -f "$GLOBAL" ]; then
  DATA="$GLOBAL"; N=$(python3 -c "import struct;print(struct.unpack('<I',open('$DATA','rb').read(8)[4:8])[0])")
  echo "dataset = cumulatif 0266 : $N positions"
else
  echo "cumulatif 0266 absent → génère ~2M (depth-8, hc-ish)"
  DATA="$ART/gen.jnnw"; PER=$(( (2000000 + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do $JASS --gen-data-wdl "$PER" "$ART/g-$s.jnnw" 6 8 200 $((RANDOM)) >"$ART/g-$s.log" 2>&1 & done; wait
  python3 - "$ART/g" "$DATA" <<'PY'
import struct,glob,sys,re
outp,dst=sys.argv[1],sys.argv[2]; REC=38; body=b""; add=0
for s in sorted(glob.glob(outp+"-*.jnnw")):
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; add+=n; body+=b[8:8+n*REC]
open(dst,'wb').write(b'JNNW'+struct.pack('<I',add)+body); print("gen",add)
PY
  N=$(python3 -c "import struct;print(struct.unpack('<I',open('$DATA','rb').read(8)[4:8])[0])")
fi

# --- dump features une fois (partagé par les deux trains) ---
$JASS --dump-eval-features "$DATA" "$ART/featM" 2>&1 | tail -1

ITER=80; L2=3e-4; CHUNK=500000
train_one(){ # $1=mode-flag  $2=tag
  local tlog="$ART/$2-train.log"; local tv="$ART/$2-time.txt"
  /usr/bin/time -v timeout 3600 python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --king-patterns \
    --eval-features-file "$ART/featM" --loss logistic --l2 "$L2" --max-iter "$ITER" --scale 1000 \
    --prune --full-fold $1 --out "$ART/$2.pjtw" >"$tlog" 2>"$tv"; local rc=$?
  local mse=$(grep -oE 'val/phase mse : .*' "$tlog" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2)
  local rss=$(grep -oE 'Maximum resident set size.*: [0-9]+' "$tv" | grep -oE '[0-9]+$')
  local wall=$(grep -oE 'Elapsed .wall clock.*: .*' "$tv" | grep -oE '[0-9:.]+$')
  echo "$2: rc=$rc  endgame_mse=${mse:-?}  peakRSS=$(python3 -c "print(round(${rss:-0}/1048576,2),'GB')")  wall=${wall:-?}"
}
elo(){ local lg="$ART/elo-$1.log"; $JASS --benchmark-scan-eval "$ART/$1.pjtw" hc 9 40 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2) (${W:-0}-${D:-0}-${L:-0})"; }

echo "=== A) LOWMEM (max-iter $ITER) ===";    A=$(train_one "--lowmem"          "lowmem");    echo "  $A"
echo "=== B) MINIBATCH $CHUNK (max-iter $ITER) ==="; B=$(train_one "--minibatch $CHUNK" "minibatch"); echo "  $B"
ELOA="n/a"; ELOB="n/a"
[ -f "$ART/lowmem.pjtw" ]    && ELOA=$(elo lowmem)
[ -f "$ART/minibatch.pjtw" ] && ELOB=$(elo minibatch)

echo; echo "=========================================================="
echo "   cpx62-0291 — CONTRÔLE minibatch vs lowmem  (N=$N positions, $ITER iters)"
echo "----------------------------------------------------------"
echo "  LOWMEM    : $A   Elo_vs_hc=$ELOA"
echo "  MINIBATCH : $B   Elo_vs_hc=$ELOB"
echo "----------------------------------------------------------"
echo "  endgame_mse ≈ identique → minibatch EXACT (même optimum que lowmem)."
echo "  peakRSS(minibatch) ≪ peakRSS(lowmem) → minibatch = l'outil mémoire pour scaler."
echo "  si lowmem rc=124 (timeout) ou RSS proche 32GB → CONFIRME le thrash = cause du wedge 0274."
echo "=========================================================="
