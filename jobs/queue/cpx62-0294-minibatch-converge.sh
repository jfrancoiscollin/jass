#!/usr/bin/env bash
# id: cpx62-0294-minibatch-converge
# description: CHECK convergence minibatch vs lowmem. 0291 (80 it) : mse 2.94 vs 3.03 → pas bit-identique.
# Le problème est CONVEXE (logistic+L2 → optimum UNIQUE), donc à convergence les deux DOIVENT donner le
# même train_loss/mse. Ici on pousse à 300 itérations (+ tol serrée) et on compare le train_loss (=
# l'objectif minimisé, le vrai juge de convergence), val mse, endgame mse, et le nb d'itérations (a-t-il
# convergé avant le cap ?). Verdict : train_loss égaux → minibatch EXACT (l'écart 0291 = juste pas
# convergé) ; encore différents → vraie divergence du chemin chunké (bug à creuser avant prod).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0294-minibatch-converge/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SRC=/root/jass/jobs/results/cpx62-0266-kingloop-deepplay/artefacts.src
DATA="$SRC/cumulative.jnnw"
[ -f "$DATA" ] || { echo "ABORT: cumulatif 0266 absent"; exit 3; }

rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_ENDGAME_FEATURES=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -15 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
N=$(python3 -c "import struct;print(struct.unpack('<I',open('$DATA','rb').read(8)[4:8])[0])")
$JASS --dump-eval-features "$DATA" "$ART/featM" 2>&1 | tail -1

ITER=300; L2=3e-4; CHUNK=500000
train_one(){ local tlog="$ART/$2-train.log"
  /usr/bin/time -v python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --king-patterns \
    --eval-features-file "$ART/featM" --loss logistic --l2 "$L2" --max-iter "$ITER" --scale 1000 \
    --prune --full-fold $1 --out "$ART/$2.pjtw" >"$tlog" 2>"$ART/$2-time.txt"
  local loss=$(grep -oE 'train_loss=[0-9.]+' "$tlog" | head -1 | cut -d= -f2)
  local iters=$(grep -oE 'iters=[0-9]+' "$tlog" | head -1 | cut -d= -f2)
  local vmse=$(grep -oE 'val   : mse=[0-9.]+' "$tlog" | head -1 | grep -oE '[0-9.]+$')
  local emse=$(grep -oE 'val/phase mse : .*' "$tlog" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2)
  local rss=$(grep -oE 'Maximum resident set size.*: [0-9]+' "$ART/$2-time.txt" | grep -oE '[0-9]+$')
  echo "$2: train_loss=${loss:-?} iters=${iters:-?} val_mse=${vmse:-?} endgame_mse=${emse:-?} peakRSS=$(python3 -c "print(round(${rss:-0}/1048576,2))")GB"
}
echo "=== lowmem (max-iter $ITER) ===";    LM=$(train_one "--lowmem"          "lowmem");    echo "  $LM"
echo "=== minibatch $CHUNK (max-iter $ITER) ==="; MB=$(train_one "--minibatch $CHUNK" "minibatch"); echo "  $MB"

# diff direct des poids (juge définitif : même optimum convexe → mêmes poids)
python3 - "$ART/lowmem.pjtw" "$ART/minibatch.pjtw" <<'PY' || echo "(diff poids indisponible)"
import sys,struct
def loadw(p):
    b=open(p,'rb').read()
    import array
    # heuristique : chercher le plus grand bloc de float32 ; sinon on saute
    return b
a=open(sys.argv[1],'rb').read(); b=open(sys.argv[2],'rb').read()
print(f"  pjtw bytes: lowmem={len(a)} minibatch={len(b)}  same_size={len(a)==len(b)}")
if len(a)==len(b):
    import numpy as np
    # compare les octets bruts : si identiques, exact. Sinon mesure l'écart sur les float32 alignés.
    n=min(len(a),len(b))//4*4
    fa=np.frombuffer(a[:n],dtype=np.float32); fb=np.frombuffer(b[:n],dtype=np.float32)
    m=np.isfinite(fa)&np.isfinite(fb)
    if m.sum():
        d=np.abs(fa[m]-fb[m])
        print(f"  weights float32 view: max|Δ|={d.max():.6g}  mean|Δ|={d.mean():.6g}  (≈0 = mêmes poids)")
PY

echo; echo "=========================================================="
echo "   cpx62-0294 — CONVERGENCE minibatch vs lowmem (N=$N, $ITER it)"
echo "  lowmem    : $LM"
echo "  minibatch : $MB"
echo "----------------------------------------------------------"
echo "  train_loss égaux + iters<$ITER → CONVERGÉ au même optimum = minibatch EXACT (écart 0291 = sous-convergence)."
echo "  train_loss encore différents → divergence réelle du chemin chunké → creuser avant prod."
echo "=========================================================="
