#!/usr/bin/env bash
# id: cpx62-0669-scratch-tour0-durci
# description: TOUR-0 FROM-SCRATCH DURCI (re-size de 0665 hung 2h11). Fix RACINE du hang : sous eval plate (zero.pjtw)
# l'elagage alpha-beta s'effondre + gen-data ne passe pas de movetime => une recherche a prof fixe explosait des heures.
# Le binaire develop a maintenant un CAP-NOEUDS deterministe (--play-max-nodes) => chaque recherche revient bornee, vite.
# Durcissements check-list : (5) timeout PAR SHARD (ceinture-bretelles), (6) calibre, (7) monitor /10min, (10) gate n=0=ABORT,
# (11) arch_assert avant cmake. Params from-scratch inchanges : qs pleine, adjud-material 2/10, eps30/decay30 + drop-post-eps,
# quiet-only, symetrique, fit WDL streame --chunk, gate eval(1) vs zero d9 (ZERO Scan). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0669-scratch-tour0-durci/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0669-scratch-tour0-durci/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
PROG="$ART/PROGRESS.txt"; : > "$PROG"
W=/root/cw-scratch-t0d; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-scratch
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz   # UNIQUEMENT pour copier le HEADER v3 (pas les poids)
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
CORPUS_GZ="$SEEDS_GZ"
QS="qs_forcing_depth=6,qs_promo_depth=6"
PLAYD=10; EVALD=10; MAXPLIES=200; EPS=30; DECAY=30; ADJM=2; ADJH=10; ROPEN=8; SEEDFRAC=50; MINP=32
CAP=60000        # --play-max-nodes : borne DETERMINISTE de chaque recherche play+label (fix hang eval-plate)
PERG=4000        # positions KEPT/shard (×NCPU ≈ 128k, leger)
SHTIMEOUT=3600   # timeout PAR SHARD (s) : ~2× le temps shard sain estime (~30min sandbox) => marge si cpx62 plus lent
                 # (leçon 0659 : timeout trop court sur box lente = shards culés a n=0). Le cap-noeuds empeche deja le hang.
L2=3e-5; MAXIT=25; CHUNK=1000000
NOPEN=96; PAIRS=8; NMIN_GATE=200   # plancher parties gate : n<NMIN_GATE => ABORT (pas "neutre")

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
merge_jnnw(){ python3 - "$1" "$2" <<'PY'
import struct,glob,sys,re
outp,pref=sys.argv[1],sys.argv[2]; REC=38; body=bytearray(); tot=0
for f in sorted(glob.glob(pref+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
}
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }

# ⭐ moniteur de progression : committe PROGRESS.txt toutes les ~10 min
START=$(date +%s)
monitor_loop(){ local phase="$1"
  while [ ! -f "$W/.stopmon" ]; do
    sleep 600; [ -f "$W/.stopmon" ] && break
    local el=$(( ($(date +%s)-START)/60 ))
    local by=0; for f in "$W"/wdl.*; do [ -f "$f" ] && by=$((by+$(stat -c%s "$f" 2>/dev/null||echo 0))); done
    local approx=$((by/38)); local done_sh=$(ls "$W"/wdl.* 2>/dev/null | wc -l)
    local last=$(tail -1 "$W/sp-0.log" 2>/dev/null | tr -d '\n' | cut -c1-70)
    printf '[+%dmin] %s : %d/%d shards ecrits, ~%d pos, sp-0: %s\n' "$el" "$phase" "$done_sh" "$NCPU" "$approx" "$last" >> "$PROG"
    commit_to_main "$PROG" "$ARTREL/PROGRESS.txt" "0666 progress +${el}min (${done_sh}/${NCPU} shards, ~${approx} pos)" >/dev/null 2>&1 || true
  done
}

say "=== TOUR-0 DURCI (cap-noeuds $CAP + timeout/shard $SHTIMEOUT) — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:src/scan_eval.cpp > src/scan_eval.cpp
git show origin/develop:src/scan_eval.hpp > src/scan_eval.hpp
git show origin/develop:src/search.cpp > src/search.cpp; git show origin/develop:src/search.hpp > src/search.hpp
git show origin/develop:src/movegen.cpp > src/movegen.cpp; git show origin/develop:src/movegen.hpp > src/movegen.hpp
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py tools/calibrate_vs_scan.py 2>/dev/null||true; }
# ---- GARDE-FOU ARCHI (check-list point 11) : opts + cap-noeuds presents AVANT cmake ----
arch_assert(){
  grep -q "g_emasks"        src/scan_eval.cpp || { say "ABORT archi: scan_eval SANS opts NPS (g_emasks)"; restore_src; exit 5; }
  grep -q "has_any_capture" src/search.cpp    || { say "ABORT archi: search SANS has_any_capture"; restore_src; exit 5; }
  grep -q "has_any_capture" src/movegen.cpp   || { say "ABORT archi: movegen SANS has_any_capture"; restore_src; exit 5; }
  grep -q "max_nodes"       src/search.hpp    || { say "ABORT archi: SearchLimits SANS max_nodes (cap-noeuds absent)"; restore_src; exit 5; }
  grep -q "play-max-nodes"  src/main.cpp      || { say "ABORT archi: gen-data SANS --play-max-nodes"; restore_src; exit 5; }
  say "  garde-fou archi ✓ : g_emasks + has_any_capture + max_nodes + --play-max-nodes"; }
