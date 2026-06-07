#!/usr/bin/env bash
# id: 0154-richer-patterns-distill
# description: LEVIER 3 — patterns plus riches. 0153 a montré que le fine-tuning
# ne dépasse pas le prior distillé (0.444 vs hc) → le limiteur n'est pas la
# méthode mais la CAPACITÉ des features. v4 enrichit la géométrie : 8 → 32
# patterns (vertical v3 + diagonales physiques + horizontales + blocs). On
# re-distille un v3 FRAIS (32 patterns) sur le 1.4M, ancré matériel, et on
# mesure fit + jeu — avec le GATE MOVETIME (32 patterns = 4× de lookups, donc
# éval plus lente : il faut gagner EN TEMPS, pas seulement à depth fixe).
#
# Baselines 8-patterns (à battre) : vs hc 0.444 ; vs v15 d9=0.111 mt=0.056.
# 2 configs l2 (1e-5 libre vs 1e-3 dompté ; la sparsité ×4 peut sur-apprendre).
# Lecture : 32-patterns vs hc >0.444 = la géométrie aide ; ET vs v15 mt >0.056
#           = ça survit au coût vitesse. Sinon : trop lent / sur-appris.
#
# expected_duration: ~1.5-2.5 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0154-richer-patterns-distill"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo "ABORT: labels 0141 manquants"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "labels: $CLEAN"; echo "v15: $V15"

echo; echo "=== build prod + tests (géométrie v4 = 32 patterns) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
# confirme la géométrie chargée
python3 -c "import sys; sys.path.insert(0,'pattern_jass/tools'); import patterns as p; print('NUM_PATTERNS', p.NUM_PATTERNS, 'TOTAL_BUCKETS', p.TOTAL_BUCKETS)"
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== dump-eval-features (extras inchangés=106 ; réutilise 0147 si présent) ==="
FEAT=/root/jass/jobs/results/0147-scan-eval-full/artefacts.src/clean.feat
if [ ! -f "$FEAT" ]; then FEAT="$ART/clean.feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1; fi
echo "feat: $FEAT"

probe () { python3 - "$1" <<'PYEOF'
import struct,numpy as np,sys
raw=open(sys.argv[1],'rb').read();_,_,s,np_,ne=struct.unpack_from('<IIIII',raw,0);o=20
pm=np.frombuffer(raw,'<i4',np_,o);o+=4*np_;pe=np.frombuffer(raw,'<i4',np_,o);o+=4*np_
em=np.frombuffer(raw,'<i4',ne,o);o+=4*ne;ee=np.frombuffer(raw,'<i4',ne,o)
print(f"    n_pat={np_} HOMMES mg b={em[100]/s:+.2f} w={em[101]/s:+.2f} | ROIS mg b_moy={(em[0:50]/s).mean():+.2f}"
      f" | PAT |w|max={np.abs(pm).max()/s:.2f}pu nnz={(pm!=0).sum()}/{np_}")
PYEOF
}
anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

train_one () {  # $1 tag  $2 l2
    local tag="$1" l2="$2"
    echo; echo "=== TRAIN $tag (32 patterns, material-anchor 1.0, l2=$l2) ==="
    python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
        --target score --score-clip 5000 --l2 "$l2" --max-iter 200 --scale 1000 \
        --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$tag.pjtw" 2>&1 \
        | tee "$ART/$tag-train.log" | grep -E "val   :|design|material-anchor|quant"
    probe "$ART/$tag.pjtw"
}

train_one A 1e-5
train_one B 1e-3

echo; echo "=== TRIANGLE vs handcrafted (depth 8) ==="
for tag in A B; do
    ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" hc 8 3 1 0 "" 64 2>&1 | tee "$ART/$tag-vs-hc.log" >/dev/null
    echo "  $tag vs hc = $(anyrate "$ART/$tag-vs-hc.log")  (baseline 8-pat = 0.444)"
done

BEST=A; RA=$(anyrate "$ART/A-vs-hc.log"); RB=$(anyrate "$ART/B-vs-hc.log")
python3 -c "import sys;a=float('${RA:-0}' or 0);b=float('${RB:-0}' or 0);sys.exit(0 if a>=b else 1)" && BEST=A || BEST=B
echo; echo "=== meilleur ($BEST) vs v15 — GATE MOVETIME (depth 9 + movetime 300) ==="
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 9  3 1 0   "" 64 2>&1 | tee "$ART/$BEST-vs-v15-d9.log" >/dev/null
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 64 3 1 300 "" 64 2>&1 | tee "$ART/$BEST-vs-v15-mt.log" >/dev/null
echo "  $BEST vs v15 : d9=$(anyrate "$ART/$BEST-vs-v15-d9.log")  mt=$(anyrate "$ART/$BEST-vs-v15-mt.log")"

echo; echo "=========================================================="
echo "        0154 PATTERNS RICHES (32) — VERDICT"
echo "  A vs hc=${RA:-?}  B vs hc=${RB:-?}   (8-pat baseline = 0.444)"
echo "  $BEST vs v15 : d9=$(anyrate "$ART/$BEST-vs-v15-d9.log")  mt=$(anyrate "$ART/$BEST-vs-v15-mt.log")"
echo "                 (8-pat baseline v15 : d9=0.111  mt=0.056)"
echo "  → vs hc >0.444 = la géométrie aide ; vs v15 mt >0.056 = survit au"
echo "    coût vitesse (32 patterns = 4× lookups). Sinon trop lent/sur-appris."
echo "=========================================================="
