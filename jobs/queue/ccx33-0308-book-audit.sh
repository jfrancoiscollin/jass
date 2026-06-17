#!/usr/bin/env bash
# id: ccx33-0308-book-audit
# description: AUDIT QUALITÉ du livre d'ouverture à la Scan (suite de 0307). Réutilise le livre de
# 0307 s'il est encore sur le disque, sinon le reconstruit à l'identique. Puis : (1) STRUCTURE/VOLUME
# via --book-audit (histogramme de plies, profondeur, branching, largeur, feuilles) → répond
# « assez de volume / assez profond ? » sans Scan ; (2) QUALITÉ via Scan-oracle (book_audit_vs_scan) :
# % d'accord coup-livre vs meilleur-coup-Scan par ply, + calibration des valeurs de feuilles
# (spearman/sign vs Scan) + pièges (livre≥+50 mais Scan<0). Indépendant de la force d'éval.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0308-book-audit/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- livre : réutiliser 0307 si présent, sinon reconstruire à l'identique ---
BOOK=""
for cand in /root/jass/jobs/results/ccx33-0307-scan-book-v1/artefacts.src/scan-book-v1.jbk2 \
            /root/jass/jobs/results/ccx33-0307-scan-book-v1/artefacts/scan-book-v1.jbk2; do
  [ -f "$cand" ] && { BOOK="$cand"; break; }
done
if [ -z "$BOOK" ]; then
  echo "=== livre 0307 absent → reconstruction (budget 40000, leaf 14, drop 50, maxply 24) ==="
  BOOK="$ART/scan-book-v1.jbk2"
  "$JASS" --gen-scan-book "$BOOK" 40000 14 50 24 "$NCPU" >"$ART/genbook.log" 2>&1 || { echo GENBOOK FAIL; tail -10 "$ART/genbook.log"; exit 6; }
fi
echo "livre audité : $BOOK ($(ls -l "$BOOK" | awk '{print $5}') o)"

# --- 1) STRUCTURE / VOLUME (sans Scan) ---
echo "=== --book-audit : structure & volume ==="
"$JASS" --book-audit "$BOOK" "$ART/aud" 30 2>&1 | tee "$ART/structure.log"
NMOVES=$(grep -cv '^#' "$ART/aud.moves.tsv" 2>/dev/null || echo 0)
NLEAVES=$(grep -cv '^#' "$ART/aud.leaves.tsv" 2>/dev/null || echo 0)
echo "  internes=$NMOVES  feuilles=$NLEAVES"

# --- 2) QUALITÉ via Scan-oracle ---
SCAN_BIN=/root/jass-scan/scan_linux
if [ -x "$SCAN_BIN" ]; then
  echo "=== Scan-oracle : accord de coup + calibration des feuilles (depth 13, échantillon 300) ==="
  python3 tools/book_audit_vs_scan.py --moves "$ART/aud.moves.tsv" --leaves "$ART/aud.leaves.tsv" \
      --scan "$SCAN_BIN" --scan-depth 13 --scan-bb-size 0 \
      --sample-moves 300 --sample-leaves 300 >"$ART/quality.log" 2>&1 || echo "(Scan-oracle a échoué — voir quality.log)"
  sed -n '1,40p' "$ART/quality.log"
else
  echo "(Scan absent à $SCAN_BIN — section qualité sautée)"
fi

echo; echo "=========================================================="
echo "   ccx33-0308 — AUDIT du livre d'ouverture à la Scan"
echo "----------------------------------------------------------"
echo "  VOLUME   : voir histogramme de plies + max ply + branching (structure.log)."
echo "             max_ply≥~12 & masse jusqu'au ply 10-16 = assez profond ; sinon trop bushy"
echo "             → resserrer drop_margin / augmenter budget / semer des ouvertures master."
echo "  QUALITÉ  : accord coup vs Scan (>85% excellent) + calibration feuilles + pièges (quality.log)."
echo "             Pièges>0 → feuilles que le livre croit saines mais que Scan juge perdues."
echo "=========================================================="
