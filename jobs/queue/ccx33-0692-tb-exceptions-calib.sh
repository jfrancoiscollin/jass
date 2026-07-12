#!/usr/bin/env bash
# id: ccx33-0692-tb-exceptions-calib
# description: C4 CALIBRATION (go JFC "prioriser C4, je valide seulement apres avoir vu le rate calibre" 2026-07-12).
# Objectif C4 = miner les EXCEPTIONS TB : positions egdb-resolvables ou l'eval materielle NAIVE se trompe (avantage
# materiel mais nulle, ou pire perd ; ou deficit mais gagne) — les positions a plus haute valeur pedagogique (elles
# enseignent ce que le materiel ne dit pas). CE JOB NE MINE PAS : il CALIBRE, pour que JFC valide le volume AVANT le
# minage. Il mesure : (1) le RATE de --gen-egdb-wld (positions/s ecrites, yield ecrit/tente) ; (2) la DENSITE
# d'exceptions par 3 categories (STM-POV : |bal|>=2&nulle ; bal>=2&perd ; bal<=-2&gagne) ; (3) extrapolation
# wall-clock + nb exceptions attendues pour 1M/5M/10M positions minees. Primitive = --gen-egdb-wld (cf 0464 l.177,
# genere positions quietes legales 3..maxp pieces + label WLD EXACT egdb, STM-POV). Build JASS_EGDB=ON (pattern 0464).
# PRE-ESTIMATION (ancre 0464 : NEGDB=4M genere en fond de job egdb ; probe egdb cachee = rapide) : N=300k calib
# ~ quelques min build + < 5 min gen -> retour < ~15 min ccx33. LEGER par defaut (regle 1). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0692-tb-exceptions-calib/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0692-tb-exceptions-calib/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-tbcalib; rm -rf "$W"; mkdir -p "$W"
N=300000; MAXP=7; CACHE=2048; SEED=6924
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== 0692 C4 calib TB-exceptions — HEAD main $(git log --oneline -1|cat) ==="

# ---- egdb dispo ----
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0692 ABORT egdb absent"; exit 4; }
say "  egdb : $EGDIR"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1

# ---- build jass JASS_EGDB=ON (jeu src COMPLET de main) ----
say "=== build jass JASS_EGDB=ON ==="
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" \
  || { say "ABORT egdb build (cmake)"; tail -8 "$W/cmake.log"|sed 's/^/  /'; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0692 ABORT cmake"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 \
  || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0692 ABORT build"; exit 6; }
J="$W/build/jass"

# ---- generation calibree, timee ----
say "=== gen-egdb-wld N=$N maxp=$MAXP (calibration timee) ==="
T0=$(date +%s)
"$J" --gen-egdb-wld "$N" "$W/cal.jnnw" "$EGDIR" "$MAXP" "$CACHE" "$SEED" >"$W/ge.log" 2>&1 \
  || { say "ABORT gen egdb"; tail -6 "$W/ge.log"|sed 's/^/  /'; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0692 ABORT gen"; exit 7; }
T1=$(date +%s); ELAPSED=$((T1-T0)); [ "$ELAPSED" -lt 1 ] && ELAPSED=1
say "  gen : $(cat "$W/ge.log")"
say "  elapsed_gen_s=$ELAPSED"

# ---- lecture cal.jnnw : yield + densites d'exceptions (materiel STM-POV vs WDL) ----
python3 - "$W/cal.jnnw" "$ELAPSED" "$N" <<'PY' | tee -a "$RES"
import struct,sys
REC=38
path,elapsed,req=sys.argv[1],float(sys.argv[2]),int(sys.argv[3])
b=open(path,'rb').read()
assert b[:4]==b'JNNW', "mauvais magic"
n=struct.unpack('<I',b[4:8])[0]
def pc(x):
    c=0
    while x: x&=x-1; c+=1
    return c
tot=dec=drw=0; ex_draw=ex_loss=ex_win=0
off=8
for i in range(n):
    wm,wk,bm,bk,stm,score,wdl=struct.unpack_from('<QQQQBib',b,off); off+=REC
    tot+=1
    bal=(pc(wm)+3*pc(wk))-(pc(bm)+3*pc(bk))          # white-POV
    sbal=bal if stm==0 else -bal                     # STM-POV (aligne sur wdl)
    if wdl==0: drw+=1
    else: dec+=1
    if abs(sbal)>=2 and wdl==0: ex_draw+=1           # avantage mais nulle
    if sbal>=2 and wdl<0:       ex_loss+=1           # avantage mais PERD (le plus tranchant)
    if sbal<=-2 and wdl>0:      ex_win+=1            # deficit mais GAGNE
rate=n/elapsed
ex_tot=ex_draw+ex_loss+ex_win
def frac(x): return (x/tot) if tot else 0.0
print(f"  records={tot}  written/req={n}/{req}  yield_write={n/req:.4f}")
print(f"  decisive={dec} ({frac(dec):.3f})  draw={drw} ({frac(drw):.3f})")
print(f"  EXC_draw_despite_adv={ex_draw} ({frac(ex_draw):.4f})")
print(f"  EXC_loss_despite_adv={ex_loss} ({frac(ex_loss):.4f})")
print(f"  EXC_win_despite_defic={ex_win} ({frac(ex_win):.4f})")
print(f"  EXC_total={ex_tot} density={frac(ex_tot):.4f}")
print(f"  RATE_pos_per_s={rate:.1f}")
# --- extrapolation minage : wall-clock + nb exceptions attendues ---
for M in (1_000_000,5_000_000,10_000_000):
    secs=M/rate; exc=frac(ex_tot)*M
    print(f"  EXTRAP mine={M}: wall≈{secs/60:.1f}min ({secs/3600:.2f}h)  exceptions≈{exc:,.0f}")
PY

commit_to_main "$RES" "$ARTREL/RESULTS.txt" \
  "0692 C4 calib : rate gen-egdb-wld + densite exceptions TB mesures (pour validation volume minage JFC)" \
  && say "  ✓ RESULTS committe sur main" || say "  ⚠ commit RESULTS echoue"
say "=== 0692 FINI ==="
