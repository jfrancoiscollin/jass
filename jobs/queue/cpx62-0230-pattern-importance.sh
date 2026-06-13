#!/usr/bin/env bash
# id: cpx62-0230-pattern-importance
# description: GÉOMÉTRIE — étape 1 (analyse). Range les 32 patterns par IMPORTANCE
# (std·|corr_ref| + redondance) sur un eval full-fold bien entraîné → identifie les
# patterns à élaguer (géométrie LEAN = moins de lookups, vitesse vers Scan, sans perdre
# d'Elo). Utilise l'eval full-fold gen8 de 0227 s'il est local (le meilleur), sinon
# entraîne un full-fold représentatif (3 gens). Sortie = classement + candidats prune.
# Étape 2 (séparée) : élaguer la géométrie, ré-entraîner, valider en Elo (RFE).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0230-pattern-importance/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$REF" ] || { echo "ABORT: master de référence introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
echo "geometry: NUM_PATTERNS=$(python3 -c 'import sys;sys.path.insert(0,"pattern_jass/tools");import patterns;print(patterns.NUM_PATTERNS)')"

fit_ff(){ python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2" \
            --loss logistic --l2 "$4" --max-iter 200 --scale 1000 --prune --full-fold --out "$3.pjtw" >"$3-train.log" 2>&1; }
shard_sp(){ local NN=$1; local OUT=$2; shift 2; local PER=$(( (NN+NCPU-1)/NCPU ))
  for s in $(seq 1 "$NCPU"); do $JASS --gen-data-wdl "$PER" "${OUT}-$s.jnnw" 6 4 200 $((RANDOM)) "$@" >"${OUT}-$s.log" 2>&1 & done; wait
  python3 - "$OUT" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38; o=open(out+".jnnw",'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',0)); tot=0
for s in sorted(glob.glob(out+"-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1))):
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; tot+=n; o.write(b[8:8+n*REC])
o.seek(4); o.write(struct.pack('<I',tot)); o.close(); print("merged",tot)
PY
  rm -f "${OUT}-"*.jnnw; }

# --- pick the eval to analyse : prefer 0227 gen8 (best, 32-pat) else train 3-gen full-fold ---
BEST=/root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/gen8.pjtw
EVAL=""
if [ -f "$BEST" ] && [ "$(python3 -c "import struct;print(struct.unpack('<I',open('$BEST','rb').read(8)[4:8])[0])")" = "17006112" ]; then
  echo "using 0227 gen8 (best 32-pat full-fold)"; EVAL="$BEST"
else
  echo "0227 gen8 unavailable → training a 3-gen full-fold eval"
  CUM="$ART/cum.jnnw"
  shard_sp 200000 "$ART/sp0"; cp "$ART/sp0.jnnw" "$CUM"
  $JASS --dump-eval-features "$CUM" "$ART/f0" 2>&1|tail -1; fit_ff "$CUM" "$ART/f0" "$ART/g0" 3e-2
  PREV="$ART/g0"
  for g in 1 2 3; do
    shard_sp 300000 "$ART/sp$g" --nnue "$PREV.pjtw"
    python3 - "$ART/sp$g.jnnw" "$CUM" <<'PY'
import struct,sys; a=open(sys.argv[1],'rb').read(); c=sys.argv[2]
n=struct.unpack('<I',a[4:8])[0]; raw=open(c,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
o=open(c,'r+b'); o.seek(0,2); o.write(a[8:8+n*38]); o.seek(4); o.write(struct.pack('<I',old+n)); o.close()
PY
    $JASS --dump-eval-features "$CUM" "$ART/f$g" 2>&1|tail -1; fit_ff "$CUM" "$ART/f$g" "$ART/g$g" 3e-4; PREV="$ART/g$g"
  done
  EVAL="$ART/g3.pjtw"
fi
echo "EVAL=$EVAL"

echo; echo "=== IMPORTANCE (target=score, Scan-d10) ==="
python3 tools/pattern_importance.py --eval "$EVAL" --data "$REF" --target score --offset 1300000 --max 50000 2>&1 | tee "$ART/importance-score.log"
echo; echo "=== IMPORTANCE (target=wdl) ==="
python3 tools/pattern_importance.py --eval "$EVAL" --data "$REF" --target wdl --offset 1300000 --max 50000 2>&1 | tee "$ART/importance-wdl.log" | tail -40
echo; echo "=========================================================="
echo "  cpx62-0230 — CLASSEMENT D'IMPORTANCE des 32 patterns (étape 1)"
echo "  → la queue basse = candidats à l'élagage (étape 2 : prune+retrain+Elo)."
echo "  → redondance haute = un des deux patterns corrélés est droppable."
echo "=========================================================="
