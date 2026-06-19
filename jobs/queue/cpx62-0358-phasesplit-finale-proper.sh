#!/usr/bin/env bash
# id: cpx62-0358-phasesplit-finale-proper
# description: OPTION C (refaite PROPREMENT — 0355 était un no-op). Le chemin --scan-eval IGNORE --phase-split et
# --tempo-stage ÉCRASE --phase-lo/hi → 0355 a entraîné DEUX configs identiques (pjtw byte-identiques, direct=0.5).
# Ici on fait varier POUR DE VRAI la rampe de phase (piece-count, PAS tempo) : eval0 = rampe legacy 0/40 (poids
# mg/eg co-fit comme aujourd'hui) vs evalC = rampe FINALE-NETTE 8/24 (la banque eg se spécialise sur ≤24p au lieu
# d'être tirée par le midgame — le conflit de phase mesuré en 0310). Build ET train doivent partager LO/HI
# (JASS_PHASE_LO/HI ↔ --phase-lo/--phase-hi), donc 2 binaires distincts → jugés vs Scan d9 (étalon absolu, méthodo
# permanente depth-égale), 270 parties/arm, openings appariés. evalC > eval0 nettement → la netteté finale aide le
# fit eg (brique à baker). ≈ → la séparation mg/eg ne lève pas le résidu finale = plafond pratique du fit linéaire.
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0358-phasesplit-finale-proper/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }

preflight_build 2; preflight_train 240000 2; preflight_note "2 arms × 270 parties vs Scan d9" 90; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indispo"; exit 5; }

# build_arm <dir> <PHASE_LO> <PHASE_HI> : build SANS tempo-stage (rampe piece-count), avec LO/HI donnés.
build_arm(){ local B="$1" lo="$2" hi="$3"
  rm -rf "$B"
  cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
        -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON \
        -DJASS_PHASE_LO="$lo" -DJASS_PHASE_HI="$hi" >"$ART/cmake-$B.log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake-$B.log" || { echo "ABORT: egdb off ($B)"; exit 6; }
  # CMake `if(JASS_PHASE_LO)` traite "0" comme FAUX → pas de message pour LO=0 (le header retombe
  # sur son défaut LO=0, ce qu'on veut). On n'assert le message que pour une rampe LO non nulle.
  if [ "$lo" != "0" ]; then
    grep -q "phase ramp LO=$lo" "$ART/cmake-$B.log" || { echo "ABORT: phase LO non pris ($B)"; exit 6; }
  fi
  grep -q "phase ramp HI=$hi" "$ART/cmake-$B.log" || { echo "ABORT: phase HI non pris ($B)"; exit 6; }
  cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build-$B.log" 2>&1 || { echo "BUILD FAIL $B"; tail -8 "$ART/build-$B.log"; exit 6; }
}
# train_arm <jass-bin> <PHASE_LO> <PHASE_HI> <out.pjtw> : train --scan-eval avec la MÊME rampe que le build (PAS de tempo).
train_arm(){ local J="$1" lo="$2" hi="$3" out="$4"
  "$J" --dump-eval-features "$DATA" "$ART/feat" >/dev/null 2>&1   # extras = indépendants de la phase
  python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/feat" \
    --target score --score-drop 3000 --phase-lo "$lo" --phase-hi "$hi" \
    --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
    --out "$out" >"$ART/train-$(basename "$out").log" 2>&1
  [ -f "$out" ] || { echo "TRAIN FAIL $out"; tail -8 "$ART/train-$(basename "$out").log"; exit 9; }
}
rate(){ grep -E 'score rate' "$1" | grep -oE '0?\.[0-9]+|[01]\.[0-9]+' | head -1; }
vs_scan(){ local J="$1" pj="$2" lg="$3"
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$pj" \
    --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 15 --max-plies 160 >"$lg" 2>&1 || true; }

echo "=== ARM 0 : rampe legacy 0/40 (mg/eg co-fit = baseline) ==="
build_arm build-p040 0 40
J0="$PWD/build-p040/jass"; train_arm "$J0" 0 40 "$ART/eval0.pjtw"

echo "=== ARM C : rampe FINALE-NETTE 8/24 (banque eg spécialisée finale) ==="
build_arm build-p824 8 24
JC="$PWD/build-p824/jass"; train_arm "$JC" 8 24 "$ART/evalC.pjtw"

echo "=== vs Scan d9 — 270 parties/arm (openings appariés, depth-égale) ==="
vs_scan "$J0" "$ART/eval0.pjtw" "$ART/vs0.log"
vs_scan "$JC" "$ART/evalC.pjtw" "$ART/vsC.log"

echo; echo "=========================================================="
echo "   cpx62-0358 — C : phase-split finale PROPRE (rampe piece-count)"
echo "----------------------------------------------------------"
echo "   eval0 (rampe 0/40)  vs Scan d9 : $(rate "$ART/vs0.log")"
echo "   evalC (rampe 8/24)  vs Scan d9 : $(rate "$ART/vsC.log")"
echo "   (rappel : ship tempo-stage ≈ 0.083 — 0353/0355)"
echo "----------------------------------------------------------"
echo "   evalC > eval0 nettement → netteté finale aide le fit eg → brique à confirmer vs tempo-ship."
echo "   evalC ≈ eval0 → la séparation mg/eg ne lève pas le résidu finale = plafond pratique du fit linéaire."
echo "=========================================================="
