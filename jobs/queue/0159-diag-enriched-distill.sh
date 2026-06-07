#!/usr/bin/env bash
# id: 0159-diag-enriched-distill
# description: AXE QUALITÉ étape 1 — géométrie diag-enrichie (v5, 40 patterns).
# 0156 : les diagonales sont l'orientation la plus contributive. L'accumulateur
# pattern (PR #243) rend une géométrie plus riche ABORDABLE (éval cheap), donc
# v5 = v4 (32) + 8 blocs diagonaux 3×4 (4 par sens). On re-distille FRAIS sur le
# 1.4M (ancré matériel) et on mesure fit + jeu, GATE MOVETIME.
#
# Baselines 32-patterns (v4, à battre) : vs hc 0.75 ; vs v15 d9=0.139 mt=0.083.
# Lecture : vs hc / vs v15 mt > baselines = la densité diagonale aide (et reste
# rapide grâce à l'accumulateur). Sparsité ×1.25 vs v4 (40 vs 32 patterns) →
# surveiller un éventuel sur-apprentissage (val bon mais jeu en retrait).
#
# expected_duration: ~1.5-2.5 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0159-diag-enriched-distill"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo "ABORT: labels 0141 manquants"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "labels: $CLEAN"; echo "v15: $V15"

echo; echo "=== build prod + tests (géométrie v5 = 40 patterns + accumulateur) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import sys; sys.path.insert(0,'pattern_jass/tools'); import patterns as p; print('NUM_PATTERNS', p.NUM_PATTERNS, 'TOTAL', p.TOTAL_BUCKETS)"
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== dump-eval-features (extras=106 ; réutilise 0147 si présent) ==="
FEAT=/root/jass/jobs/results/0147-scan-eval-full/artefacts.src/clean.feat
if [ ! -f "$FEAT" ]; then FEAT="$ART/clean.feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1; fi
echo "feat: $FEAT"

probe () { python3 - "$1" <<'PYEOF'
import struct,numpy as np,sys
raw=open(sys.argv[1],'rb').read();_,_,s,np_,ne=struct.unpack_from('<IIIII',raw,0);o=20
pm=np.frombuffer(raw,'<i4',np_,o).astype(np.float64);o+=4*np_
em=np.frombuffer(raw,'<i4',ne,20+8*np_)
print(f"    n_pat={np_} HOMMES mg b={em[100]/s:+.2f} w={em[101]/s:+.2f} | ROIS mg b_moy={(em[0:50]/s).mean():+.2f}"
      f" | PAT nnz={(pm!=0).sum()}/{np_} ({100*(pm!=0).sum()/np_:.1f}%)")
PYEOF
}
anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

train_one () {  # $1 tag  $2 l2
    echo; echo "=== TRAIN $1 (40 patterns, material-anchor 1.0, l2=$2) ==="
    python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
        --target score --score-clip 5000 --l2 "$2" --max-iter 200 --scale 1000 \
        --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$1.pjtw" 2>&1 \
        | tee "$ART/$1-train.log" | grep -E "val   :|design|material-anchor"
    probe "$ART/$1.pjtw"
}
train_one A 1e-5
train_one B 1e-3

echo; echo "=== TRIANGLE vs handcrafted (depth 8) ==="
for tag in A B; do
    ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" hc 8 3 1 0 "" 64 2>&1 | tee "$ART/$tag-vs-hc.log" >/dev/null
    echo "  $tag vs hc = $(anyrate "$ART/$tag-vs-hc.log")  (v4 32-pat baseline = 0.75)"
done
BEST=A; RA=$(anyrate "$ART/A-vs-hc.log"); RB=$(anyrate "$ART/B-vs-hc.log")
python3 -c "import sys;a=float('${RA:-0}' or 0);b=float('${RB:-0}' or 0);sys.exit(0 if a>=b else 1)" && BEST=A || BEST=B

echo; echo "=== meilleur ($BEST) vs v15 — GATE MOVETIME (depth 9 + movetime 300) ==="
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 9  3 1 0   "" 64 2>&1 | tee "$ART/$BEST-vs-v15-d9.log" >/dev/null
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 64 3 1 300 "" 64 2>&1 | tee "$ART/$BEST-vs-v15-mt.log" >/dev/null

echo; echo "=========================================================="
echo "        0159 DIAG-ENRICHI (40 patterns) — VERDICT"
echo "  A vs hc=${RA:-?}  B vs hc=${RB:-?}   (v4 32-pat baseline = 0.75)"
echo "  $BEST vs v15 : d9=$(anyrate "$ART/$BEST-vs-v15-d9.log")  mt=$(anyrate "$ART/$BEST-vs-v15-mt.log")"
echo "                 (v4 32-pat baseline : d9=0.139  mt=0.083)"
echo "  → vs hc / vs v15 mt > baselines = densité diagonale paie (et rapide via"
echo "    l'accumulateur). val bon mais jeu en retrait = sparsité → plus de data."
echo "=========================================================="
