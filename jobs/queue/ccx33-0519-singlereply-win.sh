#!/usr/bin/env bash
# id: ccx33-0519-singlereply-win
# description: WIN TEST single-reply (memo Scan #1). 0516 : single_reply = 2.3x noeuds @depth fixe (cherche les combos
# forces en profondeur, accord 0.69 = trouve d'autres coups sur les lignes forcees). Sa VALEUR se juge a MOVETIME. A/B 3
# bras vs baseline : (b) ext_single_reply=1 (forcing ETROIT gratuit largeur-1), (c) ext_forcing=1 (forcing LARGE = neutre
# 0.473 connu). dilf tactique @ movetime {0.1,0.3}s. Fix non-flush. GATE : single_reply > baseline ET > ext_forcing hors-IC
# => le forcing GRATUIT convertit les combos a movetime (recupere 0485 0.30->0.73 en jeu reel, resout 0435) => BAKE
# ext_single_reply. Si single_reply ~ ext_forcing ~ neutre => meme etroit ca ne paie pas a temps fixe. AUCUN NNUE.
# expected_duration: ~2-3 h
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0519-singlereply-win/artefacts"; mkdir -p "$ART"
W=/root/cw-srw; mkdir -p "$W"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
PAIRS=1; MAXPLIES=160; DILF=data/dilf_combinations.fen; MTS="0.1 0.3"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -10 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { echo "ABORT egdbmix absent"; exit 4; }
run_cfg(){ local name="$1" spec="$2" mt="$3"
  echo "===CFG=== ${name}_mt${mt} ($spec) vs baseline @ movetime ${mt}s, dilf"
  for s in $(seq 0 $((NCPU-1))); do
    ( echo "START $s"; python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
        --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$mt" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
        --search-params-a "$spec" --search-params-b "" 2>/dev/null; echo "DONE $s" ) &
  done; wait; echo "===ENDCFG=== ${name}_mt${mt}"; }
for mt in $MTS; do
  run_cfg single_reply "ext_single_reply=1" "$mt"
  run_cfg ext_forcing  "ext_forcing=1"       "$mt"
done
echo "=== Agreger par bloc. single_reply > baseline (0.5) ET > ext_forcing => forcing gratuit gagne => baker. ==="
