#!/usr/bin/env bash
# id: 0170-score-drop-attribution
# description: INVESTIGATION #6 — attribuer le GAIN du score-drop (0169 : retirer
# les 2% de scores extrêmes ±9989 → val_mse 38→1.8, vs hc 0.42→0.83). Question :
# le gain vient-il du FILTRE seul ou du FILTRE+DATA ? Et surtout : ça réduit-il
# l'écart vs v15 (baseline 0.11) ? train.py a maintenant --score-drop.
#
# 3 modèles v4, benchs FIABLES vs hc (216) ET vs v15 (depth 9, 144) :
#   - 1.4M sans filtre   (= contrôle, ref 0165 = 0.72 / 0.11)
#   - 1.4M + score-drop  (filtre seul)
#   - 4.7M + score-drop  (filtre + data)
#
# expected_duration: ~2.5-3.5 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0170-score-drop-attribution"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU  RAM: $(free -g 2>/dev/null | awk '/Mem/{print $2"G"}') ==="

SMALL=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
BIG=/root/jass/jobs/results/0162-good-data-full-master/artefacts.src/master-full-scan-d10.jnnw
[ -f "$SMALL" ] || { echo "ABORT: 1.4M absent"; exit 3; }
[ -f "$BIG" ]   || { echo "ABORT: 4.7M absent"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== build prod + tests (v4) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

run () {  # $1 tag  $2 data.jnnw  $3 score-drop(0|4900)
    local tag="$1" data="$2" drop="$3"
    echo; echo "##### $tag (drop=$drop) #####"
    local feat="$ART/$tag.feat"; ./build-prod/jass --dump-eval-features "$data" "$feat" 2>&1 | tail -1
    python3 pattern_jass/tools/train.py --data "$data" --scan-eval --eval-features-file "$feat" \
        --target score --score-clip 5000 --score-drop "$drop" --l2 1e-5 --max-iter 200 --scale 1000 \
        --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$tag.pjtw" 2>&1 \
        | tee "$ART/$tag-train.log" | grep -E "score-drop|val   :|split"
    rm -f "$feat"
    [ -f "$ART/$tag.pjtw" ] || { echo "  $tag : train ÉCHEC"; return; }
    ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" hc 8 12 1 0 "" 64 > "$ART/$tag-vs-hc.log" 2>&1
    ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" "$V15" 9 8 1 0 "" 64 > "$ART/$tag-vs-v15.log" 2>&1
    echo "  $tag : vs hc=$(anyrate "$ART/$tag-vs-hc.log")  vs v15 d9=$(anyrate "$ART/$tag-vs-v15.log")"
    rm -f "$ART/$tag.pjtw"
}

run small-nofilter "$SMALL" 0
run small-drop      "$SMALL" 4900
run big-drop        "$BIG"   4900

echo; echo "=========================================================="
echo "        0170 SCORE-DROP — ATTRIBUTION — VERDICT"
echo "  (vs hc 216 ±0.034 ; vs v15 d9 144)"
echo "  1.4M sans filtre : vs hc=$(anyrate "$ART/small-nofilter-vs-hc.log")  vs v15=$(anyrate "$ART/small-nofilter-vs-v15.log")  (ref 0165: 0.72/0.11)"
echo "  1.4M + drop      : vs hc=$(anyrate "$ART/small-drop-vs-hc.log")  vs v15=$(anyrate "$ART/small-drop-vs-v15.log")"
echo "  4.7M + drop      : vs hc=$(anyrate "$ART/big-drop-vs-hc.log")  vs v15=$(anyrate "$ART/big-drop-vs-v15.log")"
echo "  → 1.4M-drop > 1.4M-nofilter = le FILTRE aide. 4.7M-drop > 1.4M-drop = la DATA aide en plus."
echo "  → vs v15 qui monte = on RÉDUIT enfin l'écart (le vrai but)."
echo "=========================================================="
