#!/usr/bin/env bash
# id: cpx62-0635-mmto-bakegate-d9scan
# description: GATE DE BAKE du candidat MMTO +52 (boucle externe 0632 cand_it3). Test décisif (idée JFC) : d9-vs-Scan — la
# cellule ÉVAL-PURE restée figée à −310/−335 à travers +187 de search. Si le candidat la BOUGE => preuve que l'éval-PAR-NŒUD
# elle-même a progressé (pas juste style/interaction-search). On mesure gen1 (baseline) ET cand_it3 : d9-vs-Scan + mt0.3-vs-Scan
# + SURVIE (d1==d11, diagnostic depth-stability : devrait BAISSER si l'hypothèse tient — prédiction falsifiable). GATE bake :
# cand_it3 d9-Elo > gen1 (−310) hors-bruit ET pas de régression => l'éval a vraiment progressé => BAKE le 1er gain-éval. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0635-mmto-bakegate-d9scan/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0635-mmto-bakegate-d9scan/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-bakegate; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CAND_GZ=jobs/results/cpx62-0632-mmto-external-loop/artefacts/cand_it3.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DILF=data/dilf_combinations.fen
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
NOPEN=80; DPAIRS=8

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  SRC=/root/jass-scan-src; [ -d "$SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SRC" >"$W/sc.log" 2>&1
  mkdir -p /root/jass-scan; cp "$SRC/scan_linux" "$SCAN_BIN" 2>/dev/null && chmod +x "$SCAN_BIN"
  cp -r "$SRC/data" /root/jass-scan/data 2>/dev/null||true; cp "$SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null||true
fi
[ -x "$SCAN_BIN" ] || { say "ABORT Scan absent"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0634 ABORT Scan"; exit 3; }

say "=== GATE DE BAKE MMTO cand_it3 (+52) — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$CAND_GZ" | gunzip > "$W/cand.pjtw" || { say "ABORT cand"; exit 4; }
head -n "$NOPEN" "$DILF" > "$W/open.fen"
say "  ✓ build + gen1 + cand_it3 ; référence gen1 d9-vs-Scan = −310/−335 (0605), survie=0.340 (0597)"

# ---- d9 + mt0.3 vs Scan pour CHAQUE pattern (4 cellules // ) ----
run_cell(){ local tag="$1" pat="$2" pairs="$3"; shift 3
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$pat" \
    --scan-bb-size 0 "$@" --pairs "$pairs" --openings-file "$W/open.fen" >"$W/cell_$tag.log" 2>&1
}
say ""; say "=== cellules vs Scan (gen1 baseline vs cand_it3) ==="
run_cell d9_gen1   "$W/gen1.pjtw" "$DPAIRS" --depth 9      & P1=$!
run_cell d9_cand   "$W/cand.pjtw" "$DPAIRS" --depth 9      & P2=$!
run_cell mt03_gen1 "$W/gen1.pjtw" 3 --movetime 0.3        & P3=$!
run_cell mt03_cand "$W/cand.pjtw" 3 --movetime 0.3        & P4=$!
wait $P1 $P2 $P3 $P4
getres(){ local tag="$1"; local rate elo
  rate=$(grep -iE 'Jass score rate' "$W/cell_$tag.log" | grep -oE '[0-9]*\.[0-9]+' | head -1)
  elo=$(grep -iE 'ELO estimate' "$W/cell_$tag.log" | grep -oE '[-+]?[0-9]+' | head -1)
  echo "${rate:-NA}/${elo:-NA}"; }
D9G=$(getres d9_gen1); D9C=$(getres d9_cand); M3G=$(getres mt03_gen1); M3C=$(getres mt03_cand)
say ""
say "  === vs SCAN (rate/Elo) — la cellule d9 est l'ÉVAL-PURE ==="
say "   d9    : gen1=$D9G   cand_it3=$D9C   (gen1 réf ≈ −310/−335)"
say "   mt0.3 : gen1=$M3G   cand_it3=$M3C   (gen1 réf ≈ −161)"

# ---- survie d1==d11 pour chaque pattern ----
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
  for s in $(seq 0 $((NCPU-1))); do python3 "$W/surv.py" "$J" "$pat" "$s" "$NCPU" "$W/sv_${tag}.$s" "$W/sfens.tsv" >"$W/sv_${tag}_$s.log" 2>&1 & done; wait
  cat "$W"/sv_${tag}.[0-9]* > "$W/sv_${tag}.all" 2>/dev/null
  python3 - "$tag" "$W/sv_${tag}.all" <<'PY' 2>&1 | tee -a "$RES"
import sys
tag=sys.argv[1]; rows=[l.rstrip("\n").split("\t") for l in open(sys.argv[2],errors='replace') if l.strip()]
s=[r for r in rows if len(r)==3 and r[1]!="NA" and r[2]!="NA"]
g=sum(1 for r in s if r[1]==r[2])/len(s) if s else 0
print(f"  survie[{tag}] = {g:.4f} (n={len(s)})")
PY
}
say ""; say "=== SURVIE (d1==d11 ; diagnostic depth-stability ; baseline gen1=0.340) ==="
survie "$W/gen1.pjtw" "gen1"
survie "$W/cand.pjtw" "cand_it3"

say ""
say "  === GATE DE BAKE ==="
say "  (1) d9-vs-Scan : cand_it3 Elo > gen1 (−310) hors-bruit => l'ÉVAL-PAR-NŒUD a progressé (pas juste style) => feu vert éval."
say "  (2) mt0.3-vs-Scan : cand_it3 doit être ≥ gen1 (le +52 généraliste doit transférer vs Scan)."
say "  (3) survie : devrait BAISSER (vs 0.340) si l'hypothèse depth-stability est juste — diagnostic, pas bloquant."
say "  Si (1)+(2) OK + A/B broad sans régression (0632: généraliste +52, dilf neutre) => BAKE cand_it3 comme nouvelle éval champion."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0634 gate de bake MMTO cand_it3 : d9-vs-Scan (eval-pure) + mt0.3 + survie" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin gate de bake ==="
