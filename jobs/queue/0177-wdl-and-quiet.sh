#!/usr/bin/env bash
# id: 0177-wdl-and-quiet
# description: LEVIER 1 (dernier levier linéaire) — cible WDL + filtre quiet, sur
# la base saine (v4 106 + score-drop 4900 + l2=1e-4). La classe linéaire est
# saturée en data/géométrie/extras ; restent la CIBLE et la PROPRETÉ des rows.
#
#   Champion réf : target=score, l2=1e-4, drop4900, anchor 1/1/3 = 1.0/0.472.
#
#   A) score + QUIET   : même réglage champion + on ne garde que les positions
#      quiètes (pas de capture forcée) → isole le levier propreté sur la cible
#      éprouvée (même échelle, comparaison la plus nette).
#   B) WDL (sweep l2)  : target=wdl (résultat de partie {-1,0,1}, façon Scan) —
#      SANS material-anchor (l'échelle WDL ±1 ≠ piece-units, l'ancre fausserait
#      le fit) ; petit sweep l2 {1e-5,3e-5,1e-4} car l'échelle diffère.
#   C) WDL + QUIET     : meilleur l2 WDL + quiet.
#
# Le meilleur des trois passe en bench FIABLE (144) + movetime (72).
# expected_duration: ~2-3 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0177-wdl-and-quiet/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

FEAT="$ART/feat";  ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1
QUIET="$ART/quiet"; ./build-prod/jass --dump-quiet-flags "$CLEAN" "$QUIET" 2>&1 | tail -1
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
trn(){ # $1=tag  $2..=extra train args ; benche vs hc(6 pairs) + v15(6 pairs)
  local tag="$1"; shift
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
    --score-clip 5000 --max-iter 200 --scale 1000 "$@" --out "$ART/$tag.pjtw" \
    >"$ART/$tag-train.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" hc  8 6 1 0 "" 64 >"$ART/$tag-hc.log"  2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" "$V15" 9 6 1 0 "" 64 >"$ART/$tag-v15.log" 2>&1
  echo "  $tag : vs hc=$(rate "$ART/$tag-hc.log")  vs v15 d9=$(rate "$ART/$tag-v15.log")"
}

echo; echo "=== A) score + QUIET (champion + propreté) ==="
trn sq --target score --score-drop 4900 --l2 1e-4 --quiet-flags-file "$QUIET" --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0

echo; echo "=== B) WDL sweep l2 (no anchor) ==="
bestw=""; bestwr="0"
for L in 1e-5 3e-5 1e-4; do
  trn wdl-$L --target wdl --score-drop 4900 --l2 $L
  r=$(rate "$ART/wdl-$L-v15.log")
  awk "BEGIN{exit !($r>$bestwr)}" && { bestwr=$r; bestw=$L; }
done
echo "  meilleur WDL l2=$bestw (v15=$bestwr)"

echo; echo "=== C) WDL + QUIET (meilleur l2 WDL) ==="
[ -n "$bestw" ] && trn wq --target wdl --score-drop 4900 --l2 "$bestw" --quiet-flags-file "$QUIET"

# Finaliste = le meilleur vs v15 parmi {sq, wdl-best, wq} → bench fiable + movetime.
echo; echo "=== finaliste → bench fiable (144) + movetime (72) ==="
fin=""; finr="0"
for t in sq wdl-$bestw wq; do
  [ -f "$ART/$t.pjtw" ] || continue
  r=$(rate "$ART/$t-v15.log"); awk "BEGIN{exit !($r>$finr)}" && { finr=$r; fin=$t; }
done
echo "  finaliste=$fin (v15 d9=$finr)"
if [ -n "$fin" ]; then
  ./build-prod/jass --benchmark-scan-eval "$ART/$fin.pjtw" "$V15" 9  8 1 0   "" 64 >"$ART/fin-v15-d9.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/$fin.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/fin-v15-mt.log" 2>&1
fi

echo; echo "=========================================================="
echo "        0177 WDL + QUIET — VERDICT"
echo "  champion réf (score,l2=1e-4,drop)        : hc=1.0   v15 d9=0.472"
echo "  A score+quiet                            : hc=$(rate "$ART/sq-hc.log")  v15 d9=$(rate "$ART/sq-v15.log")"
for L in 1e-5 3e-5 1e-4; do echo "  B wdl l2=$L                              : hc=$(rate "$ART/wdl-$L-hc.log")  v15 d9=$(rate "$ART/wdl-$L-v15.log")"; done
echo "  C wdl+quiet (l2=$bestw)                  : hc=$(rate "$ART/wq-hc.log")  v15 d9=$(rate "$ART/wq-v15.log")"
echo "  finaliste=$fin  →  v15 d9(144)=$(rate "$ART/fin-v15-d9.log")  movetime(72)=$(rate "$ART/fin-v15-mt.log")"
echo "  → un config > 0.472 = la cible/propreté est un levier ; sinon le linéaire"
echo "    est bien saturé et le prochain pas est non-linéaire (FM)."
echo "=========================================================="
