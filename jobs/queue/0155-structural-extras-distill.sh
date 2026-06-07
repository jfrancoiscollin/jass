#!/usr/bin/env bash
# id: 0155-structural-extras-distill
# description: AXE QUALITÉ étape 2 — extras structurels (1er lot). On ajoute 6
# features dames (NUM_EXTRAS 106→112) : mobilité-roi séparée (B/W), intégrité
# rangée de fond (B/W), avancement (B/W). Sur la géométrie v5 (40 patterns).
# Re-dump des features (112 colonnes, l'ancien 0147 en a 106) puis distillation
# fraîche ancrée matériel. ATTRIBUTION : compare à 0159 (v5+106 extras) pour
# isoler l'apport des extras, et à 0154 (v4+106).
#
# Baselines : 0154 (v4,106) vs hc 0.75 ; 0159 (v5,106) vs hc=? ; ici v5+112.
# Lecture : > 0159 = les extras structurels aident. Bench GATE MOVETIME.
#
# expected_duration: ~1.5-2.5 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0155-structural-extras-distill"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo "ABORT: labels 0141 manquants"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== build prod + tests (v5 40 patterns + 112 extras + accumulateur) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== re-dump des features (112 colonnes) ==="
FEAT="$ART/clean112.feat"
./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1
echo "feat: $FEAT"

probe () { python3 - "$1" <<'PYEOF'
import struct,numpy as np,sys
raw=open(sys.argv[1],'rb').read();_,_,s,np_,ne=struct.unpack_from('<IIIII',raw,0)
em=np.frombuffer(raw,'<i4',ne,20+8*np_)
lab={106:'BkMob',107:'WkMob',108:'Bback',109:'Wback',110:'Badv',111:'Wadv'}
print(f"    n_ext={ne}  HOMMES mg b={em[100]/s:+.2f} w={em[101]/s:+.2f}")
print("    extras structurels (mg) : " + "  ".join(f"{lab[i]}={em[i]/s:+.3f}" for i in range(106,112)))
PYEOF
}
anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

train_one () {
    echo; echo "=== TRAIN $1 (v5+112 extras, material-anchor 1.0, l2=$2) ==="
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
    echo "  $tag vs hc = $(anyrate "$ART/$tag-vs-hc.log")"
done
BEST=A; RA=$(anyrate "$ART/A-vs-hc.log"); RB=$(anyrate "$ART/B-vs-hc.log")
python3 -c "import sys;a=float('${RA:-0}' or 0);b=float('${RB:-0}' or 0);sys.exit(0 if a>=b else 1)" && BEST=A || BEST=B

echo; echo "=== meilleur ($BEST) vs v15 — GATE MOVETIME (depth 9 + movetime 300) ==="
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 9  3 1 0   "" 64 2>&1 | tee "$ART/$BEST-vs-v15-d9.log" >/dev/null
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 64 3 1 300 "" 64 2>&1 | tee "$ART/$BEST-vs-v15-mt.log" >/dev/null

echo; echo "=========================================================="
echo "        0155 EXTRAS STRUCTURELS (v5+112) — VERDICT"
echo "  A vs hc=${RA:-?}  B vs hc=${RB:-?}"
echo "  $BEST vs v15 : d9=$(anyrate "$ART/$BEST-vs-v15-d9.log")  mt=$(anyrate "$ART/$BEST-vs-v15-mt.log")"
echo "  baselines : 0154(v4,106) hc=0.75 ; 0159(v5,106) hc=<voir 0159>"
echo "  → > 0159 = extras structurels aident. Regarder les poids appris (probe)."
echo "=========================================================="