arch_assert
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0666 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"

# ---- eval ZERO : header v3 de gen2 + corps tout-a-0 ----
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2 header"; restore_src; exit 4; }
python3 - "$W/gen2.pjtw" "$W/zero.pjtw" <<'PY'
import struct,sys
hdr=open(sys.argv[1],'rb').read(20); m,v,sc,npat,next_=struct.unpack('<IIIII',hdr)
tot=2*(npat+next_)
open(sys.argv[2],'wb').write(hdr+b'\x00'*(tot*4))
print(f"zero.pjtw : n_pat={npat} n_ext={next_} scale={sc} bytes={20+tot*4}")
PY
say "  zero.pjtw eval start = $("$J" --eval-position "$W/zero.pjtw" "W:W31-50:B1-20" 2>&1|head -1) (doit être ~0)"
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
say "  ✓ build+geom(NP=$NP)+zero.pjtw ; seeds=$(jnnw_count "$W/seeds.jnnw")"

# ---- self-play eval=0 : cap-noeuds $CAP + timeout/shard + MONITOR ----
say ""; say "=== self-play eval=0 : play d$PLAYD, qs pleine, cap-noeuds $CAP, adjud $ADJM/$ADJH, timeout/shard ${SHTIMEOUT}s, ${PERG}×${NCPU} ==="
rm -f "$W/.stopmon"; monitor_loop "self-play" & MONPID=$!
SPPIDS=()   # ⚠ collecter les PID des SHARDS : `wait` NU attendrait AUSSI le monitor (boucle jusqu'a .stopmon pose APRES) = DEADLOCK (bug 0665/0666)
for s in $(seq 0 $((NCPU-1))); do
  timeout "$SHTIMEOUT" "$J" --gen-data-wdl "$PERG" "$W/wdl.$s" "$EVALD" "$PLAYD" "$MAXPLIES" "$((s+1000))" \
    --nnue "$W/zero.pjtw" --quiet-only --explore-eps "$EPS" --explore-decay-plies "$DECAY" --drop-post-eps \
    --adjud-material "$ADJM" --adjud-hold-plies "$ADJH" --random-open-plies "$ROPEN" \
    --search-params-play "$QS" --seed-file "$W/seeds.jnnw" --seed-frac "$SEEDFRAC" \
    --play-max-nodes "$CAP" >"$W/sp-$s.log" 2>&1 &
  SPPIDS+=($!)
done
wait "${SPPIDS[@]}"   # shards SEULEMENT (pas le monitor)
touch "$W/.stopmon"; kill "$MONPID" 2>/dev/null || true; wait "$MONPID" 2>/dev/null || true
NSH_OK=$(ls "$W"/wdl.* 2>/dev/null | wc -l); say "  shards ayant ecrit : $NSH_OK/$NCPU (les autres = cules au timeout, le cap devrait tous les faire finir)"
N_WDL=$(merge_jnnw "$W/wdl.jnnw" "$W/wdl"); say "  WDL positions = $N_WDL"
[ "$N_WDL" -gt 40000 ] 2>/dev/null || { say "ABORT WDL faible ($N_WDL) — voir sp-0.log"; tail -8 "$W/sp-0.log"|sed 's/^/    /'|tee -a "$RES"; restore_src; exit 8; }
python3 - "$W/wdl.jnnw" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]
w=d=l=0
for i in range(n):
    v=struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
    if v>0:w+=1
    elif v<0:l+=1
    else:d+=1
