#!/usr/bin/env bash
# id: cpx62-0355-phasesplit-finale
# description: OPTION A — éval finale-spécifique SANS sacrifier le midgame. Poids mg/eg SÉPARÉS (--phase-split)
# avec frontière finale-focus → les poids eg se spécialisent sur la finale (≠ --phase-weight mort qui up-weight
# un modèle PARTAGÉ et sacrifie le midgame). Juge : evalA vs eval0 EN DIRECT (sensible) + vs Scan depth-égale.
# evalA > eval0 → le fit finale-spécifique aide. ≈ → la séparation mg/eg ne suffit pas (cf 0312).
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0355-phasesplit-finale/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }

preflight_build 1; preflight_train 240000 2; preflight_note "evalA vs eval0 direct + vs Scan" 50; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }

echo "=== build ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"; "$JASS" --dump-eval-features "$DATA" "$ART/feat" >/dev/null 2>&1
tr_common="--data $DATA --scan-eval --eval-features-file $ART/feat --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold"
echo "=== train eval0 (baseline) + evalA (phase-split finale-focus) ==="
python3 pattern_jass/tools/train.py $tr_common --out "$ART/eval0.pjtw" >"$ART/e0.log" 2>&1
python3 pattern_jass/tools/train.py $tr_common --phase-split --phase-lo 8 --phase-hi 24 --out "$ART/evalA.pjtw" >"$ART/eA.log" 2>&1
[ -f "$ART/eval0.pjtw" ] && [ -f "$ART/evalA.pjtw" ] || { echo "TRAIN FAIL"; tail -8 "$ART/eA.log"; exit 9; }

rate(){ grep -E 'score rate|A score rate' "$1" | grep -oE '0?\.[0-9]+|[01]\.[0-9]+' | head -1; }
echo "=== evalA vs eval0 EN DIRECT (depth9, 108 parties) — métrique sensible ==="
"$JASS" --benchmark-nnue-vs-nnue "$ART/evalA.pjtw" "$ART/eval0.pjtw" 9 6 1 0 >"$ART/direct.log" 2>&1 || true
DIR=$(grep -E 'A score rate' "$ART/direct.log" | grep -oE '[0-9.]+' | head -1)
echo "=== vs Scan depth-égale d9 ==="
[ -x "$SCAN_BIN" ] && {
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/eval0.pjtw" --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 8 --max-plies 160 >"$ART/vs0.log" 2>&1 || true
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/evalA.pjtw" --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 8 --max-plies 160 >"$ART/vsA.log" 2>&1 || true; }
echo; echo "=========================================================="
echo "   cpx62-0355 — A : phase-split finale-focus (mg/eg séparés)"
echo "   evalA vs eval0 DIRECT : ${DIR:-NA}  (>0.55 = A meilleur)"
echo "   vs Scan d9 : eval0=$(rate "$ART/vs0.log")  evalA=$(rate "$ART/vsA.log")"
echo "=========================================================="
