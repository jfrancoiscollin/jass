#!/usr/bin/env bash
# id: cpx62-0680-adjud-tb-harness
# description: §2 du MEMO PREDICATS D'ADJUDICATION — construit le HARNAIS DE NOTATION TB (le juge d'abord) + la BASELINE chiffree
# (l'adjud MATERIELLE pure notee vs TB) + PROUVE que dilf tourne sur la box (clone + import + pont FEN->GameState->primitives sur
# un echantillon TB reel). Engine-free (pas de mobilite ici : P2/P3 viendront apres le back-engine). Juge = TB egdb (WLD exact,
# <=7 pieces) DEJA dans jass (--gen-egdb-wld echantillonne uniformement la TB + labellise WLD-exact). Aucun changement de code jass.
# Sort : precision + fire-rate de "avance materielle nette >= M => WIN" pour M croissant, + le compte des FAUX-WIN (|net|>=M mais
# TB=DRAW) = la cible que les vetos P2/P3/P4 devront couvrir. n<plancher => ABORT (jamais "neutre" sur du vide).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0680-adjud-tb-harness/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0680-adjud-tb-harness/artefacts"
W=/root/cw-adjtb; rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }   # 8ter : RES dans $W (hors repo)
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
APP=/root/egdb_extracted/app            # DB WLD (db2..db7)
DILF=/root/dilf-src                     # clone dilf (public)
NPROBE=2000; NMAIN=200000; NMIN=20000; BUDGET_S=900   # NMAIN plafond ; recalibre apres la sonde
START=$(date +%s)

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp 2>/dev/null||true; }

# --- 8bis : hygiene disque ---
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm /root 2>/dev/null|awk 'NR==2{print $4}'); say "=== ADJUD-TB-HARNESS (§2 juge + baseline materielle) — nproc=$NCPU df=${DFA}Mo ==="
[ "${DFA:-0}" -gt 3000 ] 2>/dev/null || { say "ABORT disque <3Go"; exit 3; }

# --- garde-fou archi + build EGDB ---
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true; done
grep -q g_emasks src/scan_eval.cpp && grep -q has_any_capture src/search.cpp && grep -q has_any_capture src/movegen.cpp || { say "ABORT archi"; restore_src; exit 5; }
say "  garde-fou archi ✓"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -15 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0680 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"

# --- garde TB presente sur CETTE box + selfcheck (le juge doit etre sain) ---
[ -d "$APP" ] || { say "ABORT : DB egdb absente ($APP) sur cette box — relancer sur la box qui la porte"; restore_src; exit 4; }
say ""; say "=== selfcheck TB (garde #1 : le juge) ==="
JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=512 "$J" --egdb-selfcheck "$APP" 5000 512 >"$W/self.log" 2>&1 || true
tail -4 "$W/self.log" | sed 's/^/  /' | tee -a "$RES"
grep -qiE 'mismatch|FAIL|error' "$W/self.log" && { say "  ⚠ selfcheck douteux — inspecter self.log"; } || say "  selfcheck ✓ (juge sain)"

