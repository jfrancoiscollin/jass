#!/usr/bin/env bash
# id: ccx33-0496-lmr-log-ab
# description: CHANTIER EBF #1 (memo JFC) — A/B du levier LMR-LOGARITHMIQUE a TEMPS FIXE. Suite de #0 (0495 : EBF_jass=1,69
# vs Scan 1,25 => marge). Teste lmr_formula=1,lmr_log_mul=40 (forme Stockfish : doux tot, agressif tard) vs lineaire (defaut),
# MEME binaire/eval (egdbmix eval-pur), a movetime 0.3s, openings dilf (305, n=610), progress-file incremental (survit au
# non-flush). CRIBLE : dilf est tactique => FAVORABLE au log (la profondeur y compte le plus). S'il ne gagne pas la, il est
# mort. S'il gagne => #1b confirme en jeu GENERAL contre le prior 0264/0268 (jass a GAGNE +42 Elo en reduisant MOINS — la
# forme log doit battre ce prior, pas juste reduire plus). AUCUN re-entrainement, AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0496-lmr-log-ab/artefacts"; mkdir -p "$ART"
W=/root/cw-lmrlog; mkdir -p "$W"
RES="$ART/RESULTS.txt"; say(){ echo "$@" | tee -a "$RES"; }; [ -f "$RES" ] || : > "$RES"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
MOVETIME=0.3; PAIRS=1; MAXPLIES=160; DILF=data/dilf_combinations.fen
# v3 fix : 0490 plafonnait a n~30 car opening_pool_via_jass ne donne que 9 ouvertures (recherche deterministe =>
# 1 partie unique par (ouverture,couleur) => ~18). Ici --openings-file dilf (305 ouvertures, riches en combinaisons,
# DIRECTEMENT pertinentes pour le bake tactique) => 305x2 = 610 parties uniques. pairs=1 (pairs>1 = parties identiques).
# movetime 0.3s (vs 1.0) => ~3x plus rapide. => n=610 a temps fixe sur des positions a combinaison.

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { say "ABORT egdbmix absent"; exit 4; }

# A = ext_forcing ON, B = baseline. Sharded. RE-RUN de 0487 (perdu au non-flush) : chaque shard ecrit son tally
# RESULT en INCREMENTAL via --progress-file sous $ART => survit au non-flush (committe a chaque heartbeat).
say "=== CHANTIER EBF #1 — LMR-LOG(mul=40) vs LINEAIRE @ movetime ${MOVETIME}s, openings=dilf (305), progress-file ==="
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
      --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MOVETIME" --pairs "$PAIRS" \
      --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
      --search-params-a "lmr_formula=1,lmr_log_mul=40" --search-params-b "" \
      --progress-file "$ART/shard-$s.txt" >"$W/sh-$s.log" 2>&1 & done
wait
python3 - "$ART"/shard-*.txt <<'PY' | tee -a "$RES"
import sys,math
A=D=B=0
for f in sys.argv[1:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"):
                _,a,d,b=l.split(); A+=int(a); D+=int(d); B+=int(b)
    except: pass
g=A+D+B
if not g: print("  NO GAMES"); sys.exit(0)
rate=(A+0.5*D)/g                    # LMR-log(A) score rate vs lineaire(B)
se=math.sqrt(max(rate*(1-rate),1e-9)/g)
lo,hi=rate-1.96*se, rate+1.96*se
print(f"  LMR-log(A) vs lineaire(B) @ movetime, dilf : score={rate:.3f}  IC95=[{lo:.3f},{hi:.3f}]  (games={g} ; log={A} D={D} lin={B})")
print(f"  LECTURE (crible dilf, tactique = FAVORABLE au log) : IC > 0.50 => le log achete de la profondeur utile =>")
print(f"           CONFIRMER en jeu GENERAL (#1b) contre le prior 0264/0268 (jass +42 Elo en reduisant MOINS) avant de baker.")
print(f"           IC contient/sous 0.50 => le log NE gagne pas meme sur dilf => levier LMR-log MORT (coherent 0268) => consigner.")
PY
say "=== rappel : EBF_jass post-combo = 1,69 vs Scan 1,25 (0495). Le log VISE a baisser ca. Si #1 positif -> #1b general + re-mesure EBF avec lmr_formula=1 + vs Scan. ==="
