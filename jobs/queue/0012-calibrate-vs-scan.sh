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

# Prerequisite: a quantised NNUE from any of our training jobs.
# Lookup order (newest cycle wins):
#   1. 0018 — Cycle 8 v5 (hybrid loss BCE) — current best by ~250 ELO
#             vs baseline at 1.0 s/move (PR #59 result: +304 ELO vs
#             handcrafted, vs 0011's +55 ELO).
#   2. 0016 (post-rename) / 0015 (stale path) — Cycle 8 v1-v4 (pure MSE).
#             Regressed vs baseline; included only as a fallback if 0018
#             somehow isn't there.
#   3. 0011 — pre-master-blend baseline.
NNUE_0018=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
NNUE_0016=$(ls -t /root/jass/jobs/results/0016-train-with-master-blend/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
NNUE_0015=$(ls -t /root/jass/jobs/results/0015-train-with-master-blend/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
NNUE_0011=$(ls -t /root/jass/jobs/results/0011-train-and-bench/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

if [ -n "$NNUE_0018" ] && [ -f "$NNUE_0018" ]; then
    NNUE_FILE="$NNUE_0018"
    NNUE_SOURCE="0018 (Cycle 8 v5, hybrid loss BCE)"
elif [ -n "$NNUE_0016" ] && [ -f "$NNUE_0016" ]; then
    NNUE_FILE="$NNUE_0016"
    NNUE_SOURCE="0016 (Cycle 8 v1-v4, MSE)"
elif [ -n "$NNUE_0015" ] && [ -f "$NNUE_0015" ]; then
    NNUE_FILE="$NNUE_0015"
    NNUE_SOURCE="0016 (Cycle 8 v1-v4, MSE, stale-0015 path)"
elif [ -n "$NNUE_0011" ] && [ -f "$NNUE_0011" ]; then
    NNUE_FILE="$NNUE_0011"
    NNUE_SOURCE="0011 (pre-master-blend baseline)"
else
    echo "ABORT: no quantised NNUE found from 0018/0016/0015/0011."
    echo "       Looked at:"
    echo "         /root/jass/jobs/results/0018-…/artefacts.src/nnue-*-q.bin"
    echo "         /root/jass/jobs/results/0016-…/artefacts.src/nnue-*-q.bin"
    echo "         /root/jass/jobs/results/0015-…/artefacts.src/nnue-*-q.bin"
    echo "         /root/jass/jobs/results/0011-…/artefacts.src/nnue-*-q.bin"
    exit 3
fi
BEST_NNUE_NAME=$(basename "$NNUE_FILE")
echo "=== NNUE under test: $NNUE_FILE ==="
echo "  source: $NNUE_SOURCE"
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
echo "  NNUE source:      $NNUE_SOURCE"
echo "  scan source:      rhalbersma/scan@master (pre-built scan_linux)"
echo "  budget:           1.0 s/move (no bitbases)"
echo "  wall:             ${WALL}s ($(python3 -c "print(round($WALL/60,1))") min)"
echo "  rc:               $RC"
echo "  result line:"
grep -E "score rate|ELO estimate|Jass=" "$ART/calibrate.log" | sed 's/^/    /' | tail -4
echo "=========================================================="
exit $RC
