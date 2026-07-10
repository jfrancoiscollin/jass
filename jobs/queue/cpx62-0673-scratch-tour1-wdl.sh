#!/usr/bin/env bash
# id: cpx62-0673-scratch-tour1-wdl
# description: TOUR-1 FROM-SCRATCH (WDL ANCRE). Tour-0 (0669) a decolle 1056-0-0 vs zero => on itere. champion(t)=eval(1)
# self-play (PLUS aveugle : eval(1) sait le materiel) => corpus WDL => fit ANCRE sur eval(1) (wdl_finetune, JAMAIS refit-zero
# passe tour-0, leçon 0645) => eval(2). E1: adjud RESSERRE 3/16 (l'eval convertit mieux => exiger + d'avance). E4: ~256k pos
# (color-fold ~512k eff => cov20~89%) + CENSUS cov20/cov30 committe. E3 gate: eval(2) vs eval(1) d9 (champion-vs-champion,
# ZERO Scan) ; n<200=ABORT. Monitor wait-pids (fix deadlock 0665/0666). AUCUN NNUE. MMTO-self = tour-2 si WDL compose.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0673-scratch-tour1-wdl/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0673-scratch-tour1-wdl/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
PROG="$ART/PROGRESS.txt"; : > "$PROG"
W=/root/cw-scratch-t1b; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-scratch
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EVAL1_GZ=jobs/results/cpx62-0669-scratch-tour0-durci/artefacts/eval1-scratch.pjtw.gz   # champion tour-0
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
SEEDS_GZ="$CORPUS_GZ"
QS="qs_forcing_depth=6,qs_promo_depth=6"
PLAYD=10; EVALD=10; MAXPLIES=200; EPS=30; DECAY=30; ADJM=3; ADJH=16; ROPEN=8; SEEDFRAC=50; MINP=32
CAP=1000000      # cap-noeuds : eval(1) reelle => elagage OK, le cap ne borne pas les vraies recherches, juste garde-fou anti-pathologie
PERG=16000       # KEPT/shard (×16 ≈ 256k brut ; color-fold ≈ 512k eff => cov20~89%)
SHTIMEOUT=12000
ANCHOR=0.1; MAXIT=60; CHUNK=1000000   # fit WDL ancre (0.1 = leger, laisse apprendre en gardant la base eval(1))
NOPEN=96; PAIRS=8; NMIN_GATE=200

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
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0; }

START=$(date +%s)
monitor_loop(){ while [ ! -f "$W/.stopmon" ]; do sleep 600; [ -f "$W/.stopmon" ] && break
  local el=$(( ($(date +%s)-START)/60 )); local by=0; for f in "$W"/wdl.*; do [ -f "$f" ] && by=$((by+$(stat -c%s "$f" 2>/dev/null||echo 0))); done
  local approx=$((by/38)); local last=$(tail -1 "$W/sp-0.log" 2>/dev/null|tr -d '\n'|cut -c1-60)
  printf '[+%dmin] self-play : ~%d pos, sp-0: %s\n' "$el" "$approx" "$last" >> "$PROG"
  commit_to_main "$PROG" "$ARTREL/PROGRESS.txt" "0673 self-play +${el}min (~${approx} pos)" >/dev/null 2>&1||true; done; }

say "=== TOUR-1 WDL ANCRE (champion=eval(1), adjud $ADJM/$ADJH, cap $CAP) — HEAD $(git log --oneline -1|cat) — nproc=$NCPU ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp \
         pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true
done
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py 2>/dev/null||true; }
arch_assert(){
  grep -q "g_emasks"        src/scan_eval.cpp || { say "ABORT archi: scan_eval SANS g_emasks"; restore_src; exit 5; }
  grep -q "has_any_capture" src/search.cpp    || { say "ABORT archi: search SANS has_any_capture"; restore_src; exit 5; }
  grep -q "has_any_capture" src/movegen.cpp   || { say "ABORT archi: movegen SANS has_any_capture"; restore_src; exit 5; }
  grep -q "max_nodes"       src/search.hpp    || { say "ABORT archi: SANS cap-noeuds"; restore_src; exit 5; }
  grep -q "play-max-nodes"  src/main.cpp      || { say "ABORT archi: gen-data SANS --play-max-nodes"; restore_src; exit 5; }
  say "  garde-fou archi ✓"; }
arch_assert
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0673 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$EVAL1_GZ" | gunzip > "$W/eval1.pjtw" || { say "ABORT eval1 (champion tour-0 introuvable)"; restore_src; exit 4; }
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
say "  ✓ build+geom(NP=$NP) ; champion=eval(1) ; seeds=$(jnnw_count "$W/seeds.jnnw")"
say "  eval(1) sanity = $("$J" --eval-position "$W/eval1.pjtw" "W:W31-50:B1-20" 2>&1|head -1) (doit etre != 0, eval(1) voit le materiel)"

# ---- self-play champion=eval(1), cap + timeout/shard + MONITOR (wait pids !) ----
say ""; say "=== self-play eval(1) : play d$PLAYD, qs pleine, cap $CAP, adjud $ADJM/$ADJH, ${PERG}×${NCPU} ==="
rm -f "$W/.stopmon"; monitor_loop & MONPID=$!
SPPIDS=()
for s in $(seq 0 $((NCPU-1))); do
  timeout "$SHTIMEOUT" "$J" --gen-data-wdl "$PERG" "$W/wdl.$s" "$EVALD" "$PLAYD" "$MAXPLIES" "$((s+2000))" \
    --nnue "$W/eval1.pjtw" --quiet-only --explore-eps "$EPS" --explore-decay-plies "$DECAY" --drop-post-eps \
    --adjud-material "$ADJM" --adjud-hold-plies "$ADJH" --random-open-plies "$ROPEN" \
    --search-params-play "$QS" --seed-file "$W/seeds.jnnw" --seed-frac "$SEEDFRAC" \
    --play-max-nodes "$CAP" >"$W/sp-$s.log" 2>&1 &
  SPPIDS+=($!)
