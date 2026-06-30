#!/usr/bin/env bash
# id: cpx62-0501-forcing-cap-sweep
# description: FINE-TUNING ext_forcing (insight JFC) — LE point manque de tous les tests precedents. 0490/0491 ont mesure
# ext_forcing=1 avec forcing_ext_cap=0 (DEFAUT = ILLIMITE, cf search_params.hpp:132 + search.cpp:923 'cap<=0 => toujours
# vrai') => les lignes forcantes s'etendent SANS LIMITE => blowup de noeuds => a movetime ca se paie => NEUTRE (0,473).
# C'etait le PIRE reglage. Or jass est meilleur par-noeud a d4-d9 mais perd a d15 (deficit a la profondeur) : il faut
# deepen SELECTIVEMENT les combos (ext_forcing) SANS exploser uniformement. Donc on SWEEP le cap : ext_forcing=1 +
# forcing_ext_cap={4,6,8,12} vs baseline (ext_forcing=0), movetime 0.3s, dilf 305 (tactique = ou les combos comptent).
# GATE : un cap avec score >=0.55 hors-IC => ext_forcing FLIP POSITIF une fois cape => fine-tuning reussi => convertit les
# combos a movetime => baker (defaut ext_forcing=1,cap=X au jeu). Plus le cap est petit, moins de blowup mais moins de
# profondeur tactique : on cherche l'optimum. cpx62 32 coeurs = n eleve par cap. AUCUN re-entrainement, AUCUN NNUE.
# expected_duration: ~1-2 h
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0501-forcing-cap-sweep/artefacts"; mkdir -p "$ART"
W=/root/cw-fcap; mkdir -p "$W"
RES="$ART/RESULTS.txt"; say(){ echo "$@" | tee -a "$RES"; }; [ -f "$RES" ] || : > "$RES"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
MOVETIME=0.3; PAIRS=1; MAXPLIES=160; DILF=data/dilf_combinations.fen
CAPS="4 6 8 12"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { say "ABORT egdbmix absent"; exit 4; }

say "=== FINE-TUNING ext_forcing — sweep forcing_ext_cap={$CAPS} (ext_forcing=1) vs baseline(OFF) @ movetime ${MOVETIME}s, dilf ==="
say "  (rappel : 0490/0491 = cap=0 ILLIMITE => 0,473 neutre. On cherche le cap qui FLIPPE positif.)"
for CAP in $CAPS; do
  say "--- forcing_ext_cap=$CAP ---"
  for s in $(seq 0 $((NCPU-1))); do
    python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
        --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MOVETIME" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
        --search-params-a "ext_forcing=1,forcing_ext_cap=$CAP" --search-params-b "" \
        --progress-file "$ART/cap${CAP}-shard-$s.txt" >"$W/c${CAP}-sh$s.log" 2>&1 & done
  wait
  python3 - "$CAP" "$ART"/cap${CAP}-shard-*.txt <<'PY' | tee -a "$RES"
import sys,math
CAP=sys.argv[1]; A=D=B=0; nsh=0
for f in sys.argv[2:]:
    try:
        last=None
        for l in open(f):
            if l.startswith("RESULT"): last=l
        if last: _,a,d,b=last.split(); A+=int(a);D+=int(d);B+=int(b);nsh+=1
    except: pass
g=A+D+B
if not g: print(f"  cap={CAP}: NO GAMES"); sys.exit(0)
r=(A+0.5*D)/g; se=math.sqrt(max(r*(1-r),1e-9)/g); lo,hi=r-1.96*se,r+1.96*se
verd="FLIP POSITIF (>=0.55 hors-IC)" if lo>=0.55 else ("parite" if lo<=0.5<=hi else ("PERD" if hi<0.5 else "leger+ (0.5..0.55)"))
print(f"  cap={CAP}: ext_forcing score={r:.3f} IC95=[{lo:.3f},{hi:.3f}] (n={g}, {nsh} shards ; ON={A} D={D} OFF={B}) => {verd}")
PY
done
say ""
say "================= VERDICT FINE-TUNING ext_forcing ================="
say "  Un cap >=0.55 hors-IC => ext_forcing cape FLIPPE POSITIF a movetime (vs 0,473 illimite) => fine-tuning reussi =>"
say "    baker ext_forcing=1,forcing_ext_cap=X au jeu => conversion combos a movetime, sans NNUE. Puis confirmer jeu general."
say "  Tous parite/perte => meme cape, le cout-noeuds annule le gain a movetime => ext_forcing pas le levier a temps fixe."
say "  (Aussi utile : balayer le cap montre la courbe cout/gain de l'extension.)"
say "==================================================="
