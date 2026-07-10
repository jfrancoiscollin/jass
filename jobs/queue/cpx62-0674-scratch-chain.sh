#!/usr/bin/env bash
# id: cpx62-0674-scratch-chain
# description: BOUCLE AUTONOME OVERNIGHT (demande JFC) — enchaine les tours from-scratch TANT QUE l'eval GRIMPE. Part de
# champion(0)=eval(1) (tour-0 0669). Chaque tour : self-play champion(t-1) (d10 FIXE, cap, adjud E1 fade) => WDL => fit ANCRE
# (wdl_finetune, anchor 0.1) => gate compose eval(t) vs champion(t-1) d9. Si COMPOSE => promeut + tour suivant ; sinon plateau++,
# 2 plateaux consecutifs => STOP (E3). Cap MAXTOURS. E1 adjud fade : t1=3/16 t2=4/24 t3+=OFF. E4 : 256k/tour + census. Chaque
# tour COMMITTE son champion (progres preserve si la boucle meurt). GARDES : flock (anti double-exec), df, wait-pids, cap-noeuds,
# timeout genereux, RESULTS/phase, n<plancher=ABORT. d10 fixe (JFC : on reste d10 si ca marche). AUCUN NNUE. Compute illimite.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0674.lock
if ! flock -n 9; then echo "ABORT 0674 : instance deja active (anti double-exec)"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0674-scratch-chain/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0674-scratch-chain/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
PROG="$ART/PROGRESS.txt"; : > "$PROG"
W=/root/cw-chain; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-chain
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EVAL1_GZ=jobs/results/cpx62-0669-scratch-tour0-durci/artefacts/eval1-scratch.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
QS="qs_forcing_depth=6,qs_promo_depth=6"
PLAYD=10; EVALD=10; MAXPLIES=200; EPS=30; DECAY=30; ROPEN=8; SEEDFRAC=50; MINP=32
CAP=1000000; PERG=16000; SHTIMEOUT=14000     # compute illimite : timeout large pour atteindre PERG (256k/tour)
ANCHOR=0.05; MAXIT=60; CHUNK=1000000
NOPEN=96; PAIRS=8; NMIN=200; MAXTOURS=6       # E3 cap dur

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

# ---- df + build + geom (une fois) ----
DFAVAIL=$(df -Pm /root 2>/dev/null | awk 'NR==2{print $4}'); say "=== CHAIN overnight (d$PLAYD fixe, cap $CAP, MAXTOURS $MAXTOURS) — nproc=$NCPU df=${DFAVAIL}Mo ==="
[ "${DFAVAIL:-0}" -gt 3000 ] 2>/dev/null || { say "ABORT disque <3Go"; exit 3; }
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp \
         pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true
done
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py 2>/dev/null||true; }
grep -q g_emasks src/scan_eval.cpp && grep -q has_any_capture src/search.cpp && grep -q max_nodes src/search.hpp && grep -q play-max-nodes src/main.cpp || { say "ABORT archi"; restore_src; exit 5; }
say "  garde-fou archi ✓"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0674 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$EVAL1_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT eval1"; restore_src; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
# openings gate (une fois)
python3 - "$W/seeds.jnnw" "$W/gen.fen" "$NOPEN" <<'PY' 2>&1 | tee -a "$RES"
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
open(sys.argv[2],'w').write("\n".join(out)+"\n"); print(f"  openings gate : {len(out)}")
PY
say "  ✓ build+geom(NP=$NP) ; champion(0)=eval(1) ; seeds=$(jnnw_count "$W/seeds.jnnw")"

# ---- monitor par tour (wait-pids !) ----
monitor_loop(){ local tg="$1"; while [ ! -f "$W/.stopmon" ]; do sleep 600; [ -f "$W/.stopmon" ] && break
  local by=0; for f in "$W"/wdl.*; do [ -f "$f" ] && by=$((by+$(stat -c%s "$f" 2>/dev/null||echo 0))); done
  printf '[%s] self-play ~%d pos\n' "$tg" "$((by/38))" >> "$PROG"
  commit_to_main "$PROG" "$ARTREL/PROGRESS.txt" "0674 $tg self-play ~$((by/38)) pos" >/dev/null 2>&1||true; done; }

