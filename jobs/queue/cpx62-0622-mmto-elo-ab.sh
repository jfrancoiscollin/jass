#!/usr/bin/env bash
# id: cpx62-0622-mmto-elo-ab
# description: A/B Elo confirmatoire du candidat MMTO v2 (POV fixé, 0621) vs champion gen1. Contexte : le pré-fit
# pairwise-acc à travers la recherche était DÉJÀ 0.686 (le search classe déjà les coups maîtres), le fit n'a bougé que
# +0.0014 -> candidat ≈ champion -> Elo neutre attendu. Ce job CLÔT la piste MMTO avec la VRAIE métrique (cohérent avec
# la discipline Elo-juge). Même binaire + search-params bakés, seule l'éval diffère ; dilf+généraliste mt0.2 ; harnais
# robuste 0619 (cellules séquentielles, verdict par cellule). GATE : MMTO bat gen1 hors-IC (là où statique=−847) => la
# méthode-à-travers-recherche débloque un reste de marge => boucle externe. Neutre => marge close (search capte déjà tout).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0622-mmto-elo-ab/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0622-mmto-elo-ab/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-mmtoab; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CAND_GZ=jobs/results/ccx33-0621-mmto-maitres-v2-povfix/artefacts/mmto2_0.1.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DILF=data/dilf_combinations.fen
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
NOPEN=48; PAIRS=8; MT=0.2

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== A/B Elo MMTO vs gen1 — HEAD main $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$CAND_GZ" | gunzip > "$W/mmto.pjtw" || { say "ABORT candidat MMTO (0621)"; exit 4; }
head -n "$NOPEN" "$DILF" > "$W/dilf.fen"
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }
python3 - "$W/corpus.jnnw" "$W/gen.fen" "$NOPEN" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
d=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]; K=int(sys.argv[3])
def fen(wm,wk,bm,bk,stm):
    Wl=[];Bl=[]
    for sq in range(1,51):
        b=1<<(sq-1)
        if wm&b:Wl.append(str(sq))
        elif wk&b:Wl.append("K"+str(sq))
        elif bm&b:Bl.append(str(sq))
        elif bk&b:Bl.append("K"+str(sq))
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
out=[]; step=max(1,n//(K*40))
for i in range(0,n,step):
    r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if pc>=38: out.append(fen(wm,wk,bm,bk,stm))
    if len(out)>=K: break
open(sys.argv[2],'w').write("\n".join(out)+"\n"); print(f"  generaliste : {len(out)} openings")
PY
say "  build OK ; openings dilf=$(wc -l<"$W/dilf.fen") gen=$(wc -l<"$W/gen.fen") ; ~$((NOPEN*PAIRS*2)) games/cellule ; mt=$MT"

cell(){ local oset="$1" openf="$2"; local pref="$W/x_${oset}"
  rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/mmto.pjtw" --jass-b "$J" --pattern-b "$W/gen1.pjtw" \
    --movetime "$MT" --pairs "$PAIRS" --max-plies 160 \
    --shard "$s" --nshards "$NCPU" --quiet --openings-file "$openf" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$oset" "$W/.cellout" "${pref}".* <<'PY'
import sys,math
st,outp=sys.argv[1],sys.argv[2]; a=d=b=0
for f in sys.argv[3:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [MMTO vs gen1 | {st}] A(mmto)={a} B(gen1)={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.cellout" | tee -a "$RES"; rm -f "${pref}".*
}
say ""; say "=== A/B Elo MMTO(anchor0.1) vs gen1 (mt$MT) ==="
cell dilf "$W/dilf.fen"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0622 A/B Elo MMTO vs gen1 (dilf fait)" >/dev/null 2>&1 || true
cell gen  "$W/gen.fen"
say ""
say "  GATE : MMTO rate_A>0.5 hors-IC (là où statique=−847) => la recherche débloque un reste de marge => boucle externe 0623."
say "  neutre => piste MMTO close : le search capte déjà l'ordre maître (pré-fit 0.686), pas de marge à récupérer."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0622 A/B Elo MMTO v2 vs gen1 (verdict : marge exploitable ou close)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin A/B MMTO ==="
