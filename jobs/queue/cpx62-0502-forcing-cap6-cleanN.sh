#!/usr/bin/env bash
# id: cpx62-0502-forcing-cap6-cleanN
# description: RE-RUN CLEAN haut-N a forcing_ext_cap=6 (le meilleur du sweep 0501, ~0,491 mais sous-puissant n~227). But :
# trancher NET « neutre » vs « marginalement positif ». ext_forcing=1,forcing_ext_cap=6 vs baseline(OFF), movetime 0.3s,
# dilf 305, pairs=2 (=> 1220 parties cible). FIX NON-FLUSH : chaque shard ecrit son stdout (qui finit par 'RESULT a d b'
# imprime APRES toutes ses parties) dans un fichier COMMITTE $ART/shard-$s.log ; on agrege APRES wait depuis ces logs et on
# imprime l'agregat sur le STDOUT du job (output.log = committe de facon fiable au finalize, contrairement a RESULTS.txt).
# Visibilite totale : si un shard crash, son shard.log committe le montre. AUCUN re-entrainement, AUCUN NNUE. main gated-OFF.
# expected_duration: ~40-60 min
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0502-forcing-cap6-cleanN/artefacts"; mkdir -p "$ART"
W=/root/cw-cap6; mkdir -p "$W"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
MOVETIME=0.3; PAIRS=2; MAXPLIES=160; DILF=data/dilf_combinations.fen; CAP=6

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -10 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { echo "ABORT egdbmix absent"; exit 4; }

echo "=== RE-RUN CLEAN cap=6 : ext_forcing=1,forcing_ext_cap=6 vs OFF @ movetime ${MOVETIME}s, dilf, pairs=$PAIRS, nshards=$NCPU ==="
echo "=== (rappel sweep 0501 : cap6=0,491 n~227 sous-puissant ; ref cap-illimite=0,473) ==="
# stdout+stderr de chaque shard -> fichier COMMITTE (RESULT imprime apres toutes les parties = tally COMPLET)
for s in $(seq 0 $((NCPU-1))); do
  ( python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
      --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MOVETIME" --pairs "$PAIRS" \
      --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --openings-file "$DILF" \
      --progress-file "$ART/prog-$s.txt" ; echo "EXIT $?" ) > "$ART/shard-$s.log" 2>&1 &
done
wait
echo "=== shards terminés, agrégation depuis les shard.log committés ==="
python3 - "$ART" "$NCPU" <<'PY'
import sys,glob,os,re,math
ART=sys.argv[1]; ncpu=int(sys.argv[2])
A=D=B=0; ok=0; crashed=[]
for s in range(ncpu):
    f=f"{ART}/shard-{s}.log"
    if not os.path.exists(f): crashed.append((s,"no-log")); continue
    txt=open(f,errors='ignore').read()
    rl=[l for l in txt.splitlines() if l.startswith("RESULT")]
    ex=[l for l in txt.splitlines() if l.startswith("EXIT")]
    if rl:
        _,a,d,b=rl[-1].split(); A+=int(a);D+=int(d);B+=int(b); ok+=1
    else:
        tail=txt.strip().splitlines()[-1] if txt.strip() else "empty"
        crashed.append((s, (ex[-1] if ex else "no-RESULT")+" | "+tail[:80]))
g=A+D+B
print(f"=== AGREGAT CLEAN cap=6 ===")
print(f"shards OK={ok}/{ncpu} ; crashés/vides={len(crashed)}")
for s,why in crashed[:8]: print(f"  shard {s} KO: {why}")
if g:
    r=(A+0.5*D)/g; se=math.sqrt(max(r*(1-r),1e-9)/g); lo,hi=r-1.96*se,r+1.96*se
    verd="FLIP POSITIF" if lo>=0.55 else ("parite" if lo<=0.5<=hi else ("PERD" if hi<0.5 else "leger+"))
    print(f"CLEANRESULT cap=6 : ext_forcing score={r:.3f} IC95=[{lo:.3f},{hi:.3f}] n={g} (ON={A} D={D} OFF={B}) => {verd}")
    print(f"  vs sweep0501 cap6=0,491 (n227) et cap-illimite=0,473. Si <0,50 hors-IC => ext_forcing NEUTRE/negatif confirme propre.")
else:
    print("CLEANRESULT : AUCUN jeu agrege -> voir shard.log committés")
PY
echo "=== FIN 0502 ==="
