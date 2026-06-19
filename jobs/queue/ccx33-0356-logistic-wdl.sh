#!/usr/bin/env bash
# id: ccx33-0356-logistic-wdl
# description: OPTION B — méthode de Scan : WDL LOGISTIQUE (pas distillation de score). Même data (old-scan a aussi le WDL),
# avec frontière finale-focus → les poids eg se spécialisent sur la finale (≠ --phase-weight mort qui up-weight
# un modèle PARTAGÉ et sacrifie le midgame). Juge : evalB vs eval0 EN DIRECT (sensible) + vs Scan depth-égale.
# evalB > eval0 → le fit finale-spécifique aide. ≈ → la séparation mg/eg ne suffit pas (cf 0312).
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0356-logistic-wdl/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }

preflight_build 1; preflight_train 240000 2; preflight_note "evalB vs eval0 direct + vs Scan" 50; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }

echo "=== build ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"; "$JASS" --dump-eval-features "$DATA" "$ART/feat" >/dev/null 2>&1
COMMON="--data $DATA --scan-eval --eval-features-file $ART/feat --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold"
echo "=== train eval0 (baseline = distill score) + evalB (WDL logistique = méthode Scan, MÊME data) ==="
python3 pattern_jass/tools/train.py $COMMON --target score --score-drop 3000 --out "$ART/eval0.pjtw" >"$ART/e0.log" 2>&1
python3 pattern_jass/tools/train.py $COMMON --target wdl --loss logistic --out "$ART/evalB.pjtw" >"$ART/eA.log" 2>&1
[ -f "$ART/eval0.pjtw" ] && [ -f "$ART/evalB.pjtw" ] || { echo "TRAIN FAIL"; tail -8 "$ART/eA.log"; exit 9; }

rate(){ grep -E 'score rate|A score rate' "$1" | grep -oE '0?\.[0-9]+|[01]\.[0-9]+' | head -1; }
echo "=== evalB vs eval0 EN DIRECT (depth9, 108 parties) — métrique sensible ==="
"$JASS" --benchmark-nnue-vs-nnue "$ART/evalB.pjtw" "$ART/eval0.pjtw" 9 6 1 0 >"$ART/direct.log" 2>&1 || true
DIR=$(grep -E 'A score rate' "$ART/direct.log" | grep -oE '[0-9.]+' | head -1)
echo "=== vs Scan depth-égale d9 ==="
[ -x "$SCAN_BIN" ] && {
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/eval0.pjtw" --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 8 --max-plies 160 >"$ART/vs0.log" 2>&1 || true
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/evalB.pjtw" --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 8 --max-plies 160 >"$ART/vsA.log" 2>&1 || true; }
echo; echo "=========================================================="
echo "   ccx33-0356 — B : WDL logistique (méthode Scan, même data)"
echo "   evalB vs eval0 DIRECT : ${DIR:-NA}  (>0.55 = B meilleur)"
echo "   vs Scan d9 : eval0=$(rate "$ART/vs0.log")  evalB=$(rate "$ART/vsA.log")"
echo "=========================================================="
