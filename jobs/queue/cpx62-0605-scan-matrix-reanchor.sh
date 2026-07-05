#!/usr/bin/env bash
# id: cpx62-0605-scan-matrix-reanchor
# description: RE-ANCRAGE matrice vs Scan sur main FRAIS (9422fc02 : coin+49, threat_ext+108, ordering-prob+30 = +187 search
# cumules). La baseline 0571 est perimee de 3 bakes ; toute la campagne rank-loss (G3/G4) sera jugee contre cette reference.
# 5 cellules, PREDICTIONS PRE-ENGAGEES (le coeur du test). Build MAIN brut (defauts runner = prob-pur bake). Meme Scan, memes
# openings (dilf 60) que 0571 pour comparabilite. Cellules calibrate EN PARALLELE sans oversubscription (movetime non-biaise
# sur 16 coeurs). Cellule survie shardee (baseline G1 rank-loss). VERDICT atomique job-side. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0605-scan-matrix-reanchor/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0605-scan-matrix-reanchor/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-reanchor; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DILF=data/dilf_combinations.fen
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
NOPEN=60

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

say "=== RE-ANCRAGE vs Scan (main frais) — HEAD $(git log --oneline -1|cat) ==="
say "  bake ordering present : $(git show origin/main:src/search_params.hpp|grep -cE 'int hist_mode  = 1|int hist_pure  = 1')/2 ; coin : $(git show origin/main:src/search_params.hpp|grep -cE 'probcut_min_depth = 5|qs_threat_ext = true|lmr_first_full_nonpv = 2')/3"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
head -n "$NOPEN" "$DILF" > "$W/open.fen"

say ""
say "  === PRÉDICTIONS PRÉ-ENGAGÉES (0571 baseline -> main frais) ==="
say "   d9 fixe   : 0.127/-335  -> ~INCHANGÉ (ordering ne touche pas l'éval-par-nœud) [invariant]"
say "   mt0.3     : 0.250/-191  -> ~-150..-160 (+30 transféré)"
say "   mt1.0     : 0.300/-147  -> ~-110..-120 (gain croît avec t)"
say "   NPS-comp  : 0.292/-154  -> légère amélioration ; RÉSIDU = éval-marge propre"
say "   survie    : 0.340 (Scan 0.431) -> ~INCHANGÉ (propriété éval, pas search) [invariant, baseline G1]"

# ---- cellules 1-4 : calibrate_vs_scan en PARALLELE (mono-process/cellule, pas d'oversubscription) ----
run_cell(){ local tag="$1" pairs="$2"; shift 2
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/gen1.pjtw" \
    --scan-bb-size 0 "$@" --pairs "$pairs" --openings-file "$W/open.fen" >"$W/cell_$tag.log" 2>&1
}
say ""; say "=== lancement cellules calibrate (parallèle, SEULES => movetime non-biaisé) ==="
run_cell d9    3 --depth 9                          & P1=$!
run_cell mt03  3 --movetime 0.3                     & P2=$!
run_cell mt10  2 --movetime 1.0                     & P3=$!
run_cell nps   2 --jass-movetime 0.6 --scan-movetime 0.3 & P4=$!
wait $P1 $P2 $P3 $P4
say ""; say "=== RÉSULTATS calibrate (rate / Elo, gen1 vs Scan) ==="
for tag in d9 mt03 mt10 nps; do
  rate=$(grep -iE 'Jass score rate' "$W/cell_$tag.log" | grep -oE '[0-9]*\.[0-9]+' | head -1)
  elo=$(grep -iE 'ELO estimate' "$W/cell_$tag.log" | grep -oE '[-+]?[0-9]+' | head -1)
  say "  $tag : rate=${rate:-NA} elo=${elo:-NA}"
done

# ---- cellule 5 : survie-1er-choix jass (d1 vs d11), APRES calibrate (pas de contention) ----
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }
python3 - "$W/corpus.jnnw" "$W/sfens.tsv" 800 <<'PY'
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
bands={0:(0,12),1:(13,20),2:(21,28),3:(29,40)}; byb=collections.defaultdict(list); per=K//4; step=max(1,n//(K*6))
for i in range(0,n,step):
    r=body[i*REC:(i+1)*REC]; p=pc(r)
    for bi,(lo,hi) in bands.items():
        if lo<=p<=hi and len(byb[bi])<per:
            wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); byb[bi].append((bi,fen(wm,wk,bm,bk,r[32]))); break
rows=[]
for bi in range(4): rows+=byb[bi]
open(sys.argv[2],'w').write("\n".join(f"{b}\t{f}" for b,f in rows)+"\n")
print(f"  survie sample : {len(rows)}")
PY
cat > "$W/surv.py" <<'PY'
import sys; sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine
jbin,gen1,shard,nsh,outp,fensf=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),sys.argv[5],sys.argv[6]
rows=[l.rstrip("\n").split("\t") for l in open(fensf) if l.strip()][shard::nsh]
def mv(m): return f"{m.frm}-{m.to}" if m else "NA"
J=JassEngine(jbin, pattern_path=gen1); o=open(outp,"w")
for band,fen in rows:
    try:
        J.set_position_fen(fen); d1=mv(J.go(depth=1)); d11=mv(J.go(depth=11))
    except Exception: d1=d11="NA"
    o.write(f"{band}\t{d1}\t{d11}\n"); o.flush()
o.close()
try: J.close()
except Exception: pass
PY
say ""; say "=== cellule survie (jass d1 vs d11, après calibrate) ==="
SURV_SH=8
for s in $(seq 0 $((SURV_SH-1))); do python3 "$W/surv.py" "$J" "$W/gen1.pjtw" "$s" "$SURV_SH" "$W/surv.$s" "$W/sfens.tsv" >"$W/surv_$s.log" 2>&1 & done
wait
cat "$W"/surv.* > "$W/surv.all" 2>/dev/null
python3 - "$W/surv.all" <<'PY' 2>&1 | tee -a "$RES"
import sys,collections
rows=[l.rstrip("\n").split("\t") for l in open(sys.argv[1]) if l.strip()]
BN={0:'finale<=12',1:'milieu13-20',2:'milieu21-28',3:'ouverture>=29'}
def surv(sel):
    s=[r for r in sel if r[1]!="NA" and r[2]!="NA"];
    if not s: return (0,0)
    return (sum(1 for r in s if r[1]==r[2])/len(s), len(s))
g=surv(rows)
print(f"  SURVIE-1er-choix (jass d1==d11) GLOBAL={g[0]:.3f} (n={g[1]}) ; baseline 0597=0.340, Scan=0.431")
for bi in range(4):
    b=surv([r for r in rows if r and int(r[0])==bi]); print(f"    {BN[bi]:14s} {b[0]:.3f} (n={b[1]})")
PY
say ""
say "  LECTURE : d9 & survie ~INCHANGÉS = invariants OK ; movetime ~-110..-160 = +30 transféré (référence re-ancrée)."
say "  Si d9 ou survie BOUGENT sans fit => quelque chose d'incompris => STOP avant rank-loss, investiguer."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0605 re-ancrage vs Scan (main frais +187 search) : 5 cellules + predictions pre-engagees + baseline G1" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin re-ancrage ==="
