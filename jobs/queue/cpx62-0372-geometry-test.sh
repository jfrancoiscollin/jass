#!/usr/bin/env bash
# id: cpx62-0372-geometry-test
# description: LE test propre de géométrie qu'on n'a JAMAIS fait (tous nos verdicts géométrie 0230/0234/0239/0359
# étaient en full-fold = familles de translates ÉCRASÉES → confondus). Ici : MÊME data poolée (de la boucle), deux
# évals au repli CORRECT (color-fold, position-préservant) — 32-pat (8,5M poids, surensemble de Scan : verticales +
# 24 géométries enrichies) vs 8-pat (2,1M ≈ Scan exact). Jugé CROSS-ARCH en DIRECT (jass_vs_jass_arch : 2 binaires,
# car NUM_PATTERNS différent). >0.5 pour le 32 → les géométries enrichies (diagonales etc., que Scan n'a PAS) captent
# du signal → levier pour DÉPASSER l'éval de Scan en linéaire. ≈/<0.5 → le 8 (Scan-fidèle) suffit. ⚠️ N'A DE SENS
# qu'avec un GROS pool (fitter 8,5M poids) → pointer POOL_PATH sur le pool le + volumineux dispo (après plusieurs tours).
# Aucun Scan (pivot self). DÉPLOYER après que la boucle ait accumulé du volume.
# expected_duration: ~1 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-120}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0372-geometry-test/artefacts"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"; SCALE=1000
GEOM=/root/jass-geom-lean8
# pool poolé de la boucle : pointer sur le + volumineux dispo (tour récent). Défaut = 0371 (tour 1 cap-relevé).
POOL_PATH="${POOL_PATH:-jobs/results/cpx62-0371-round-refit/artefacts/pooled.jnnw}"
preflight_build 2; preflight_train 2000000 2; preflight_note "2 évals color-fold (32 vs 8) + match cross-arch" 60; preflight_check

echo "=== récupère le pool de la boucle ($POOL_PATH) ==="
ok=0; for i in $(seq 1 20); do git fetch origin main >/dev/null 2>&1 || true
  git cat-file -e "origin/main:$POOL_PATH" 2>/dev/null && { ok=1; break; }; echo "  attente pool ($i/20)"; sleep 30; done
[ "$ok" = 1 ] || { echo "ABORT: pool $POOL_PATH absent (la boucle a-t-elle tourné ?)"; exit 4; }
git show "origin/main:$POOL_PATH" > "$ART/pooled.jnnw"
NPOOL=$(python3 -c "import struct;print(struct.unpack('<I',open('$ART/pooled.jnnw','rb').read(8)[4:8])[0])")
echo "  pool = ${NPOOL} positions"
[ "$NPOOL" -ge 800000 ] || echo "  ⚠️ pool < 800k → 32-pat (8,5M poids) sera SOUS-fitté ; test peu équitable au 32 (note-le dans la lecture)."

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
cmake_jass(){ local B="$1"; cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake-$B.log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake-$B.log" || { echo "ABORT: egdb off ($B)"; exit 6; }
  cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build-$B.log" 2>&1 || { echo "BUILD FAIL $B"; tail -8 "$ART/build-$B.log"; exit 6; }; }

echo "=== ARM 32 : build 32-pat (arbre défaut) + train color-fold ==="
B32=build-32; rm -rf "$B32"; cmake_jass "$B32"; J32="$PWD/$B32/jass"
"$J32" --dump-eval-features "$ART/pooled.jnnw" "$ART/feat" >/dev/null 2>&1   # extras = arch-indépendants, partagés
python3 pattern_jass/tools/train.py --data "$ART/pooled.jnnw" --scan-eval --eval-features-file "$ART/feat" \
  --loss logistic --l2 1e-4 --max-iter 250 --scale "$SCALE" --prune --lowmem --color-fold \
  --out "$ART/eval32cf.pjtw" >"$ART/train32.log" 2>&1
[ -f "$ART/eval32cf.pjtw" ] || { echo "TRAIN FAIL 32"; tail -8 "$ART/train32.log"; exit 9; }
grep -E "color-fold|17M ->" "$ART/train32.log" | head -1 | sed 's/^/  [32] /'

echo "=== ARM 8 : réduit à 8-pat (reset-proof) + build + train color-fold ==="
python3 pattern_jass/tools/gen_patterns.py --emit \
  --drop diag_0,diag_1,diag_2,diag_3,diag_4,diag_5,diag_6,anti_0,anti_1,anti_2,anti_3,anti_4,anti_5,anti_6,anti_7,horiz_0,horiz_1,horiz_2,horiz_3,horiz_4,sq_0,sq_1,sq_2,sq_3 >"$ART/gen8.log" 2>&1
NP8=$(grep -oE "NUM_PATTERNS *= *[0-9]+" pattern_jass/src/pattern.hpp | grep -oE "[0-9]+" | head -1)
[ "$NP8" = "8" ] || { echo "ABORT: drop 8 raté"; exit 7; }
B8=build-8; rm -rf "$B8"; cmake_jass "$B8"; J8="$PWD/$B8/jass"
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"   # géométrie 8 hors-tree (reset-proof)
JASS_PATTERNS_DIR="$GEOM" python3 pattern_jass/tools/train.py --data "$ART/pooled.jnnw" --scan-eval --eval-features-file "$ART/feat" \
  --loss logistic --l2 1e-4 --max-iter 250 --scale "$SCALE" --prune --lowmem --color-fold \
  --out "$ART/eval8cf.pjtw" >"$ART/train8.log" 2>&1
[ -f "$ART/eval8cf.pjtw" ] || { echo "TRAIN FAIL 8"; tail -8 "$ART/train8.log"; exit 9; }
grep -qE "17M -> *8,503,072|17M -> *8503072" "$ART/train8.log" && { echo "ABORT: arm-8 flippé en 32 (reset)"; exit 8; }
grep -E "color-fold|17M ->" "$ART/train8.log" | head -1 | sed 's/^/  [8] /'

echo "=== MATCH cross-arch : 32+color-fold vs 8+color-fold (DIRECT, d9) ==="
python3 tools/jass_vs_jass_arch.py --jass-a "$J32" --pattern-a "$ART/eval32cf.pjtw" \
  --jass-b "$J8" --pattern-b "$ART/eval8cf.pjtw" --depth 9 --pairs 8 --max-plies 160 >"$ART/match.log" 2>&1 || true
RATE=$(grep -E 'A score rate' "$ART/match.log" | grep -oE '[0-9.]+' | head -1)

echo; echo "=========================================================="
echo "   cpx62-0372 — TEST GÉOMÉTRIE PROPRE (color-fold), pool=${NPOOL}"
echo "   32+color-fold (8,5M, surensemble) vs 8+color-fold (2,1M ≈ Scan) : A=${RATE}"
echo "----------------------------------------------------------"
echo "   A > 0.55 → les 24 géométries enrichies captent du signal (diagonales que Scan n'a pas) → 32 = le bon pari."
echo "   A ≈ 0.5  → le 8 Scan-fidèle suffit (la richesse ne paie pas, même au bon repli/volume)."
echo "   A < 0.45 → le 8 est MEILLEUR (le 32 dilue) — mais vérifier que le pool était assez gros pour le 32."
echo "=========================================================="