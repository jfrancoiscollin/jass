#!/usr/bin/env bash
# id: cpx62-0613-rank-anchor-sweep
# description: PISTE (a) — JUGE DE PAIX G1. Fine-tune rank-loss (bras S, corpus baked 0604) ancré au champion gen1, puis
# mesure la SURVIE-1er-choix (accord d1↔d11) du candidat vs champion (baseline 0597=0.340, cible ->0.43). rank_finetune.py
# a 3 GATES auto (POV gate X·w0==eval-C++ + grad-check + pairwise-acc avant/après) => si config/pipeline faux, ABORT propre
# avec diagnostic (pas de G1 trompeur). λ=0.3, color-fold+tempo (config champion). Si survie MONTE hors bruit => l'éval-marge
# est apprenable => on scale (G2/G3/G4). Si plate => clause d'échec propre. AUCUN NNUE. NB survie sur echantillon frais
# (recouvrement partiel possible avec les 50k parents d'entrainement — held-out propre = follow-up si G1 prometteur).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0613-rank-anchor-sweep/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0613-rank-anchor-sweep/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-anchsweep; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-rank
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
PAIRS_GZ=jobs/results/ccx33-0604-siblings-corpus-baked/artefacts/siblings-50k-baked.jnnw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
LAM=0.3

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== PISTE (a) G1 — HEAD main $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:pattern_jass/tools/rank_finetune.py > pattern_jass/tools/rank_finetune.py
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; git checkout -- pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 6; }
J="$W/build/jass"
# geometrie 32cf (v4) sur le path d'import
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom $NP!=32"; git checkout -- pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$PAIRS_GZ" | gunzip > "$W/pairs.jnnw" || { say "ABORT pairs (0604)"; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }
NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pairs.jnnw','rb').read(8)[4:8])[0]//2)")
say "  gen1 + pairs($NPAIRS) + corpus prets ; NUM_PATTERNS=$NP"

# ---- dump eval-features des enfants (paires) ----
"$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/dump.log"|sed 's/^/  /'; exit 8; }
say "  dump-eval-features : $(tail -1 "$W/dump.log")"

# ---- SWEEP ANCHOR : fit rank-loss a plusieurs anchors (min-pairs=5 = regularisation) ----
OKA=""
for A in 0.001 0.01 0.1 1.0; do
  say ""; say "=== rank_finetune anchor=$A (min-pairs=5, lam=$LAM) ==="
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
      --champion "$W/gen1.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/cand_$A.pjtw" \
      --tools pattern_jass/tools --lam "$LAM" --anchor "$A" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
      --full-fold --tempo-stage --verify-jass "$J" --verify-n 60 >"$W/ft_$A.log" 2>&1
  if [ $? = 0 ]; then grep -E 'pairwise-acc|buckets|delta' "$W/ft_$A.log" | sed "s/^/  [$A] /" | tee -a "$RES"; OKA="$OKA $A"; \
  else say "  [$A] ABORT (gate) : $(tail -1 "$W/ft_$A.log")"; fi
done
git checkout -- pattern_jass/tools/rank_finetune.py 2>/dev/null || true
[ -n "$OKA" ] || { say "  => tous les fits ont avorté"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0613 anchor sweep abort"; exit 0; }

# ---- G1 : survie-1er-choix candidat vs champion (echantillon frais) ----
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
bands={0:(0,12),1:(13,20),2:(21,28),3:(29,40)}; byb=collections.defaultdict(list); per=K//4
# offset different de 0604 (stride depart decale) pour reduire le recouvrement
step=max(1,n//(K*6)); start=step//2
for i in range(start,n,step):
    r=body[i*REC:(i+1)*REC]; p=pc(r)
    for bi,(lo,hi) in bands.items():
        if lo<=p<=hi and len(byb[bi])<per:
            wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); byb[bi].append((bi,fen(wm,wk,bm,bk,r[32]))); break
rows=[]
for bi in range(4): rows+=byb[bi]
open(sys.argv[2],'w').write("\n".join(f"{b}\t{f}" for b,f in rows)+"\n"); print(f"  survie sample : {len(rows)}")
PY
cat > "$W/surv.py" <<'PY'
import sys; sys.path.insert(0,'tools')
from calibrate_vs_scan import JassEngine
jbin,pat,shard,nsh,outp,fensf=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),sys.argv[5],sys.argv[6]
rows=[l.rstrip("\n").split("\t") for l in open(fensf) if l.strip()][shard::nsh]
def mv(m): return f"{m.frm}-{m.to}" if m else "NA"
J=JassEngine(jbin, pattern_path=pat); o=open(outp,"w")
for band,fen in rows:
    try: J.set_position_fen(fen); d1=mv(J.go(depth=1)); d11=mv(J.go(depth=11))
    except Exception: d1=d11="NA"
    o.write(f"{band}\t{d1}\t{d11}\n"); o.flush()
o.close()
try: J.close()
except Exception: pass
PY
survie(){ local pat="$1" tag="$2"
  for s in $(seq 0 $((NCPU-1))); do python3 "$W/surv.py" "$J" "$pat" "$s" "$NCPU" "$W/${tag}.$s" "$W/sfens.tsv" >"$W/${tag}_$s.log" 2>&1 & done; wait
  cat "$W"/${tag}.[0-9]* > "$W/${tag}.all" 2>/dev/null
  python3 - "$tag" "$W/${tag}.all" <<'PY' 2>&1 | tee -a "$RES"
import sys
tag=sys.argv[1]; rows=[l.rstrip("\n").split("\t") for l in open(sys.argv[2],errors='replace') if l.strip()]
s=[r for r in rows if len(r)==3 and r[1]!="NA" and r[2]!="NA"]
g=sum(1 for r in s if r[1]==r[2])/len(s) if s else 0
print(f"  survie[{tag}] = {g:.4f} (n={len(s)})")
PY
}
say ""; say "=== G1 : survie-1er-choix (d1==d11) champion vs candidats (par anchor) ==="
survie "$W/gen1.pjtw" "champ"
for A in $OKA; do survie "$W/cand_$A.pjtw" "cand_$A"; done
say ""
say "  GATE G1 : survie[cand] > survie[champ] hors bruit (vers 0.43) => éval-marge APPRENABLE => scale (G2/G3/G4)."
say "  survie plate => clause d'échec propre (résidu -133/-161 acté = prix des marges)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0606 G1 juge de paix : survie champion vs candidat rank-loss (piste-a)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin G1 ==="
