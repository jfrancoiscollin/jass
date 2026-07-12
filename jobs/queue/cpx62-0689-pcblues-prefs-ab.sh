#!/usr/bin/env bash
# id: cpx62-0689-pcblues-prefs-ab
# description: GATE A/B des candidats 0687 (pcblues-prefs !/!!) vs champion gen2-mmto (go JFC 2026-07-12). S'execute
# APRES 0687 sur cpx62 (ordre de queue) : les candidats pcbprefs_{0.05,0.1} sont committes par 0687 ; ABORT propre s'ils
# manquent. Harnais 0679 : d9 + qs6, NSH=NCPU/2 shards (zero oversub), --progress-file (partiels survivent), openings =
# head-160 de data/dilf_combinations.fen (source DISJOINTE du fit PC Blues — pas de contamination train-test). 320
# parties/candidat, NMIN 250. PRE-ESTIMATION (ancre 0679 : 320 games d9 << 1h cpx62) : ~40-60 min pour les 2 candidats.
# LECTURE : hors-IC>0.5 = le prof humain elite (!/!!) ajoute au-dela de gen2-mmto (la ou Scan-d14 0672 a PERDU) => 1re
# marge depuis le point fixe => confirmer haut-N puis phase 2 negatives ?/??. Plat/negatif = signal deja capte par le
# search => phase 2 directement (les negatives sont l'inedit). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0689-pcblues-prefs-ab/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0689-pcblues-prefs-ab/artefacts"
W=/root/cw-pcbab; rm -rf "$W"; mkdir -p "$W"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
CHAMP_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CAND_DIR=jobs/results/cpx62-0687-pcblues-prefs-finetune/artefacts
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
QS="qs_forcing_depth=6,qs_promo_depth=6"
NSH=$(( NCPU/2 )); [ "$NSH" -ge 1 ] || NSH=1
NOPEN=160; PAIRS=1; NMIN=250; SHTIMEOUT=3600

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

# hygiene disque + garde df (patron 0679)
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm /root 2>/dev/null|awk 'NR==2{print $4}')
say "=== 0689 GATE pcbprefs vs gen2-mmto — nproc=$NCPU NSH=$NSH df=${DFA}Mo ==="
[ "${DFA:-0}" -gt 3000 ] 2>/dev/null || { say "ABORT disque <3Go"; exit 3; }

git fetch origin main --quiet 2>/dev/null || true
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champion"; exit 4; }
HAVE=""
for A in 0.05 0.1; do
  if git show "origin/main:$CAND_DIR/pcbprefs_$A.pjtw.gz" 2>/dev/null | gunzip > "$W/cand_$A.pjtw" 2>/dev/null \
     && [ -s "$W/cand_$A.pjtw" ]; then HAVE="$HAVE $A"; else say "  (candidat $A absent — 0687 pas fini ou fit fail)"; fi
done
[ -n "$HAVE" ] || { say "ABORT: aucun candidat 0687 sur main — requeuer apres 0687"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0689 ABORT candidats absents"; exit 4; }
say "  candidats presents :$HAVE"

say "=== build jass (main) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0689 BUILD FAIL"; exit 6; }
J="$W/build/jass"
head -"$NOPEN" data/dilf_combinations.fen > "$W/open.fen"; NO=$(grep -c . "$W/open.fen")
say "  ✓ build ; openings=$NO (dilf_combinations — disjoint du fit PC Blues)"

for A in $HAVE; do
  say ""; say "=== GATE pcbprefs_$A vs gen2-mmto | d9 qs6 | ${NOPEN}op x${PAIRS} x2 sur $NSH shards ==="
  rm -f "$W"/g.*; pids=()
  for s in $(seq 0 $((NSH-1))); do
    timeout "$SHTIMEOUT" python3 tools/jass_vs_jass_arch.py \
      --jass-a "$J" --pattern-a "$W/cand_$A.pjtw" --jass-b "$J" --pattern-b "$W/champ.pjtw" \
      --search-params-a "$QS" --search-params-b "$QS" --depth 9 --pairs "$PAIRS" --max-plies 160 \
      --shard "$s" --nshards "$NSH" --quiet --openings-file "$W/open.fen" \
      --progress-file "$W/g.$s" >"$W/o.$s" 2>&1 &
    pids+=($!)
  done
  wait "${pids[@]}"
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
    open(outp,'w').write(f"  n={g} (<{nmin}) sur {shards} shards => INCONCLUANT (re-mesurer, ne PAS interpreter)\n")
else:
    r=(a+0.5*d)/g; se=0.5/(g**0.5); lo,hi=r-1.96*se,r+1.96*se; elo=-400*math.log10(1/r-1) if 0<r<1 else 999
    vd=("GAGNE hors-IC => le prof humain elite ajoute au-dela de gen2-mmto => confirmer haut-N puis phase 2 negatives" if lo>0.5 else
        ("PERD hors-IC => le fit prefs degrade => revoir anchor/volume avant phase 2" if hi<0.5 else
         "in-IC => signal deja capte par le search a ce N => phase 2 negatives ?/?? directement"))
    open(outp,'w').write(f"  W={a} L={b} D={d} n={g} ({shards} shards) rate={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}]\n  => {vd}\n")
PY
  say "  [pcbprefs_$A vs gen2-mmto | d9]"; cat "$W/.gate" | tee -a "$RES"
done

commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0689 gate pcbprefs vs gen2-mmto : verdicts" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin 0689 ==="
