#!/usr/bin/env bash
# id: cpx62-0675-scratch-diag-adjud
# description: TOUR-DIAGNOSTIC (demande JFC) — trancher pourquoi 0674 a STOP a d10 : (a) d10 EPUISE vs (b) adjud faded TROP TOT.
# Fait : T2 (adjud ON 4/24) COMPOSE +170, puis T3/T4 (adjud OFF) REGRESS => confondu. Ce job re-joue UN tour d10 depuis
# champion-current (=T2) MAIS avec adjud MAINTENU 4/24 (comme T2). Gate cand vs T2 d9. Verdict : COMPOSE => c'etait le
# FADE ADJUD (b) => corriger E1 (tenir l'adjud + garde conversion-self) avant de grimper ; REGRESS => d10 vraiment EPUISE (a)
# => R2 d12 (memo v2). UN seul tour, pas de boucle. Gardes complets. AUCUN NNUE.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0675.lock
if ! flock -n 9; then echo "ABORT 0675 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0675-scratch-diag-adjud/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0675-scratch-diag-adjud/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
PROG="$ART/PROGRESS.txt"; : > "$PROG"
W=/root/cw-diag; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-diag
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
CHAMP_GZ=jobs/results/cpx62-0674-scratch-chain/artefacts/champion-current.pjtw.gz   # = T2 (meilleur d10)
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
QS="qs_forcing_depth=6,qs_promo_depth=6"
PLAYD=10; EVALD=10; MAXPLIES=200; EPS=30; DECAY=30; ADJM=4; ADJH=24; ROPEN=8; SEEDFRAC=50; MINP=32
CAP=1000000; PERG=16000; SHTIMEOUT=14000
ANCHOR=0.05; MAXIT=60; CHUNK=1000000
NOPEN=96; PAIRS=8; NMIN=200

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
  local by=0; for f in "$W"/wdl.*; do [ -f "$f" ] && by=$((by+$(stat -c%s "$f" 2>/dev/null||echo 0))); done
  printf '[+%dmin] self-play ~%d pos\n' "$(( ($(date +%s)-START)/60 ))" "$((by/38))" >> "$PROG"
  commit_to_main "$PROG" "$ARTREL/PROGRESS.txt" "0675 diag self-play ~$((by/38)) pos" >/dev/null 2>&1||true; done; }

DFAVAIL=$(df -Pm /root 2>/dev/null|awk 'NR==2{print $4}'); say "=== TOUR-DIAG adjud tenu 4/24 depuis T2 (tranche a/b) — nproc=$NCPU df=${DFAVAIL}Mo ==="
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
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0675 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champion-current"; restore_src; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
say "  ✓ build+geom(NP=$NP) ; champion=T2 (current) ; seeds=$(jnnw_count "$W/seeds.jnnw") ; champ eval=$("$J" --eval-position "$W/champ.pjtw" "W:W31-50:B1-20" 2>&1|head -1)"

# ---- self-play adjud TENU 4/24 (wait-pids) ----
say ""; say "=== self-play T2, adjud MAINTENU $ADJM/$ADJH, d$PLAYD, cap $CAP, ${PERG}×${NCPU} ==="
rm -f "$W/.stopmon"; monitor_loop & MON=$!; SPPIDS=()
for s in $(seq 0 $((NCPU-1))); do
  timeout "$SHTIMEOUT" "$J" --gen-data-wdl "$PERG" "$W/wdl.$s" "$EVALD" "$PLAYD" "$MAXPLIES" "$((s+5000))" \
    --nnue "$W/champ.pjtw" --quiet-only --explore-eps "$EPS" --explore-decay-plies "$DECAY" --drop-post-eps \
    --adjud-material "$ADJM" --adjud-hold-plies "$ADJH" --random-open-plies "$ROPEN" \
    --search-params-play "$QS" --seed-file "$W/seeds.jnnw" --seed-frac "$SEEDFRAC" \
    --play-max-nodes "$CAP" >"$W/sp-$s.log" 2>&1 &
  SPPIDS+=($!)
