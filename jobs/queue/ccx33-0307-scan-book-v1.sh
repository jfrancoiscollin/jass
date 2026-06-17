#!/usr/bin/env bash
# id: ccx33-0307-scan-book-v1
# description: PREMIER livre d'ouverture À LA SCAN, bout-en-bout. Construit le livre par expansion
# best-first + drop-out en self-play (--gen-scan-book : valeurs negamax remontées, format JBK2),
# vérifie que le moteur le JOUE (book=1), puis MESURE sa valeur de deux façons : (A) A/B self-play
# jass+livre vs jass-sans-livre (diag_book_jass_vs_jass, ISOLE le livre, indépendant de l'éval —
# méthode 0029) ; (B) si Scan dispo, jass-sans-livre vs Scan et jass+livre vs Scan (le livre
# rapproche-t-il de Scan ?). Éval = défaut compilé (cohérente partout, pas de couplage de flags) ;
# rebuild avec l'éval champion post-0297 = étape suivante. ccx33 est libre.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0307-scan-book-v1/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

# --- build (éval défaut compilée : aucun couplage flags/pjtw) ---
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- 1) CONSTRUIRE le livre (drop-out best-first, self-play) ---
BOOK="$ART/scan-book-v1.jbk2"
BUDGET=40000; LEAFD=14; DROP=50; MAXPLY=24
echo "=== gen-scan-book budget=$BUDGET leaf_depth=$LEAFD drop_margin=$DROP max_ply=$MAXPLY ==="
/usr/bin/time -v "$JASS" --gen-scan-book "$BOOK" "$BUDGET" "$LEAFD" "$DROP" "$MAXPLY" "$NCPU" \
    >"$ART/genbook.log" 2>"$ART/genbook.time"
tail -4 "$ART/genbook.log"
[ -f "$BOOK" ] || { echo "ABORT: livre non écrit"; tail -20 "$ART/genbook.log"; exit 6; }
echo "  taille fichier : $(ls -l "$BOOK" | awk '{print $5}') o   (magic $(head -c4 "$BOOK"))"

# --- 2) SANITY : le moteur joue-t-il le livre ? ---
echo "=== sanity : le moteur consulte le livre (attendu book=1) ==="
printf 'hub\ninit\nnew-game\npos start\nlevel depth=12\ngo\nquit\n' \
    | "$JASS" --book "$BOOK" hub 2>&1 | grep -iE 'bestmove' | head -1 | tee "$ART/sanity.log"
grep -q 'book=1' "$ART/sanity.log" || { echo "ABORT: le moteur ne joue PAS le livre (pas de book=1)"; exit 7; }

# --- 3) A/B self-play : jass+livre vs jass-sans-livre (isole la valeur du livre) ---
echo "=== A/B  jass+livre  vs  jass-sans-livre  (méthode 0029, indépendant de l'éval) ==="
python3 tools/diag_book_jass_vs_jass.py --jass "$JASS" --book "$BOOK" \
    --movetime 1.0 --pairs 12 -o "$ART/ab-selfplay.log" >"$ART/ab-selfplay.out" 2>&1 || true
AB=$(grep -iE 'score rate|rate ' "$ART/ab-selfplay.out" | head -3 | tr '\n' ' ')
echo "  $AB"
tail -20 "$ART/ab-selfplay.out" > "$ART/ab-tail.txt"

# --- 4) vs Scan (si dispo) : le livre rapproche-t-il de Scan ? ---
SCAN_BIN=/root/jass-scan/scan_linux
if [ -x "$SCAN_BIN" ]; then
  echo "=== jass SANS livre  vs Scan (sans livre) — baseline ==="
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" \
      --scan-bb-size 0 --scan-book off --movetime 1.0 --pairs 12 >"$ART/vs-scan-nobook.log" 2>&1 || true
  B0=$(grep -E 'score rate|ELO estimate' "$ART/vs-scan-nobook.log" | tr '\n' ' ')
  echo "  $B0"
  echo "=== jass AVEC livre  vs Scan (sans livre) — apport du livre ==="
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-book "$BOOK" \
      --scan-bb-size 0 --scan-book off --movetime 1.0 --pairs 12 >"$ART/vs-scan-book.log" 2>&1 || true
  B1=$(grep -E 'score rate|ELO estimate' "$ART/vs-scan-book.log" | tr '\n' ' ')
  echo "  $B1"
else
  echo "(Scan absent à $SCAN_BIN — section vs-Scan sautée)"; B0="(n/a)"; B1="(n/a)"
fi

echo; echo "=========================================================="
echo "   ccx33-0307 — LIVRE D'OUVERTURE À LA SCAN v1 (drop-out best-first + probe marge/softmax)"
echo "----------------------------------------------------------"
echo "  livre        : $(basename "$BOOK")  ($("$JASS" --book "$BOOK" hub <<<'quit' >/dev/null 2>&1; echo ok) positions via genbook.log)"
echo "  A/B livre    : $AB"
echo "    rate≈0.50 → livre SAIN (neutre, + variété) ; >0.55 → livre AIDE ; <0.45 → livre nuit."
echo "  vs Scan      : sans-livre  $B0"
echo "                 avec-livre  $B1   (delta = apport du livre)"
echo "----------------------------------------------------------"
echo "  SI livre sain/positif → intégrer + rebuild avec l'éval CHAMPION (post-0297) et"
echo "     sweeper (drop_margin/budget/leaf_depth) + probe margin/temp. SINON diagnostiquer genbook."
echo "=========================================================="
