#!/usr/bin/env bash
# id: ccx33-0433-match-vs-scan
# description: MATCH de calibration — champion 32cf (fit L2=3e-5@35M, le plus fort) vs SCAN (Letouzey) a CONDITIONS
# COMPARABLES : MEME profondeur fixe des 2 cotes, et AUCUN endgame DB ni cote (jass sans JASS_EGDB_PATH, Scan
# --scan-bb-size 0) => compa pure eval+search. ⚠️ HORS-PLATEAU : a lire comme ORDRE DE GRANDEUR (vs-Scan au plancher
# est bruite ±0.05, cf regle metrique). Probe Scan d'abord (binaire hors-tree /root/jass-scan, peut avoir disparu au
# recyclage box -> abort propre). Resultat leger (score + Elo estime), rien de lourd committe.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0433-match-vs-scan/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"
say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-vs-scan; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
DEPTH=11; PAIRS=40        # 80 parties (40 paires, couleurs alternees) ; depth fixe partage = conditions comparables
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz

# ---------- 0) probe Scan (sans lui, aucun match possible) ----------
say "=== probe Scan ($SCAN_BIN) ==="
if [ ! -x "$SCAN_BIN" ]; then
  say "ABORT: Scan introuvable a $SCAN_BIN (binaire hors-tree, perdu au recyclage box ?)."
  say "  Pour le restaurer : build rhalbersma/scan (GPL3) + scan.ini + data/ dans /root/jass-scan/."
  ls -la /root/jass-scan/ 2>&1 | head | sed 's/^/  /' | tee -a "$RES"
  exit 4
fi
[ -f /root/jass-scan/scan.ini ] && say "  scan.ini : present" || say "  scan.ini : MANQUANT (Scan peut refuser de demarrer)"
say "  scan dir : $(ls /root/jass-scan/ 2>/dev/null | tr '\n' ' ')"

# ---------- 1) build jass (memes extras que le champion ; PAS d'EGDB compile -> aucun DB, pas besoin du clone) ----------
say "=== build jass (32-pat, extras = build du champion, sans EGDB) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
    >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log" | sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log" | sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT: attendait 32 patterns, a $NP"; exit 7; }

# ---------- 2) champion 3e-5 ----------
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion 3e-5 absent ($CHAMP_GZ)"; exit 4; }
say "# champion = w32 fit L2=3e-5 @35M (le plus fort 32cf connu)"

# ---------- 3) match a conditions comparables (depth fixe, aucun endgame DB des 2 cotes) ----------
unset JASS_EGDB_PATH        # jass SANS egdb (equite vs --scan-bb-size 0)
say "=== MATCH : champion 32cf vs Scan | depth=${DEPTH} (partage) | ${PAIRS} paires = $((PAIRS*2)) parties | no-DB des 2 cotes ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
    --scan-bb-size 0 --depth "$DEPTH" --pairs "$PAIRS" 2>&1 | tee "$W/match.log" | tail -20 | sed 's/^/  /' | tee -a "$RES"

# ---------- 4) resume score + Elo (best-effort depuis la sortie de l'outil) ----------
say "=== RESUME ==="
python3 - "$W/match.log" <<'PY' 2>/dev/null | tee -a "$RES" || say "(parsing score: voir match.log)"
import re,sys,math
t=open(sys.argv[1]).read()
m=re.findall(r'(\d+)\s*[-/]\s*(\d+)\s*[-/]\s*(\d+)', t)  # heuristique W-D-L
# cherche un score 0..1 explicite
s=re.findall(r'score[^0-9]*([01]?\.\d+)', t, re.I)
if s:
    sc=float(s[-1]); elo=-400*math.log10(1/sc-1) if 0<sc<1 else float('nan')
    print(f"  score champion vs Scan = {sc:.3f}  (~{elo:+.0f} Elo)")
else:
    print("  (score non parse automatiquement — lire les dernieres lignes ci-dessus)")
PY
say "# LECTURE : ~0.5 = a egalite ; <0.5 = on est sous Scan (de combien = l'ecart restant). Bruite, ordre de grandeur."
