#!/usr/bin/env bash
# id: cpx62-0707-b4-bootstrap-gate
# description: GATE B4 (L3 bloquant 1) — valide la graine bootstrap.pjtw (make_bootstrap_eval.py). Le bootstrap
# donne à la lignée from-scratch un eval(0) MATÉRIEL-conscient (économise T0-T2). Gate : (1) build v4 même flags que
# gen2 ; (2) REGÉNÈRE bootstrap.pjtw via make_bootstrap_eval --like <header gen2> (dims build-matched) + zero.pjtw
# (--men 0 …) ; (3) eval-position ~10 étalons -> ORDRE matériel monotone (black-POV) ; (4) A/B bootstrap vs zero ->
# ÉCRASE ~1.000 (sinon graine fausse) ; (5) jass_tests 100%. PUR offline, pas d'egdb. AUCUN NNUE.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0707.lock
if ! flock -n 9; then echo "ABORT 0707 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0707-b4-bootstrap-gate/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0707-b4-bootstrap-gate/artefacts"
W=/root/cw-0707
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
QS="qs_forcing_depth=6,qs_promo_depth=6"; DEPTH=9; NOPEN=120; PAIRS=1

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== GATE B4 bootstrap — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
git show "origin/$SRC_BRANCH:pattern_jass/tools/make_bootstrap_eval.py" > pattern_jass/tools/make_bootstrap_eval.py 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src tools/jass_vs_jass_arch.py 2>/dev/null||true; rm -f pattern_jass/tools/make_bootstrap_eval.py; }
[ -s pattern_jass/tools/make_bootstrap_eval.py ] || { say "ABORT: make_bootstrap_eval.py absent de $SRC_BRANCH"; restore_src; exit 5; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile pattern_jass/tools/make_bootstrap_eval.py || { say "ABORT py_compile"; restore_src; exit 5; }

say "=== build jass (v4, flags gen2) ==="
cmake -S . -B "$W/build" $FLAGS >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0707 BUILD FAIL"; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }

# --- regenère bootstrap + zero, dims build-matched via --like (header gen2, DIMENSIONS seules) ---
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2 header"; restore_src; exit 4; }
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/bootstrap.pjtw" --like "$W/gen2.pjtw" | tee -a "$RES"
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/zero.pjtw" --like "$W/gen2.pjtw" \
    --men 0 --king 0 --king-center 0 --mobility 0 >/dev/null
say "  ✓ bootstrap.pjtw + zero.pjtw régénérés (build-matched)"

# --- (3) eval-position : ORDRE matériel monotone (black-POV) ---
say ""; say "=== eval-position étalons (ordre matériel monotone attendu, black-POV) ==="
python3 - "$J" "$W/bootstrap.pjtw" <<'PY' 2>&1 | tee -a "$RES"
import subprocess,sys,re
J,PJ=sys.argv[1],sys.argv[2]
def ev(fen):
    r=subprocess.run([J,"--eval-position",PJ,fen],capture_output=True,text=True,timeout=60)
    m=re.search(r'-?\d+\.?\d*',(r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else "")
    return float(m.group(0)) if m else None
cases=[
 ("W:W31-50:B1-20","symétrique 20v20 (~0)"),
 ("W:W31-50:B6-20","blanc +5 hommes"),
 ("W:W36-50:B1-20","noir +5 hommes"),
 ("W:WK31:B1-5","1 dame blanche vs 5 hommes noirs"),
 ("W:W1-5:BK31","5 hommes blancs vs 1 dame noire"),
]
vals=[(ev(f),d) for f,d in cases]
for v,d in vals: print(f"  {v:+8.3f}  {d}")
sym,wp5,bp5=vals[0][0],vals[1][0],vals[2][0]
ok = (wp5 < sym < bp5) and abs(sym) < 1.0
print(f"  MONOTONIE matériel (blanc+5 < sym < noir+5, |sym|<1) : {'OK ✓' if ok else 'ÉCHEC ✗'}")
open("/root/cw-0707/.evalok","w").write("1" if ok else "0")
PY

# --- (4) A/B bootstrap vs zero -> écrase ~1.000 ---
say ""; say "=== A/B bootstrap vs zero (d$DEPTH qs6, doit écraser ~1.000) ==="
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"
NSH=$((NCPU/2)); [ "$NSH" -lt 1 ] && NSH=1; pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout 2400 python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/bootstrap.pjtw" \
    --jass-b "$J" --pattern-b "$W/zero.pjtw" --search-params-a "$QS" --search-params-b "$QS" \
    --depth "$DEPTH" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NSH" --quiet \
    --openings-file "$W/open.fen" >"$W/ab.$s" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
read A D B < <(python3 -c "
import glob
a=d=b=0
for f in glob.glob('$W/ab.*'):
    try:
        for l in open(f):
            if l.startswith('RESULT'): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except: pass
print(a,d,b)")
G=$((A+D+B)); RATE=$(python3 -c "print(f'{($A+0.5*$D)/max($G,1):.4f}')")
say "  bootstrap vs zero : W=$A L=$B D=$D n=$G rate=$RATE (attendu ~1.000)"

# --- (5) jass_tests ---
say ""; say "=== jass_tests ==="
cmake --build "$W/build" -j"$NCPU" --target jass_tests >"$W/tbuild.log" 2>&1 || say "  (cible jass_tests indispo : $(tail -1 "$W/tbuild.log"))"
TESTOK="n/a"
if [ -x "$W/build/jass_tests" ]; then
  if "$W/build/jass_tests" >"$W/tests.log" 2>&1; then TESTOK="PASS"; else TESTOK="FAIL"; fi
  tail -3 "$W/tests.log"|sed 's/^/    /'|tee -a "$RES"
fi

# --- VERDICT B4 ---
say ""; say "=== VERDICT GATE B4 ==="
EVALOK=$(cat "$W/.evalok" 2>/dev/null||echo 0)
python3 - "$RATE" "$EVALOK" "$TESTOK" <<'PY' | tee -a "$RES"
import sys
rate=float(sys.argv[1]); evalok=sys.argv[2]=="1"; testok=sys.argv[3]
crush = rate>=0.95
verdict = "ADMIS — bootstrap valide (écrase zero + ordre matériel + tests) => graine L3 prête" \
    if (crush and evalok and testok in ("PASS","n/a")) else \
    f"ÉCHEC — crush={crush}(rate={rate}) eval_monotone={evalok} tests={testok} : corriger avant T-0"
print(f"  crush zero (rate≥0.95) : {crush} (rate={rate})")
print(f"  ordre matériel monotone : {evalok}")
print(f"  jass_tests : {testok}")
print(f"  => {verdict}")
PY
cp "$W/bootstrap.pjtw" "$W/b.pjtw"; gzip -c "$W/b.pjtw" > "$ART/bootstrap-build-matched.pjtw.gz" 2>/dev/null || true
commit_to_main "$ART/bootstrap-build-matched.pjtw.gz" "$ARTREL/bootstrap-build-matched.pjtw.gz" "0707 bootstrap build-matched" >/dev/null 2>&1||true
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0707 FIN gate B4 bootstrap : rate=$RATE eval=$EVALOK tests=$TESTOK" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0707 FINI ==="
rm -rf "$W"
