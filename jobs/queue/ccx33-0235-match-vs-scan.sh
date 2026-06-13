#!/usr/bin/env bash
# id: ccx33-0235-match-vs-scan
# description: ÉTOILE POLAIRE — match RÉEL de notre meilleur éval (full-fold 32-pat,
# 0227 gen8 +175 / repli 0231 gen8) contre SCAN (Letouzey, ~2500 FMJD) via calibrate_vs_scan.py
# (protocole HUB, color-swap, SANS bitbases = comparaison juste). Donne enfin l'écart ABSOLU
# en Elo — tout le reste est mesuré vs hc. Deux réglages : (A) profondeur égale d9 = qualité
# d'éval pure ; (B) temps égal 1s = force réelle (inclut notre lenteur d'éval, ratio 0.653).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0235-match-vs-scan/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SCAN_BIN=/root/jass-scan/scan_linux

# --- 0) Scan présent ? (binaire hors du tree git ; peut avoir disparu si box recyclée) ---
echo "=== probe Scan ==="
if [ ! -x "$SCAN_BIN" ]; then
  echo "ABORT: Scan introuvable à $SCAN_BIN — il faut le restaurer (rhalbersma/scan, GPL3,"
  echo "       build + scan.ini + data/ dans /root/jass-scan/). Aucun match possible sans lui."
  ls -la /root/jass-scan/ 2>&1 | head
  exit 3
fi
echo "  scan binary: $(ls -la "$SCAN_BIN" | awk '{print $5,$NF}')"
echo "  scan dir   : $(ls /root/jass-scan/ 2>/dev/null | tr '\n' ' ')"
[ -f /root/jass-scan/scan.ini ] && echo "  scan.ini   : present" || echo "  scan.ini   : MISSING (Scan may refuse to start)"

# --- 1) build jass (main = 32-pat, géométrie du gen8 32-pat) ---
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
echo "geometry: $(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)") patterns"

# --- 2) pick the best 32-pat full-fold eval available locally ---
E0227=/root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/gen8.pjtw
E0231=/root/jass/jobs/results/ccx33-0231-rfe-baseline32/artefacts.src/gen8.pjtw
EVAL=""
for cand in "$E0227" "$E0231"; do
  if [ -f "$cand" ]; then
    W=$(python3 -c "import struct;print(struct.unpack('<I',open('$cand','rb').read(8)[4:8])[0])" 2>/dev/null)
    echo "  candidate $cand : $W weights"
    EVAL="$cand"; break
  fi
done
[ -n "$EVAL" ] || { echo "ABORT: aucun gen8 32-pat local (0227/0231)"; exit 6; }
echo "EVAL = $EVAL"

run_match(){ # label  extra-args...
  local tag="$1"; shift
  echo; echo "=== MATCH vs Scan [$tag] : $* ==="
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" \
      --jass-pattern "$EVAL" --scan-bb-size 0 "$@" 2>&1 | tee "$ART/match-$tag.log" | tail -8
}

# --- 3) smoke test (Scan vivant + pont de protocole OK) avant les vrais matchs ---
echo "=== SMOKE (depth 6, 2 paires) ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" \
    --jass-pattern "$EVAL" --scan-bb-size 0 --depth 6 --pairs 2 >"$ART/smoke.log" 2>&1
if ! grep -q "Jass score rate" "$ART/smoke.log"; then
  echo "ABORT: smoke échoué — Scan ne répond pas / pont de protocole cassé :"; tail -25 "$ART/smoke.log"; exit 7
fi
echo "  smoke OK : $(grep -E 'score rate|ELO estimate' "$ART/smoke.log" | tr '\n' ' ')"

# --- 4) vrais matchs : qualité d'éval (depth égal) + force réelle (temps égal) ---
run_match "d9"      --depth 9    --pairs 24
run_match "mt1000"  --movetime 1000 --pairs 24

echo; echo "=========================================================="
echo "   ccx33-0235 — ÉCART RÉEL À SCAN (full-fold 32-pat, sans bitbases)"
echo "  eval = $(basename "$(dirname "$(dirname "$EVAL")")")/gen8"
for t in d9 mt1000; do
  echo "  [$t]  $(grep -E 'score rate|ELO estimate' "$ART/match-$t.log" 2>/dev/null | tr '\n' ' | ')"
done
echo "  (depth égal = qualité d'éval pure ; temps égal = force réelle incl. lenteur d'éval)"
echo "=========================================================="
