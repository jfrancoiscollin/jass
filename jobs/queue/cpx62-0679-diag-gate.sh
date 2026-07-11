#!/usr/bin/env bash
# id: cpx62-0679-diag-gate
# description: RE-MESURE PROPRE du gate diag 0675 (qui a fini n=0). Cause n=0 identifiee : 0675 lancait 16 shards sur 16 coeurs
# (=32 process moteur => 2x oversubscription) et RESULT ne s'imprime qu'en FIN de shard sans --progress-file => tous les shards
# tues par le timeout AVANT d'imprimer RESULT. FIX : 8 shards (=16 moteurs sur 16 coeurs, zero oversub) + --progress-file
# (tally RESULT incremental, survit au kill) + openings riches (dilf 160). Le candidat cand-diag est DEJA genere/committe par
# 0675 => ce job ne fait QUE build + gate (rapide). Verdict : cand(adjud-tenu 4/24) vs T2. COMPOSE => fade-adjud (b) confirme
# (rester d10 + escalier adjud) ; REGRESS => d10 epuise (a) (monter R2 d12). n<NMIN => ABORT (jamais "neutre" sur du vide).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0679-diag-gate/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0679-diag-gate/artefacts"
W=/root/cw-diaggate; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-diaggate
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }   # 8ter : RES dans $W (hors repo), jamais clobbe par le reset runner
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
CAND_GZ=jobs/results/cpx62-0675-scratch-diag-adjud/artefacts/cand-diag.pjtw.gz     # candidat adjud-tenu 4/24 (deja fit par 0675)
CHAMP_GZ=jobs/results/cpx62-0674-scratch-chain/artefacts/champion-current.pjtw.gz  # = T2 (meilleur d10)
QS="qs_forcing_depth=6,qs_promo_depth=6"
NSH=$(( NCPU/2 )); [ "$NSH" -ge 1 ] || NSH=1   # 8 sur cpx62 : 2 moteurs/shard => 16 process = NCPU, zero oversub
NOPEN=160; PAIRS=1; NMIN=250; SHTIMEOUT=3600   # 160 openings x1 x2 = 320 games / NSH ; --progress-file => partiels survivent
START=$(date +%s)

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp tools/jass_vs_jass_arch.py 2>/dev/null||true; }

# --- 8bis : hygiene disque (auto-clean cw-* stale + garde df) ---
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm /root 2>/dev/null|awk 'NR==2{print $4}'); say "=== DIAG-GATE cand(adjud-tenu 4/24) vs T2 — nproc=$NCPU NSH=$NSH df=${DFA}Mo ==="
[ "${DFA:-0}" -gt 3000 ] 2>/dev/null || { say "ABORT disque <3Go"; exit 3; }

# --- garde-fou archi : pull explicite develop + assert avant cmake ---
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp tools/jass_vs_jass_arch.py; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true; done
grep -q g_emasks src/scan_eval.cpp && grep -q has_any_capture src/search.cpp && grep -q has_any_capture src/movegen.cpp || { say "ABORT archi"; restore_src; exit 5; }
say "  garde-fou archi ✓"

cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0679 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"

git show "origin/main:$CAND_GZ"  | gunzip > "$W/cand.pjtw"  || { say "ABORT cand-diag"; restore_src; exit 4; }
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champion-current"; restore_src; exit 4; }
head -"$NOPEN" data/dilf_combinations.fen > "$W/open.fen"; NO=$(grep -c . "$W/open.fen")
say "  ✓ build(NP=$NP) ; cand eval=$("$J" --eval-position "$W/cand.pjtw" "W:W31-50:B1-20" 2>&1|head -1) champ eval=$("$J" --eval-position "$W/champ.pjtw" "W:W31-50:B1-20" 2>&1|head -1) ; openings=$NO"

# --- GATE : cand vs T2, d9, qs6, NSH shards (zero oversub), --progress-file (partiels survivent) ---
say ""; say "=== GATE cand(adjud-tenu 4/24) vs T2 (champion-current) | d9 qs6 | ${NOPEN}op x${PAIRS} x2 sur $NSH shards ==="
rm -f "$W"/g.*; pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout "$SHTIMEOUT" python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/cand.pjtw" --jass-b "$J" --pattern-b "$W/champ.pjtw" \
    --search-params-a "$QS" --search-params-b "$QS" --depth 9 --pairs "$PAIRS" --max-plies 160 \
    --shard "$s" --nshards "$NSH" --quiet --openings-file "$W/open.fen" \
    --progress-file "$W/g.$s" >"$W/o.$s" 2>&1 &
  pids+=($!)
done
wait "${pids[@]}"   # wait-pids explicite (jamais wait nu) ; ici pas de monitor mais on garde le patron sur

python3 - "$W/.gate" "$NMIN" "$W"/g.* <<'PY'
import sys,math
outp=sys.argv[1]; nmin=int(sys.argv[2]); a=d=b=0; shards=0
for f in sys.argv[3:]:
    try:
        last=None
        for l in open(f):
            if l.startswith("RESULT"): last=l
        if last: _,x,y,z=last.split(); a+=int(x); d+=int(y); b+=int(z); shards+=1
    except: pass
g=a+d+b
if g<nmin:
    open(outp,'w').write(f"  [DIAG GATE] n={g} (<{nmin}) sur {shards} shards => ABORT/INCONCLUANT (re-mesurer, ne PAS interpreter)\n")
else:
    r=(a+0.5*d)/g; se=0.5/(g**0.5); lo,hi=r-1.96*se,r+1.96*se; elo=-400*math.log10(1/r-1) if 0<r<1 else 999
    vd=("COMPOSE => FADE-ADJUD (b) confirme : rester d10 + escalier adjud (crans gates conv_self)" if lo>0.5 else
        ("REGRESS => d10 EPUISE (a) : monter le prof R2 d12" if hi<0.5 else
         "in-IC (ambigu) : refaire haut-N (doubler openings)"))
    open(outp,'w').write(f"  [cand(adjud-tenu 4/24) vs T2 | d9] W={a} L={b} D={d} n={g} ({shards} shards) rate={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}]\n  => {vd}\n")
PY
GATE=$(cat "$W/.gate"); say "$GATE"
VERD=$(sed -n 's/.*=> //p' "$W/.gate" | head -1)
say "=== fin diag-gate ($(( ($(date +%s) - ${START:-$(date +%s)}) )) s) ==="
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0679 diag-gate FIN : ${VERD:-n=0/ABORT}" && say "  RESULTS committé ✓" || say "  ⚠ commit RESULTS"
restore_src
