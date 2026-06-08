#!/usr/bin/env bash
# id: 0172-extras-retest-with-drop
# description: Re-test des EXTRAS structurels AVEC le filtre (analogue de 0171
# pour la géométrie). 0155 condamnait les extras (0.25) MAIS sur base v5 +
# poison. Maintenant sur base SAINE (v4 + score-drop), on teste v4+112 extras
# (mobilité-roi, back-rank, avancement) vs le baseline v4+106 = 0.944/0.389.
#
# Lecture : v4+112+drop > 0.944/0.389 = les extras apportent de la connaissance
# utile sur base saine → nouveau levier vers v15. Sinon neutres/négatifs.
# + probe des poids appris des 6 extras (sensés maintenant ?).
#
# expected_duration: ~1-1.5 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0172-extras-retest-with-drop"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo "ABORT: 1.4M (0141) absent"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== build prod + tests (v4 32 patterns + 112 extras) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== dump features (112) + distill v4+112 (score-drop 4900, l2=1e-5) ==="
FEAT="$ART/clean112.feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-5 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/v4e.pjtw" 2>&1 \
    | tee "$ART/train.log" | grep -E "score-drop|val   :"

# probe des poids des 6 extras structurels
python3 - "$ART/v4e.pjtw" <<'PYEOF'
import struct,numpy as np,sys
raw=open(sys.argv[1],'rb').read();_,_,s,np_,ne=struct.unpack_from('<IIIII',raw,0)
em=np.frombuffer(raw,'<i4',ne,20+8*np_)
lab={106:'BkMob',107:'WkMob',108:'Bback',109:'Wback',110:'Badv',111:'Wadv'}
print("    extras structurels (poids mg) : "+"  ".join(f"{lab[i]}={em[i]/s:+.3f}" for i in range(106,112)))
PYEOF

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
echo; echo "=== benchs fiables ==="
[ -f "$ART/v4e.pjtw" ] || { echo "ABORT train"; exit 7; }
./build-prod/jass --benchmark-scan-eval "$ART/v4e.pjtw" hc 8 10 1 0 "" 64 2>&1 | tee "$ART/vs-hc.log" | grep -E "Result|rate"
./build-prod/jass --benchmark-scan-eval "$ART/v4e.pjtw" "$V15" 9 8 1 0 "" 64 2>&1 | tee "$ART/vs-v15.log" | grep -E "Result|rate"

echo; echo "=========================================================="
echo "        0172 EXTRAS RE-TEST (avec score-drop) — VERDICT"
echo "  v4+112+drop : vs hc=$(anyrate "$ART/vs-hc.log")  vs v15 d9=$(anyrate "$ART/vs-v15.log")"
echo "  baseline v4+106+drop (0171) : 0.944 / 0.389"
echo "  → > 0.944/0.389 = les extras structurels aident sur base saine (levier)."
echo "  → ≈ = neutres. < = nuisent même propre."
echo "=========================================================="
