#!/usr/bin/env bash
# id: ccx33-0551-gen1M-d8-feed
# description: FEEDER ccx33 (JFC) — gen 1M self-play a PLAY_DEPTH 8 (qualite intermediaire ; gen2/cpx62 est a pd6),
# pilote+recette = gen1 (nouveau champion, asym ext_forcing, quiet-only, combo-seed). Puis POOL avec le corpus
# SALVAGED (682k, 0549) => feed-pooled ~1.68M committe, que cpx62 recuperera ensuite pour un fit poole. GEN-ONLY
# (pas de fit/juge). Moniteur de volume + CHECKPOINT incremental (recup si kill), wait-on-pids (pas de bug hang).
# AUCUN NNUE. expected_duration: ~5-9 h (ccx33 8 coeurs, pd8).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0551-gen1M-d8-feed/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-feed8; rm -rf "$W"; mkdir -p "$W"
FRESH=1000000; PLAY_DEPTH=8; LABEL_DEPTH=4; OPEN_PLIES=8; EXPLORE_EPS=5; MAXPLIES=200
FORCE_SPEC="ext_forcing=1,forcing_ext_cap=6"; SEED_FRAC=25
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
SALVAGED_GZ=jobs/results/ccx33-0549-salvage-feeder/artefacts/corpus-gen1b-salvaged.jnnw.gz
DILF=data/dilf_combinations.fen
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"

say "=== build jass (qs_sacs bake, 32-pat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1 absent"; exit 4; }
say "  HEAD main : $(git log --oneline -1 | cat)"
say "  pilote = gen1 ; play_depth=$PLAY_DEPTH ; cible=$FRESH"

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
concat(){ local out="$1"; shift; python3 - "$out" "$@" <<'PY'
import struct,sys
out=sys.argv[1]; ins=sys.argv[2:]; REC=38; body=b""; tot=0; parts=[]
for f in ins:
    try: b=open(f,'rb').read()
    except Exception: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n; parts.append((f.split('/')[-1],n))
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body)
print("  concat -> "+str(tot)+" : "+", ".join(f"{k}={v}" for k,v in parts))
PY
}
count_pos(){ python3 -c "import glob,os
t=0
for f in glob.glob('$1.*'):
    try: t+=max(0,(os.path.getsize(f)-8)//38)
    except: pass
print(t)" 2>/dev/null || echo 0; }
checkpoint(){ python3 - "$1" "$ART/feed-partial.jnnw" <<'PY' 2>/dev/null
import glob,struct,sys,re
pre,out=sys.argv[1],sys.argv[2]; REC=38; body=b""; tot=0
for f in sorted(glob.glob(pre+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1)) if re.search(r"\.(\d+)$",p) else 0):
    try: b=open(f,'rb').read()
    except Exception: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body)
PY
gzip -f "$ART/feed-partial.jnnw" 2>/dev/null || true; }
gen_strong(){ local pilot="$1" nn="$2" out="$3"; local per=$(( (nn+NCPU-1)/NCPU )); local pids=()
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
      --nnue "$pilot" --asym-punisher-params "$FORCE_SPEC" --quiet-only \
      --seed-file "$SEEDFILE" --seed-frac "$SEED_FRAC" --random-open-plies "$OPEN_PLIES" --explore-eps "$EXPLORE_EPS" \
      >/dev/null 2>&1 & pids+=($!); done
  ( T0=$SECONDS; while kill -0 "${pids[0]}" 2>/dev/null; do
      P=$(count_pos "$out"); DT=$((SECONDS-T0)); R=$(( P/(DT>0?DT:1) ))
      echo "$(date -u +%H:%M:%SZ) positions~${P}/${nn} debit~${R}/s" >> "$ART/progress.txt"
      checkpoint "$out"; sleep 300
    done ) & local MON=$!
  wait "${pids[@]}"; kill "$MON" 2>/dev/null || true; wait "$MON" 2>/dev/null || true
  merge "$out"; }

# seed-file
say ""; say "=== seed-file (dilf + lidraughts) ==="
SHARDS=$(ls $SHARD_GLOB 2>/dev/null || true)
python3 - "$W" "$DILF" 14 40 300000 $SHARDS <<'PY' | tee -a "$RES"
import sys,struct,gzip,random
sys.path.insert(0,'tools'); from pdn_to_jnnw import fen_to_bitboards,_REC_STRUCT
REC=38; W=sys.argv[1]; dilf=sys.argv[2]; lo=int(sys.argv[3]); hi=int(sys.argv[4]); cap=int(sys.argv[5]); shards=sys.argv[6:]
random.seed(0xBEEF); drecs=bytearray(); nd=0
for ln in open(dilf):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm,wm,wk,bm,bk=fen_to_bitboards(b); drecs+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); nd+=1
mids=[]
for sh in shards:
    try: raw=gzip.open(sh,'rb').read()
    except Exception: continue
    if raw[:4]!=b'JNNW': continue
    m=struct.unpack('<I',raw[4:8])[0]; body=memoryview(raw)[8:8+m*REC]
    for i in range(m):
        r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
        pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
        if lo<=pc<=hi: mids.append(bytes(r))
random.shuffle(mids); mids=mids[:cap]
open(f"{W}/seeds.jnnw",'wb').write(b'JNNW'+struct.pack('<I',nd+len(mids))+bytes(drecs)+b"".join(mids))
print(f"  seed-file : dilf={nd} lidraughts={len(mids)}")
PY
SEEDFILE="$W/seeds.jnnw"; [ -s "$SEEDFILE" ] || { say "ABORT seed vide"; exit 7; }

# GEN 1M @ pd8
say ""; say "================= GEN 1M (pilote=gen1, play_depth $PLAY_DEPTH, asym) ================="
gen_strong "$W/gen1.pjtw" "$FRESH" "$W/sp.jnnw"
NSP=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/sp.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
say "  self-play pd8 : ${NSP} pos"
[ "${NSP:-0}" -ge 200000 ] || { say "ABORT corpus trop petit ($NSP)"; exit 7; }
rm -f "$ART/feed-partial.jnnw.gz"

# POOL avec le salvaged (682k)
say ""; say "=== POOL : ccx33 1M(pd8) + salvaged(682k) -> feed pour cpx62 ==="
git show "origin/main:$SALVAGED_GZ" | gunzip > "$W/salvaged.jnnw" 2>/dev/null && [ -s "$W/salvaged.jnnw" ] \
  && say "  salvaged tire : $(python3 -c "import struct;print(struct.unpack('<I',open('$W/salvaged.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0) pos" \
  || { say "  (salvaged absent -> feed = ccx33 seul)"; : > "$W/salvaged.jnnw"; }
concat "$W/feed.jnnw" "$W/sp.jnnw" "$W/salvaged.jnnw" | tee -a "$RES"
gzip -c "$W/feed.jnnw" > "$ART/feed-pooled.jnnw.gz"
NF=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/feed.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
say "  feed-pooled.jnnw.gz : ${NF} pos, $(du -h "$ART/feed-pooled.jnnw.gz" | cut -f1)"
say "  => pret a etre feed a cpx62 (pool fit)."
say "=== fin feeder ccx33 pd8 ==="
