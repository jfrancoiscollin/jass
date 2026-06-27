#!/usr/bin/env bash
# id: ccx33-0480-genoff-scale
# description: PRE-GEN du scale (demande JFC, anticipation) : pendant que 0479 tranche l'A/B elagage ON/OFF, on accumule sur
# ccx33 (idle) un gros corpus self-play ELAGAGE-OFF (--search-params), pret a fitter si 0479 confirme. Self-play normal (PAS de
# seeds dilf = test set), pilote egdbmix, play d8 full-width (attrape les shots 2-6 plis dans l'horizon => labels voyants,
# recette Scan). Genere par CHUNKS de 1M, chaque chunk merge + gzip + committe dans artefacts/genoff-NN.jnnw.gz (survit aux
# resets ; reutilisable). Pur GEN, AUCUN fit/juge (ca vient apres le verdict 0479). Si 0479 dit OFF~ON, on jette ce corpus.
# 100%% lineaire, self-play, sans prof, sans NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0480-genoff-scale/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-genoff; rm -rf "$W"; mkdir -p "$W"
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
CHUNK=1000000; NCHUNKS=24; EVALDEPTH=4; PLAYDEPTH=8; OPEN=8
OFF="rfp_max_depth=0,nmp_min_depth=99,lmr_min_depth=99,lmp_max_depth=0,razor_max_depth=0,multicut_min_depth=0,probcut_min_depth=0"
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR ; CHUNK=$CHUNK x $NCHUNKS ; play d$PLAYDEPTH full-width (elagage OFF)"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
say "=== build jass JASS_EGDB=ON (avec --search-params au gen) ==="
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$PILOT_GZ" 2>/dev/null | gunzip > "$W/pilot.pjtw" || { say "ABORT: pilot absent"; exit 4; }
[ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted

merge(){ python3 - "$1" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38; body=b""; tot=0
for f in sorted(glob.glob(out+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; body+=b[8:8+n*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
rm -f "$1".[0-9]* ; }

TOTAL=0
for k in $(seq 1 "$NCHUNKS"); do
  kk=$(printf "%02d" "$k")
  [ -f "$ART/genoff-$kk.jnnw.gz" ] && { say "  chunk $kk deja la, skip"; continue; }   # reprise apres reset
  per=$(( (CHUNK+NCPU-1)/NCPU ))
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$W/c$kk.jnnw.$s" "$EVALDEPTH" "$PLAYDEPTH" 200 "$((RANDOM*RANDOM+s+k*100))" \
      --nnue "$W/pilot.pjtw" --random-open-plies "$OPEN" --search-params "$OFF" >"$W/gen-$kk.$s.log" 2>&1 & done; wait
  N=$(merge "$W/c$kk.jnnw")
  gzip -c "$W/c$kk.jnnw" > "$ART/genoff-$kk.jnnw.gz"; rm -f "$W/c$kk.jnnw"
  TOTAL=$((TOTAL+N)); say "  chunk $kk : +${N} (cumul ~${TOTAL}) -> committe genoff-$kk.jnnw.gz"
done
say ""; say "=== PRE-GEN TERMINE : ~${TOTAL} positions self-play ELAGAGE-OFF committees (artefacts/genoff-*.jnnw.gz) ==="
say "  reutilisable directement comme pool pour le fit du scale, SI 0479 confirme OFF > ON."
