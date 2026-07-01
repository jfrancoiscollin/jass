#!/usr/bin/env bash
# id: cpx62-0518-lmrasym-elo
# description: VALIDATION ELO du levier LMR asym pv/non-pv (0516 : -24% NOEUDS exact, mais 23% best-moves changes).
# Le -24% d'arbre est-il GRATUIT (Elo >= baseline) ou de la sur-reduction (perte de force) ? A/B movetime : side A =
# lmr_first_full_nonpv=X,lmr_first_full_pv=Y vs baseline(4/4 uniforme). Balaye (nonpv,pv) = (1,3) Scan-like, (1,4), (2,4).
# dilf (tactique) @ movetime 0.3s. Fix non-flush (stdout START/RESULT/DONE -> output.log). GATE : >= parite (IC contient/
# depasse 0.5) => le -24% EBF est gratuit => BAKER cet asym (defaut) + re-mesure EBF vs Scan (croisement repousse). PERD =>
# sur-reduction (coherent 0264/0268 pour l'agressif). Le 1er vrai reducteur d'EBF cote recherche si l'Elo tient. AUCUN NNUE.
# expected_duration: ~1.5-2 h
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0518-lmrasym-elo/artefacts"; mkdir -p "$ART"
W=/root/cw-lae; mkdir -p "$W"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
MOVETIME=0.3; PAIRS=1; MAXPLIES=160; DILF=data/dilf_combinations.fen
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -10 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { echo "ABORT egdbmix absent"; exit 4; }
run_cfg(){ local name="$1" spec="$2"
  echo "===CFG=== $name ($spec) vs baseline @ movetime ${MOVETIME}s, dilf"
  for s in $(seq 0 $((NCPU-1))); do
    ( echo "START $s"; python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
        --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MOVETIME" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
        --search-params-a "$spec" --search-params-b "" 2>/dev/null; echo "DONE $s" ) &
  done; wait; echo "===ENDCFG=== $name"; }
run_cfg asym_1_3 "lmr_first_full_nonpv=1,lmr_first_full_pv=3"
run_cfg asym_1_4 "lmr_first_full_nonpv=1,lmr_first_full_pv=4"
run_cfg asym_2_4 "lmr_first_full_nonpv=2,lmr_first_full_pv=4"
echo "=== Agreger RESULT par cfg depuis output.log. >=parite => -24% EBF gratuit => baker. base ref 0.5 ==="
