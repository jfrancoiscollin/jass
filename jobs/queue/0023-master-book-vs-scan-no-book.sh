#!/usr/bin/env bash
# id: 0023-master-book-vs-scan-no-book
# description: Isolation diagnostic. 0019 (depth-12 book) and 0022
#              (master-freq book) both scored exactly 0/53/1 = -812
#              ELO against Scan-with-book. Two completely different
#              books → identical result means the book on jass's
#              side isn't the limiting factor: Scan's NATIVE book
#              (Letouzey-curated) is so strong it crushes jass
#              irrespective of which book jass loads.
#
#              This job isolates the variable: same NNUE, same
#              master-book.bok from 0022, but `--scan-book off`
#              (matching the 0012 baseline shape on Scan's side).
#
#              Reads:
#                jobs/results/0022-build-master-book-and-calibrate/
#                  artefacts/master-book.bok          (44 KB, 2772 entries)
#
#              Lecture:
#                * 0023 rate >> 0012 rate    →  master-book HELPS vs naked Scan.
#                                                The depth-12 book likely also helps,
#                                                but Scan-with-book dominates either
#                                                way. We should pursue v2 (hybrid).
#                * 0023 rate ≈ 0012 rate     →  master-book is neutral; it neither
#                                                helps nor hurts vs naked Scan.
#                                                v2 might still gain via NNUE filter,
#                                                but the marginal value is small.
#                * 0023 rate << 0012 rate    →  master-book HURTS even vs naked Scan.
#                                                Probable bug somewhere else
#                                                (HUB book handshake, move parsing,
#                                                 jass mishandling book-returned
#                                                 moves in its internal state).
# expected_duration: ~75 min on 4 vCPU CCX23 (calibrate is the bulk).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0023-master-book-vs-scan-no-book"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

# Same NNUE lookup chain as 0019/0022.
NNUE_0018=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
NNUE_0016=$(ls -t /root/jass/jobs/results/0016-train-with-master-blend/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
NNUE_0011=$(ls -t /root/jass/jobs/results/0011-train-and-bench/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
if   [ -n "$NNUE_0018" ] && [ -f "$NNUE_0018" ]; then
    NNUE_FILE="$NNUE_0018"; NNUE_SOURCE="0018 (Cycle 8 v5, hybrid BCE)"
elif [ -n "$NNUE_0016" ] && [ -f "$NNUE_0016" ]; then
    NNUE_FILE="$NNUE_0016"; NNUE_SOURCE="0016 (Cycle 8 v1-v4, MSE)"
elif [ -n "$NNUE_0011" ] && [ -f "$NNUE_0011" ]; then
    NNUE_FILE="$NNUE_0011"; NNUE_SOURCE="0011 (pre-master-blend baseline)"
else
    echo "ABORT: no quantised NNUE found"
    exit 3
fi

BOOK_FILE="/root/jass/jobs/results/0022-build-master-book-and-calibrate/artefacts/master-book.bok"
if [ ! -f "$BOOK_FILE" ]; then
    echo "ABORT: master-book not found at $BOOK_FILE — did 0022 finish?"
    exit 3
fi

echo "=== host facts ==="
echo "host:   $(hostname)"
echo "nproc:  $(nproc)"
echo "NNUE:   $NNUE_FILE"
echo "        source: $NNUE_SOURCE"
echo "book:   $BOOK_FILE ($(stat -c%s "$BOOK_FILE") B)"

echo
echo "=== rebuilding jass ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass:   $(./build/jass --version)"

SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then
    rm -rf "$SCAN_DIR"
    git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" \
        || { echo "ABORT: scan clone failed"; exit 4; }
    chmod +x "$SCAN_DIR/scan_linux"
fi

echo
echo "=== calibrate (54 games, 1.0 s/move): master-book on, scan-book OFF ==="
START=$(date +%s)
python3 tools/calibrate_vs_scan.py \
    --jass         /root/jass/build/jass \
    --scan         "$SCAN_DIR/scan_linux" \
    --movetime     1.0 \
    --pairs        3 \
    --nnue         "$NNUE_FILE" \
    --jass-book    "$BOOK_FILE" \
    --scan-book    off \
    2>&1 | tee "$ART/calibrate.log"
RC=${PIPESTATUS[0]}
WALL=$(( $(date +%s) - START ))

echo
echo "=========================================================="
echo "       0023 MASTER-BOOK vs NAKED-SCAN SUMMARY"
echo "=========================================================="
echo "  NNUE:           $(basename "$NNUE_FILE")  ($NNUE_SOURCE)"
echo "  jass book:      $(basename "$BOOK_FILE")  (44 KB, 2772 entries)"
echo "  scan book:      OFF"
echo "  budget:         1.0 s/move"
echo "  wall:           ${WALL}s ($(python3 -c "print(round($WALL/60,1))") min)"
echo "  result line:"
grep -E "score rate|ELO estimate|Jass=" "$ART/calibrate.log" | sed 's/^/    /' | tail -4
echo "=========================================================="
echo
echo "Comparison points:"
echo "  0012 baseline (no books either side): 0.07-0.13 score, ~-618 ELO"
echo "  0019 (depth-12 book, scan-book on):   0.009, -812 ELO"
echo "  0022 (master-book, scan-book on):     0.009, -812 ELO"
echo
echo "Interpret 0023:"
echo "  > 0.13 → master-book HELPS vs naked Scan. Go v2 (hybrid)."
echo "  ≈ 0.10 → master-book is neutral. Marginal v2 gain expected."
echo "  < 0.05 → master-book HURTS even vs naked Scan. Bug elsewhere."
exit "$RC"
