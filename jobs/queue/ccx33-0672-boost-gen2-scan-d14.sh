#!/usr/bin/env bash
# id: ccx33-0672-boost-gen2-scan-d14
# description: BOOST gen2-mmto par MMTO-PROF-FORT (demande JFC). Self-play Scan-d14 (teacher fort, symetrique -> ~92 parents/
# partie, sonde 0667) genere des PREFERENCES de coups, puis on fine-tune gen2-mmto vers ces prefs : gen-siblings --leaf-mode
# WS-OFF (--ws-margin tres negatif = TOUTES les paires, cas d'accord regularisent ; WS-ON=-354, WS-OFF=+50 leçon 0643) ancre
# gen2, rank_finetune --leaf-pov --chunk (streame exact). Gate cand vs gen2-mmto (generaliste=signal + dilf=garde-fou, 2 mt).
# Durci : timeout/shard sur la GENERATION, gate n<plancher=ABORT, arch_assert. GATE : gen>0.5 hors-IC => Scan-d14 ajoute sur
# gen2 => cumuler + baker. AUCUN NNUE.
set -uo pipefail
cd /root/jass
# ⚠ GARDE #1 anti-DOUBLE-EXECUTION concurrente (cause suspectee 0670 : 6x "generation finie" pid unique + RESULTS vide =
# 2 copies du script qui se marchent dessus). flock non-bloquant : si une autre instance detient le lock => ABORT propre.
exec 9>/root/.jass-0672.lock
if ! flock -n 9; then echo "ABORT 0672 : une autre instance tourne deja (lock detenu) — double-execution evitee"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0672-boost-gen2-scan-d14/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0672-boost-gen2-scan-d14/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
PROG="$ART/PROGRESS.txt"; : > "$PROG"
W=/root/cw-boost-d14b; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-boost
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
CORPUS_GZ="$SEEDS_GZ"; DILF=data/dilf_combinations.fen
SCAN_BIN=/root/jass-scan/scan_linux
# generation Scan-d14
DEPTH=14; PERG=100; MAXPLIES=160; MINP=32; SKIP=8; DRAWFRAC=0.2; GSEED=66800; GEN_TIMEOUT=3000
# fit MMTO WS-OFF
LEAFD=5; MAXPP=16; LAM=0.3; ANCHOR=0.05; WS_MARGIN=-1000000000; CHUNK=200000
# gate
NOPEN=96; PAIRS=8; NMIN=200

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0; }

say "=== BOOST gen2-mmto MMTO-prof-fort (Scan-d14) — HEAD $(git log --oneline -1|cat) — nproc=$NCPU ==="
# GARDE #4 disque : un write silencieusement echoue (disque plein) => RESULTS vide. On le VOIT et on abort si trop bas.
DFAVAIL=$(df -Pm /root 2>/dev/null | awk 'NR==2{print $4}'); say "  disque /root libre = ${DFAVAIL:-?} Mo"
[ "${DFAVAIL:-0}" -gt 2000 ] 2>/dev/null || { say "ABORT disque quasi plein (<2Go) — write RESULTS risque"; exit 3; }
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0672 START (df=${DFAVAIL}Mo, lock OK)" >/dev/null 2>&1||true  # phase 0 committee => on voit que le run demarre VRAIMENT

