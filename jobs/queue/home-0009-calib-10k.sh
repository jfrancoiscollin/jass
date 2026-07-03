#!/usr/bin/env bash
# id: home-0009-calib-10k
# description: CALIBRATION débit self-play (JFC : mesurer sur le PC pour extrapoler le temps 3M des box, et trancher
# si les 15h de 0545 = normal ou hang). Génère 10k positions ISO-CONFIG boxes (qs_sacs baké, 32-pat, play_depth 10,
# label_depth 4, asym punisher ext_forcing, quiet-only, seed dilf, explore-eps 5, pilote=champion egdbmix), chronométré.
# Sort : positions/s, temps 3M du PC, et extrapolation par cœur vers cpx62 (16c) / ccx33 (8c). AUCUN NNUE. ~6 min.
set -uo pipefail
cd /root/jass
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/home-0009-calib-10k/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
W=/root/cw-calib; rm -rf "$W"; mkdir -p "$W"
TARGET=10000; PLAY_DEPTH=10; LABEL_DEPTH=4; MAXPLIES=200
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen

preflight_build 1
preflight_note "calibration 10k self-play iso-box (play_depth 10, x$NCPU)" 3
preflight_check

say "=== build jass (32-pat, qs_sacs baké — ISO box ; egdb OFF, PC sans bitbase) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -15 "$W/build.log"|sed 's/^/  /'; exit 5; }
J="$W/build/jass"
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champ egdbmix absent"; exit 4; }
say "  HEAD main : $(git log --oneline -1 | cat)"
say "  sanity qs_sacs (doit lister des SACS) : $(head -1 "$DILF" | sed 's/#.*//' | "$J" --dump-sacs 2>/dev/null | head -1)"
say "  CPU : $NCPU coeurs ; modele : $(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo '?')"

# seed-file dilf (iso-box)
python3 - "$W" "$DILF" <<'PY'
import sys,struct; sys.path.insert(0,'tools'); from pdn_to_jnnw import fen_to_bitboards,_REC_STRUCT
W,dilf=sys.argv[1],sys.argv[2]; r=bytearray(); n=0
for ln in open(dilf):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm,wm,wk,bm,bk=fen_to_bitboards(b); r+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); n+=1
open(f"{W}/seed.jnnw","wb").write(b'JNNW'+struct.pack('<I',n)+bytes(r)); print(f"seed:{n}")
PY

per=$(( (TARGET+NCPU-1)/NCPU ))
say ""
say "=== GÉNÉRATION 10k chronométrée ($NCPU shards x $per, iso-config box) ==="
T0=$(date +%s)
for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$W/cal.jnnw.$s" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
    --nnue "$W/champ.pjtw" --asym-punisher-params "ext_forcing=1,forcing_ext_cap=6" --quiet-only \
    --seed-file "$W/seed.jnnw" --seed-frac 25 --random-open-plies 8 --explore-eps 5 \
    >/dev/null 2>"$W/gen.$s.err" & done
wait
T1=$(date +%s); DT=$((T1-T0)); [ "$DT" -lt 1 ] && DT=1
POS=$(python3 -c "import glob,os
t=0
for f in glob.glob('$W/cal.jnnw.*'):
    try: t+=max(0,(os.path.getsize(f)-8)//38)
    except: pass
print(t)")

say ""
python3 - "$POS" "$DT" "$NCPU" <<'PY' 2>&1 | tee -a "$RES"
import sys
pos,dt,nc=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
rate=pos/dt if dt else 0; per_core=rate/nc if nc else 0
def hms(s):
    s=int(s); return f"{s//3600}h{(s%3600)//60:02d}m"
print("================= CALIBRATION 10k =================")
print(f"  positions : {pos:,}  en {dt}s  ({nc} coeurs)")
print(f"  debit total   : {rate:,.0f} pos/s")
print(f"  debit /coeur  : {per_core:,.1f} pos/s/coeur")
print(f"  --> PC, 3M    : {hms(3_000_000/rate) if rate else 'NA'}")
print(f"  --> extrapolation box (meme vitesse/coeur) :")
print(f"        cpx62 (16c) 3M ~ {hms(3_000_000/(per_core*16)) if per_core else 'NA'}")
print(f"        ccx33 ( 8c) 3M ~ {hms(3_000_000/(per_core*8)) if per_core else 'NA'}")
print(f"  (leger surestime : inclut init une-fois ; vrai 3M un poil plus rapide)")
print(f"  => si box 'devrait' faire 3M en quelques h -> les 15h de 0545 = HANG.")
print("==================================================")
PY
say "  (erreurs gen eventuelles : $W/gen.*.err)"
say "=== fin calibration ==="
