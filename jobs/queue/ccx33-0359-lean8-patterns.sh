#!/usr/bin/env bash
# id: ccx33-0359-lean8-patterns
# description: OPTION F — la simplicité comme remède au SUR-PARAMÉTRAGE de la finale. On est un SURENSEMBLE de Scan
# (32 patterns ⊃ ses 8 bandes verticales, PATTERN_HASH=3^12 = AUCUN hash). Hypothèse : nos 24 patterns enrichis
# (diagonales/horizontales/blocs) sur-paramètrent la finale CLAIRSEMÉE → poids eg sous-ajustés. Test : réduire au
# jeu LEAN de Scan = les 8 bandes verticales (gen_patterns --drop des 24 autres), retrain à recette identique, juger
# vs Scan d9. evalF (8) > eval0 (32) → moins = mieux en finale (le surplus géométrique nuit au fit eg, on baker 8).
# ≈/pire → la capacité n'est pas le problème (cohérent surensemble) = plafond pratique du fit linéaire (→ pivot NN).
# NB : NUM_PATTERNS diffère ⇒ pjtw incomparables en direct → vs Scan (étalon absolu, depth-égale) uniquement.
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0359-lean8-patterns/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }

preflight_build 2; preflight_train 240000 2; preflight_note "2 arms × 216 parties vs Scan d9" 90; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indispo"; exit 5; }

build_jass(){ local B="$1"
  rm -rf "$B"
  cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
        -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake-$B.log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake-$B.log" || { echo "ABORT: egdb off ($B)"; exit 6; }
  cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build-$B.log" 2>&1 || { echo "BUILD FAIL $B"; tail -8 "$ART/build-$B.log"; exit 6; }
}
train_arm(){ local J="$1" out="$2"
  "$J" --dump-eval-features "$DATA" "$ART/feat" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/feat" \
    --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
    --out "$out" >"$ART/train-$(basename "$out").log" 2>&1
  [ -f "$out" ] || { echo "TRAIN FAIL $out"; tail -8 "$ART/train-$(basename "$out").log"; exit 9; }
}
rate(){ grep -E 'score rate' "$1" | grep -oE '0?\.[0-9]+|[01]\.[0-9]+' | head -1; }
vs_scan(){ local J="$1" pj="$2" lg="$3"
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$pj" \
    --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 12 --max-plies 160 >"$lg" 2>&1 || true; }

echo "=== ARM 32 : jeu enrichi actuel (baseline, arbre par défaut) ==="
build_jass build-p32
J32="$PWD/build-p32/jass"; train_arm "$J32" "$ART/eval0_32.pjtw"
NP32=$(grep -oE "NUM_PATTERNS *= *[0-9]+" pattern_jass/src/pattern.hpp | grep -oE "[0-9]+" | head -1)
echo "  NUM_PATTERNS (arbre défaut) = ${NP32}"

echo "=== régénère le jeu LEAN 8 (8 bandes verticales = les patterns de Scan) ==="
python3 pattern_jass/tools/gen_patterns.py --emit \
  --drop diag_0,diag_1,diag_2,diag_3,diag_4,diag_5,diag_6,anti_0,anti_1,anti_2,anti_3,anti_4,anti_5,anti_6,anti_7,horiz_0,horiz_1,horiz_2,horiz_3,horiz_4,sq_0,sq_1,sq_2,sq_3 >"$ART/gen8.log" 2>&1
NP8=$(grep -oE "NUM_PATTERNS *= *[0-9]+" pattern_jass/src/pattern.hpp | grep -oE "[0-9]+" | head -1)
echo "  NUM_PATTERNS (après drop) = ${NP8}"
[ "$NP8" = "8" ] || { echo "ABORT: réduction patterns ratée (NP8=$NP8)"; tail -20 "$ART/gen8.log"; exit 7; }

echo "=== ARM 8 : build + train sur le jeu LEAN ==="
build_jass build-p8
J8="$PWD/build-p8/jass"; train_arm "$J8" "$ART/evalF_8.pjtw"

echo "=== vs Scan d9 — 216 parties/arm (openings appariés, depth-égale) ==="
vs_scan "$J32" "$ART/eval0_32.pjtw" "$ART/vs32.log"
vs_scan "$J8"  "$ART/evalF_8.pjtw"  "$ART/vs8.log"

echo; echo "=========================================================="
echo "   ccx33-0359 — F : jeu LEAN 8 patterns (Scan) vs enrichi 32"
echo "----------------------------------------------------------"
echo "   eval0 (32 patterns) vs Scan d9 : $(rate "$ART/vs32.log")"
echo "   evalF ( 8 patterns) vs Scan d9 : $(rate "$ART/vs8.log")"
echo "----------------------------------------------------------"
echo "   evalF > eval0 → le surplus géométrique sur-paramètre la finale → baker le jeu 8."
echo "   evalF ≈/pire eval0 → la capacité n'est pas le mur (surensemble) = plafond pratique du fit linéaire → pivot NN."
echo "=========================================================="
