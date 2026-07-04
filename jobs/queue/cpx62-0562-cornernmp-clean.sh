#!/usr/bin/env bash
# id: cpx62-0562-cornernmp-clean
# description: RELAUNCH PROPRE de corner+nmp (JFC "relance proprement"). A 0561 corner+nmp est ressorti +39 hors-IC (248g,
# calcul job-side) MAIS il contredit son propre -28 de 0560 (173g) => sign-flip = suspect de bruit. On tranche avec UN
# SEUL bras (tout le budget dessus), gros N, et CAPTURE BLINDEE (le vrai coupable de 0561 : RESULTS fragmente + prog
# snapshots perimes du runner). corner+nmp = probcut_min_depth=5,lmr_first_full_nonpv=2,multicut_min_depth=4,eg_no_nmp=0
# (NMP sound via F1) vs baseline ERE-GEN1 (qs_threat_ext=0). movetime 0.3s, dilf, eval gen1. PAIRS=4.
# BLINDAGE : agrege depuis les prog LIVE en fin de job (pas les snapshots git), ecrit UN VERDICT.txt atomique, le commit
# JOB-SIDE une seule fois + concatene les RESULT bruts par shard pour verif independante. Critere : borne basse IC>0.50
# hors-IC ET coherent (pas un sign-flip) => baker corner+nmp au jeu. Sinon => referme EBF, pivot eval. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0562-cornernmp-clean/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0562-cornernmp-clean/artefacts"
W=/root/cw-cornernmp; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen; MT=0.3; PAIRS=4; MAXPLIES=180
BASE="qs_threat_ext=0"
LEV="probcut_min_depth=5,lmr_first_full_nonpv=2,multicut_min_depth=4,eg_no_nmp=0"
LOG="$W/run.log"; note(){ echo "$@" | tee -a "$LOG"; }

commit_to_main(){ local abspath="$1" relpath="$2" msg="$3"
  for a in 1 2 3 4 5; do
    git fetch origin main --quiet 2>/dev/null || true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"
    GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null || return 1
    local blob; blob=$(git hash-object -w "$abspath") || return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$blob" "$relpath"
    local tree; tree=$(GIT_INDEX_FILE="$idx" git write-tree)
    local commit; commit=$(printf '%s\n' "$msg" | git commit-tree "$tree" -p origin/main)
    if git push origin "$commit:main" 2>/dev/null; then rm -f "$idx"; return 0; fi
    sleep $((a*3))
  done; return 1; }

note "=== build jass depuis main (archi complete) — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { note "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { note "ABORT gen1 absent"; exit 4; }
note "  corner+nmp ($LEV) vs baseline ERE-GEN1 ($BASE) ; mt${MT}s ; PAIRS=$PAIRS ; dilf ; eval gen1"

prog="$ART/prog"
for s in $(seq 0 $((NCPU-1))); do
  ( python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/gen1.pjtw" \
      --jass-b "$J" --pattern-b "$W/gen1.pjtw" --movetime "$MT" --pairs "$PAIRS" \
      --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
      --search-params-a "$BASE,$LEV" --search-params-b "$BASE" \
      --progress-file "${prog}.$s" >"$W/o.$s" 2>&1; echo "$?" >"$W/rc.$s" ) &
done
note "  16 shards lances @ $(date -u +%H:%M:%S)Z ; attente..."
wait
note "  shards finis @ $(date -u +%H:%M:%S)Z"

# ---- CAPTURE BLINDEE : agrege depuis les prog LIVE (pas git), verdict atomique ----
crash=0; mute=0; RAW="$ART/raw_shards.txt"; : > "$RAW"
for s in $(seq 0 $((NCPU-1))); do
  rc=$(cat "$W/rc.$s" 2>/dev/null || echo 99); [ "$rc" != "0" ] && crash=$((crash+1))
  grep -qiE 'traceback|segfault|core dumped|assert|abort' "$W/o.$s" 2>/dev/null && crash=$((crash+1))
  line=$(grep '^RESULT' "${prog}.$s" 2>/dev/null | tail -1)
  [ -z "$line" ] && mute=$((mute+1))
  echo "shard $s rc=$rc : ${line:-<muet>}" >> "$RAW"
done

VERD="$ART/VERDICT.txt"
python3 - "$prog" "$NCPU" "$crash" "$mute" "$LEV" "$BASE" "$MT" "$PAIRS" > "$VERD" <<'PY'
import sys,math
prog,nc,crash,mute,lev,base,mt,pairs=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),sys.argv[5],sys.argv[6],sys.argv[7],sys.argv[8]
a=d=b=0; ns=0
for s in range(nc):
    try:
        last=[l for l in open(f"{prog}.{s}") if l.startswith("RESULT")][-1]
        _,x,y,z=last.split(); a+=int(x);d+=int(y);b+=int(z); ns+=1
    except: pass
g=a+d+b
print("=== VERDICT cpx62-0562 corner+nmp CLEAN (capture blindee, agrege prog LIVE) ===")
print(f"bras   : corner+nmp = {base},{lev}")
print(f"config : movetime {mt}s ; PAIRS {pairs} ; dilf ; eval gen1 ; baseline {base}")
print(f"shards : {ns}/{nc} avec RESULT ; crashs/erreurs={crash} ; muets={mute}")
if not g:
    print("AUCUNE DONNEE"); sys.exit()
r=(a+0.5*d)/g; ex2=(a+0.25*d)/g; v=ex2-r*r
se=math.sqrt(v/g) if v>0 else 0.5/math.sqrt(g); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
verd="GAGNE hors-IC (borne basse > 0.50)" if lo>0.5 else ("PERD hors-IC (borne haute < 0.50)" if hi<0.5 else "PARITE (IC contient 0.50)")
print(f"games  : {g}  (A={a} wins  D={d} nulles  B={b})")
print(f"rate   : {r:.4f} +- {1.96*se:.4f}  (draw-adjusted SE)")
print(f"elo    : {elo:+.0f}")
print(f"IC95   : [{lo:.4f}, {hi:.4f}]")
print(f"=> {verd}")
print("")
print("RAPPEL historique corner+nmp : 0560=-28 (173g) ; 0561=+39 hors-IC (248g, capture douteuse).")
print("Ce run tranche : si GAGNE hors-IC ET coherent => baker au jeu. Si PARITE/sign-flip => bruit, referme EBF, pivot eval.")
PY
cat "$VERD"

# commit JOB-SIDE : verdict + bruts, une seule fois, robuste au runner
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0562 corner+nmp CLEAN : VERDICT job-side (capture blindee)" \
  && note "  VERDICT committe job-side ✓" || note "  ⚠ commit VERDICT echoue"
commit_to_main "$RAW"  "$ARTREL/raw_shards.txt" "0562 corner+nmp CLEAN : raw shards job-side" || true
note "=== fin 0562 corner+nmp clean ==="
