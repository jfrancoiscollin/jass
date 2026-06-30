#!/usr/bin/env bash
# id: cpx62-0505-ordering-elo
# description: ORDERING — confirmation Elo des gains EBF (0504 : iid6 -9.5%, iid8 -24.8% R15, conthist -13.4% EBF d9-12).
# L'ordering baisse l'EBF du milieu ; reste a verifier que c'est GRATUIT (Elo >= baseline : l'ordering ne change pas QUELS
# coups, juste l'ordre). A/B a movetime : side A = knob ON, side B = baseline. Configs : iid6, iid8, conthist (conthist
# etait -11 Elo en 0253 sur ancien champion -> revalider sur egdbmix). + DIAGNOSTIC mort-de-shard : chaque shard echo
# 'START s' avant et 'DONE s RESULT...' apres ; on lit tout depuis OUTPUT.LOG (fiable) -> on saura si les shards meurent au
# lancement (log vide) ou en cours (START sans DONE + traceback). main gated-OFF. AUCUN NNUE.
# expected_duration: ~1.5-2 h
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0505-ordering-elo/artefacts"; mkdir -p "$ART"
W=/root/cw-ordelo; mkdir -p "$W"
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
  echo "===CFG=== $name ($spec) vs baseline @ movetime ${MOVETIME}s, dilf, nshards=$NCPU"
  for s in $(seq 0 $((NCPU-1))); do
    ( echo "START $s"; python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
        --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MOVETIME" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
        --search-params-a "$spec" --search-params-b "" 2>"$ART/$name-err-$s.txt" \
      && echo "DONE $s $(tail -1 "$ART/$name-err-$s.txt" 2>/dev/null)" || echo "FAIL $s rc=$?" ) &
    # NB: stdout (START/RESULT/DONE) -> output.log du job (fiable) ; stderr -> fichier (diag crash)
  done
  wait
  echo "===ENDCFG=== $name"
}
# jass_vs_jass_arch --quiet imprime 'RESULT a d b' sur stdout -> capté dans output.log (entre START et DONE)
run_cfg iid6     "iid_min_depth=6"
run_cfg iid8     "iid_min_depth=8"
run_cfg conthist "use_conthist=1"
echo "=== Agrégation : sommer les lignes RESULT par cfg depuis CE stdout (output.log). Un cfg >=0.55 hors-IC ET EBF baisse"
echo "    (0504) => ordering = gain GRATUIT => baker le knob. Si Elo<baseline => le knob baisse l'EBF mais coute (cas conthist?)."
