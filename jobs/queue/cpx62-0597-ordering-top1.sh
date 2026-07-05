#!/usr/bin/env bash
# id: cpx62-0597-ordering-top1
# description: DIAGNOSTIC ORDERING + TOP-1 jass vs Scan (JFC : "taux de cutoff-au-premier-coup jass vs Scan + accord top-1").
# Le cutoff-au-premier-coup litteral est interne (jass instrumentable, Scan non) => version CROSS-ENGINE equitable =
# "survie du premier choix" = accord(bestmove@d1, bestmove@dDEEP) mesure a l'IDENTIQUE pour les 2 moteurs : a quel point
# le coup immediat (1-ply, dirige par l'ordering) egale le coup reflechi (profond). jass<<Scan => on ordonne/selectionne
# moins bien le bon coup au 1er essai => arbre plus gros => moins de profondeur => vrai levier. + ACCORD TOP-1 jass-deep
# vs Scan-deep (jouons-nous les memes coups ?). Reutilise les adaptateurs HUB de calibrate_vs_scan (bestmove a profondeur
# fixe, deja prouves en jeu 0592). gen1, moteur coin. N=1500 positions stratifiees par phase. AUCUN NNUE, pure mesure.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0597-ordering-top1/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0597-ordering-top1/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-ord; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DILF=data/dilf_combinations.fen
N=1500; DEEP=11; SHAL=1

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

