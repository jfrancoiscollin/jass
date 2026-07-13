#!/usr/bin/env bash
# id: cpx62-0708-b3-convself-gate
# description: GATE B3 (L3 bloquant 2) — valide l'instrument conv_self.py. conv_self = P(vraie victoire | avantage
# matériel >=3 pièces) sur lot témoin adjud-OFF (self-play champion, play_game). C'est le critère qui pilote l'escalier
# d'adjud (fade éval-driven, leçon 0702). GATE = MONOTONIE : conv_self(zero) < conv_self(gen2-mmto) (un champion qui
# CONVERTIT doit scorer plus haut qu'une éval aveugle). Sharded (NSH). PUR offline, pas d'egdb. AUCUN NNUE.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0708.lock
if ! flock -n 9; then echo "ABORT 0708 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0708-b3-convself-gate/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0708-b3-convself-gate/artefacts"
W=/root/cw-0708
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
GAMES=306; DEPTH=8; LEAD=3; MAXPLIES=260; NSH="$NCPU"; SHARD_TIMEOUT=3000

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== GATE B3 conv_self — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show "origin/$SRC_BRANCH:tools/conv_self.py" > tools/conv_self.py 2>/dev/null || true
git show "origin/$SRC_BRANCH:pattern_jass/tools/make_bootstrap_eval.py" > pattern_jass/tools/make_bootstrap_eval.py 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src tools/calibrate_vs_scan.py 2>/dev/null||true; rm -f tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; }
[ -s tools/conv_self.py ] && [ -s pattern_jass/tools/make_bootstrap_eval.py ] || { say "ABORT: outils absents de $SRC_BRANCH"; restore_src; exit 5; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py || { say "ABORT py_compile"; restore_src; exit 5; }

say "=== build jass (v4) ==="
cmake -S . -B "$W/build" $FLAGS >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0708 BUILD FAIL"; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/zero.pjtw" --like "$W/gen2.pjtw" --men 0 --king 0 --king-center 0 --mobility 0 >/dev/null
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' > "$W/open.fen"
NO=$(grep -c . "$W/open.fen"); say "  ✓ build ; openings=$NO ; games=$GAMES depth=$DEPTH lead=$LEAD"

run_champ(){ # $1=label $2=pattern
  local lab="$1" pat="$2"; local pids=()
  for s in $(seq 0 $((NSH-1))); do
    timeout "$SHARD_TIMEOUT" python3 tools/conv_self.py --jass "$J" --pattern "$pat" \
      --openings-file "$W/open.fen" --games "$GAMES" --depth "$DEPTH" --lead "$LEAD" --max-plies "$MAXPLIES" \
      --shard "$s" --nshards "$NSH" --out "$W/cs_${lab}.$s.json" >"$W/cs_${lab}.$s.log" 2>&1 & pids+=($!)
  done
  wait "${pids[@]}"
  python3 - "$lab" "$W"/cs_${lab}.*.json <<'PY'
import json,sys
lab=sys.argv[1]; R=C=D=G=P=0
for f in sys.argv[2:]:
    try: j=json.load(open(f)); R+=j["n_reached"]; C+=j["n_converted"]; D+=j["n_draw"]; G+=j["n_games"]; P+=j["n_cap"]
    except Exception: pass
cs = C/R if R else float('nan')
print(f"{lab} {G} {R} {C} {D} {P} {cs:.4f}")
PY
}
say ""; say "=== conv_self sharded ($NSH) : zero vs gen2-mmto ==="
read _ ZG ZR ZC ZD ZP ZCS < <(run_champ zero "$W/zero.pjtw" | tail -1); say "  zero      : games=$ZG reached=$ZR conv=$ZC draw=$ZD cap=$ZP conv_self=$ZCS"
read _ GG GR GC GD GP GCS < <(run_champ gen2 "$W/gen2.pjtw" | tail -1); say "  gen2-mmto : games=$GG reached=$GR conv=$GC draw=$GD cap=$GP conv_self=$GCS"

say ""; say "=== VERDICT GATE B3 (monotonie conv_self) ==="
python3 - "$ZCS" "$ZR" "$GCS" "$GR" <<'PY' | tee -a "$RES"
import sys,math
zcs=float(sys.argv[1]); zr=int(sys.argv[2]); gcs=float(sys.argv[3]); gr=int(sys.argv[4])
if zr<20 or gr<20:
    print(f"  INCONCLUANT : n_reached bas (zero={zr}, gen2={gr}) — augmenter games/depth (jamais 'neutre')"); sys.exit(0)
mono = gcs > zcs
print(f"  conv_self : zero={zcs:.4f} (n_reached={zr})  <  gen2-mmto={gcs:.4f} (n_reached={gr}) ?  => {'OUI ✓' if mono else 'NON ✗'}")
print(f"  => {'ADMIS — conv_self monotone (zero<gen2) : instrument valide, pilote l escalier d adjud' if mono else 'ÉCHEC — conv_self non monotone : instrument cassé, corriger avant T-0'}")
PY
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0708 FIN gate B3 conv_self : zero=$ZCS gen2=$GCS (monotone attendu)" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0708 FINI ==="
rm -rf "$W"
