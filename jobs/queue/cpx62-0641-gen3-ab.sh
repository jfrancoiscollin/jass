#!/usr/bin/env bash
# id: cpx62-0641-gen3-ab
# description: RE-A/B PROPRE du candidat gen3 (ronde MMTO 2, 0638 : conversion Scan 57k ancré gen2-mmto, fit delta +0.042) vs
# gen2-mmto. 0639 avait sorti n=0 (bug harnais : ouvertures dilf → crash engine + lignes vides). Ici : GÉNÉRALISTE SEUL
# (openings corpus propres, prouvé marcher), arch FIXÉ (filtre vides), per-cellule committé, mt0.2+0.3. GATE : gen3 >0 hors-IC
# => la ronde conversion ancrée gen2-mmto AJOUTE => on itère (gen3 devient champion candidat). AUCUN NNUE. (dilf = à part,
# bug engine sur positions de combinaison à investiguer.)
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0641-gen3-ab/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0641-gen3-ab/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-gen3ab; rm -rf "$W"; mkdir -p "$W"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CAND_GZ=jobs/results/ccx33-0638-mmto-scan-asym-gen2/artefacts/gen3-candidate.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
NOPEN=96; PAIRS=8

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== RE-A/B gen3 vs gen2-mmto (généraliste, arch fixé) — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; exit 4; }
git show "origin/main:$CAND_GZ" | gunzip > "$W/gen3.pjtw" || { say "ABORT gen3"; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }
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
NG=$(grep -c . "$W/gen.fen"); say "  openings généralistes : $NG ; ~$((NG*PAIRS*2)) games/cellule"
[ "$NG" -gt 10 ] 2>/dev/null || { say "ABORT openings vides"; exit 7; }

cell(){ local mt="$1"; local pref="$W/x_${mt}"; rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/gen3.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" \
    --movetime "$mt" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$mt" "$W/.cellout" "${pref}".* <<'PY'
import sys,math
mt,outp=sys.argv[1],sys.argv[2]; a=d=b=0
for f in sys.argv[3:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [gen3 vs gen2-mmto | generaliste mt{mt}] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.cellout" | tee -a "$RES"; rm -f "${pref}".* ; }
say ""; say "=== A/B gen3 vs gen2-mmto (généraliste, mt0.2 + mt0.3) ==="
cell 0.2
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0641 A/B progrès (mt0.2)" >/dev/null 2>&1 || true
cell 0.3
say ""; say "  GATE : gen3 rate_A>0.5 hors-IC => la ronde conversion ancrée gen2-mmto AJOUTE => gen3 candidat champion => itérer/baker."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0641 A/B gen3 vs gen2-mmto (généraliste) : la conversion ajoute-t-elle" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin re-A/B gen3 ==="
