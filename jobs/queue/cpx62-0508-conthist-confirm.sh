#!/usr/bin/env bash
# id: cpx62-0508-conthist-confirm
# description: CONFIRMATION conthist avant bake. 0507 : conthist = -9,5% noeuds @d12 EXACT + Elo-neutre dilf (0505 n=610).
# Bemol : conthist etait -11 Elo en 0253 (ancien champion). Ici : A/B use_conthist=1 vs OFF a movetime {0.1,0.3,1.0}s, dilf,
# n=610/regime, fix non-flush qui marche (stdout START/RESULT/DONE -> output.log fiable). Le node-savings (-9%) doit donner
# Elo>=parite a tous les regimes (ideal : leger+ a temps court ou la profondeur gagnee compte). >=parite partout => BAKER
# use_conthist par defaut (gain EBF gratuit). Perte a un regime => ne pas baker, consigner. AUCUN NNUE.
# expected_duration: ~1.5-2 h
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0508-conthist-confirm/artefacts"; mkdir -p "$ART"
W=/root/cw-ch; mkdir -p "$W"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
PAIRS=1; MAXPLIES=160; DILF=data/dilf_combinations.fen; MTS="0.1 0.3 1.0"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -10 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { echo "ABORT egdbmix absent"; exit 4; }
for MT in $MTS; do
  echo "===CFG=== conthist_mt$MT (use_conthist=1 vs OFF @ movetime ${MT}s, dilf)"
  for s in $(seq 0 $((NCPU-1))); do
    ( echo "START $s"; python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
        --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MT" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
        --search-params-a "use_conthist=1" --search-params-b "" 2>/dev/null; echo "DONE $s" ) &
  done
  wait
  echo "===ENDCFG=== conthist_mt$MT"
done
echo "=== Agreger les RESULT par bloc movetime depuis output.log. >=parite partout => baker use_conthist. ==="
