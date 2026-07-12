#!/usr/bin/env bash
# id: cpx62-0682-adjud-mine-exceptions
# description: MEMO PREDICATS §3 (boucle vertueuse) — MINE le corpus des EXCEPTIONS (|net materiel|>=M mais TB=NULLE) pour
# laisser la DONNEE dire ce qui separe structurellement NULLE vs GAIN (au lieu de mes priors P2/P3 v0, rejetes en 0681).
# Engine-free : features MATERIEL + GEOMETRIE dilf (dame defenseure, min_promotion_distance, compte pieces, men-only, ...),
# qui portent les gros signaux de nulle en finale. Sort, sur le sous-ensemble |net|>=M : distribution WIN vs DRAW +
# une BATTERIE de conditions candidates classees par (precision DRAW, couverture) => matiere a predicats P4.x data-driven.
# n<plancher => ABORT. Aucun bake, aucune boucle gen.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0682-adjud-mine-exceptions/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0682-adjud-mine-exceptions/artefacts"
W=/root/cw-adjmine; rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }   # 8ter
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
APP=/root/egdb_extracted/app
DILF=/root/dilf-src
NPROBE=2000; NMAIN=300000; NMIN=40000; BUDGET_S=800
START=$(date +%s)

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp 2>/dev/null||true; }

find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm /root 2>/dev/null|awk 'NR==2{print $4}'); say "=== ADJUD MINE EXCEPTIONS (§3) — nproc=$NCPU df=${DFA}Mo ==="
[ "${DFA:-0}" -gt 3000 ] 2>/dev/null || { say "ABORT disque <3Go"; exit 3; }

git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true; done
grep -q g_emasks src/scan_eval.cpp && grep -q has_any_capture src/search.cpp && grep -q gen-egdb-wld src/main.cpp || { say "ABORT archi"; restore_src; exit 5; }
say "  garde-fou archi ✓"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -15 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0682 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
[ -d "$APP" ] || { say "ABORT DB egdb absente ($APP)"; restore_src; exit 4; }
if [ -d "$DILF/.git" ]; then git -C "$DILF" pull --quiet 2>/dev/null || true; else git clone --depth=1 https://github.com/jfrancoiscollin/dilf.git "$DILF" >"$W/dilf.log" 2>&1; fi
PYTHONPATH="$DILF" python3 -c "import pedagogy.features.geometry, pedagogy.features.material; print('OK')" >"$W/imp.log" 2>&1
grep -q OK "$W/imp.log" && say "  dilf import ✓" || { say "ABORT dilf import"; cat "$W/imp.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 8; }

t0=$(date +%s); JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=1024 "$J" --gen-egdb-wld "$NPROBE" "$W/probe.jnnw" "$APP" 7 1024 1 >"$W/probe.log" 2>&1
dt=$(( $(date +%s)-t0 )); [ "$dt" -lt 1 ] && dt=1; RATE=$(( NPROBE/dt )); N=$(( RATE*BUDGET_S )); [ "$N" -gt "$NMAIN" ] && N="$NMAIN"; [ "$N" -lt "$NMIN" ] && N="$NMIN"
say "  rate≈${RATE} pos/s → N=$N"
JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=2048 "$J" --gen-egdb-wld "$N" "$W/pool.jnnw" "$APP" 7 2048 12345 >"$W/gen.log" 2>&1 || { say "ABORT gen-egdb-wld"; tail -6 "$W/gen.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 7; }
tail -1 "$W/gen.log" | sed 's/^/  /' | tee -a "$RES"

say ""; say "=== minage : |net|>=M, WIN-ahead vs DRAW (exceptions), features engine-free ==="
PYTHONPATH="$DILF" python3 - "$W/pool.jnnw" "$NMIN" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
from pedagogy.features.geometry import promotion_distance, row_of
pool=sys.argv[1]; nmin=int(sys.argv[2])
d=open(pool,'rb').read(); assert d[:4]==b'JNNW'; n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]
def sqs(x): return [s for s in range(1,51) if (x>>(s-1))&1]
M=2
# accumulate over |net|>=M & ahead-material
rows=[]   # (is_draw, feat dict)
tot=0; ndraw=nwin=nloss=0
for i in range(n):
    r=body[i*REC:(i+1)*REC]
    if len(r)<REC: break
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]; wdl=struct.unpack('<b',r[37:38])[0]
    WM,WK,BM,BK=sqs(wm),sqs(wk),sqs(bm),sqs(bk)
    net=(len(WM)+3*len(WK))-(len(BM)+3*len(BK))
    if abs(net)<M: continue
    tot+=1
    ahead='white' if net>0 else 'black'
    stm_side='white' if stm==0 else 'black'
    win_ahead = (wdl==1) if ahead==stm_side else (wdl==-1)
    is_draw = (wdl==0)
    if is_draw: ndraw+=1
    elif win_ahead: nwin+=1
    else: nloss+=1
    # ahead/defender piece sets
    if ahead=='white': A_men,A_k,D_men,D_k=WM,WK,BM,BK
    else:              A_men,A_k,D_men,D_k=BM,BK,WM,WK
    npieces=len(WM)+len(WK)+len(BM)+len(BK)
    mpd = min((promotion_distance(s,ahead) for s in A_men), default=11)
    feat=dict(
        def_has_king = len(D_k)>0,
        ahead_has_king = len(A_k)>0,
        ahead_men_only = len(A_k)==0,
        def_bare_king = (len(D_men)==0 and len(D_k)>=1),
        npieces = npieces,
        mpd = mpd,
        absnet = abs(net),
        A_men=len(A_men), A_k=len(A_k), D_men=len(D_men), D_k=len(D_k),
    )
    rows.append((is_draw,feat))
