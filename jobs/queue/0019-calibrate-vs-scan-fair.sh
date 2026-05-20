#!/usr/bin/env bash
# id: 0019-calibrate-vs-scan-fair
# description: "Armes-égales" calibrate of the v5 NNUE vs Scan.
#              Same NNUE + same 54-game match shape as 0012, but with
#              both engines' opening books AND endgame bitbases enabled
#              instead of disabled. Lets us separate eval+search
#              strength (0012) from full-engine strength (0019).
#
#              0012 measured the v5 NNUE at "X / 54" with both books
#              and bitbases off — pure eval contest. 0019 enables:
#                * jass: --book openings-77k-depth12.bok from 0013
#                * scan: native book (set-param book=true)
#                * jass: native KvK / KKvK bitbase (always on, no flag)
#                * scan: NO bitbase (bb-size=0 default). The earlier
#                        attempt with bb-size=6 hung Scan for 6.5h —
#                        rhalbersma/scan's data/ dir doesn't actually
#                        ship the 6-piece bitbase data (readme.txt
#                        warns "bitbases require a separate copy or
#                        download"). So we keep Scan's bitbase off
#                        and accept the residual endgame asymmetry
#                        (jass: KvK/KKvK, Scan: nothing in 0019).
#              Reading the delta as "ELO contribution from book
#              alone" (vs 0012 which had both books AND bitbases off).
#
#              Read the delta (0019 score rate − 0012 score rate) as
#              "how much do book + endgame add to the engine on top
#              of NNUE+search alone".
#
# expected_duration: ~80-90 min on 4 vCPU CCX23 (same as 0012; the
#                    book lookup is fast, the bitbase costs <1 ms per
#                    endgame query).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0019-calibrate-vs-scan-fair"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

# Prerequisites:
#   - a quantised NNUE from 0018 (v5) or fallback chain
#   - the opening book from 0013

# NNUE lookup: same order as 0012.
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
    exit 3
fi

# Book lookup. 0013 commits its book under artefacts/ (small file).
BOOK_FILE="/root/jass/jobs/results/0013-build-book/artefacts/openings-77k-depth12.bok"
if [ ! -f "$BOOK_FILE" ]; then
    echo "ABORT: opening book not found at $BOOK_FILE — did 0013 finish?"
    ls -la /root/jass/jobs/results/0013-build-book/artefacts/ 2>/dev/null \
        || echo "  (0013 results directory missing)"
    exit 3
fi

echo "=== fair-comparison calibrate setup ==="
echo "  NNUE under test:  $NNUE_FILE"
echo "    source:         $NNUE_SOURCE"
echo "  opening book:     $BOOK_FILE"
ls -lh "$NNUE_FILE" "$BOOK_FILE"

echo
echo "=== host facts ==="
echo "host:   $(hostname)"
echo "nproc:  $(nproc)"
echo "mem:    $(free -h | awk '/^Mem:/ {print $2}')"

echo
echo "=== rebuilding jass (no-op if src/ unchanged) ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass:   $(./build/jass --version)"

SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then
    echo
    echo "=== installing Scan (rhalbersma/scan) ==="
    rm -rf "$SCAN_DIR"
    git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" \
        || { echo "ABORT: git clone failed"; exit 4; }
    chmod +x "$SCAN_DIR/scan_linux"
fi
echo "scan: $SCAN_DIR/scan_linux ($(ls -lh "$SCAN_DIR/scan_linux" | awk '{print $5}'))"
echo "scan data files: $(ls "$SCAN_DIR/data/" 2>/dev/null | wc -l) entries"

# Sanity ping.
echo
echo "=== Scan HUB handshake sanity ==="
( cd "$SCAN_DIR" && (echo "hub"; sleep 1) | timeout 5 ./scan_linux hub 2>&1 | head -15 ) \
    || echo "(handshake non-zero rc, may be normal)"

echo
echo "=== running calibrate_vs_scan.py (54 games, 1.0 s/move, fair) ==="
echo "  flags: --jass-book $(basename "$BOOK_FILE")"
echo "         --scan-book on  (no --scan-bb-size — bitbase data not shipped)"
START=$(date +%s)
python3 tools/calibrate_vs_scan.py \
    --jass         /root/jass/build/jass \
    --scan         "$SCAN_DIR/scan_linux" \
    --movetime     1.0 \
    --pairs        3 \
    --nnue         "$NNUE_FILE" \
    --jass-book    "$BOOK_FILE" \
    --scan-book    on \
    2>&1 | tee "$ART/calibrate.log"
RC=${PIPESTATUS[0]}
WALL=$(( $(date +%s) - START ))

echo
echo "=========================================================="
echo "       0019 CALIBRATE-VS-SCAN-FAIR SUMMARY"
echo "=========================================================="
echo "  NNUE under test:    $(basename "$NNUE_FILE")"
echo "  NNUE source:        $NNUE_SOURCE"
echo "  jass book:          $(basename "$BOOK_FILE") ($(stat -c%s "$BOOK_FILE") B)"
echo "  scan book:          on  (native)"
echo "  scan bb-size:       0  (bitbase data not shipped in rhalbersma/scan)"
echo "  budget:             1.0 s/move"
echo "  wall:               ${WALL}s ($(python3 -c "print(round($WALL/60,1))") min)"
echo "  rc:                 $RC"
echo "  result line:"
grep -E "score rate|ELO estimate|Jass=" "$ART/calibrate.log" | sed 's/^/    /' | tail -4
echo "=========================================================="
echo
echo "To read the 'book + bitbase contribution' delta:"
echo "  0019 rate − 0012 rate ≈ book + endgame ELO contribution"
exit "$RC"
