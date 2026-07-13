#!/usr/bin/env bash
# id: ccx33-0698-b4-tb-exceptions-fit
# description: B4 — CONTINGENT EXCEPTIONS-TB (mémo BOOST, go JFC "B4" 2026-07-13, sizing 200k + cellule finale validés).
# Le corpus C4 (700 185 exceptions TB, 99,6% nulle-malgré-avantage ≥2) = connaissance matériel-défiante EXACTE, ciblant
# le pire segment de gen2-mmto (survie finale −0.184, oracle-gap +0.038). PRÉALABLES GRAVÉS : (a) ÉQUILIBRAGE — la
# distribution est dégénérée, on mélange ~50/50 avec des positions TB NORMALES (gen fraîche --gen-egdb-wld, WDL exact) ;
# (b) DÉDUP bitboard croisée (exceptions ⊥ normales). Contingent ~200k (100k exc sous-échant. + 100k normales). FIT =
# wdl_finetune --anchor 0.05 ANCRÉ gen2-mmto (recette B1, gradient streamé). GATE COMPLET : A/B généraliste ≥38p
# mt0.2+0.3 vs gen2-mmto + CELLULE FINALE dédiée (openings ≤10 pièces = le segment ciblé). Attente : petit gain finale
# OU neutre — vérité pure, risque faible avec l'anchor. Build JASS_EGDB=ON. Robustesse 12-pts (df, timeout/shard, RES
# hors-arbre, pull src divergents develop, garde-fou archi). AUCUN NNUE. gen2-mmto reste champion (candidat committé).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0698-b4-tb-exceptions-fit/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0698-b4-tb-exceptions-fit/artefacts"
W=/root/cw-b4tb
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-b4tb
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go ($DFA)"; exit 3; }
EXC_GZ=jobs/results/ccx33-0693-tb-exceptions-mine/artefacts/exceptions.jnnw
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EXC_N=100000; NORM_GEN=150000; NORM_N=100000; MAXP=7; CACHE=2048; SEED=6980
ANCHOR=0.05; CHUNK=1000000; MAXIT=25
NOPEN=96; PAIRS=8; SHARD_TIMEOUT=2400; MIN_N=600

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }

say "=== B4 contingent exceptions-TB — HEAD main $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
# --- consistance src (pull divergents develop) + garde-fou archi + egdb ---
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
restore_src(){ git checkout -- src pattern_jass/src tools/jass_vs_jass_arch.py pattern_jass/tools/train_stream.py pattern_jass/tools/wdl_finetune.py 2>/dev/null||true; }
grep -q "g_emasks" src/scan_eval.cpp && grep -q "has_any_capture" src/search.cpp || { say "ABORT archi"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb introuvable"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0698 ABORT egdb"; exit 4; }
say "  egdb: $EGDIR ; src divergents pull: $(echo $DIVERGED|tr '\n' ' ')"
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" \
  || { say "ABORT egdb build"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0698 ABORT cmake"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0698 ABORT build"; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$EXC_GZ" > "$W/exc.jnnw" || { say "ABORT exceptions"; restore_src; exit 4; }
say "  ✓ build+geom(NP=$NP)+gen2 ; exceptions=$(jnnw_count "$W/exc.jnnw")"

# --- gen normales TB + ÉQUILIBRAGE (dédup bitboard croisée, ~50/50) ---
say ""; say "=== gen normales TB (--gen-egdb-wld $NORM_GEN) + équilibrage ==="
"$J" --gen-egdb-wld "$NORM_GEN" "$W/norm.jnnw" "$EGDIR" "$MAXP" "$CACHE" "$SEED" >"$W/ge.log" 2>&1 \
  || { say "ABORT gen normales"; tail -4 "$W/ge.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0698 ABORT gen"; exit 7; }