# ---- Scan ----
if [ ! -x "$SCAN_BIN" ]; then
  SRC=/root/jass-scan-src; [ -d "$SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SRC" >"$W/sc.log" 2>&1
  mkdir -p /root/jass-scan; cp "$SRC/scan_linux" "$SCAN_BIN" 2>/dev/null && chmod +x "$SCAN_BIN"
  cp -r "$SRC/data" /root/jass-scan/data 2>/dev/null||true; cp "$SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null||true
fi
[ -x "$SCAN_BIN" ] || { say "ABORT Scan absent"; exit 3; }

# ---- build develop (arch_assert) ----
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp \
         pattern_jass/tools/rank_finetune.py pattern_jass/tools/train_stream.py tools/scan_selfplay_gen.py tools/jass_vs_jass_arch.py; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true
done
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp pattern_jass/tools/rank_finetune.py pattern_jass/tools/train_stream.py tools/scan_selfplay_gen.py tools/jass_vs_jass_arch.py 2>/dev/null||true; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi: scan_eval SANS g_emasks"; restore_src; exit 5; }
grep -q "has_any_capture" src/search.cpp || { say "ABORT archi: search SANS has_any_capture"; restore_src; exit 5; }
grep -q "has_any_capture" src/movegen.cpp || { say "ABORT archi: movegen SANS has_any_capture"; restore_src; exit 5; }
say "  Scan ✓ + garde-fou archi ✓"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j2 --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0672 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
say "  ✓ build+geom(NP=$NP) ; ancre=gen2-mmto ; seeds=$(jnnw_count "$W/seeds.jnnw")"

# ---- MONITOR generation ----
START=$(date +%s)
monitor_loop(){ while [ ! -f "$W/.stopmon" ]; do sleep 600; [ -f "$W/.stopmon" ] && break
  local el=$(( ($(date +%s)-START)/60 )); local pp=0; for f in "$W"/.pp-*.jnnw; do [ -f "$f" ] && pp=$((pp+$(jnnw_count "$f"))); done
  local done_sh=$(ls "$W"/.pp-*.jnnw 2>/dev/null|wc -l)
  printf '[+%dmin] gen Scan-d14 : %d/%d shards, ~%d parents\n' "$el" "$done_sh" "$NCPU" "$pp" >> "$PROG"
  commit_to_main "$PROG" "$ARTREL/PROGRESS.txt" "0672 gen +${el}min (${done_sh}/${NCPU}, ~${pp} parents)" >/dev/null 2>&1||true; done; }

# ---- A. generation prefs Scan-d14 (timeout/shard) ----
say ""; say "=== A. self-play Scan-d14 : $PERG parties×$NCPU, min-pieces $MINP, timeout/shard ${GEN_TIMEOUT}s ==="
rm -f "$W/.stopmon"; monitor_loop & MONPID=$!
GENPIDS=()   # ⚠ PID des shards SEULEMENT : `wait` nu attendrait aussi le monitor = DEADLOCK (bug 0665/0666/0668)
for s in $(seq 0 $((NCPU-1))); do
  timeout "$GEN_TIMEOUT" python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$J" \
    --seeds "$W/seeds.jnnw" --out "$W/.sp-$s.jnnw" --games "$PERG" \
    --max-plies "$MAXPLIES" --min-pieces "$MINP" --sample-every 1 --depth "$DEPTH" \
    --pref-parents "$W/.pp-$s.jnnw" --pref-moves "$W/.pm-$s.bin" \
    --skip-book "$SKIP" --keep-draw-frac "$DRAWFRAC" \
    --seed "$GSEED" --nshards "$NCPU" --shard "$s" >"$W/gen-$s.log" 2>&1 &
  GENPIDS+=($!)
done
wait "${GENPIDS[@]}"   # shards SEULEMENT (pas le monitor)
touch "$W/.stopmon"; kill "$MONPID" 2>/dev/null||true; wait "$MONPID" 2>/dev/null||true
# concat parents (JNNW) + moves (raw 2o/parent) alignes
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NCPU" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys,os,glob,re
outp,outm,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); REC=38; body=bytearray(); mov=bytearray(); tot=0
for s in range(nc):
    pf=f"{W}/.pp-{s}.jnnw"; mf=f"{W}/.pm-{s}.bin"
    if not os.path.exists(pf): continue
    b=open(pf,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
    m=open(mf,'rb').read() if os.path.exists(mf) else b''
    mov+=m[:n*2]
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); open(outm,'wb').write(bytes(mov))
print(f"  parents Scan-d14 concat = {tot} (moves {len(mov)//2})")
PY
NPAR=$(jnnw_count "$W/parents.jnnw"); say "  parents = $NPAR"
[ "$NPAR" -gt 3000 ] 2>/dev/null || { say "ABORT parents faible ($NPAR) — voir gen-0.log"; tail -6 "$W/gen-0.log"|sed 's/^/    /'|tee -a "$RES"; restore_src; exit 8; }
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0672 generation Scan-d14 finie ($NPAR parents)" >/dev/null 2>&1||true

# ---- B. gen-siblings --leaf-mode WS-OFF (ancre gen2) ----
say ""; say "=== B. gen-siblings --leaf-mode WS-OFF (ancre gen2-mmto, d$LEAFD, ws-margin $WS_MARGIN) ==="
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NCPU" <<'PY'
import struct,sys
pf,mf,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); REC=38
pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; body=pb[8:]; mb=open(mf,'rb').read()
per=(n+nc-1)//nc
for s in range(nc):
    lo,hi=s*per,min((s+1)*per,n)
    if lo>=hi: open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',0)); open(f"{W}/ms_{s}.bin",'wb').write(b''); continue
    open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',hi-lo)+body[lo*REC:hi*REC]); open(f"{W}/ms_{s}.bin",'wb').write(mb[lo*2:hi*2])
