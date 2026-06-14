#!/usr/bin/env bash
# id: ccx33-0252-eval-vs-search
# description: DIAGNOSTIC FINALES 2/2 — ÉVAL vs RECHERCHE. Les autopsies montrent un
# saignement en finale (perte oracle ~2.8 à mt0.5, cf 0249). Cette perte est-elle de
# l'ÉVAL (la fonction note mal les finales) ou de la RECHERCHE (assez de profondeur la
# corrigerait) ? On rejoue NOTRE éval men-only (0227 gen8, la baseline de 0249) vs Scan à
# DEUX budgets — depth 1 (quasi éval pure) et movetime 2s (recherche profonde) — et on
# autopsie chaque lot (oracle Scan depth 11, perte par phase). Trois points de profondeur :
#   depth1  <  mt0.5 (0249, finale=2.82)  <  mt2.0   (effort de recherche croissant)
#   * perte finale DÉCROÎT avec la profondeur  -> SEARCH-bound (l'éval va, la recherche manque)
#   * perte finale PLATE                       -> EVAL-bound (la fonction note mal les finales,
#                                                  cohérent avec un plafond de classe en finale)
# Men-only (build par défaut), pour coller exactement à la baseline 0249/0238.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0252-eval-vs-search/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

# --- ensure Scan (auto-install) ---
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  echo "=== Scan absent → install (git clone rhalbersma/scan) ==="; rm -rf /root/jass-scan
  git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 \
    || { echo "ABORT: clone Scan échoué (réseau ?)"; tail -5 "$ART/scan-clone.log"; exit 4; }
  chmod +x "$SCAN_BIN" 2>/dev/null || true
fi
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan introuvable"; exit 4; }

# --- build MEN-ONLY jass (défaut) pour charger l'éval men-only de 0227 ---
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- éval men-only baseline (0227 gen8 / repli 0231) — la MÊME que 0249/0238 ---
EVAL=""
for cand in /root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/gen8.pjtw \
            /root/jass/jobs/results/ccx33-0231-rfe-baseline32/artefacts.src/gen8.pjtw; do
  [ -f "$cand" ] && { EVAL="$cand"; break; }
done
[ -n "$EVAL" ] || { echo "ABORT: aucun gen8 men-only local (0227/0231) — box recyclée ?"; exit 6; }
echo "EVAL (men-only) = $EVAL"

# run_one BUDGETLABEL  <calibrate budget args...>  : match (dump) + autopsie par phase
run_one() {
  local tag="$1"; shift
  local games="$ART/games-$tag"; mkdir -p "$games"
  echo "=== match vs Scan [$tag] : $* (dump) ==="
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$EVAL" \
      --scan-bb-size 0 "$@" --pairs 2 --dump-games-dir "$games" >"$ART/match-$tag.log" 2>&1
  echo "  $(grep -E 'score rate|ELO estimate' "$ART/match-$tag.log" | tr '\n' ' ')"
  local ng; ng=$(ls "$games"/game-*.json 2>/dev/null | wc -l); echo "  parties : $ng"
  [ "$ng" -gt 0 ] || { echo "  (aucune partie [$tag] — autopsie sautée)"; tail -15 "$ART/match-$tag.log"; return 1; }
  echo "=== autopsie [$tag] (oracle Scan depth 11, par phase) ==="
  python3 tools/game_autopsy.py --games-dir "$games" --jass /bin/true --scan "$SCAN_BIN" \
      --scan-depth 11 --scan-bb-size 0 --worst 10 --out "$ART/autopsy-$tag.txt" 2>"$ART/autopsy-$tag.err"
}

# depth 1 = quasi éval pure ; movetime 2.0s = recherche profonde
run_one depth1 --depth 1            || true
run_one mt2.0  --movetime 2.0       || true

# --- synthèse : perte par phase aux deux budgets (+ rappel baseline 0249 mt0.5) ---
phase_block() { sed -n '/-- par PHASE --/,/-- par ROIS/p' "$1" 2>/dev/null | grep -E 'opening|midgame|late-mid|endgame|deep-eg'; }
echo; echo "=========================================================="
echo "   ccx33-0252 — ÉVAL vs RECHERCHE : perte par phase selon la profondeur"
echo "----------------------------------------------------------"
echo "[depth 1 — quasi éval pure]"; phase_block "$ART/autopsy-depth1.txt"
echo "[mt 0.5s — BASELINE 0249]  (rappel : endgame=2.82  deep-eg=2.38)"
echo "[mt 2.0s — recherche profonde]"; phase_block "$ART/autopsy-mt2.0.txt"
echo "----------------------------------------------------------"
echo "  perte FINALE qui DÉCROÎT depth1 -> mt0.5 -> mt2.0 = SEARCH-bound (éval OK)"
echo "  perte FINALE ~PLATE selon la profondeur          = EVAL-bound (note mal les finales)"
echo "=========================================================="