# Scan pret
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  SRC=/root/jass-scan-src; [ -d "$SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SRC" >"$W/sc.log" 2>&1
  mkdir -p /root/jass-scan; cp "$SRC/scan_linux" "$SCAN_BIN" 2>/dev/null && chmod +x "$SCAN_BIN"
  cp -r "$SRC/data" /root/jass-scan/data 2>/dev/null||true; cp "$SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null||true
fi
[ -x "$SCAN_BIN" ] || { say "ABORT Scan absent"; exit 3; }

say "=== ordering + top-1 jass vs Scan — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }
say "  Scan=$SCAN_BIN ; N=$N ; d_shallow=$SHAL d_deep=$DEEP"

# echantillon stratifie -> fens.tsv  (phase<TAB>fen)
python3 - "$W/corpus.jnnw" "$W/fens.tsv" "$N" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys,collections
d=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]; K=int(sys.argv[3])
def pc(r):
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); return bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
def fen(wm,wk,bm,bk,stm):
    Wl=[];Bl=[]
    for sq in range(1,51):
        b=1<<(sq-1)
        if wm&b:Wl.append(str(sq))
        elif wk&b:Wl.append("K"+str(sq))
        elif bm&b:Bl.append(str(sq))
        elif bk&b:Bl.append("K"+str(sq))
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
bands={0:(0,12),1:(13,20),2:(21,28),3:(29,40)}; byb=collections.defaultdict(list); per=K//4
step=max(1,n//(K*6))
for i in range(0,n,step):
    r=body[i*REC:(i+1)*REC]; p=pc(r)
    for bi,(lo,hi) in bands.items():
        if lo<=p<=hi and len(byb[bi])<per:
            wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
            # ecarte positions sans coup (finales bloquees rares) : garde tout, le driver filtre None
            byb[bi].append((bi,fen(wm,wk,bm,bk,stm))); break
rows=[]
for bi in range(4): rows+=byb[bi]
open(sys.argv[2],'w').write("\n".join(f"{b}\t{f}" for b,f in rows)+"\n")
print(f"  echantillon : {len(rows)} ({[len(byb[b]) for b in range(4)]} par bande)")
PY
NROWS=$(wc -l < "$W/fens.tsv")

# driver per-shard : importe les adaptateurs HUB de calibrate_vs_scan
cat > "$W/driver.py" <<'PY'
import sys
sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine, ScanEngine, jass_fen_to_scan_pos
jbin=sys.argv[1]; gen1=sys.argv[2]; scan_bin=sys.argv[3]; shard=int(sys.argv[4]); nsh=int(sys.argv[5])
deep=int(sys.argv[6]); shal=int(sys.argv[7]); outp=sys.argv[8]; fensf=sys.argv[9]
rows=[ln.rstrip("\n").split("\t") for ln in open(fensf) if ln.strip()]
rows=[(int(b),f) for b,f in rows][shard::nsh]
def mv(m): return f"{m.frm}-{m.to}" if m else "NA"
jass=JassEngine(jbin, pattern_path=gen1); scan=ScanEngine(scan_bin, bb_size=0)
out=open(outp,"w")
for (band,fen) in rows:
    try:
        jass.set_position_fen(fen); jd1=mv(jass.go(depth=shal)); jdD=mv(jass.go(depth=deep))
    except Exception: jd1=jdD="NA"
    try:
        sp=jass_fen_to_scan_pos(fen); sd1=mv(scan.go_from(sp,[],depth=shal)); sdD=mv(scan.go_from(sp,[],depth=deep))
    except Exception: sd1=sdD="NA"
    out.write(f"{band}\t{jd1}\t{jdD}\t{sd1}\t{sdD}\n"); out.flush()
out.close()
try: jass.close(); scan.close()
except Exception: pass
PY

say ""; say "=== query jd1/jd${DEEP} + sd1/sd${DEEP} sur $NROWS positions ($NCPU shards) ==="
for s in $(seq 0 $((NCPU-1))); do
  python3 "$W/driver.py" "$J" "$W/gen1.pjtw" "$SCAN_BIN" "$s" "$NCPU" "$DEEP" "$SHAL" "$W/out.$s" "$W/fens.tsv" >"$W/drv_$s.log" 2>&1 &
done; wait
cat "$W"/out.* > "$W/all.tsv" 2>/dev/null
say "  reponses : $(wc -l < "$W/all.tsv") / $NROWS  (echecs shards : $(grep -lc Traceback "$W"/drv_*.log 2>/dev/null | wc -l))"

python3 - "$W/all.tsv" "$DEEP" <<'PY' 2>&1 | tee -a "$RES"
import sys,collections
rows=[ln.rstrip("\n").split("\t") for ln in open(sys.argv[1]) if ln.strip()]; deep=sys.argv[2]
BN={0:'finale<=12',1:'milieu13-20',2:'milieu21-28',3:'ouverture>=29'}
def rate(sel,cond):
    num=sum(1 for r in sel if cond(r)); den=len(sel); return (num/den if den else 0, den)
def block(tag, sel):
    sel=[r for r in sel if r[2]!="NA" and r[4]!="NA"]  # deep dispo des 2 cotes
    jsurv=rate(sel, lambda r: r[1]!="NA" and r[1]==r[2])   # jass d1==dDeep
    ssurv=rate(sel, lambda r: r[3]!="NA" and r[3]==r[4])   # scan d1==dDeep
    top1 =rate(sel, lambda r: r[2]==r[4])                  # jass_deep == scan_deep
    sh1  =rate(sel, lambda r: r[1]!="NA" and r[3]!="NA" and r[1]==r[3])
    print(f"  {tag:14s} n={jsurv[1]:5d} | survie-1er-choix jass={jsurv[0]:.3f} scan={ssurv[0]:.3f} (ecart={jsurv[0]-ssurv[0]:+.3f}) | accord-top1 deep={top1[0]:.3f} shallow={sh1[0]:.3f}")
    return jsurv[0], ssurv[0], top1[0]
print("")
print(f"  [SURVIE DU 1er CHOIX] = accord(bestmove@d1, bestmove@d{deep}) — proxy cross-engine du cutoff-au-1er-coup :")
gj,gsc,gt=block("GLOBAL", rows)
for bi in range(4): block(BN[bi], [r for r in rows if r and int(r[0])==bi])
print("")
print("  ===== ROUTAGE =====")
d=gj-gsc
if d < -0.05:
    print(f"  jass survie MOINS que Scan (ecart {d:+.3f}) => notre coup immediat (ordering/eval) est le bon coup profond")
    print(f"  MOINS souvent que Scan => on gaspille des noeuds sur de mauvais 1ers coups => arbre plus gros / moins profond")
    print(f"  => LEVIER ORDERING/eval-marge REEL. Piste : meilleure selection du 1er coup (eval au coup, history/SEE ordering).")
elif d > 0.05:
    print(f"  jass survie PLUS que Scan (ecart {d:+.3f}) => notre ordering n'est pas le retard.")
else:
    print(f"  parite survie 1er-choix (ecart {d:+.3f}) => l'ordering n'est PAS le levier => le -338 fixed-depth vient d'ailleurs")
    print(f"  (eval-en-arbre profonde / interplay extensions), pas de la selection du 1er coup.")
print(f"  accord-top1 deep global={gt:.3f} : a quel point on joue les MEMES coups que Scan a d{deep} (bas => on diverge).")
PY
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0597 ordering+top1 jass vs Scan : survie du 1er choix (proxy cutoff) + accord top-1 par phase" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin ordering+top1 ==="