PY
for s in $(seq 0 $((NCPU-1))); do
  "$J" --gen-siblings "$W/ps_$s.jnnw" "$W/pairs_$s.jnnw" "$LEAFD" --played-moves "$W/ms_$s.bin" \
       --leaf-mode --ws-margin "$WS_MARGIN" --nnue "$W/gen2.pjtw" --max-pairs-per-parent "$MAXPP" >"$W/gs_$s.log" 2>&1 &
done; wait
python3 - "$W/pairs.jnnw" "$W" "$NCPU" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys,os
out,W,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38; body=bytearray(); tot=0
for s in range(nc):
    f=f"{W}/pairs_{s}.jnnw"
    if not os.path.exists(f): continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(f"  MMTO paires = {tot//2}")
PY
NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pairs.jnnw','rb').read(8)[4:8])[0]//2)" 2>/dev/null||echo 0)
say "  MMTO paires (feuilles-PV gen2, WS-OFF) : $NPAIRS"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0672 PHASE gen-siblings OK ($NPAIRS paires)" >/dev/null 2>&1||true  # phase committee
[ "$NPAIRS" -gt 500 ] 2>/dev/null || { say "ABORT paires faible ($NPAIRS)"; restore_src; exit 9; }
"$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; restore_src; exit 9; }

# ---- C. rank_finetune ancre gen2, leaf-pov, streame ----
say ""; say "=== C. rank_finetune ancre gen2-mmto --leaf-pov anchor=$ANCHOR --chunk $CHUNK ==="
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
    --champion "$W/gen2.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/cand.pjtw" \
    --tools pattern_jass/tools --lam "$LAM" --anchor "$ANCHOR" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
    --full-fold --tempo-stage --leaf-pov --chunk "$CHUNK" --verify-jass "$J" --verify-n 60 >"$W/ft.log" 2>&1 \
  || { say "FIT ABORT : $(tail -2 "$W/ft.log"|tr '\n' ' ')"; restore_src; exit 10; }
grep -E 'pairwise-acc|delta|wrote' "$W/ft.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/cand.pjtw" > "$ART/cand-boost-d14.pjtw.gz"
commit_to_main "$ART/cand-boost-d14.pjtw.gz" "$ARTREL/cand-boost-d14.pjtw.gz" "0672 candidat boost Scan-d14 WS-OFF" >/dev/null 2>&1||true

# ---- D. openings + GATE cand vs gen2 (n<NMIN => ABORT) ----
head -n "$NOPEN" "$DILF" > "$W/dilf.fen"
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
cell(){ local oset="$1" openf="$2" mt="$3"; local pref="$W/x_${oset}_${mt}"; rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/cand.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" \
    --movetime "$mt" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$openf" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$oset" "$mt" "$NMIN" "$W/.cellout" "${pref}".* <<'PY'
import sys,math
st,mt,nmin,outp=sys.argv[1],sys.argv[2],int(sys.argv[3]),sys.argv[4]; a=d=b=0
for f in sys.argv[5:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b
if g<nmin:
    open(outp,'w').write(f"  [{st} mt{mt}] n={g} < plancher {nmin} => ABORT/INCONCLUANT (harnais, PAS un verdict)\n")
else:
    r=(a+0.5*d)/g; ex2=(a+0.25*d)/g; v=ex2-r*r; se=math.sqrt(v/g) if v>0 else 0.5/(g**0.5)
    elo=-400*math.log10(1/r-1) if 0<r<1 else 0; lo,hi=r-1.96*se,r+1.96*se
    vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
    open(outp,'w').write(f"  [boost-d14 vs gen2-mmto | {st} mt{mt}] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.cellout" | tee -a "$RES"; rm -f "${pref}".*; }
say ""; say "=== D. GATE : cand(boost-d14) vs gen2-mmto — généraliste=signal + dilf=garde-fou ==="
cell gen  "$W/gen.fen"  0.2
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0672 gate gen mt0.2" >/dev/null 2>&1||true
cell gen  "$W/gen.fen"  0.3
cell dilf "$W/dilf.fen" 0.3
restore_src
say ""; say "  GATE : généraliste >0.5 hors-IC => Scan-d14 (prof fort) AJOUTE sur gen2-mmto => cumuler + bake (go JFC)."
say "  neutre/PERD => le prof-fort ne compose pas non plus sur gen2 (point fixe confirme)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0672 FIN boost Scan-d14 : le prof-fort ajoute-t-il sur gen2-mmto" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin boost gen2-mmto Scan-d14 ==="
