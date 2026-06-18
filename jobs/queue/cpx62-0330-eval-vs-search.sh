#!/usr/bin/env bash
# id: cpx62-0330-eval-vs-search
# description: ISOLE ÉVAL vs RECHERCHE — le vrai mur. 0327/0329 montrent que jass se fait broyer vs Scan à
# TEMPS égal (mt1.5), toutes défaites « no legal move » → mais à temps égal on mesure éval+vitesse. Ici on
# rejoue la MÊME éval (distillée Scan, distrib 0314 = la meilleure, −387) à PROFONDEUR égale et asymétrique :
#   C1 mt1.5 (baseline temps égal)   C2 depth=9 (les deux)   C3 jass depth=11 vs Scan depth=9 (+2 plies)
# Si jass remonte à depth égale mais perd à temps égal → le verrou est la RECHERCHE/vitesse (NPS), pas l'éval
# ni la data. Si jass perd même à depth égale → le verrou est l'ÉVAL (classe). Le temps/partie en depth fixe
# = signal de vitesse (à depth 9 Scan est quasi-instantané → le wall-time ≈ le temps de réflexion de jass).
# expected_duration: ~2-3 h (matchs depth-fixe, pas de relabel)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-240}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/cpx62-0330-eval-vs-search/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw  # committé, déjà Scan-relabel
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw (0327) absent ($DATA)"; exit 4; }

preflight_build 1
preflight_train 240000 1
preflight_match 18 1.5 150              # C1 temps égal
preflight_note "C2 depth=9 (18 parties)"  55
preflight_note "C3 jass11/scan9 (18 parties)" 75
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

echo "=== build jass FULL Scan-alignée ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
      >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"

echo "=== train éval (distrib 0314, Scan-relabel, FULL-aligned + tempo-stage) ==="
"$JASS" --dump-eval-features "$DATA" "$ART/e.feat" >"$ART/dump.log" 2>&1
python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/e.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 \
  --prune --lowmem --full-fold --out "$ART/eval.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/eval.pjtw" ] || { echo "TRAIN FAIL"; tail -10 "$ART/train.log"; exit 9; }
manifest_write "$ART/eval.pjtw" "DISTILL=Scan SRC=0314-old FULL-aligned" "$DATA" >/dev/null

# run_match <name> <calibrate-extra-args...>
declare -A RATE ELO TPG
run_match(){
  local name="$1"; shift
  local lg="$ART/m-$name.log"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/eval.pjtw" \
      --scan-bb-size 0 --pairs 1 --max-plies 150 --allow-long-movetime "$@" >"$lg" 2>&1 || true
  RATE[$name]=$(grep -E 'score rate' "$lg" | grep -oE '0\.[0-9]+' | head -1)
  ELO[$name]=$(grep -E 'ELO estimate' "$lg" | grep -oE '\-?[0-9]+' | head -1)
  # temps moyen / partie (proxy vitesse) : dernier [Xs] par partie, moyenné
  TPG[$name]=$(grep -oE '\[[0-9]+s\]' "$lg" | grep -oE '[0-9]+' | awk 'NR>1{print $1-p} {p=$1} END{}' | awk '{s+=$1;n++} END{if(n)printf "%.0f", s/n; else print "NA"}')
  echo "  $name : rate=${RATE[$name]:-NA}  Elo=${ELO[$name]:-NA}  ~temps/partie=${TPG[$name]:-NA}s"
}

echo "=== C1 : TEMPS ÉGAL mt1.5 (baseline) ==="
run_match time-mt15 --movetime 1.5
echo "=== C2 : PROFONDEUR ÉGALE depth=9 ==="
run_match depth9-eq --depth 9
echo "=== C3 : ASYMÉTRIQUE jass depth=11 vs Scan depth=9 (+2 plies) ==="
run_match jass11-scan9 --jass-depth 11 --scan-depth 9

echo; echo "=========================================================="
echo "   cpx62-0330 — ISOLER ÉVAL vs RECHERCHE (même éval distillée Scan)"
echo "----------------------------------------------------------"
printf "  %-14s rate=%-7s Elo=%-6s temps/partie≈%ss\n" "C1 mt1.5"      "${RATE[time-mt15]:-NA}"   "${ELO[time-mt15]:-NA}"   "${TPG[time-mt15]:-NA}"
printf "  %-14s rate=%-7s Elo=%-6s temps/partie≈%ss\n" "C2 depth9=9"   "${RATE[depth9-eq]:-NA}"   "${ELO[depth9-eq]:-NA}"   "${TPG[depth9-eq]:-NA}"
printf "  %-14s rate=%-7s Elo=%-6s temps/partie≈%ss\n" "C3 jass11/sc9" "${RATE[jass11-scan9]:-NA}" "${ELO[jass11-scan9]:-NA}" "${TPG[jass11-scan9]:-NA}"
echo "----------------------------------------------------------"
echo "  C2 ≫ C1 → le verrou est la RECHERCHE/vitesse (NPS) : on arrête la data/éval, on attaque le NPS."
echo "  C2 ≈ C1 (toujours broyé) → le verrou est l'ÉVAL (classe) : ni features ni distrib ne l'ont bougé."
echo "  C3 montre combien de plies de recherche en plus compensent l'écart d'éval."
echo "=========================================================="