# ---- UN TOUR : self-play champion -> fit ancre -> gate ; ecrit $W/.verdict (COMPOSE/PLATEAU/REGRESS) ----
run_tour(){ local t="$1" adjm="$2" adjh="$3"
  rm -f "$W"/wdl.* "$W/.stopmon" "$W/.verdict"
  say ""; say "=== TOUR $t : self-play champion(t-1), adjud $adjm/$adjh, d$PLAYD, cap $CAP, ${PERG}×${NCPU} ==="
  monitor_loop "T$t" & local MON=$!
  local pids=()
  for s in $(seq 0 $((NCPU-1))); do
    timeout "$SHTIMEOUT" "$J" --gen-data-wdl "$PERG" "$W/wdl.$s" "$EVALD" "$PLAYD" "$MAXPLIES" "$((t*100+s))" \
      --nnue "$W/champ.pjtw" --quiet-only --explore-eps "$EPS" --explore-decay-plies "$DECAY" --drop-post-eps \
      --adjud-material "$adjm" --adjud-hold-plies "$adjh" --random-open-plies "$ROPEN" \
      --search-params-play "$QS" --seed-file "$W/seeds.jnnw" --seed-frac "$SEEDFRAC" \
      --play-max-nodes "$CAP" >"$W/sp-$s.log" 2>&1 &
    pids+=($!)
  done
  wait "${pids[@]}"; touch "$W/.stopmon"; kill "$MON" 2>/dev/null||true; wait "$MON" 2>/dev/null||true
  local N; N=$(merge_jnnw "$W/wdl.jnnw" "$W/wdl"); say "  WDL positions = $N"
  [ "$N" -gt 100000 ] 2>/dev/null || { say "  TOUR $t ABORT : WDL faible ($N) — STOP chain"; echo "REGRESS" > "$W/.verdict"; return; }
  python3 - "$W/wdl.jnnw" <<'PY' 2>&1 | tee -a "$RES"
import numpy as np,struct,sys; sys.path.insert(0,'pattern_jass/tools'); import patterns as P
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]
w=d=l=0
for i in range(n):
    v=struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
    if v>0:w+=1
    elif v<0:l+=1
    else:d+=1
a=np.frombuffer(body[:n*REC],dtype=np.uint8).reshape(n,REC); bb=a[:,0:32].copy().view('<u8').reshape(n,4)
cols=P.flat_feature_columns(P.extract_indices(bb[:,2],bb[:,0])).astype(np.int32); flat=cols.ravel()
c=np.bincount(flat,minlength=P.TOTAL_BUCKETS)
print(f"  WDL {100*d//max(n,1)}% nulles (E1 conversion) ; COUVERTURE cov20={float((c>=20)[flat].mean())*100:.1f}% cov30={float((c>=30)[flat].mean())*100:.1f}%")
PY
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0674 T$t self-play+census (N=$N)" >/dev/null 2>&1||true
  # fit ancre
  say "  fit WDL ancre (wdl_finetune --anchor $ANCHOR --color-fold)"
  "$J" --dump-eval-features "$W/wdl.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "  DUMP FAIL — STOP"; echo "REGRESS">"$W/.verdict"; return; }
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
      --champion "$W/champ.pjtw" --data "$W/wdl.jnnw" --feat "$W/feat" --out "$W/cand.pjtw" \
      --tools pattern_jass/tools --anchor "$ANCHOR" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" \
      --verify-jass "$J" --verify-n 60 >"$W/ft.log" 2>&1 || { say "  FIT ABORT : $(tail -1 "$W/ft.log") — STOP"; echo "REGRESS">"$W/.verdict"; return; }
  grep -iE 'pairwise|delta|wrote' "$W/ft.log" | tail -2 | sed 's/^/    /' | tee -a "$RES"
  gzip -c "$W/cand.pjtw" > "$ART/champion-tour$t.pjtw.gz"
  commit_to_main "$ART/champion-tour$t.pjtw.gz" "$ARTREL/champion-tour$t.pjtw.gz" "0674 T$t champion candidat" >/dev/null 2>&1||true
  # gate cand vs champion(t-1)
  say "  GATE : eval(t=$t) vs champion(t-1) d9"
  rm -f "$W"/g.*
  for s in $(seq 0 $((NCPU-1))); do timeout 4000 python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/cand.pjtw" --jass-b "$J" --pattern-b "$W/champ.pjtw" \
    --search-params-a "$QS" --search-params-b "$QS" --depth 9 --pairs "$PAIRS" --max-plies 160 \
    --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"$W/g.$s" 2>&1 & done; wait
  python3 - "$W/.gateline" "$W/.verdict" "$NMIN" "$t" "$W"/g.* <<'PY'
