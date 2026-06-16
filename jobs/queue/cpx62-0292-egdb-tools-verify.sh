#!/usr/bin/env bash
# id: cpx62-0292-egdb-tools-verify
# description: VALIDE les 2 outils egdb (--gen-egdb-wld, --egdb-relabel) sur la vraie base. (1) génère
# 100k positions de coverage WLD exact → vérifie distribution W/D/L saine + toutes ≤7 pièces + ≥1/côté.
# (2) génère un petit self-play (50k, sans egdb) puis le RELABEL → compte les labels changés (>0 attendu
# sur les finales) + IDEMPOTENCE (relabel ×2 = 0 changement au 2e). Garde-fou avant de brancher coverage
# /relabel dans la boucle de prod.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0292-egdb-tools-verify/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
APP=/root/egdb_extracted/app
ls "$APP"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: base absente"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-egdb -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo BUILD FAIL; tail -15 "$ART/build.log"; exit 5; }
./build-egdb/jass_tests 2>&1 | tail -1
JASS=./build-egdb/jass

dist(){ python3 - "$1" <<'PY'
import sys,struct,collections
p=sys.argv[1]; b=open(p,'rb').read(); assert b[:4]==b'JNNW',"bad magic"
cnt=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]
wdl=collections.Counter(); pc=collections.Counter(); bad=0
import numpy as np
for i in range(min(cnt, (len(body))//REC)):
    r=body[i*REC:(i+1)*REC]
    bbs=struct.unpack('<4Q',r[:32]); stm=r[32]; w=struct.unpack('<b',r[37:38])[0]
    wdl[w]+=1
    n=sum(bin(x).count('1') for x in bbs); pc[n]+=1
    wm,wk,bm,bk=bbs
    if (bin(wm|wk).count('1')<1) or (bin(bm|bk).count('1')<1): bad+=1
print(f"  header_count={cnt} records={sum(wdl.values())}")
print(f"  WDL: win(+1)={wdl[1]} draw(0)={wdl[0]} loss(-1)={wdl[-1]}")
print(f"  pieces: {dict(sorted(pc.items()))}")
print(f"  one-sided(BAD)={bad}  max_pieces={max(pc) if pc else 0}")
PY
}

echo "=== (1) gen-egdb-wld 100k (coverage WLD exact) ==="
$JASS --gen-egdb-wld 100000 "$ART/cov.jnnw" "$APP" 7 1024 1 2>&1 | tail -2
dist "$ART/cov.jnnw"

echo "=== (2) relabel : petit self-play (50k, sans egdb) → relabel → idempotence ==="
PER=$(( (50000 + NCPU - 1) / NCPU ))
for s in $(seq 1 "$NCPU"); do $JASS --gen-data-wdl "$PER" "$ART/sp-$s.jnnw" 6 6 200 $((RANDOM)) >"$ART/sp-$s.log" 2>&1 & done; wait
python3 - "$ART/sp" "$ART/sp.jnnw" <<'PY'
import struct,glob,sys,re
outp,dst=sys.argv[1],sys.argv[2]; REC=38; body=b""; add=0
for s in sorted(glob.glob(outp+"-*.jnnw")):
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; add+=n; body+=b[8:8+n*REC]
open(dst,'wb').write(b'JNNW'+struct.pack('<I',add)+body); print("self-play",add)
PY
echo "--- relabel pass 1 (attendu : labels changés > 0) ---"
$JASS --egdb-relabel "$ART/sp.jnnw" "$APP" "$ART/sp-rl.jnnw" 2>&1 | tail -1
echo "--- relabel pass 2 sur le déjà-relabelisé (attendu : 0 changement = idempotent) ---"
$JASS --egdb-relabel "$ART/sp-rl.jnnw" "$APP" "$ART/sp-rl2.jnnw" 2>&1 | tail -1
cmp -s "$ART/sp-rl.jnnw" "$ART/sp-rl2.jnnw" && echo "  IDEMPOTENT (rl == rl2)" || echo "  NON-IDEMPOTENT (BUG)"

echo; echo "=========================================================="
echo "   cpx62-0292 — VALIDATION outils egdb"
echo "  coverage : distribution + ≤7p + ≥1/côté ci-dessus."
echo "  relabel  : changements>0 (finales corrigées) + idempotence = OK → prêts pour la boucle."
echo "=========================================================="
