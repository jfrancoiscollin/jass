#!/usr/bin/env bash
# id: ccx33-0304-hybrid-dist
# description: Confirme que le relabel HYBRIDE (proxy matériel+centralité + MTC) donne une distribution
# DENSE de la cible graduée (vs 58/150k en MTC-seul, 0303). Build egdb, gen 100k coverage ≤7, relabel
# hybride, dump la distribution du score=prob*10000 (doit montrer des milliers de valeurs graduées
# étalées, pas tout clampé à 0.55/1.0). Rapide (pas de train).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0304-hybrid-dist/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app; MTC=/root/egdb_mtc/app
ls "$WLD"/db2.idx1 "$MTC"/*.idx_mtc >/dev/null 2>&1 || { echo "ABORT: bases absentes"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-egdb -j"$NCPU" --target jass >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo BUILD FAIL; tail -15 "$ART/build.log"; exit 5; }
JASS=./build-egdb/jass

$JASS --gen-egdb-wld 100000 "$ART/cov.jnnw" "$WLD" 7 512 7777 2>&1 | tail -1
$JASS --egdb-mtc-relabel "$ART/cov.jnnw" "$WLD" "$MTC" "$ART/cg.jnnw" 1024 2>&1 | tail -1
python3 - "$ART/cg.jnnw" <<'PY'
import sys,struct,numpy as np
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38
sc=np.array([struct.unpack_from('<i',body,i*REC+33)[0] for i in range(n)],dtype=np.float64)/10000.0
flat=int(((sc==0.0)|(sc==0.5)|(sc==1.0)).sum())
graded=n-flat
print(f"  total={n}  flat(0/0.5/1)={flat}  GRADED={graded} ({graded/n*100:.1f}%)")
g=sc[(sc>0.5)&(sc<1.0)]
if len(g): print(f"  win-graded: n={len(g)} range[{g.min():.3f}..{g.max():.3f}] mean {g.mean():.3f} std {g.std():.3f}")
import collections
hist=collections.Counter((round(v,1) for v in sc))
print("  histogramme (arrondi 0.1):",dict(sorted(hist.items())))
PY
echo; echo "=========================================================="
echo "   ccx33-0304 — distribution hybride (GRADED ≫ 58 = le proxy comble le <10)"
echo "=========================================================="
