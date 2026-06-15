#!/usr/bin/env bash
# id: cpx62-0265-reval-control
# description: CONTRÔLE — résoudre le confond de mesure de 0263. Son elo_vs_hc (+182.8) a été
# mesuré avec le binaire NMP-off, celui de 0241 (+229.5) avec l'ANCIEN binaire (NMP on) → pas
# comparable. On re-mesure les DEUX évals king-aware (0241 gen8 et 0263 gen8) avec le MÊME
# binaire ACTUEL (NMP off, improving on), vs hc 60 paires. Verdict :
#   0241 ≈ 0263 → le play profond finale (Chemin B) était NEUTRE (le -47 était l'effet NMP-off
#                 sur la mesure) ; la densif finale reste OUVERTE, on teste « play fort partout ».
#   0241 >> 0263 → le play profond finale a NUI (comme phase-weight/label-depth).
# Donne aussi le VRAI champion king-aware (le point de départ du prochain loop).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0265-reval-control/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
grep -q "eg_pieces  = 40" src/search_params.hpp && echo "binaire = NMP OFF (eg_pieces=40)" || echo "WARNING: NMP pas off ?"

E0241=/root/jass/jobs/results/cpx62-0241-kingloop-scaled/artefacts.src/gen8.pjtw
E0263=/root/jass/jobs/results/cpx62-0263-kingloop-playdepth/artefacts.src/gen8.pjtw
[ -f "$E0241" ] || { echo "ABORT: 0241 gen8 introuvable"; exit 6; }
[ -f "$E0263" ] || { echo "ABORT: 0263 gen8 introuvable"; exit 6; }

elo_vs_hc(){ local lg="$ART/elo-$1.log"
  $JASS --benchmark-scan-eval "$2" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)"
}
echo "=== re-mesure 0241 gen8 (binaire NMP-off, 60p) ==="; R0241=$(elo_vs_hc 0241 "$E0241"); echo "  $R0241"
echo "=== re-mesure 0263 gen8 (binaire NMP-off, 60p) ==="; R0263=$(elo_vs_hc 0263 "$E0263"); echo "  $R0263"

echo; echo "=========================================================="
echo "   cpx62-0265 — CONTRÔLE : 0241 vs 0263 sur le MÊME binaire (NMP-off)"
echo "----------------------------------------------------------"
echo "  0241 gen8 (sans deep-play)   : $R0241   [mesuré +229.5 sur l'ANCIEN binaire]"
echo "  0263 gen8 (deep-play finale) : $R0263   [mesuré +182.8 sur le binaire NMP-off]"
echo "----------------------------------------------------------"
echo "  Écart faible → Chemin B NEUTRE (le -47 = effet NMP-off sur la mesure) → densif finale OUVERTE."
echo "  0241 >> 0263 → Chemin B a NUI. Dans les 2 cas : le champion = le plus haut des deux."
echo "=========================================================="
