#!/usr/bin/env bash
# id: ccx33-0450-egdb-fit
# description: BITBASES -> POIDS (demande JFC). Sonde decisive AVANT le gros mix : un eval lineaire PEUT-il fitter la WDL
# EXACTE des finales (<=7 pieces), et de combien le champion actuel est-il loin de ce plafond ? On MINE des positions
# directement depuis l'egdb (--gen-egdb-wld, label exact, pas besoin de jouer) : 3M train + 40k test (seed disjoint).
# On fit un champion 32cf SUR l'egdb seul (logistic WDL) -> plafond linéaire. Puis on mesure la PRECISION (eval-pur,
# SANS egdb, profondeur 1 ~ statique) du champion BASE 3e-5 vs du champion EGDB-fit, contre la verite egdb du test :
#   - decisifs (wdl=+-1) : le signe de l'eval est-il correct ?   - nulles (wdl=0) : |eval| reste-t-il petit ?
# base faible & egdb-fit haut => gros gain de finale recuperable en MIXANT l'egdb au pool (job suivant). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0450-egdb-fit/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-egdbfit; rm -rf "$W"; mkdir -p "$W"
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
EGDIR=/root/egdb_extracted; GEOM32=/root/jass-geom32-egdbfit
NTRAIN=3000000; NTEST=40000; L2=3e-5; MAXIT=25; CHUNK=1000000; BAND=40

[ -d "$EGDIR" ] || { say "ABORT: egdb absent ($EGDIR)"; exit 4; }
say "=== build jass JASS_EGDB=ON ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ_base.pjtw" || { say "ABORT: champion absent"; exit 4; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

say "=== mine egdb : ${NTRAIN} train + ${NTEST} test (seeds disjoints) ==="
"$JASS" --gen-egdb-wld "$NTRAIN" "$W/train.jnnw" "$EGDIR" 7 2048 1001 >"$W/gtr.log" 2>&1 || { say "ABORT gen train"; tail -6 "$W/gtr.log"|sed 's/^/  /'; exit 7; }
"$JASS" --gen-egdb-wld "$NTEST"  "$W/test.jnnw"  "$EGDIR" 7 2048 9999 >"$W/gte.log" 2>&1 || { say "ABORT gen test"; tail -6 "$W/gte.log"|sed 's/^/  /'; exit 7; }
NTR=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/train.jnnw','rb').read(8)[4:8])[0])")
NTE=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/test.jnnw','rb').read(8)[4:8])[0])")
say "  train=${NTR}  test=${NTE}"

say "=== fit champion 32cf SUR l'egdb seul (plafond lineaire de la finale) ==="
"$JASS" --dump-eval-features "$W/train.jnnw" "$W/train.feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/train.jnnw" --feat "$W/train.feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_egdb.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "target=|train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_egdb.pjtw" > "$ART/champion-egdbfit.pjtw.gz"

say "=== precision finale vs egdb (eval-pur, SANS egdb, prof 1) : base vs egdb-fit ==="
export JASS="$JASS" BASE="$W/champ_base.pjtw" EGFIT="$W/champ_egdb.pjtw" TESTJ="$W/test.jnnw" BAND="$BAND"
worker(){ SHARD="$1" NS="$2" python3 - <<'PY'
import os,sys,re,struct
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine
JASS=os.environ["JASS"]; BASE=os.environ["BASE"]; EGFIT=os.environ["EGFIT"]; TESTJ=os.environ["TESTJ"]; BAND=int(os.environ["BAND"])
SH=int(os.environ["SHARD"]); NS=int(os.environ["NS"]); REC=38
b=open(TESTJ,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
def fen(i):
    wm,wk,bm,bk=struct.unpack('<QQQQ',body[i*REC:i*REC+32]); stm=body[i*REC+32]
    sl=lambda x:[j+1 for j in range(50) if (x>>j)&1]
    Wp=[str(s) for s in sl(wm)]+[f"K{s}" for s in sl(wk)]; Bp=[str(s) for s in sl(bm)]+[f"K{s}" for s in sl(bk)]
    return f"{'W' if stm==0 else 'B'}:W{','.join(Wp)}:B{','.join(Bp)}", struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
be=JassEngine(JASS, pattern_path=BASE, no_book=True); ee=JassEngine(JASS, pattern_path=EGFIT, no_book=True)
def ev(e,f):
    e.set_position_fen(f); e._drain(); e._send("go depth 1")
    L=e._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=20)[-1]
    if L.startswith("error"): return None
    m=re.search(r"score=(-?\d+)",L); return int(m.group(1)) if m else None
# compteurs : [base, egfit] x {dec_ok, dec_tot, draw_ok, draw_tot}
acc={"base":[0,0,0,0],"egfit":[0,0,0,0]}
for i in range(SH,n,NS):
    f,wdl=fen(i)
    for nm,e in (("base",be),("egfit",ee)):
        s=ev(e,f)
        if s is None: continue
        if wdl!=0:
            acc[nm][1]+=1
            if (wdl>0 and s>BAND) or (wdl<0 and s<-BAND): acc[nm][0]+=1
        else:
            acc[nm][3]+=1
            if abs(s)<=BAND: acc[nm][2]+=1
be.close(); ee.close()
print(f"R {acc['base'][0]} {acc['base'][1]} {acc['base'][2]} {acc['base'][3]} {acc['egfit'][0]} {acc['egfit'][1]} {acc['egfit'][2]} {acc['egfit'][3]}")
PY
}
export -f worker
for s in $(seq 0 $((NCPU-1))); do worker "$s" "$NCPU" >"$W/acc.$s" 2>&1 & done; wait
python3 - "$W"/acc.* <<'PY' | tee -a "$RES"
import sys
b=[0,0,0,0]; e=[0,0,0,0]
for f in sys.argv[1:]:
    try:
        for l in open(f):
            if l.startswith("R "):
                v=list(map(int,l.split()[1:9])); b=[b[i]+v[i] for i in range(4)]; e=[e[i]+v[i+4] for i in range(4)]
    except: pass
def pc(ok,tot): return f"{100*ok/tot:.1f}% ({ok}/{tot})" if tot else "n/a"
print(f"  {'champion':>10} | {'decisifs (signe correct)':>26} | {'nulles (|eval|<=band)':>22}")
print(f"  {'BASE 3e-5':>10} | {pc(b[0],b[1]):>26} | {pc(b[2],b[3]):>22}")
print(f"  {'EGDB-fit':>10} | {pc(e[0],e[1]):>26} | {pc(e[2],e[3]):>22}")
print("\n  LECTURE :")
print("   EGDB-fit >> BASE sur les decisifs => l'eval de finale du champion est tres ameliorable par les bitbases")
print("     => GO mix egdb au pool self-play (phase-weighted) -> refit -> juger vs base + Scan.")
print("   EGDB-fit ~ BASE                   => le champion classe deja bien la finale, peu a gagner.")
print("   EGDB-fit lui-meme bas (<~85%)     => plafond d'expressivite lineaire : l'eval ne PEUT pas representer la finale exacte.")
PY
say ""; say "# si prometteur : job suivant = assemble pool self-play + egdb (mix phase-weightee) -> fit -> juge vs base 3e-5 + Scan."
