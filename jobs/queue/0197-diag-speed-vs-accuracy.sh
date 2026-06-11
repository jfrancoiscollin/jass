#!/usr/bin/env bash
# id: 0197-diag-speed-vs-accuracy
# description: DIAGNOSTIC — séparer le -685 ELO de v15 vs Scan en deux causes :
# VITESSE (v15 cherche moins profond) vs PRÉCISION (l'éval de v15 est moins
# bonne à profondeur égale). 0137 north-star = v15 mt=0.5s vs Scan = 0.019 ;
# mais le match depth-fixe de 0137 était CORROMPU (coups illégaux de Scan dus
# à un désync de buffer dans calibrate_vs_scan.py, corrigé DEPUIS via le thread
# lecteur + _drain). On rejoue donc proprement le match À PROFONDEUR ÉGALE.
#
#   * ACCURACY (livrable garanti) : match v15-vs-Scan à depth ∈ {7,9,11},
#     livres OFF, sans bitbases (FAIR). Si rate ≥ 0.5 → l'éval v15 vaut celle
#     de Scan à profondeur contrôlée → tout le -685 est de la VITESSE → l'archi
#     à viser = accumulateur incrémental + int8/AVX2 (cf. discussion). Si rate
#     ≪ 0.5 même à depth égale → l'éval n'y est pas → problème DONNÉES/FEATURES,
#     pas archi.
#   * SPEED (best-effort) : profondeur atteinte à movetime 0.5s par v15 et par
#     Scan (sonde hub brute). Quantifie le déficit de plies. Rappels : v15-128-64
#     = 0.92 Mnps / depth ~15 (0091).
#
# expected_duration: ~30-50 min (build + install Scan + 3 matchs courts).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/0197-diag-speed-vs-accuracy/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

# --- build ----------------------------------------------------------------
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
echo "jass : $($JASS --version 2>/dev/null)"

# --- Scan -----------------------------------------------------------------
SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then
    echo "=== installing Scan (rhalbersma/scan) ==="
    rm -rf "$SCAN_DIR"
    git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" || { echo "ABORT: git clone scan failed"; exit 4; }
    chmod +x "$SCAN_DIR/scan_linux"
fi
SCAN="$SCAN_DIR/scan_linux"
[ -x "$SCAN" ] || { echo "ABORT: scan binary missing"; exit 4; }
echo "scan : $SCAN ($(ls -lh "$SCAN" | awk '{print $5}'))"

# --- v15 weights ----------------------------------------------------------
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 weights introuvables"; exit 3; }
echo "v15 : $V15"
jrate(){ grep -oE 'Jass score rate:\s*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+' | head -1; }

# --- (1) ACCURACY : match à PROFONDEUR ÉGALE (harness corrigé) -------------
echo; echo "############ ACCURACY — v15 vs Scan à profondeur égale ############"
for D in 7 9 11; do
  echo "=== depth $D (livres off, no bitbases, 1t) ==="
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN" --nnue "$V15" \
      --depth "$D" --pairs 8 --jass-threads 1 >"$ART/eqd-$D.log" 2>&1
  echo "  depth $D : Jass score rate = $(jrate "$ART/eqd-$D.log")"
  grep -iE 'Jass=|Draws=|illegal' "$ART/eqd-$D.log" | tail -3
done

# --- (2) SPEED : profondeur atteinte @ movetime 0.5s (best-effort) ---------
echo; echo "############ SPEED — profondeur atteinte @ mt=0.5s (best-effort) ############"
python3 - "$SCAN" "$V15" "$JASS" >"$ART/speed-probe.log" 2>&1 <<'PY' || echo "  (sonde vitesse échouée — non bloquant)"
import sys, time
sys.path.insert(0, 'tools')
from calibrate_vs_scan import JassEngine, ScanEngine, jass_fen_to_scan_pos
SCAN, V15, JASS = sys.argv[1], sys.argv[2], sys.argv[3]
# jass @ mt=0.5s depuis startpos
j = JassEngine(JASS, nnue_path=V15)
j._send("position startpos"); j._send("fen")
fen = [l for l in j._read_until(lambda l: l.startswith("fen "))][-1][4:].strip()
j._send("position startpos"); j._drain(); j._send("go movetime 500")
for l in j._read_until(lambda l: l.startswith("bestmove"), timeout_s=15):
    if any(k in l for k in ("depth", "nodes", "bestmove")): print("JASS", l)
j.close()
# scan @ mt=0.5s, meme position
s = ScanEngine(SCAN)
pos = jass_fen_to_scan_pos(fen)
s._drain(); s._send(f"pos pos={pos}"); s._send("level move-time=0.5"); s._send("go think")
for l in s._read_until(lambda l: l.startswith("done") or l.startswith("error"), timeout_s=15):
    print("SCAN", l)
s.close()
PY
echo "--- sonde (lignes depth/nps) ---"
grep -iE 'depth|nps|nodes|done' "$ART/speed-probe.log" 2>/dev/null | tail -20

# --- VERDICT --------------------------------------------------------------
echo; echo "=========================================================="
echo "   0197 DIAG — VITESSE vs PRÉCISION (v15 vs Scan)"
echo "  ACCURACY (profondeur égale, FAIR) :"
for D in 7 9 11; do echo "    depth $D : rate = $(jrate "$ART/eqd-$D.log")"; done
echo "  SPEED : v15 ref 0.92 Mnps / depth ~15 @0.5s (0091) ; Scan depth@0.5s → voir sonde"
echo "  Rappel : v15 mt=0.5s vs Scan = 0.019 (0137, north-star)"
echo "  → rate ≥ 0.5 à depth égale = éval OK, tout le gap est VITESSE"
echo "       → archi : accumulateur incrémental + int8/AVX2 (NNUE rapide façon Kingsrow)."
echo "  → rate ≪ 0.5 à depth égale = éval insuffisante → DONNÉES/FEATURES, pas archi."
echo "=========================================================="
