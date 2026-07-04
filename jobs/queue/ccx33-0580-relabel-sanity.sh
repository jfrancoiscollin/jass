#!/usr/bin/env bash
# id: ccx33-0580-relabel-sanity
# description: SONDE-GATE du levier DEEP-RELABEL (JFC "penchons-nous dessus"). Hypothese : nos labels WDL self-play sont
# SYSTEMATIQUEMENT FAUX sur les positions tactiques (on convertit 23% de nos combos gagnants => une position gagnante
# recoit label "pas gagnant"). Fix autonome (pas de Scan) : re-labelliser par la recherche PROFONDE de jass, elagage-off
# (probcut/multicut/razor=0) pour exposer les shots + qs_sacs bake qui voit les sacs. Les combos etant FORCES, la
# profondeur les trouve quelle que soit la qualite de l'eval => casse la circularite. GATE cheap : deep-relabel les
# combos dilf (ou le trait GAGNE par construction) et mesurer la fraction que jass marque GAGNANTE. self-play=23% ;
# si deep-relabel >> 23% => le mecanisme corrige le biais => on fait le vrai run relabel-fit-judge. Sinon inutile.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0580-relabel-sanity/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0580-relabel-sanity/artefacts"
W=/root/cw-relabelsan; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
SUITE_SRC="jobs/results/cpx62-0534-combo-gen-balanced/artefacts/combos_balanced.fen"
DEPTH=14; SPARAMS="probcut_min_depth=0,multicut_min_depth=0,razor_max_depth=0"; DRAWBAND=50
VERD="$ART/VERDICT.txt"; : > "$VERD"; say(){ echo "$@" | tee -a "$VERD"; }

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== SONDE deep-relabel combos (d$DEPTH, elagage-off, qs_sacs bake) — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$SUITE_SRC" > "$W/suite.fen" 2>/dev/null || { say "ABORT suite"; exit 4; }

# combos_balanced.fen -> JNNW (le trait GAGNE par construction ; on garde la position telle quelle)
python3 - "$W/suite.fen" "$W/combos.jnnw" <<'PY'
import sys,struct
sys.path.insert(0,'tools'); from pdn_to_jnnw import fen_to_bitboards,_REC_STRUCT
recs=bytearray(); n=0
for ln in open(sys.argv[1]):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    try: stm,wm,wk,bm,bk=fen_to_bitboards(b)
    except Exception: continue
    recs+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); n+=1
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',n)+bytes(recs))
print(f"  combos -> JNNW : {n} positions")
PY
NC=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/combos.jnnw','rb').read(8)[4:8])[0])")
say "  suite : $NC combos (trait=gagnant par construction) ; eval=gen1"

# split en NCPU shards (deep-relabel n'a pas --start/--count), relabel //, merge (ordre preserve)
python3 - "$W/combos.jnnw" "$W/sh" "$NCPU" <<'PY'
import sys,struct
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]; nsh=int(sys.argv[3])
per=(n+nsh-1)//nsh
for s in range(nsh):
    lo=s*per; hi=min((s+1)*per,n)
    if lo>=hi:
        open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',0)); continue
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',hi-lo)+body[lo*REC:hi*REC])
PY
say "=== deep-relabel // ($NCPU shards) ==="
for s in $(seq 0 $((NCPU-1))); do
  "$J" --deep-relabel "$W/sh.$s.jnnw" "$W/out.$s.jnnw" "$DEPTH" --nnue "$W/gen1.pjtw" \
      --search-params "$SPARAMS" --draw-band "$DRAWBAND" >"$W/rl.$s.log" 2>&1 &
done; wait

# analyse : fraction des combos que le deep-relabel marque GAGNANTS pour le trait (STM-score > draw_band)
python3 - "$W/out" "$NCPU" "$DRAWBAND" "$W/combos.jnnw" 2>&1 | tee -a "$VERD" <<'PY'
import sys,struct,glob
pre,nsh,band=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]); REC=38
win=draw=loss=tot=0; scores=[]
for s in range(nsh):
    try: b=open(f"{pre}.{s}.jnnw",'rb').read()
    except: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
    for i in range(n):
        sc=struct.unpack('<i',body[i*REC+33:i*REC+37])[0]  # STM-POV cp (deep-relabel l'a reecrit)
        scores.append(sc); tot+=1
        if sc>band: win+=1
        elif sc<-band: loss+=1
        else: draw+=1
if not tot: print("  AUCUNE SORTIE (deep-relabel a echoue)"); raise SystemExit
scores.sort()
print(f"=== VERDICT : deep-relabel de {tot} combos (trait=gagnant par construction) ===")
print(f"  marques GAGNANTS (STM-score>{band})  : {win}/{tot} = {win/tot:.3f}")
print(f"  marques nuls                         : {draw}/{tot} = {draw/tot:.3f}")
print(f"  marques PERDANTS (faux)              : {loss}/{tot} = {loss/tot:.3f}")
print(f"  score STM median = {scores[tot//2]} cp")
print("")
print(f"  RAPPEL : notre self-play convertit ~23% de ces combos (offense d9, dumps 0571).")
r=win/tot
if r>=0.60: print(f"  => deep-relabel recupere {r:.0%} (>> 23%) : le mecanisme CORRIGE le biais tactique. GO le vrai run (relabel-fit-judge).")
elif r>=0.40: print(f"  => deep-relabel recupere {r:.0%} (> 23% mais modere) : correction partielle. Vrai run justifie, gain a mesurer.")
else: print(f"  => deep-relabel {r:.0%} ~ self-play : la profondeur ne recupere pas les combos => approche a revoir (depth/params).")
PY
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0580 sonde deep-relabel : fraction combos recuperes vs self-play 23%" \
  && say "  VERDICT committe ✓" || say "  ⚠ commit echoue"
say "=== fin sonde relabel ==="
