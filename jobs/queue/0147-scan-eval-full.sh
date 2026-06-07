#!/usr/bin/env bash
# id: 0147-scan-eval-full
# description: BUILD + ENTRAÎNEMENT de l'éval Scan-style COMPLÈTE (PJTW v3),
# « tout comme Scan » : material + king PST + mobilité + balance + patterns
# men, TOUT phase-split MG/EG, codé en C++ (src/scan_eval.*), playable.
#
# Cette éval structurée est la brique demandée explicitement (peu importe le
# verdict des fit-checks 0144/0145/0146). On l'entraîne en standalone sur les
# labels PROPRES Scan-d10 (1.4M, réutilisés de 0141), puis on la bench vs v15
# en depth + movetime (la v3 est ~100× plus rapide que le NNUE → elle creuse
# plus à temps égal).
#
# Pipeline :
#   1. build prod (compile src/scan_eval.cpp + tests)
#   2. ctest (la consistance Python↔C++ est verrouillée par test_scan_eval)
#   3. dump-eval-features (les 106 extras = SOURCE UNIQUE partagée C++/train)
#   4. train --scan-eval (phase-split complet → v3 playable)
#   5. bench v3 vs v15 : depth 8 (vitesse invisible) + movetime 0.3s
#   6. SPSA-tune les constantes POUR la v3, re-bench movetime tuné
#
# expected_duration: ~1.5-2.5 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0147-scan-eval-full"
ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo "ABORT: labels propres de 0141 manquants ($CLEAN)"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "labels : $CLEAN"; echo "v15 : $V15"

echo; echo "=== Phase 0 : deps ==="
python3 -c "import numpy, scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== Phase 1 : build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }
echo "--- ctest (consistance Python↔C++ : test_scan_eval) ---"
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || {
    echo "TESTS FAIL"; tail -20 "$ART/tests.log"; exit 6; }

echo; echo "=== Phase 2 : dump-eval-features (106 extras, source unique) ==="
FEAT="$ART/clean.feat"
./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tee "$ART/dump.log"
[ -f "$FEAT" ] || { echo "ABORT dump-eval-features"; exit 4; }

echo; echo "=== Phase 3 : train éval Scan-style complète (v3, phase-split) ==="
V3="$ART/scan_eval_v3.pjtw"
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval \
    --eval-features-file "$FEAT" --target score --score-clip 5000 \
    --l2 1e-5 --max-iter 200 --scale 1000 --out "$V3" \
    2>&1 | tee "$ART/train.log"
[ -f "$V3" ] || { echo "ABORT train v3"; exit 4; }

rate_se () { grep -oE 'SCAN_EVAL score rate vs NNUE: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }
rate_sp () { grep -oE 'A score rate: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }

echo; echo "=== Phase 4 : bench v3 vs v15 (depth 8 + movetime 0.3s) ==="
./build-prod/jass --benchmark-scan-eval "$V3" "$V15" 8 5 1 0 2>&1 | tee "$ART/v3-vs-v15-d8.log"
R_D=$(rate_se "$ART/v3-vs-v15-d8.log")
./build-prod/jass --benchmark-scan-eval "$V3" "$V15" 64 5 1 300 2>&1 | tee "$ART/v3-vs-v15-mt.log"
R_MT=$(rate_se "$ART/v3-vs-v15-mt.log")

echo; echo "=== Phase 5 : SPSA-tune les constantes POUR la v3 (depth 8) ==="
BEST_JSON="$ART/spsa-best.json"
python3 tools/spsa_tune.py --jass ./build-prod/jass --net "$V3" \
    --iters 60 --pairs 4 --depth 8 --threads 1 --use-pvs 1 --out "$BEST_JSON" \
    2>&1 | tee "$ART/spsa.log"
BEST=$(python3 -c "import json;print(json.load(open('$BEST_JSON'))['spec'])" 2>/dev/null || echo "use_pvs=1")
echo "best spec : $BEST"

echo; echo "=== Phase 6 : re-bench v3 (tunée) vs v15 movetime ==="
./build-prod/jass --benchmark-scan-eval "$V3" "$V15" 64 5 1 300 "$BEST" 2>&1 | tee "$ART/v3-tuned-vs-v15-mt.log"
R_MT_T=$(rate_se "$ART/v3-tuned-vs-v15-mt.log")

echo; echo "=========================================================="
echo "        0147 SCAN-EVAL COMPLÈTE (v3) — VERDICT"
echo "=========================================================="
echo "  v3 : $V3   best spec : $BEST"
python3 - "${R_D:-}" "${R_MT:-}" "${R_MT_T:-}" <<'EOF'
import sys, math
def elo(r):
    try: r=float(r)
    except: return "n/a"
    if r<=0: return "-inf"
    if r>=1: return "+inf"
    return f"{-400*math.log10(1/r-1):+.0f}"
d,mt,mtt=sys.argv[1:4]
print(f"  v3 vs v15 @ DEPTH 8   : {d or 'n/a':>6}  ELO {elo(d)}  (vitesse invisible)")
print(f"  v3 vs v15 @ MOVETIME  : {mt or 'n/a':>6}  ELO {elo(mt)}  (vitesse compte)")
print(f"  v3(TUNÉ) vs v15 @ MT  : {mtt or 'n/a':>6}  ELO {elo(mtt)}")
def f(x):
    try: return float(x)
    except: return None
dd,mm=f(d),f(mt)
if dd is not None and mm is not None:
    print(f"  → depth→movetime : {dd:.3f}→{mm:.3f}  gain {mm-dd:+.3f}",
          "(la profondeur de la v3 paie)" if mm>=dd else "(⚠ time-mgmt haute profondeur)")
EOF
echo "=========================================================="
