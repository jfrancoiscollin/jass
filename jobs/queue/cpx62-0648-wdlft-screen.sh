#!/usr/bin/env bash
# id: cpx62-0648-wdlft-screen
# description: PISTE 1 SCREEN — fine-tune WDL ANCRÉ gen2-mmto (wdl_finetune) sur les 3M du corpus 0645, sweep anchor
# {0.03, 0.1, 0.3}, puis A/B chaque BASE directement vs gen2-mmto (généraliste ≥38p, mt0.2). Teste si la CALIBRATION WDL
# ancrée du champion AIDE, SANS MMTO (screen rapide/décisif ; le pipeline MMTO-last complet tourne en // sur ccx33-0648).
# Outil validé smoke 0647 (POV 0.999, logloss descend, |Δw| minuscule => ranking préservé). GATE : une base >0.5 hors-IC =>
# calibration WDL ancrée aide => re-MMTO du gagnant en follow-up. AUCUN NNUE. gen2-mmto reste champion.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0648-wdlft-screen/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0648-wdlft-screen/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-wdlft-screen; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-wdlftscr
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
WDL_CPX=jobs/results/cpx62-0645-couplage-genA-cpx62/artefacts/wdl-cpx62.jnnw.gz
WDL_CCX=jobs/results/ccx33-0645-couplage-genA-ccx33/artefacts/wdl-ccx33.jnnw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
ANCHORS="0.03 0.1 0.3"; CHUNK=1000000; MAXIT=25
NOPEN=96; PAIRS=8; ABMT=0.2

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }

say "=== PISTE 1 SCREEN wdl_finetune ancré gen2-mmto — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
restore_src(){ git checkout -- src/main.cpp pattern_jass/tools/train_stream.py pattern_jass/tools/wdl_finetune.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$WDL_CPX" | gunzip > "$W/wdl_cpx.jnnw"; git show "origin/main:$WDL_CCX" | gunzip > "$W/wdl_ccx.jnnw"
python3 - "$W/wdl.jnnw" "$W/wdl_cpx.jnnw" "$W/wdl_ccx.jnnw" <<'PY'
import struct,sys
outp=sys.argv[1]; REC=38; body=bytearray(); tot=0
for f in sys.argv[2:]:
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
N_WDL=$(jnnw_count "$W/wdl.jnnw"); say "  ✓ build+geom(NP=$NP)+gen2 ; WDL corpus mergé = $N_WDL"
[ "$N_WDL" -gt 1000000 ] 2>/dev/null || { say "ABORT WDL < 1M"; restore_src; exit 7; }
"$J" --dump-eval-features "$W/wdl.jnnw" "$W/wdlfeat" >"$W/wdlfeat.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/wdlfeat.log"|sed 's/^/  /'; restore_src; exit 8; }

# ---- fit wdlft bases (sweep anchor) ----
say ""; say "=== fit wdl_finetune ancré gen2-mmto, sweep anchor {$ANCHORS} (chunk $CHUNK, iter $MAXIT) ==="
declare -A BASE
for A in $ANCHORS; do
  tag=$(echo "$A" | tr '.' 'p')
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
      --champion "$W/gen2.pjtw" --data "$W/wdl.jnnw" --feat "$W/wdlfeat" --out "$W/wdlft_$tag.pjtw" \
      --tools pattern_jass/tools --anchor "$A" --logit-scale 1.0 --chunk "$CHUNK" --max-iter "$MAXIT" \
      --full-fold --tempo-stage --verify-jass "$J" --verify-n 60 >"$W/wdlft_$tag.log" 2>&1
  if [ $? = 0 ] && [ -s "$W/wdlft_$tag.pjtw" ]; then
    BASE[$A]="$W/wdlft_$tag.pjtw"
    say "  [anchor=$A] $(grep -iE 'fit : logloss|mean' "$W/wdlft_$tag.log" | tr '\n' ' ')"
    gzip -c "$W/wdlft_$tag.pjtw" > "$ART/wdlft-a$tag.pjtw.gz"
    commit_to_main "$ART/wdlft-a$tag.pjtw.gz" "$ARTREL/wdlft-a$tag.pjtw.gz" "0648 base wdlft anchor=$A" >/dev/null 2>&1 || true
  else say "  [anchor=$A] FIT FAIL : $(tail -3 "$W/wdlft_$tag.log"|tr '\n' ' ')"; fi
done
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0648 bases wdlft fittées (sweep anchor)" >/dev/null 2>&1 || true
[ "${#BASE[@]}" -gt 0 ] || { say "ABORT aucune base"; restore_src; exit 9; }

# ---- openings généralistes ≥38p ----
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw"
python3 - "$W/corpus.jnnw" "$W/gen.fen" "$NOPEN" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
d=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]; K=int(sys.argv[3])
def fen(wm,wk,bm,bk,stm):
    Wl=[str(s) for s in range(1,51) if (wm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (wk>>(s-1))&1]
    Bl=[str(s) for s in range(1,51) if (bm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (bk>>(s-1))&1]
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
out=[]; step=max(1,n//(K*40))
for i in range(0,n,step):
    r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
    if bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')>=38: out.append(fen(wm,wk,bm,bk,stm))
    if len(out)>=K: break
open(sys.argv[2],'w').write("\n".join(out)+"\n"); print(f"  generaliste : {len(out)} openings")
PY
NG=$(grep -c . "$W/gen.fen"); say "  openings généralistes ≥38p : $NG"
[ "$NG" -gt 10 ] 2>/dev/null || { say "ABORT openings"; restore_src; exit 10; }

# ---- A/B chaque base vs gen2-mmto (généraliste mt$ABMT) ----
say ""; say "=== A/B bases wdlft vs gen2-mmto (généraliste mt$ABMT) ==="
abcell(){ local cand="$1" tag="$2"; local pref="$W/ab_$tag"; rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$cand" --jass-b "$J" --pattern-b "$W/gen2.pjtw" \
    --movetime "$ABMT" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$tag" "$W/.about" "${pref}".* <<'PY'
import sys,math
tag,outp=sys.argv[1],sys.argv[2]; a=d=b=0
for f in sys.argv[3:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [base wdlft anchor {tag} vs gen2-mmto | generaliste mt] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.about" | tee -a "$RES"; rm -f "${pref}".* ; }
for A in $ANCHORS; do
  tag=$(echo "$A" | tr '.' 'p'); [ -n "${BASE[$A]:-}" ] || continue
  abcell "${BASE[$A]}" "$tag"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0648 A/B base wdlft anchor=$A vs gen2-mmto (mt$ABMT)" >/dev/null 2>&1 || true
done
restore_src
say ""; say "  GATE : une base wdlft rate_A>0.5 hors-IC => la calibration WDL ancrée gen2-mmto AIDE (sans MMTO)."
say "  => re-MMTO du meilleur anchor (MMTO last) + confirm mt0.3+dilf + d9-vs-Scan puis bake. (ccx33-0648 fait déjà le full anchor=0.1.)"
say "  => neutre/négatif partout => la calibration WDL n'ajoute pas ; piste 1 morte, conclure sur le linéaire."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0648 FIN screen piste 1 : la calibration WDL ancrée aide-t-elle" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin screen piste 1 ==="
