#!/usr/bin/env bash
# id: ccx33-0547-gendata
# description: FEEDER self-play combo-aware (JFC "ccx33 alimente cpx62, on poolera les 2 gen-data pour plus de puissance").
# GEN-ONLY : genere 3M positions self-play (config identique a 0545 : pilote=champion, asym CONSERVEE, combo-seeded,
# qs_sacs bake ON) puis COMMIT le corpus gzippe comme artefact. PAS de fit, PAS de judge (le fit poole se fait sur cpx62,
# job 0548). Le corpus committe = corpus-gen1b.jnnw.gz. AUCUN NNUE. expected_duration: ~4-8 h (ccx33 8 coeurs).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0547-gendata/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-feeder; rm -rf "$W"; mkdir -p "$W"
FRESH=3000000; PLAY_DEPTH=10; LABEL_DEPTH=4; OPEN_PLIES=8; EXPLORE_EPS=5; MAXPLIES=200
FORCE_SPEC="ext_forcing=1,forcing_ext_cap=6"; SEED_FRAC=25
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"

say "=== build jass depuis main (qs_sacs bake ON, 32-pat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champ absent"; exit 4; }
say "  HEAD main : $(git log --oneline -1 | cat)"

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

# seed-file (dilf + lidraughts) — meme construction que 0545
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

say ""
say "=== GENERATION 3M (pilote=champion, asym CONSERVEE, combo-seeded) ==="
per=$(( (FRESH+NCPU-1)/NCPU ))
for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$W/sp.jnnw.$s" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
    --nnue "$W/champ.pjtw" --asym-punisher-params "$FORCE_SPEC" --quiet-only \
    --seed-file "$SEEDFILE" --seed-frac "$SEED_FRAC" --random-open-plies "$OPEN_PLIES" --explore-eps "$EXPLORE_EPS" \
    >/dev/null 2>&1 & done; wait
merge "$W/sp.jnnw"
NSP=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/sp.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
say "  self-play genere : ${NSP} pos"
[ "${NSP:-0}" -ge 500000 ] || { say "ABORT corpus trop petit ($NSP)"; exit 7; }

say ""
say "=== COMMIT corpus (feeder -> pool cpx62-0548) ==="
gzip -c "$W/sp.jnnw" > "$ART/corpus-gen1b.jnnw.gz"
say "  corpus-gen1b.jnnw.gz : ${NSP} pos, $(du -h "$ART/corpus-gen1b.jnnw.gz" | cut -f1)"
say "=== fin feeder ccx33 (corpus pret a etre poole) ==="