print(f"  WDL signal : win={w} draw={d} loss={l} ({100*d//max(n,1)}% nulles — si >90% le pur-zéro amorce mal)")
PY
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0666 self-play fini (N=$N_WDL, ${NSH_OK}/${NCPU} shards)" >/dev/null 2>&1 || true

# ---- fit WDL 100% STREAMÉ ----
say ""; say "=== fit WDL frais STREAMÉ (train_stream --target wdl --chunk $CHUNK --color-fold --l2 $L2) ==="
"$J" --dump-eval-features "$W/wdl.jnnw" "$W/wdlfeat" >"$W/feat.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/feat.log"|sed 's/^/  /'; restore_src; exit 9; }
env JASS_PATTERNS_DIR="$GEOM" python3 pattern_jass/tools/train_stream.py --data "$W/wdl.jnnw" --feat "$W/wdlfeat" \
    --target wdl --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --out "$W/eval1.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -12 "$W/fit.log"|sed 's/^/  /'; restore_src; exit 9; }
grep -iE 'target=wdl|train.?loss|wrote' "$W/fit.log" | tail -3 | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/eval1.pjtw" > "$ART/eval1-scratch.pjtw.gz"
commit_to_main "$ART/eval1-scratch.pjtw.gz" "$ARTREL/eval1-scratch.pjtw.gz" "0666 eval(1) from-scratch tour0" >/dev/null 2>&1 || true

# ---- openings ≥38p pour le gate ----
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
NG=$(grep -c . "$W/gen.fen"); [ "$NG" -gt 20 ] 2>/dev/null || { say "ABORT openings"; restore_src; exit 10; }

# ---- GATE PUR : eval(1) vs eval(0)=zero, prof fixe d9, qs pleine, ZERO Scan ; n<NMIN => ABORT ----
say ""; say "=== GATE : eval(1) vs eval(0)=zero (prof fixe d9, qs pleine, généraliste) — ZÉRO Scan ==="
for s in $(seq 0 $((NCPU-1))); do timeout 3000 python3 tools/jass_vs_jass_arch.py \
  --jass-a "$J" --pattern-a "$W/eval1.pjtw" --jass-b "$J" --pattern-b "$W/zero.pjtw" \
  --search-params-a "$QS" --search-params-b "$QS" \
  --depth 9 --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"$W/g.$s" 2>&1 & done; wait
python3 - "$W/.gate" "$NMIN_GATE" "$W"/g.* <<'PY'
import sys,math,glob
outp=sys.argv[1]; nmin=int(sys.argv[2]); a=d=b=0
for f in sys.argv[3:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b
if g < nmin:   # check-list point 10 : n<plancher = ECHEC, PAS "neutre"
    open(outp,'w').write(f"  [GATE] n={g} < plancher {nmin} => ABORT/INCONCLUANT (harnais casse ou self-play/fit vide, PAS un verdict)\n")
else:
    r=(a+0.5*d)/g; se=(0.5/(g**0.5))
    elo=-400*math.log10(1/r-1) if 0<r<1 else 0; lo,hi=r-1.96*se,r+1.96*se
    vd="eval(1) DÉCOLLE (bat zero hors-IC)" if lo>0.5 else ("ne bat pas zero (amorce ratée)" if hi<0.5 else "≈ zero (amorce molle)")
    open(outp,'w').write(f"  [eval(1) vs eval(0)=zero | d9 qs-pleine généraliste] W={a} L={b} D={d} n={g} rate={r:.3f}+-{1.96*se:.3f} elo~{elo:+.0f} => {vd}\n")
PY
cat "$W/.gate" | tee -a "$RES"
restore_src
say ""; say "  => eval(1) ≫ zero hors-IC : le matériel + 1re structure appris PAR NOUS (zéro prof) => TOUR 1 (adjud 3/16, gate vs champion tour-0)."
say "  => ABORT/n<plancher : harnais/self-play casse (PAS un verdict) ; ≈ zero : amorce molle => monter eps/cap/adjud."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0666 FIN tour0 durci : eval(1) décolle-t-il de zero (cap-noeuds, zéro prof/Scan)" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin tour 0 durci ==="
