#!/usr/bin/env bash
# id: ccx33-0497-lmr-log-sweep
# description: CHANTIER EBF #1b (memo v2) — SWEEP du coefficient LMR-log vers le BAS. #1 (0496) : log mul=40 = 0.444 sur
# dilf (PERD : sur-reduction, signature 0264/0268). Rappel R=log(d)*log(idx)*mul/100 => mul plus PETIT = MOINS de reduction
# = moins de force perdue. On balaye {20,25,30,35} vs lineaire (defaut), MEME setup que 0496 (movetime 0.3s, dilf 305, eval
# egdbmix-pur), chaque mul A/B sur tous les coeurs avec progress-file (survit au non-flush). GATE v2 : un mul avec score
# >=0.55 hors-IC = candidat (garde la force EN reduisant) => ensuite re-mesure EBF + jeu general + vs Scan. TOUS <0.5 =>
# le LMR-log ne marche pas en dames (le prior 0264/0268 gagne) => consigner negatif et basculer sur le diagnostic #3
# (part eval-noise de l'EBF). main gated-OFF ; table-ize seulement au bake. AUCUN re-entrainement, AUCUN NNUE.
# expected_duration: ~2-3 h
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0497-lmr-log-sweep/artefacts"; mkdir -p "$ART"
W=/root/cw-lmrsweep; mkdir -p "$W"
RES="$ART/RESULTS.txt"; say(){ echo "$@" | tee -a "$RES"; }; [ -f "$RES" ] || : > "$RES"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
MOVETIME=0.3; PAIRS=1; MAXPLIES=160; DILF=data/dilf_combinations.fen
MULS="20 25 30 35"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { say "ABORT egdbmix absent"; exit 4; }

say "=== CHANTIER EBF #1b — SWEEP LMR-log mul={$MULS} vs lineaire @ movetime ${MOVETIME}s, dilf (305) ==="
say "  (rappel #1/0496 : mul=40 = 0.444 PERD ; on cherche un mul plus doux >=0.55 hors-IC)"
for MUL in $MULS; do
  say "--- mul=$MUL (R=log(d)*log(idx)*$MUL/100) ---"
  for s in $(seq 0 $((NCPU-1))); do
    python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
        --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MOVETIME" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
        --search-params-a "lmr_formula=1,lmr_log_mul=$MUL" --search-params-b "" \
        --progress-file "$ART/mul${MUL}-shard-$s.txt" >"$W/m${MUL}-sh$s.log" 2>&1 & done
  wait
  python3 - "$MUL" "$ART"/mul${MUL}-shard-*.txt <<'PY' | tee -a "$RES"
import sys,math
mul=sys.argv[1]; A=D=B=0; nsh=0
for f in sys.argv[2:]:
    try:
        last=None
        for l in open(f):
            if l.startswith("RESULT"): last=l
        if last: _,a,d,b=last.split(); A+=int(a); D+=int(d); B+=int(b); nsh+=1
    except: pass
g=A+D+B
if not g: print(f"  mul={mul}: NO GAMES"); sys.exit(0)
rate=(A+0.5*D)/g; se=math.sqrt(max(rate*(1-rate),1e-9)/g); lo,hi=rate-1.96*se,rate+1.96*se
verdict="CANDIDAT (>=0.55 hors-IC)" if lo>=0.55 else ("parite (IC contient 0.5)" if lo<=0.5<=hi else ("PERD" if hi<0.5 else "leger+ (0.5..0.55)"))
print(f"  mul={mul}: log score={rate:.3f} IC95=[{lo:.3f},{hi:.3f}] (n={g}, {nsh} shards ; log={A} D={D} lin={B}) => {verdict}")
PY
done
say ""
say "================= VERDICT SWEEP ================="
say "  LECTURE : un mul >=0.55 hors-IC = garde/gagne la force EN reduisant => CANDIDAT => #1c (re-mesure EBF avec ce mul +"
say "            A/B jeu GENERAL Elo>=baseline + vs Scan + table-ize au bake). TOUS <=0.5 => le LMR-log SUR-REDUIT a tout"
say "            coefficient utile en dames (prior 0264/0268 confirme) => chantier LMR-log NEGATIF => basculer diagnostic #3"
say "            (part eval-noise de l'EBF : churn PV / re-recherches). EBF baseline #0 = 1,69 (cible : croisement >= d15)."
say "==============================================="
