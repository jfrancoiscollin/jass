#!/usr/bin/env bash
# id: cpx62-0520-scan-combo-ab
# description: PAYOFF #1+#2 (memo Scan) — la COMBINAISON single_reply + LMR-asym compose-t-elle ? Isolement (0518/0519) :
# LMR-asym_2_4 = parite (0,491, -24% noeuds) ; single_reply = parite/penche+ (0,487-0,535, bat l'ext_forcing large). Ensemble
# ils pourraient composer (asym recupere de la profondeur, single_reply la depense sur les combos forces). A/B movetime {0.1,
# 0.3}s vs baseline, dilf, cpx62 (n=610 fiable). Bras : (a) single_reply seul, (b) asym_2_4 seul, (c) COMBO. GATE : combo >
# baseline hors-IC (surtout @0.1s) => la recette Scan assemblee gagne en jeu reel => baker (single_reply + asym) + boucle
# self-play. combo ~ parite => les leviers Scan sont de l'efficacite, pas un gain de force => consigner. AUCUN NNUE.
# expected_duration: ~2 h
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0520-scan-combo-ab/artefacts"; mkdir -p "$ART"
W=/root/cw-cmb; mkdir -p "$W"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
PAIRS=1; MAXPLIES=160; DILF=data/dilf_combinations.fen; MTS="0.1 0.3"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -10 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { echo "ABORT egdbmix absent"; exit 4; }
SR="ext_single_reply=1"; ASYM="lmr_first_full_nonpv=2,lmr_first_full_pv=4"; COMBO="ext_single_reply=1,lmr_first_full_nonpv=2,lmr_first_full_pv=4"
run_cfg(){ local name="$1" spec="$2" mt="$3"
  echo "===CFG=== ${name}_mt${mt} ($spec) vs baseline @ ${mt}s"
  for s in $(seq 0 $((NCPU-1))); do
    ( echo "START $s"; python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
        --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$mt" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
        --search-params-a "$spec" --search-params-b "" 2>/dev/null; echo "DONE $s" ) &
  done; wait; echo "===ENDCFG=== ${name}_mt${mt}"; }
for mt in $MTS; do
  run_cfg single_reply "$SR" "$mt"; run_cfg asym24 "$ASYM" "$mt"; run_cfg combo "$COMBO" "$mt"
done
echo "=== combo > baseline hors-IC (surtout @0.1) => recette Scan gagne => baker + boucle. Sinon efficacite seule. ==="