done
wait "${SPPIDS[@]}"   # shards SEULEMENT (jamais wait nu avec un monitor de fond = deadlock)
touch "$W/.stopmon"; kill "$MONPID" 2>/dev/null || true; wait "$MONPID" 2>/dev/null || true
N_WDL=$(merge_jnnw "$W/wdl.jnnw" "$W/wdl"); say "  WDL positions = $N_WDL"
[ "$N_WDL" -gt 100000 ] 2>/dev/null || { say "ABORT WDL faible ($N_WDL)"; tail -8 "$W/sp-0.log"|sed 's/^/    /'|tee -a "$RES"; restore_src; exit 8; }
# WDL signal + CENSUS couverture buckets (E4)
python3 - "$W/wdl.jnnw" <<'PY' 2>&1 | tee -a "$RES"
import numpy as np,struct,sys; sys.path.insert(0,'pattern_jass/tools'); import patterns as P
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]
w=d=l=0
for i in range(n):
    v=struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
    if v>0:w+=1
    elif v<0:l+=1
    else:d+=1
print(f"  WDL signal : win={w} draw={d} loss={l} ({100*d//max(n,1)}% nulles — E1: si bas, eval(1) convertit => adjud 3/16 OK)")
a=np.frombuffer(body[:n*REC],dtype=np.uint8).reshape(n,REC); bb=a[:,0:32].copy().view('<u8').reshape(n,4)
cols=P.flat_feature_columns(P.extract_indices(bb[:,2],bb[:,0])).astype(np.int32); flat=cols.ravel()
c=np.bincount(flat,minlength=P.TOTAL_BUCKETS)
print(f"  COUVERTURE (E4) : N={n} buckets_vus={int((c>0).sum())} cov20={float((c>=20)[flat].mean())*100:.1f}% cov30={float((c>=30)[flat].mean())*100:.1f}% (color-fold ~double l'effectif)")
PY
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0673 self-play fini (N=$N_WDL) + census" >/dev/null 2>&1||true

# ---- fit WDL ANCRE sur eval(1) (wdl_finetune, streame) ----
say ""; say "=== fit WDL ANCRE eval(1) (wdl_finetune --anchor $ANCHOR --color-fold --chunk $CHUNK) ==="
"$J" --dump-eval-features "$W/wdl.jnnw" "$W/wdlfeat" >"$W/feat.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/feat.log"|sed 's/^/  /'; restore_src; exit 9; }
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/eval1.pjtw" --data "$W/wdl.jnnw" --feat "$W/wdlfeat" --out "$W/eval2.pjtw" \
    --tools pattern_jass/tools --anchor "$ANCHOR" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" \
    --verify-jass "$J" --verify-n 60 >"$W/fit.log" 2>&1 || { say "FIT ABORT : $(tail -2 "$W/fit.log"|tr '\n' ' ')"; restore_src; exit 9; }
grep -iE 'logloss|pairwise|delta|wrote|anchor' "$W/fit.log" | tail -4 | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/eval2.pjtw" > "$ART/eval2-scratch.pjtw.gz"
commit_to_main "$ART/eval2-scratch.pjtw.gz" "$ARTREL/eval2-scratch.pjtw.gz" "0673 eval(2) tour1 WDL ancre" >/dev/null 2>&1||true

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

# ---- GATE E3 : eval(2) vs eval(1), d9, ZERO Scan ; n<NMIN => ABORT ----
say ""; say "=== GATE E3 : eval(2) vs eval(1) (d9, qs pleine, généraliste) — champion-vs-champion, ZÉRO Scan ==="
for s in $(seq 0 $((NCPU-1))); do timeout 3000 python3 tools/jass_vs_jass_arch.py \
  --jass-a "$J" --pattern-a "$W/eval2.pjtw" --jass-b "$J" --pattern-b "$W/eval1.pjtw" \
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
if g<nmin:
    open(outp,'w').write(f"  [GATE] n={g} < plancher {nmin} => ABORT/INCONCLUANT (PAS un verdict)\n")
else:
    r=(a+0.5*d)/g; ex2=(a+0.25*d)/g; v=ex2-r*r; se=math.sqrt(v/g) if v>0 else 0.5/(g**0.5)
    elo=-400*math.log10(1/r-1) if 0<r<1 else 0; lo,hi=r-1.96*se,r+1.96*se
    vd="eval(2) COMPOSE (bat eval(1) hors-IC)" if lo>0.5 else ("REGRESSE (perd hors-IC)" if hi<0.5 else "≈ eval(1) (plateau, pas de compose)")
    open(outp,'w').write(f"  [eval(2) vs eval(1) | d9 généraliste] W={a} L={b} D={d} n={g} rate={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
cat "$W/.gate" | tee -a "$RES"
restore_src
say ""; say "  => eval(2) ≫ eval(1) hors-IC : le WDL COMPOSE => TOUR 2 (WDL + MMTO-self, adjud 4/24)."
say "  => ≈ eval(1) : plateau WDL (1er des 2 tours sans compose, cf E3) => tour-2 tente MMTO-self ; 2 plats consecutifs => cloture."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0673 FIN tour1 WDL : eval(2) compose-t-il sur eval(1) (zéro prof/Scan)" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin tour 1 WDL ancré ==="