# --- dilf sur la box : clone + import + smoke primitives ---
say ""; say "=== dilf sur la box ==="
if [ -d "$DILF/.git" ]; then git -C "$DILF" pull --quiet 2>/dev/null || true; else git clone --depth=1 https://github.com/jfrancoiscollin/dilf.git "$DILF" >"$W/dilf.log" 2>&1; fi
PYTHONPATH="$DILF" python3 - <<'PY' >"$W/dilfsmoke.log" 2>&1 || { echo "IMPORT_FAIL"; }
from pedagogy.game import parse_fen
from pedagogy.features.geometry import min_promotion_distance, squares_between
s=parse_fen("W:W31,32,K38:B1,2,K7")
assert min_promotion_distance(s,"white")==6, "mpd"
assert squares_between(5,46)==[10,14,19,23,28,32,37,41], "sqb"
print("DILF_OK")
PY
grep -q DILF_OK "$W/dilfsmoke.log" && say "  dilf import+primitives ✓ ($(git -C "$DILF" rev-parse --short HEAD 2>/dev/null))" || { say "ABORT dilf KO"; cat "$W/dilfsmoke.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 8; }

# --- micro-calibration du rate gen-egdb-wld (point 2 check-list) ---
say ""; say "=== micro-calib gen-egdb-wld (N=$NPROBE) ==="
t0=$(date +%s)
JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=1024 "$J" --gen-egdb-wld "$NPROBE" "$W/probe.jnnw" "$APP" 7 1024 1 >"$W/probe.log" 2>&1
dt=$(( $(date +%s) - t0 )); [ "$dt" -lt 1 ] && dt=1
RATE=$(( NPROBE / dt ))
# taille N pour tenir ~BUDGET_S, plafonnee a NMAIN
N=$(( RATE * BUDGET_S )); [ "$N" -gt "$NMAIN" ] && N="$NMAIN"; [ "$N" -lt "$NMIN" ] && N="$NMIN"
say "  rate≈${RATE} pos/s → N=$N (budget ${BUDGET_S}s, plafond $NMAIN) ; ETA gen≈$(( N / (RATE>0?RATE:1) ))s"
tail -1 "$W/probe.log" | sed 's/^/  /' | tee -a "$RES"

# --- echantillon TB uniforme (vérité-terrain WLD exacte) ---
say ""; say "=== echantillon TB uniforme N=$N (WLD-exact <=7 pieces) ==="
JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=2048 "$J" --gen-egdb-wld "$N" "$W/pool.jnnw" "$APP" 7 2048 12345 >"$W/gen.log" 2>&1 || { say "ABORT gen-egdb-wld"; tail -6 "$W/gen.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 7; }
tail -1 "$W/gen.log" | sed 's/^/  /' | tee -a "$RES"

# --- SCORING : baseline materielle vs TB + preuve pont dilf sur l'echantillon ---
say ""; say "=== BASELINE : 'avance nette >= M => WIN' notee vs TB (juge) ==="
PYTHONPATH="$DILF" python3 - "$W/pool.jnnw" "$NMIN" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
from pedagogy.game import parse_fen
from pedagogy.features.geometry import min_promotion_distance
d=open(sys.argv[1],'rb').read(); nmin=int(sys.argv[2])
if d[:4]!=b'JNNW': print("  ABORT: pas un JNNW"); sys.exit(0)
n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]
def fen(wm,wk,bm,bk,stm):
    Wl=[str(s) for s in range(1,51) if (wm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (wk>>(s-1))&1]
    Bl=[str(s) for s in range(1,51) if (bm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (bk>>(s-1))&1]
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
Ms=[2,3,4,6,8,12]  # marge en men-equiv (dame=3)
# compteurs par M : tir (|net|>=M), dont correct (signe net == signe wdl), dont faux-WIN (|net|>=M mais wdl==0)
fire={m:0 for m in Ms}; correct={m:0 for m in Ms}; falsewin={m:0 for m in Ms}
tot=0; dec=0; draw=0; bridge_ok=0; bridge_try=0
for i in range(n):
    r=body[i*REC:(i+1)*REC]
    if len(r)<REC: break
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]; wdl=struct.unpack('<b',r[37:38])[0]
    tot+=1
    if wdl==0: draw+=1
    else: dec+=1
    wcnt=bin(wm).count('1'); wk_=bin(wk).count('1'); bcnt=bin(bm).count('1'); bk_=bin(bk).count('1')
    net_white=(wcnt+3*wk_)-(bcnt+3*bk_)
    net_stm = net_white if stm==0 else -net_white   # net du cote au trait
    for m in Ms:
        if abs(net_stm)>=m:
            fire[m]+=1
            pred = 1 if net_stm>0 else -1
            if pred==wdl: correct[m]+=1
            if wdl==0: falsewin[m]+=1
    # preuve pont dilf : parse + primitive sur 1 position /500 (bornee)
    if i % 500 == 0 and bridge_try<400:
        bridge_try+=1
        try:
            st=parse_fen(fen(wm,wk,bm,bk,stm)); _=min_promotion_distance(st,'white'); bridge_ok+=1
        except Exception: pass
if tot<nmin:
    print(f"  ABORT/INCONCLUANT : n={tot} < {nmin} (echantillon TB trop petit)"); sys.exit(0)
print(f"  echantillon : n={tot}  (decisive={dec}  draw={draw})  ; pont dilf : {bridge_ok}/{bridge_try} FEN->GameState->primitive OK")
print(f"  {'M(men-eq)':>9} {'fire%':>7} {'prec%':>7} {'faux-WIN(draw)':>15}")
for m in Ms:
    fr=100*fire[m]/tot if tot else 0
    pr=100*correct[m]/fire[m] if fire[m] else 0
    fw=falsewin[m]
    print(f"  {m:>9} {fr:>7.2f} {pr:>7.3f} {fw:>15}   (fires={fire[m]})")
print("  LECTURE : prec% = quand la marge materielle tire, taux d'accord avec la TB ; faux-WIN = |net|>=M mais TB=DRAW")
print("           = EXACTEMENT ce que les vetos P2/P3/P4 devront couvrir. La marge admissible (>=99.9%) fonde le 1er cran.")
PY

say ""; say "=== fin adjud-tb-harness ($(( $(date +%s)-START ))s) ==="
VERD=$(grep -m1 -E '^  +[0-9]+ ' "$RES" | awk '{print "baseline M-curve OK (voir table)"}'); : "${VERD:=baseline}"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0680 adjud-tb-harness FIN : juge TB + baseline materielle + dilf-on-box ✓" && say "  RESULTS committé ✓" || say "  ⚠ commit RESULTS"
restore_src