python3 - "$W/exc.jnnw" "$W/norm.jnnw" "$W/contingent.jnnw" "$EXC_N" "$NORM_N" "$SEED" <<'PY' | tee -a "$RES"
import struct,sys,random
REC=38
exc,norm,out,exc_n,norm_n,seed=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),int(sys.argv[5]),int(sys.argv[6])
def load(p):
    b=open(p,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; return b[8:8+n*REC],n
eb,en=load(exc); nb,nn=load(norm)
rng=random.Random(seed)
# sous-échantillon exceptions
ei=list(range(en)); rng.shuffle(ei); ei=ei[:min(exc_n,en)]
exc_recs=[eb[i*REC:(i+1)*REC] for i in ei]
exc_keys=set(r[:32] for r in exc_recs)
# normales : dédup interne + exclure celles présentes dans les exceptions (⊥), prendre norm_n
seen=set(exc_keys); norm_recs=[]
ni=list(range(nn)); rng.shuffle(ni)
for i in ni:
    r=nb[i*REC:(i+1)*REC]; k=r[:32]
    if k in seen: continue
    seen.add(k); norm_recs.append(r)
    if len(norm_recs)>=norm_n: break
allr=exc_recs+norm_recs; rng.shuffle(allr)
open(out,'wb').write(b'JNNW'+struct.pack('<I',len(allr))+b''.join(allr))
print(f"  contingent : exc={len(exc_recs)} + norm={len(norm_recs)} = {len(allr)} (dédup ⊥ ok)")
PY
NC=$(jnnw_count "$W/contingent.jnnw"); [ "$NC" -gt 50000 ] 2>/dev/null || { say "ABORT contingent < 50k"; restore_src; exit 7; }
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0698 contingent équilibré prêt ($NC)" >/dev/null 2>&1 || true

# --- fit wdl_finetune ancré gen2-mmto (recette B1) ---
say ""; say "=== fit wdl_finetune ancré gen2-mmto anchor=$ANCHOR sur contingent ($NC) ==="
"$J" --dump-eval-features "$W/contingent.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "DUMP FAIL"; tail -4 "$W/feat.log"|sed 's/^/  /'; restore_src; exit 8; }
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/gen2.pjtw" --data "$W/contingent.jnnw" --feat "$W/feat" --out "$W/candB4.pjtw" \
    --tools pattern_jass/tools --anchor "$ANCHOR" --logit-scale 1.0 --chunk "$CHUNK" --max-iter "$MAXIT" \
    --full-fold --tempo-stage --verify-jass "$J" --verify-n 60 >"$W/fit.log" 2>&1
[ -s "$W/candB4.pjtw" ] || { say "FIT FAIL : $(tail -4 "$W/fit.log"|tr '\n' ' ')"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0698 ABORT fit"; exit 8; }
say "  ✓ fit : $(grep -iE 'logloss|verify|mean' "$W/fit.log"|tr '\n' ' ')"
gzip -c "$W/candB4.pjtw" > "$ART/candB4.pjtw.gz"; commit_to_main "$ART/candB4.pjtw.gz" "$ARTREL/candB4.pjtw.gz" "0698 candidat B4" >/dev/null 2>&1 || true
restore_src

# --- openings : généraliste (≥38p corpus) + FINALE (≤10p depuis normales egdb) ---
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw"
python3 - "$W/corpus.jnnw" "$W/norm.jnnw" "$W/gen.fen" "$W/fin.fen" "$NOPEN" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
REC=38
def fen(wm,wk,bm,bk,stm):
    W=[str(s) for s in range(1,51) if (wm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (wk>>(s-1))&1]
    B=[str(s) for s in range(1,51) if (bm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (bk>>(s-1))&1]
    return f"{'B' if stm==1 else 'W'}:W{','.join(W)}:B{','.join(B)}"
def pc(x):
    c=0
    while x: x&=x-1; c+=1
    return c
K=int(sys.argv[5])
# généraliste ≥38p depuis corpus
d=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; body=d[8:]
gen=[]; step=max(1,n//(K*40))
for i in range(0,n,step):
    r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
    if pc(wm)+pc(wk)+pc(bm)+pc(bk)>=38: gen.append(fen(wm,wk,bm,bk,stm))
    if len(gen)>=K: break
open(sys.argv[3],'w').write("\n".join(gen)+"\n"); print(f"  généraliste openings ≥38p : {len(gen)}")
# FINALE ≤10p depuis normales egdb (le segment ciblé)
d=open(sys.argv[2],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; body=d[8:]
fin=[]
for i in range(n):
    r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
    if pc(wm)+pc(wk)+pc(bm)+pc(bk)<=10: fin.append(fen(wm,wk,bm,bk,stm))
    if len(fin)>=K: break
open(sys.argv[4],'w').write("\n".join(fin)+"\n"); print(f"  finale openings ≤10p : {len(fin)}")
PY
NG=$(grep -c . "$W/gen.fen"); NF=$(grep -c . "$W/fin.fen")
[ "$NG" -gt 10 ] 2>/dev/null && [ "$NF" -gt 10 ] 2>/dev/null || { say "ABORT openings (gen=$NG fin=$NF)"; exit 7; }

# --- GATE : candB4 vs gen2-mmto (généraliste mt0.2+0.3 + finale mt0.2) ---
abcell(){ local openf="$1" tag="$2" mt="$3"; local pref="$W/x_${tag}_${mt}"; rm -f "${pref}".*; local pids=()
  for s in $(seq 0 $((NCPU-1))); do timeout "$SHARD_TIMEOUT" python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/candB4.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" \
    --movetime "$mt" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$openf" >"${pref}.$s" 2>&1 & pids+=($!); done
  wait "${pids[@]}"
  python3 - "$tag" "$mt" "$W/.cell" "$MIN_N" "${pref}".* <<'PY'
import sys,math
tag,mt,outp,min_n=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); a=d=b=0
for f in sys.argv[5:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b
if g<min_n: open(outp,'w').write(f"  [{tag:12s} mt{mt}] n={g}<{min_n} => INCONCLUANT\n"); sys.exit(0)
r=(a+0.5*d)/g; ex2=(a+0.25*d)/g; v=ex2-r*r; se=math.sqrt(v/g) if v>0 else 0.5/(g**0.5)
elo=-400*math.log10(1/r-1) if 0<r<1 else 0; lo,hi=r-1.96*se,r+1.96*se
vd="candB4 GAGNE hors-IC" if lo>0.5 else ("candB4 PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [{tag:12s} mt{mt}] A={a} B={b} D={d} n={g} rate={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.cell" | tee -a "$RES"; rm -f "${pref}".*; }
say ""; say "=== GATE candB4 vs gen2-mmto : généraliste mt0.2+0.3 + FINALE mt0.2 ==="
abcell "$W/gen.fen" "general" 0.2; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0698 gate general mt0.2" >/dev/null 2>&1 || true
abcell "$W/gen.fen" "general" 0.3
abcell "$W/fin.fen" "FINALE" 0.2
say ""; say "  LECTURE : candB4 GAGNE (surtout FINALE) hors-IC => les exceptions-TB colmatent la finale => baker (go JFC)."
say "  neutre => vérité pure sans coût (anchor) mais pas de gain mesurable ; PERD => écarter (peu probable avec anchor)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0698 FIN B4 : exceptions-TB équilibrées colmatent-elles la finale de gen2-mmto" \
  && say "  ✓ RESULTS committé" || say "  ⚠ commit échoue"
say "=== 0698 B4 FINI ==="
