#!/usr/bin/env bash
# id: 0201-eval-vs-search-depth-handicap
# description: DIAGNOSTIC eval-vs-recherche. 0199 a montré champion ≈ v15 ≈ ~0
# vs Scan à profondeur ÉGALE (d9/d11). À profondeur égale, avec un alpha-beta
# sain + quiescence, la qualité du coup est gouvernée par l'EVAL des feuilles
# (la recherche de jass est déjà complète : TT/ID/aspiration/PVS/LMR/null-move/
# IID/singular/multicut/quiescence — cf docs/archives/ARCHITECTURE.md). Reste à CHIFFRER :
# de combien de plies de RAB jass a-t-il besoin pour égaler Scan ? Peu (+1-2) =
# léger déficit d'efficacité/extensions ; beaucoup (+4-6) ou jamais = c'est
# l'EVAL qui est loin, la profondeur ne compense pas.
#
# On fixe Scan à depth 9 et on donne à jass un handicap croissant
# (--jass-depth/--scan-depth, ajoutés au harness) :
#   champion vs Scan-d9, jass à d ∈ {9, 11, 13}   (+0, +2, +4)
#   v15      vs Scan-d9, jass à d ∈ {9, 13}        (contrôle)
# Rappel ancre (0199) : champion d9=d9 ≈ 0.000.
#
#   rate monte vers 0.5 avec +k plies → la profondeur compense, déficit surtout
#     d'efficacité de recherche (k = le « coût en plies » de notre éval).
#   rate reste ~0 même à +4 → l'EVAL est le gap dominant, la recherche n'y peut
#     rien → tout l'effort doit aller sur l'éval (ligne 0196-0200).
#
# expected_duration: ~1.5-2.5 h (jass à d13 fixe = le poste lent).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/0201-eval-vs-search-depth-handicap/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass

SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then
    git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" || { echo "ABORT clone scan"; exit 4; }
    chmod +x "$SCAN_DIR/scan_linux"
fi
SCAN="$SCAN_DIR/scan_linux"; [ -x "$SCAN" ] || { echo ABORT scan; exit 4; }

V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
CHAMP=/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src/champ.pjtw
if [ ! -f "$CHAMP" ]; then
  echo "=== re-distill champion ==="
  CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
  [ -f "$CLEAN" ] || { echo "ABORT master clean"; exit 3; }
  $JASS --dump-eval-features "$CLEAN" "$ART/champ.feat" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$ART/champ.feat" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/champ.pjtw" >"$ART/champ-train.log" 2>&1
  CHAMP="$ART/champ.pjtw"; [ -f "$CHAMP" ] || { echo ABORT redistill; exit 7; }
  rm -f "$ART/champ.feat"
fi
echo "champion=$CHAMP ; v15=$V15"
jrate(){ grep -oE 'Jass score rate:\s*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+'|head -1; }
match(){ # <tag> <eval-flag> <eval-path> <jass-depth>
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN" "$2" "$3" \
    --scan-depth 9 --jass-depth "$4" --pairs 6 --jass-threads 1 >"$ART/$1.log" 2>&1
  echo "$(jrate "$ART/$1.log")"; }

echo; echo "############ champion vs Scan-d9, handicap de profondeur jass ############"
for JD in 9 11 13; do
  r=$(match "champ-jd$JD" --jass-pattern "$CHAMP" "$JD")
  echo "  jass d$JD  vs Scan d9 : champion = $r   (+$((JD-9)) plies)"
done
echo; echo "############ v15 (contrôle) vs Scan-d9 ############"
for JD in 9 13; do
  r=$(match "v15-jd$JD" --nnue "$V15" "$JD")
  echo "  jass d$JD  vs Scan d9 : v15 = $r   (+$((JD-9)) plies)"
done

echo; echo "=========================================================="
echo "   0201 DIAG eval-vs-recherche (handicap de profondeur) — VERDICT"
echo "  champion vs Scan-d9 :  d9=$(jrate "$ART/champ-jd9.log")  d11=$(jrate "$ART/champ-jd11.log")  d13=$(jrate "$ART/champ-jd13.log")   (+0 / +2 / +4 plies)"
echo "  v15      vs Scan-d9 :  d9=$(jrate "$ART/v15-jd9.log")  d13=$(jrate "$ART/v15-jd13.log")"
echo "  RAPPEL 0199 : champion d9=d9 ≈ 0.000 ; v15 d9=d9 ≈ 0.056"
echo "  → rate ↗ vers 0.5 avec +k = la profondeur compense → déficit d'efficacité de recherche (≈ +k plies)."
echo "  → rate ~0 même à +4 = l'EVAL est le gap dominant → tout l'effort sur l'éval (0196-0200)."
echo "=========================================================="
