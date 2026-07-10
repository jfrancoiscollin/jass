#!/usr/bin/env bash
# id: ccx33-0667-scan-d14-sonde
# description: SONDE de calibration (check-list point 2) — mesure le RATE REEL de Scan-d14 sur ccx33 (8 coeurs) AVANT de sizer
# le vrai job boost gen2-mmto. Clone Scan (rhalbersma/scan), build jass, lance scan_selfplay_gen --depth 14 sur un TOUT PETIT
# volume (quelques parties, timeout), mesure secondes/partie + parents generes => rate d14 (parties/h, parents/h) + ETA
# extrapolee pour un volume-cible de parents. NE PRODUIT PAS de data utile — juste le chiffre pour sizer 0668. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0667-scan-d14-sonde/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0667-scan-d14-sonde/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-sonde-d14; rm -rf "$W"; mkdir -p "$W"
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DEPTH=14; GAMES=3; SHARDS=2; MAXPLIES=160; MINP=40; SKIP=8; DRAWFRAC=0.2; SHTIMEOUT=1500
TARGET_PARENTS=60000   # volume-cible hypothetique du boost, pour l'ETA extrapolee

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0; }

say "=== SONDE Scan-d14 (rate reel ccx33 8 coeurs) — HEAD $(git log --oneline -1|cat) — nproc=$NCPU ==="

# ---- Scan binaire (clone rhalbersma/scan) ----
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  SRC=/root/jass-scan-src; [ -d "$SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SRC" >"$W/sc.log" 2>&1
  mkdir -p /root/jass-scan; cp "$SRC/scan_linux" "$SCAN_BIN" 2>/dev/null && chmod +x "$SCAN_BIN"
  cp -r "$SRC/data" /root/jass-scan/data 2>/dev/null||true; cp "$SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null||true
fi
[ -x "$SCAN_BIN" ] || { say "ABORT Scan absent (clone rhalbersma/scan echoue)"; exit 3; }
say "  Scan ✓ : $SCAN_BIN"

# ---- build jass develop (arch_assert) ----
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp tools/scan_selfplay_gen.py; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true
done
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp tools/scan_selfplay_gen.py 2>/dev/null||true; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi: scan_eval SANS g_emasks"; restore_src; exit 5; }
grep -q "has_any_capture" src/search.cpp || { say "ABORT archi: search SANS has_any_capture"; restore_src; exit 5; }
say "  garde-fou archi ✓"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j2 --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 6; }
J="$W/build/jass"; say "  build jass ✓ (-j2 mem-safe)"

git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
say "  seeds=$(jnnw_count "$W/seeds.jnnw")"

# ---- micro-run Scan-d14, timing ----
say ""; say "=== micro-run : scan_selfplay_gen --depth $DEPTH, $GAMES parties × $SHARDS shards, timeout ${SHTIMEOUT}s ==="
T0=$(date +%s)
for s in $(seq 0 $((SHARDS-1))); do
  timeout "$SHTIMEOUT" python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$J" \
    --seeds "$W/seeds.jnnw" --out "$W/.sp-$s.jnnw" --games "$GAMES" \
    --max-plies "$MAXPLIES" --min-pieces "$MINP" --sample-every 1 --depth "$DEPTH" \
    --pref-parents "$W/.pp-$s.jnnw" --pref-moves "$W/.pm-$s.bin" \
    --skip-book "$SKIP" --keep-draw-frac "$DRAWFRAC" \
    --seed 66700 --nshards "$SHARDS" --shard "$s" >"$W/sp-$s.log" 2>&1 &
done; wait
T1=$(date +%s); ELAPSED=$((T1-T0))

# ---- mesure : parties finies + parents ; rate + ETA extrapolee ----
PARENTS=0; for f in "$W"/.pp-*.jnnw; do [ -f "$f" ] && PARENTS=$((PARENTS+$(jnnw_count "$f"))); done
GAMES_DONE=$(grep -hoE "games=[0-9]+|/[0-9]+ games|played [0-9]+" "$W"/sp-*.log 2>/dev/null | grep -oE "[0-9]+" | tail -1)
# fallback : si les shards ont fini (rc=0), ils ont joue GAMES*SHARDS parties
NDONE_SHARDS=$(ls "$W"/.pp-*.jnnw 2>/dev/null | wc -l)
python3 - "$ELAPSED" "$GAMES" "$SHARDS" "$NDONE_SHARDS" "$PARENTS" "$TARGET_PARENTS" "$NCPU" <<'PY' 2>&1 | tee -a "$RES"
import sys
el,games,shards,ndone,parents,target,ncpu=[int(x) for x in sys.argv[1:8]]
# parties reellement terminees = games * (shards ayant ecrit leur pref = fini)
games_done = games*ndone if ndone>0 else 0
print(f"  elapsed={el}s  shards_finis={ndone}/{shards}  parties_finies≈{games_done}  parents={parents}")
if games_done>0 and parents>0:
    spg = el/games_done                       # secondes/partie (2 shards paralleles => wall)
    ppg = parents/games_done                  # parents/partie (yield)
    # rate a pleine echelle sur ncpu shards : parties/h = 3600/spg * (ncpu/shards) approx (spg mesure a 'shards' shards)
    games_per_h_full = 3600.0/spg * (ncpu/shards) if spg>0 else 0
    parents_per_h_full = games_per_h_full*ppg
    eta_h = target/parents_per_h_full if parents_per_h_full>0 else 0
    games_needed = target/ppg if ppg>0 else 0
    print(f"  => Scan-d14 : ~{spg:.1f}s/partie (wall, {shards} shards), yield ~{ppg:.1f} parents/partie")
    print(f"  => plein regime {ncpu} shards : ~{games_per_h_full:.0f} parties/h, ~{parents_per_h_full:.0f} parents/h")
    print(f"  => POUR {target} parents cibles : ~{games_needed:.0f} parties, ETA self-play ~{eta_h:.1f}h (+ gen-siblings+fit+gate)")
else:
    print(f"  ⚠ INCONCLUANT : aucune partie finie dans le timeout (Scan-d14 trop lent pour {games} parties en {el}s)")
    print(f"     => baisser GAMES ou augmenter SHTIMEOUT ; NE PAS sizer le boost sur ce run.")
PY
tail -3 "$W/sp-0.log" 2>/dev/null | sed 's/^/    sp-0: /' | tee -a "$RES"
restore_src
say ""; say "  => rate/ETA ci-dessus fondent le sizing du job boost gen2-mmto (0668). GO JFC requis avant de le lancer."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0667 FIN sonde Scan-d14 : rate reel ccx33 pour sizer le boost gen2-mmto" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin sonde Scan-d14 ==="
