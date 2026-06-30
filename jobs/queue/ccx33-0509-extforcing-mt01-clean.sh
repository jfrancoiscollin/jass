#!/usr/bin/env bash
# id: ccx33-0509-extforcing-mt01-clean
# description: CONFIRMATION CLEAN ext_forcing cap=6 @ movetime 0.1s (le signal 0503 : 0.543 mais sous-puissant n=456/3sh).
# A movetime court le budget-noeuds est tendu => l'extension forcante selective paierait. A/B ext_forcing=1,forcing_ext_cap=6
# vs OFF @ movetime 0.1s, dilf, n=610, fix non-flush (stdout START/RESULT/DONE -> output.log). >=0.55 hors-IC => ext_forcing
# capé flippe positif a temps court => baker au regime rapide. ~parite => meme a temps court c'est neutre. AUCUN NNUE.
# expected_duration: ~30-45 min
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0509-extforcing-mt01-clean/artefacts"; mkdir -p "$ART"
W=/root/cw-ef01; mkdir -p "$W"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
PAIRS=1; MAXPLIES=160; DILF=data/dilf_combinations.fen; MT=0.1
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -10 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { echo "ABORT egdbmix absent"; exit 4; }
echo "===CFG=== extforcing_cap6_mt01 (ext_forcing=1,forcing_ext_cap=6 vs OFF @ movetime ${MT}s, dilf)"
for s in $(seq 0 $((NCPU-1))); do
  ( echo "START $s"; python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
      --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MT" --pairs "$PAIRS" \
      --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
      --search-params-a "ext_forcing=1,forcing_ext_cap=6" --search-params-b "" 2>/dev/null; echo "DONE $s" ) &
done
wait
echo "===ENDCFG=== extforcing_cap6_mt01"
echo "=== Agreger RESULT depuis output.log. >=0.55 hors-IC => ext_forcing capé positif a temps court => baker au rapide. ==="