done
wait "${SPPIDS[@]}"; touch "$W/.stopmon"; kill "$MON" 2>/dev/null||true; wait "$MON" 2>/dev/null||true
N=$(merge_jnnw "$W/wdl.jnnw" "$W/wdl"); say "  WDL positions = $N"
[ "$N" -gt 100000 ] 2>/dev/null || { say "ABORT WDL faible ($N)"; tail -6 "$W/sp-0.log"|sed 's/^/    /'|tee -a "$RES"; restore_src; exit 8; }
python3 - "$W/wdl.jnnw" <<'PY' 2>&1 | tee -a "$RES"
import numpy as np,struct,sys; sys.path.insert(0,'pattern_jass/tools'); import patterns as P
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]
w=d=l=0
for i in range(n):
    v=struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
    if v>0:w+=1
    elif v<0:l+=1
    else:d+=1
print(f"  WDL {100*d//max(n,1)}% nulles (adjud TENU => devrait etre bas comme T2 26%)")
a=np.frombuffer(body[:n*REC],dtype=np.uint8).reshape(n,REC); bb=a[:,0:32].copy().view('<u8').reshape(n,4)
cols=P.flat_feature_columns(P.extract_indices(bb[:,2],bb[:,0])).astype(np.int32); flat=cols.ravel()
c=np.bincount(flat,minlength=P.TOTAL_BUCKETS)
print(f"  COUVERTURE cov20={float((c>=20)[flat].mean())*100:.1f}% cov30={float((c>=30)[flat].mean())*100:.1f}%")
PY
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0675 diag self-play fini (N=$N)" >/dev/null 2>&1||true

# ---- fit ancre T2 ----
say ""; say "=== fit WDL ancre T2 (wdl_finetune --anchor $ANCHOR) ==="
"$J" --dump-eval-features "$W/wdl.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; restore_src; exit 9; }
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/champ.pjtw" --data "$W/wdl.jnnw" --feat "$W/feat" --out "$W/cand.pjtw" \
    --tools pattern_jass/tools --anchor "$ANCHOR" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" \
    --verify-jass "$J" --verify-n 60 >"$W/ft.log" 2>&1 || { say "FIT ABORT : $(tail -1 "$W/ft.log")"; restore_src; exit 9; }
grep -iE 'logloss|delta|wrote' "$W/ft.log"|tail -2|sed 's/^/  /'|tee -a "$RES"
gzip -c "$W/cand.pjtw" > "$ART/cand-diag.pjtw.gz"
commit_to_main "$ART/cand-diag.pjtw.gz" "$ARTREL/cand-diag.pjtw.gz" "0675 diag candidat" >/dev/null 2>&1||true

# ---- openings + GATE cand vs T2 d9 ----
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
open(sys.argv[2],'w').write("\n".join(out)+"\n"); print(f"  openings : {len(out)}")
PY
say ""; say "=== GATE : cand(adjud-tenu) vs T2 (champion-current) d9 ==="
for s in $(seq 0 $((NCPU-1))); do timeout 4000 python3 tools/jass_vs_jass_arch.py \
  --jass-a "$J" --pattern-a "$W/cand.pjtw" --jass-b "$J" --pattern-b "$W/champ.pjtw" \
  --search-params-a "$QS" --search-params-b "$QS" --depth 9 --pairs "$PAIRS" --max-plies 160 \
  --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"$W/g.$s" 2>&1 & done; wait
python3 - "$W/.gate" "$NMIN" "$W"/g.* <<'PY'
import sys,math
outp=sys.argv[1]; nmin=int(sys.argv[2]); a=d=b=0
for f in sys.argv[3:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except: pass
g=a+d+b
if g<nmin: open(outp,'w').write(f"  [DIAG GATE] n={g} < {nmin} => ABORT/INCONCLUANT\n")
else:
    r=(a+0.5*d)/g; se=0.5/(g**0.5); lo,hi=r-1.96*se,r+1.96*se; elo=-400*math.log10(1/r-1) if 0<r<1 else 999
    vd="COMPOSE => c'etait le FADE ADJUD (b) : corriger E1 (tenir adjud + garde conversion-self) AVANT de grimper" if lo>0.5 else \
       ("REGRESS => d10 vraiment EPUISE (a) : monter le prof R2 d12 (v2)" if hi<0.5 else "in-IC (ambigu) : refaire haut-N")
    open(outp,'w').write(f"  [cand(adjud-tenu 4/24) vs T2 | d9] W={a} L={b} D={d} n={g} rate={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}]\n  => {vd}\n")
PY
cat "$W/.gate" | tee -a "$RES"
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0675 FIN tour-diag adjud-tenu : fade-adjud (b) ou d10-epuise (a)" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit"
say "=== fin tour-diag ==="
