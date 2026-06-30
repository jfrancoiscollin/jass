#!/usr/bin/env bash
# id: ccx33-0503-forcing-cap6-movetime
# description: BALAYAGE MOVETIME a forcing_ext_cap=6 (suite re-run clean 0502). Hypothese : l'extension forcante paie
# surtout quand le budget-noeuds est TENDU (movetime court) ; a movetime long la recherche de base atteint deja les combos.
# A/B ext_forcing=1,forcing_ext_cap=6 vs OFF a movetime={0.1,0.3,1.0}s, dilf 305, pairs=2. MEME fix non-flush que 0502
# (stdout shard -> fichier committe ; agregat sur stdout du job). GATE : un movetime ou ext_forcing >=0.55 hors-IC =>
# c'est le regime ou le fine-tuning paie => baker a ce movetime/cap. Si plat partout => ext_forcing pas le levier a temps
# fixe quel que soit le regime. main gated-OFF. AUCUN re-entrainement, AUCUN NNUE.
# expected_duration: ~2-3 h
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0503-forcing-cap6-movetime/artefacts"; mkdir -p "$ART"
W=/root/cw-cap6mt; mkdir -p "$W"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
PAIRS=2; MAXPLIES=160; DILF=data/dilf_combinations.fen; CAP=6; MTS="0.1 0.3 1.0"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb build"; tail -6 "$W/cmake.log"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -10 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { echo "ABORT egdbmix absent"; exit 4; }

for MT in $MTS; do
  echo "=== BALAYAGE movetime=${MT}s, cap=6 : ext_forcing=1,forcing_ext_cap=6 vs OFF, dilf, pairs=$PAIRS ==="
  for s in $(seq 0 $((NCPU-1))); do
    ( python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
        --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MT" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --openings-file "$DILF" \
        --progress-file "$ART/mt${MT}-prog-$s.txt" ; echo "EXIT $?" ) > "$ART/mt${MT}-shard-$s.log" 2>&1 &
  done
  wait
  python3 - "$ART" "$NCPU" "$MT" <<'PY'
import sys,os,math
ART=sys.argv[1]; ncpu=int(sys.argv[2]); MT=sys.argv[3]
A=D=B=0; ok=0
for s in range(ncpu):
    f=f"{ART}/mt{MT}-shard-{s}.log"
    if not os.path.exists(f): continue
    rl=[l for l in open(f,errors='ignore').read().splitlines() if l.startswith("RESULT")]
    if rl: _,a,d,b=rl[-1].split(); A+=int(a);D+=int(d);B+=int(b); ok+=1
g=A+D+B
if g:
    r=(A+0.5*D)/g; se=math.sqrt(max(r*(1-r),1e-9)/g); lo,hi=r-1.96*se,r+1.96*se
    verd="FLIP POSITIF" if lo>=0.55 else ("parite" if lo<=0.5<=hi else ("PERD" if hi<0.5 else "leger+"))
    print(f"CLEANRESULT movetime={MT} cap=6 : ext_forcing score={r:.3f} IC95=[{lo:.3f},{hi:.3f}] n={g} shardsOK={ok}/{ncpu} (ON={A} D={D} OFF={B}) => {verd}")
else:
    print(f"CLEANRESULT movetime={MT} : aucun jeu")
PY
done
echo "=== FIN 0503 : si un movetime court flippe positif => regime budget-tendu paie. ==="
