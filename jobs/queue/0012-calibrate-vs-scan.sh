#!/usr/bin/env bash
# id: 0012-calibrate-vs-scan
# description: Measure the post-0011 NNUE strength against Scan
#              (Fabien Letouzey, GPL3, the standard external draughts
#              engine). Clones rhalbersma/scan — pre-built scan_linux
#              and data/ included — then runs calibrate_vs_scan.py
#              with the best quantized NNUE from 0011 at 1s/move
#              over 54 games. Reports Jass-vs-Scan score rate and
#              ELO estimate (95% CI ~ +-109 ELO at 54 games).
#
#              No bitbases on first run (they need a separate
#              download). Both engines run with --no-book by default
#              inside calibrate_vs_scan.py.
# expected_duration: ~45-90 min on 4 vCPU CCX23 (1.0s/move x 54 games)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0012-calibrate-vs-scan"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

# Prerequisite: 0011 produced a quantized JNNQ network.
NNUE_FILE=$(ls -t /root/jass/jobs/results/0011-train-and-bench/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
if [ -z "$NNUE_FILE" ] || [ ! -f "$NNUE_FILE" ]; then
    echo "ABORT: no nnue-*-q.bin found from 0011. Did 0011 finish successfully?"
    ls -la /root/jass/jobs/results/0011-train-and-bench/artefacts.src/ 2>/dev/null \
        || echo "  (0011 results directory missing entirely)"
    exit 3
fi
BEST_NNUE_NAME=$(basename "$NNUE_FILE")
echo "=== NNUE under test: $NNUE_FILE ==="
ls -lh "$NNUE_FILE"

echo
echo "=== host facts ==="
echo "host:   $(hostname)"
echo "nproc:  $(nproc)"
echo "mem:    $(free -h | awk '/^Mem:/ {print $2}')"
echo "disk:   $(df -h / | awk 'NR==2{print $4 \" free of \" $2}')"

echo
echo "=== rebuilding jass (no-op if src/ unchanged) ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass:   $(./build/jass --version)"

SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then
    echo
    echo "=== installing Scan (rhalbersma/scan, includes pre-built scan_linux + data/) ==="
    rm -rf "$SCAN_DIR"
    git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" \
        || { echo "ABORT: git clone failed (no network? GitHub rate-limit?)"; exit 4; }
    chmod +x "$SCAN_DIR/scan_linux"
fi
echo "scan binary: $SCAN_DIR/scan_linux"
ls -lh "$SCAN_DIR/scan_linux" "$SCAN_DIR/scan.ini" 2>&1 | head -3
echo "scan data files: $(ls "$SCAN_DIR/data/" 2>/dev/null | wc -l) files in data/"

# Sanity handshake: send "hub", expect "wait" within 5s.
echo
echo "=== Scan HUB handshake sanity ==="
( cd "$SCAN_DIR" && (echo "hub"; sleep 1) | timeout 5 ./scan_linux hub 2>&1 | head -20 ) \
    || echo "(handshake produced non-zero rc, may be normal if 'quit' wasn't sent)"

echo
echo "=== running calibrate_vs_scan.py (3 pairs x 9 openings x 2 colours = 54 games) ==="
START=$(date +%s)
python3 tools/calibrate_vs_scan.py \
    --jass     /root/jass/build/jass \
    --scan     "$SCAN_DIR/scan_linux" \
    --movetime 1.0 \
    --pairs    3 \
    --nnue     "$NNUE_FILE" \
    2>&1 | tee "$ART/calibrate.log"
RC=${PIPESTATUS[0]}
WALL=$(( $(date +%s) - START ))

echo
echo "=========================================================="
echo "             0012 CALIBRATE-VS-SCAN SUMMARY"
echo "=========================================================="
echo "  NNUE under test:  $BEST_NNUE_NAME"
echo "  scan source:      rhalbersma/scan@master (pre-built scan_linux)"
echo "  budget:           1.0 s/move (no bitbases)"
echo "  wall:             ${WALL}s ($(python3 -c "print(round($WALL/60,1))") min)"
echo "  rc:               $RC"
echo "  result line:"
grep -E "score rate|ELO estimate|Jass=" "$ART/calibrate.log" | sed 's/^/    /' | tail -4
echo "=========================================================="
exit $RC