if tot<nmin:
    print(f"  ABORT/INCONCLUANT : sous-ensemble |net|>=%d n=%d < %d" % (M,tot,nmin)); sys.exit(0)
print(f"  sous-ensemble |net|>=%d : n=%d  (WIN-ahead=%d  DRAW=%d  LOSS-ahead=%d)  base draw-rate=%.2f%%"
      % (M,tot,nwin,ndraw,nloss,100*ndraw/tot))

def prof(name, cond):
    fired=[d for d,f in rows if cond(f)]
    k=len(fired)
    if k==0: print(f"    {name:52} fire=0"); return
    draws=sum(1 for d in fired if d)
    prec=100*draws/k          # precision "cond => DRAW"
    cov=100*draws/ndraw if ndraw else 0   # part des DRAW couverts
    print(f"    {name:52} fire={k:6d} prec(DRAW)={prec:6.2f}%  cov(draw-set)={cov:5.1f}%")

print("  --- conditions candidates (cond => DRAW) : precision + couverture du set DRAW ---")
prof("def_has_king", lambda f: f['def_has_king'])
prof("def_bare_king (dame nue seule)", lambda f: f['def_bare_king'])
prof("def_has_king & ahead_men_only", lambda f: f['def_has_king'] and f['ahead_men_only'])
prof("def_bare_king & ahead_men_only", lambda f: f['def_bare_king'] and f['ahead_men_only'])
for k in (2,3,4):
    prof(f"def_has_king & ahead_men_only & mpd>={k}", lambda f,k=k: f['def_has_king'] and f['ahead_men_only'] and f['mpd']>=k)
prof("def_bare_king & ahead_men_only & mpd>=3", lambda f: f['def_bare_king'] and f['ahead_men_only'] and f['mpd']>=3)
prof("npieces<=4", lambda f: f['npieces']<=4)
prof("npieces<=5", lambda f: f['npieces']<=5)
prof("def_has_king & npieces<=5", lambda f: f['def_has_king'] and f['npieces']<=5)
prof("def_kings>=1 & ahead_kings==0 & absnet<=3", lambda f: f['D_k']>=1 and f['A_k']==0 and f['absnet']<=3)
prof("def_bare_king & absnet<=3 (dame nue vs petit avantage)", lambda f: f['def_bare_king'] and f['absnet']<=3)
prof("def_bare_king & ahead_men_only & absnet<=3 & mpd>=3", lambda f: f['def_bare_king'] and f['ahead_men_only'] and f['absnet']<=3 and f['mpd']>=3)

print("  --- distributions par classe (moyennes) WIN vs DRAW ---")
def mean(sel,key):
    xs=[f[key] for d,f in rows if d==sel]; return sum(xs)/len(xs) if xs else 0
for key in ('npieces','mpd','absnet','A_men','A_k','D_men','D_k'):
    print(f"    {key:10} WIN={mean(False,key):6.2f}  DRAW={mean(True,key):6.2f}")
frac=lambda sel,key: (sum(1 for d,f in rows if d==sel and f[key])/max(1,sum(1 for d,f in rows if d==sel)))
for key in ('def_has_king','ahead_has_king','ahead_men_only','def_bare_king'):
    print(f"    {key:14} WIN={100*frac(False,key):5.1f}%  DRAW={100*frac(True,key):5.1f}%")
print("  LECTURE : une condition a prec(DRAW)>=99.9% avec cov non-negligeable = candidat prédicat P4.x (veto forteresse).")
PY

say ""; say "=== fin adjud-mine ($(( $(date +%s)-START ))s) ==="
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0682 adjud-mine FIN : corpus exceptions |net|>=2&draw profilé (features dilf) → candidats P4.x" && say "  RESULTS committé ✓" || say "  ⚠ commit RESULTS"
restore_src
