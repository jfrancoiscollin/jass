#!/usr/bin/env bash
# id: ccx33-0499-histlmr-ab
# description: CHANTIER EBF #2 (memo v2, INDEPENDANT de #1) — history-LMR. Le mémo : lmr_hist_div est OFF par defaut (=0),
# c'est un +Elo standard ET un reducteur d'EBF JAMAIS active (reduit MOINS les coups a fort historique => meilleur ordering
# => moins de re-recherches/churn => arbre plus stable). A/B a TEMPS FIXE : side A = lmr_hist_div=H (softening ON) vs
# side B = defaut (hist_div=0). Sweep H={4000,8000,16000} (softening fort->doux ; history_max=16384 => jusqu'a ~4/2/1 plies).
# MEME harnais que 0497 (movetime 0.3s, dilf 305, egdbmix-pur, progress-file). Tourne sur ccx33 EN PARALLELE de 0498
# (decideur log sur cpx62). GATE : un H >=0.55 hors-IC = history-LMR aide la force (a combiner avec #1 plus tard) =>
# candidat. Parite/perte a tous H => history-LMR ne paie pas en dames seul => consigner. Garde-fou : Elo >= baseline.
# AUCUN re-entrainement, AUCUN NNUE. main gated-OFF (lmr_hist_div deja present, defaut 0 = inchange).
# expected_duration: ~2-3 h
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0499-histlmr-ab/artefacts"; mkdir -p "$ART"
W=/root/cw-histlmr; mkdir -p "$W"
RES="$ART/RESULTS.txt"; say(){ echo "$@" | tee -a "$RES"; }; [ -f "$RES" ] || : > "$RES"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
MOVETIME=0.3; PAIRS=1; MAXPLIES=160; DILF=data/dilf_combinations.fen
HISTS="4000 8000 16000"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { say "ABORT egdbmix absent"; exit 4; }

say "=== CHANTIER EBF #2 — history-LMR (lmr_hist_div=H ON) vs defaut(0) @ movetime ${MOVETIME}s, dilf (305) ==="
for H in $HISTS; do
  say "--- lmr_hist_div=$H (softening ~$(python3 -c "print(f'{16384/$H:.1f}')") plies max) ---"
  for s in $(seq 0 $((NCPU-1))); do
    python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
        --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MOVETIME" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
        --search-params-a "lmr_hist_div=$H" --search-params-b "" \
        --progress-file "$ART/hist${H}-shard-$s.txt" >"$W/h${H}-sh$s.log" 2>&1 & done
  wait
  python3 - "$H" "$ART"/hist${H}-shard-*.txt <<'PY' | tee -a "$RES"
import sys,math
H=sys.argv[1]; A=D=B=0; nsh=0
for f in sys.argv[2:]:
    try:
        last=None
        for l in open(f):
            if l.startswith("RESULT"): last=l
        if last: _,a,d,b=last.split(); A+=int(a);D+=int(d);B+=int(b);nsh+=1
    except: pass
g=A+D+B
if not g: print(f"  hist_div={H}: NO GAMES"); sys.exit(0)
r=(A+0.5*D)/g; se=math.sqrt(max(r*(1-r),1e-9)/g); lo,hi=r-1.96*se,r+1.96*se
verd="CANDIDAT (>=0.55 hors-IC)" if lo>=0.55 else ("parite" if lo<=0.5<=hi else ("PERD" if hi<0.5 else "leger+"))
print(f"  hist_div={H}: histON score={r:.3f} IC95=[{lo:.3f},{hi:.3f}] (n={g}, {nsh} shards ; ON={A} D={D} OFF={B}) => {verd}")
PY
done
say ""
say "================= VERDICT #2 history-LMR ================="
say "  Un H >=0.55 hors-IC => history-softening aide la force seule => candidat (a combiner avec #1 si #1 baisse l'EBF)."
say "  Tous parite/perte => history-LMR ne paie pas seul en dames => consigner ; le levier EBF reste #1 (log) ou #3 (eval-noise)."
say "========================================================="
