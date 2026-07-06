#!/usr/bin/env bash
# id: cpx62-0619-rank-elo-ab-v2
# description: RE-RUN robuste du juge de paix Elo (0617 a perdu 5/6 cellules — tee -a partagé + snapshots runner
# entrelacés ; seule la cellule contrôle cand_1.0 gen a survécu : rate_A=0.490 n=528 neutre, conforme au contrôle).
# Ici : chaque cellule écrit son verdict dans un log dédié (append explicite Python, pas de tee partagé) + commit
# de progrès après chaque anchor (durable si kill). Fit bras M {0.01,0.1,1.0} sur corpus maîtres 0615, A/B DIRECT
# pattern-a=candidat vs pattern-b=gen1 (MÊME binaire + search-params bakés, seule l'éval diffère), dilf+généraliste
# mt0.2. Candidats archivés (gz) pour réutilisation. GATE : un candidat rate_A>0.5 hors-IC => survie=mauvais proxy,
# rank-loss MARCHE => scale. Tous neutres/négatifs => clause d'échec confirmée par l'Elo => piste rank-loss CLOSE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0619-rank-elo-ab-v2/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0619-rank-elo-ab-v2/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-eloab2; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-eloab2
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
PAIRS_GZ=jobs/results/ccx33-0615-master-prefs-corpus/artefacts/master-prefs.jnnw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DILF=data/dilf_combinations.fen
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
LAM=0.3; NOPEN=48; PAIRS=8; MT=0.2; ANCHORS="0.01 0.1 1.0"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== A/B ELO v2 (juge de paix robuste) — HEAD main $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:pattern_jass/tools/rank_finetune.py > pattern_jass/tools/rank_finetune.py
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; git checkout -- pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom $NP!=32"; git checkout -- pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$PAIRS_GZ" | gunzip > "$W/pairs.jnnw" || { say "ABORT pairs (0615)"; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }
NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pairs.jnnw','rb').read(8)[4:8])[0]//2)")
say "  gen1 + master-pairs($NPAIRS) prets ; NUM_PATTERNS=$NP"

"$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/dump.log"|sed 's/^/  /'; exit 8; }
say "  dump-eval-features : $(tail -1 "$W/dump.log")"

# ---- fits bras M ----
OKA=""
for A in $ANCHORS; do
  say ""; say "=== rank_finetune bras M anchor=$A ==="
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
      --champion "$W/gen1.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/cand_$A.pjtw" \
      --tools pattern_jass/tools --lam "$LAM" --anchor "$A" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
      --full-fold --tempo-stage --verify-jass "$J" --verify-n 60 >"$W/ft_$A.log" 2>&1
  if [ $? = 0 ]; then grep -E 'pairwise-acc|delta' "$W/ft_$A.log" | sed "s/^/  [$A] /" | tee -a "$RES"; OKA="$OKA $A"
    gzip -c "$W/cand_$A.pjtw" > "$ART/cand_$A.pjtw.gz"
    commit_to_main "$ART/cand_$A.pjtw.gz" "$ARTREL/cand_$A.pjtw.gz" "0619 candidat bras M anchor=$A (archive)" >/dev/null 2>&1 || true
  else say "  [$A] ABORT (gate) : $(tail -1 "$W/ft_$A.log")"; fi
done
git checkout -- pattern_jass/tools/rank_finetune.py 2>/dev/null || true
[ -n "$OKA" ] || { say "  => tous les fits ont avorté"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0619 tous fits avortés"; exit 0; }

# ---- openings dilf + généraliste ----
head -n "$NOPEN" "$DILF" > "$W/dilf.fen"
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
say "  openings : dilf=$(wc -l<"$W/dilf.fen") gen=$(wc -l<"$W/gen.fen") ; ~$((NOPEN*PAIRS*2)) games/cellule ; mt=$MT"

# ---- A/B ROBUSTE : cellules SÉQUENTIELLES, chaque verdict écrit en 1 shot puis appendé à RES (aucun writer concurrent) ----
cell(){ local cand="$1" tag="$2" oset="$3" openf="$4"; local pref="$W/x_${tag}_${oset}"
  rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$cand" --jass-b "$J" --pattern-b "$W/gen1.pjtw" \
    --movetime "$MT" --pairs "$PAIRS" --max-plies 160 \
    --shard "$s" --nshards "$NCPU" --quiet --openings-file "$openf" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$tag" "$oset" "$W/.cellout" "${pref}".* <<'PY'
import sys,math
tag,st,outp=sys.argv[1],sys.argv[2],sys.argv[3]; a=d=b=0
for f in sys.argv[4:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [anchor {tag} | {st}] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.cellout" | tee -a "$RES"   # writer unique, séquentiel
  rm -f "${pref}".*
}
say ""; say "=== A/B ELO candidat vs gen1 (mt$MT, dilf + generaliste) — un candidat = 2 cellules ==="
for A in $OKA; do
  cell "$W/cand_$A.pjtw" "$A" dilf "$W/dilf.fen"
  cell "$W/cand_$A.pjtw" "$A" gen  "$W/gen.fen"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0619 A/B Elo progrès (anchor $A fait)" >/dev/null 2>&1 || true
done

say ""
say "  GATE : un candidat rate_A>0.5 hors-IC => la SURVIE était le mauvais proxy, le rank-loss MARCHE => scale (G2/G3/G4)."
say "  tous neutres/négatifs => clause d'échec CONFIRMÉE par l'Elo => piste rank-loss CLOSE (résidu -133/-161 acté = prix des marges)."
say "  (anchor 1.0 ≈ champion = contrôle sanité, doit sortir ~0.500 ; 0617 l'avait donné 0.490 sur gen)"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0619 A/B Elo v2 bras M vs gen1 (juge de paix robuste — verdict complet 6 cellules)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin A/B Elo v2 ==="
