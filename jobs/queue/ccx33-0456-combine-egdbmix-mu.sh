#!/usr/bin/env bash
# id: ccx33-0456-combine-egdbmix-mu
# description: SYNTHESE (demande JFC : "tester le nouveau champion sur le corpus 442"). Les 2 gains sont orthogonaux :
# egdb-mix = FINALE, diversification mu = MILIEU. On les COMBINE en un champion. Piloté par champion-egdbmix (le nouveau
# best), on genere ~10M de self-play DIVERSIFIE (seeds combinaisons dilf + milieux lidraughts seed_frac=30, mix jeu
# d10/d12, explore-eps=8, open-plies=10 ; terminate-at-TB pour labels finale exacts), on MIXE 4M egdb-finale, on refit, et
# on juge : (a) combine vs champion-egdbmix self-play (la diversite ajoute-t-elle ?), (b) CONVERSION combinaisons dilf vs
# Scan (le MILIEU s'ameliore-t-il ? cible 0440 : base 0.246), (c) conversion finale vs Scan (garde-t-on le gain endgame ?).
# Disponible MAINTENANT (vs attendre les jours de 0442). On ne touche pas a 0442. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0456-combine-egdbmix-mu/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-combine; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
BASE_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
DILF=data/dilf_combinations.fen
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"
GEOM32=/root/jass-geom32-combine
FRESH=10000000; NEGDB=4000000; SEEDFRAC=30; MID_LO=14; MID_HI=40; SEED_CAP=400000
P1=10; F1=70; P2=12; LBL=4; OPEN=10; EPS=8           # recette combine (milieu)
EVAL_DEPTH=4; L2=3e-5; MAXIT=25; CHUNK=1000000; D=11; JUDGE_PAIRS=28

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 4; }
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR"
say "=== build jass JASS_EGDB=ON ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; export JASS_EGDB_PATH="$EGDIR"
git show "origin/main:$PILOT_GZ" 2>/dev/null | gunzip > "$W/pilot.pjtw" || { say "ABORT: pilot egdbmix absent"; exit 4; }
git show "origin/main:$BASE_GZ"  2>/dev/null | gunzip > "$W/base.pjtw"  || { say "ABORT: base absent"; exit 4; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

# ---------- seed-file (dilf + lidraughts milieux) ----------
SHARDS=$(ls $SHARD_GLOB 2>/dev/null || true)
python3 - "$W/seeds.jnnw" "$DILF" "$MID_LO" "$MID_HI" "$SEED_CAP" $SHARDS <<'PY' | tee -a "$RES"
import sys,struct,gzip,random; sys.path.insert(0,'tools'); from pdn_to_jnnw import fen_to_bitboards,_REC_STRUCT
REC=38; out=sys.argv[1]; dilf=sys.argv[2]; lo=int(sys.argv[3]); hi=int(sys.argv[4]); cap=int(sys.argv[5]); shards=sys.argv[6:]
random.seed(0xC0DE); recs=bytearray(); nd=0
for ln in open(dilf):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm,wm,wk,bm,bk=fen_to_bitboards(b); recs+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); nd+=1
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
for r in mids: recs+=r
open(out,'wb').write(b'JNNW'+struct.pack('<I',nd+len(mids))+bytes(recs)); print(f"  seeds : {nd+len(mids)} (dilf={nd}, lidr={len(mids)})")
PY

# ---------- helpers ----------
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
app(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]; acc=sys.argv[2]
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    old=struct.unpack('<I',open(acc,'rb').read(8)[4:8])[0]; o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else: open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
gen(){ local pilot="$1" nn="$2" out="$3" depth="$4"; local per=$(( (nn+NCPU-1)/NCPU ))
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$LBL" "$depth" 200 "$((RANDOM*RANDOM+s))" \
      --nnue "$pilot" --seed-file "$W/seeds.jnnw" --seed-frac "$SEEDFRAC" --random-open-plies "$OPEN" --explore-eps "$EPS" >/dev/null 2>&1 & done; wait
  merge "$out"; }
conv(){ python3 - "$1" "$2" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]; stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0]
jw=jn=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue
    jw+=0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0); jn+=1
print(f"{jw/jn:.3f} ({jw:.0f}/{jn})" if jn else "NA")
PY
}
pjudge(){ for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$1" --jass-b "$J" --pattern-b "$2" --depth 9 --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>&1 & done; wait
  python3 - "$W"/j.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f}" if g else "NA")
PY
  rm -f "$W"/j.* ; }

# ---------- gen diversifie (pilote = champion-egdbmix) + egdb + fit ----------
say "=== gen ${FRESH} diversifie (pilote=egdbmix, ${F1}% d${P1}+$((100-F1))% d${P2}, seed_frac=${SEEDFRAC}, eps=${EPS}) ==="
N1=$(( FRESH*F1/100 )); N2=$(( FRESH-N1 ))
gen "$W/pilot.pjtw" "$N1" "$W/g1.jnnw" "$P1"; gen "$W/pilot.pjtw" "$N2" "$W/g2.jnnw" "$P2"
rm -f "$W/corpus.jnnw"; app "$W/g1.jnnw" "$W/corpus.jnnw" >/dev/null; app "$W/g2.jnnw" "$W/corpus.jnnw" >/dev/null
say "=== + 4M egdb-finale (baké) ==="
"$J" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 4004 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
app "$W/egdb.jnnw" "$W/corpus.jnnw" >/dev/null
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])"); say "  corpus combine : ${NMIX}"
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_combine.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_combine.pjtw" > "$ART/champion-combine.pjtw.gz"; rm -f "$W/feat"
unset JASS_EGDB_PATH   # juges eval-pur (no-DB)

# ---------- juges ----------
say ""; say "=== (a) combine vs champion-egdbmix (self-play d9) : la diversite mu ajoute-t-elle ? ==="
say "  combine vs egdbmix : $(pjudge "$W/champ_combine.pjtw" "$W/pilot.pjtw")   (>0.5 = la diversite aide)"
say "  combine vs base3e-5 : $(pjudge "$W/champ_combine.pjtw" "$W/base.pjtw")"
say ""; say "=== (b) CONVERSION combinaisons dilf vs Scan (d${D}) : le MILIEU s'ameliore-t-il ? (cible 0440=0.246) ==="
python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ_combine.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/combo-combine" >"$W/cc.log" 2>&1 || say "  (combo combine echoue)"
python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/pilot.pjtw"        --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/combo-egdbmix" >"$W/cp.log" 2>&1 || say "  (combo egdbmix echoue)"
say "  conversion combinaisons : egdbmix $(conv "$ART/combo-egdbmix" "$DILF")   combine $(conv "$ART/combo-combine" "$DILF")"
say ""; say "================= LECTURE ================="
say "  combine > egdbmix (self-play) ET conversion combinaisons monte => la diversification mu (piloté par le nouveau"
say "       champion) + egdb donne un MEILLEUR champion (milieu ET finale) => nouvelle promotion."
say "  conversion ~ egale => la diversite mu ne suffit pas a debloquer le milieu (cohérent si 0442 stagne aussi)."
say "=========================================="
