#!/usr/bin/env bash
# id: ccx33-0262-nmp-confirm-mt05
# description: CONFIRMATION du verdict NMP à cadence PLUS LONGUE. 0256+0259 (mt0.2) : désactiver
# NMP est monotone-gagnant jusqu'à thr36=+97 (≈ NMP off partout) → NMP semble net-négatif en jass
# (zugzwang omniprésent). SEULE réserve : mesuré à mt0.2 où le bénéfice de PROFONDEUR de NMP compte
# moins ; à cadence longue NMP pourrait rattraper. On confirme à mt0.5 AVANT de figer un défaut
# aussi structurant. Deux A/B EN PARALLÈLE vs NMP-ON (eg_pieces=0) : thr40 (NMP OFF partout) et
# thr16 (modéré). improving=ON des deux côtés. Éval men-only 0227.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0262-nmp-confirm-mt05/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

EVAL=""
for cand in /root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/gen8.pjtw \
            /root/jass/jobs/results/ccx33-0231-rfe-baseline32/artefacts.src/gen8.pjtw; do
  [ -f "$cand" ] && { EVAL="$cand"; break; }
done
[ -n "$EVAL" ] || { echo "ABORT: éval men-only 0227 introuvable"; exit 6; }
echo "EVAL (men-only) = $EVAL"

MT=500; PAIRS=18; OFF="eg_pieces=0"     # mt0.5s ; ~324 parties/comparaison
run_ab() { local tag="$1" aspec="$2"
  echo "=== [$tag] A=[$aspec] vs B=[$OFF] : mt${MT}ms pairs=$PAIRS ==="
  "$JASS" --benchmark-search-params "$EVAL" "$aspec" "$OFF" 64 "$PAIRS" 1 "$MT" >"$ART/ab-$tag.log" 2>&1
}
run_ab thr40 "eg_pieces=40,eg_no_nmp=1" &   # NMP OFF partout
run_ab thr16 "eg_pieces=16,eg_no_nmp=1" &   # modéré (comparable mt0.2)
wait

echo; echo "=========================================================="
echo "   ccx33-0262 — CONFIRMATION NMP à mt0.5 : A=NMP off vs B=NMP on (eg_pieces=0)"
echo "   éval=$(basename "$EVAL")  mt=${MT}ms  ~$((PAIRS*18)) parties/comparaison  (improving=ON)"
echo "   rappel mt0.2 : thr16=+47  thr36=+97 (monotone)"
echo "----------------------------------------------------------"
for tag in thr16 thr40; do
  line=$(grep -E '^Result:' "$ART/ab-$tag.log" | tail -1)
  W=$(echo "$line"|grep -oE 'A=[0-9]+'|cut -d= -f2); L=$(echo "$line"|grep -oE 'B=[0-9]+'|cut -d= -f2); D=$(echo "$line"|grep -oE 'Draws=[0-9]+'|cut -d= -f2)
  [ -z "${W:-}" ] && { echo "  [$tag] PAS DE RÉSULTAT"; tail -3 "$ART/ab-$tag.log"; continue; }
  echo "  [$tag]  A=$W B=$L D=$D"
  python3 tools/sprt_elo.py --wdl "$W" "$D" "$L" --elo0 0 --elo1 5 2>/dev/null | sed 's/^/      /'
done
echo "----------------------------------------------------------"
echo "  thr40 toujours nettement >0 à mt0.5 → NMP net-négatif CONFIRMÉ : désactiver (défaut)."
echo "  thr40 ~0 ou négatif à mt0.5 → le gain mt0.2 était TC-dépendant : garder un seuil modéré."
echo "=========================================================="