import sys,math
gl,vf,nmin,t=sys.argv[1],sys.argv[2],int(sys.argv[3]),sys.argv[4]; a=d=b=0
for f in sys.argv[5:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b
if g<nmin:
    open(gl,'w').write(f"  [T{t} GATE] n={g} < {nmin} => ABORT/INCONCLUANT\n"); open(vf,'w').write("REGRESS")
else:
    r=(a+0.5*d)/g; se=0.5/(g**0.5); lo,hi=r-1.96*se,r+1.96*se
    elo=-400*math.log10(1/r-1) if 0<r<1 else 999
    v="COMPOSE" if lo>0.5 else ("REGRESS" if hi<0.5 else "PLATEAU")
    open(gl,'w').write(f"  [T{t} eval(t) vs champion(t-1) | d9] W={a} L={b} D={d} n={g} rate={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {v}\n")
    open(vf,'w').write(v)
PY
  cat "$W/.gateline" | tee -a "$RES"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0674 T$t gate $(cat "$W/.verdict")" >/dev/null 2>&1||true
}

# ---- BOUCLE DES TOURS (E1 adjud fade + E3 stop) ----
plateau=0
for t in $(seq 1 "$MAXTOURS"); do
  # E1 fade : t1=3/16, t2=4/24, t3+=OFF (adjud_material=0)
  if   [ "$t" = 1 ]; then ADJM=3; ADJH=16
  elif [ "$t" = 2 ]; then ADJM=4; ADJH=24
  else ADJM=0; ADJH=10; fi
  run_tour "$t" "$ADJM" "$ADJH"
  V=$(cat "$W/.verdict" 2>/dev/null || echo REGRESS)
  if [ "$V" = "COMPOSE" ]; then
    cp "$W/cand.pjtw" "$W/champ.pjtw"; plateau=0
    gzip -c "$W/champ.pjtw" > "$ART/champion-current.pjtw.gz"
    commit_to_main "$ART/champion-current.pjtw.gz" "$ARTREL/champion-current.pjtw.gz" "0674 T$t COMPOSE => champion promu" >/dev/null 2>&1||true
    say "  ⟹ TOUR $t COMPOSE : champion promu (eval grimpe), on continue."
  else
    plateau=$((plateau+1))
    say "  ⟹ TOUR $t = $V (plateau $plateau/2) : champion NON promu."
    [ "$plateau" -ge 2 ] && { say "  ⟹ 2 tours sans compose consecutifs => STOP chain (E3)."; break; }
  fi
done
restore_src
say ""; say "=== CHAIN FINIE : dernier champion promu = champion-current.pjtw.gz (le plus haut atteint sans prof/Scan) ==="
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0674 FIN chain overnight from-scratch" && say "  RESULTS committé ✓" || say "  ⚠ commit"
