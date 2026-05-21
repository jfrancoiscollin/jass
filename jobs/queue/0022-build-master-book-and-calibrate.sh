#!/usr/bin/env bash
# id: 0022-build-master-book-and-calibrate
# description: v1 master-frequency book + fair-comparison vs Scan.
#              0019 measured the current depth-12-built book at -812
#              ELO vs Scan — worse than the no-book baseline (-618).
#              Hypothesis: the 0013 book was built with the OLD NNUE
#              at depth 12, which is shallow for opening theory;
#              jass picks a tactically-fine but strategically-bad
#              move, then loses in the middlegame.
#
#              This job builds a different kind of book: master
#              frequencies (Lidraughts games, rating >= 2000, first
#              16 plies). For each position reached by >=3 games, we
#              keep the most-played master move. No engine search —
#              just trust the masters. If the v1 still regresses, we
#              add NNUE validation in 0023 (hybrid).
#
#              Then re-runs the fair-comparison vs Scan (same shape
#              as 0019, same NNUE, same Scan settings) so the score
#              rate is directly comparable.
#
# expected_duration: ~10-20 min book build (~6K games, replay only)
#                    + ~75 min calibrate vs Scan = ~90 min total.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0022-build-master-book-and-calibrate"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DB="/root/jass/data/expert_games.db"
if [ ! -f "$DB" ]; then
    echo "ABORT: $DB not found — was 0014 run on this host?"
    exit 3
fi

# Same NNUE lookup chain as 0019.
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

echo "=== host facts ==="
echo "host:   $(hostname)"
echo "nproc:  $(nproc)"
echo "mem:    $(free -h | awk '/^Mem:/ {print $2}')"
echo "db:     $DB ($(stat -c%s "$DB") B)"
echo "NNUE:   $NNUE_FILE"
echo "        source: $NNUE_SOURCE"

echo
echo "=== rebuilding jass ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass:   $(./build/jass --version)"

# ---------------------------------------------------------------------------
# Phase 1: extract master-frequency (FEN, move) pairs.
# ---------------------------------------------------------------------------
PAIRS="$ART/master-pairs.tsv"
BOOK="$ART/master-book.bok"
echo
echo "=== Phase 1: extracting master moves (rating>=2000, plies<16, min-count=3) ==="
START_P1=$(date +%s)
python3 tools/build_master_book.py \
    --db         "$DB" \
    --jass       /root/jass/build/jass \
    --out        "$PAIRS" \
    --min-rating 2000 \
    --max-plies  16 \
    --min-count  3 \
    2>&1 | tee "$ART/build.log"
RC1=${PIPESTATUS[0]}
WALL_P1=$(( $(date +%s) - START_P1 ))
if [ "$RC1" -ne 0 ]; then
    echo "ABORT: build_master_book.py failed rc=$RC1"
    exit "$RC1"
fi
echo "phase 1: ${WALL_P1}s, $(wc -l < "$PAIRS") rows in $PAIRS"

# ---------------------------------------------------------------------------
# Phase 2: pack pairs into a JBOK file via the new C++ subcommand.
# ---------------------------------------------------------------------------
echo
echo "=== Phase 2: packing pairs into JBOK ==="
./build/jass --build-book-from-moves "$PAIRS" "$BOOK" \
    2>&1 | tee -a "$ART/build.log"
ls -lh "$BOOK"

# ---------------------------------------------------------------------------
# Phase 3: fair-comparison calibrate vs Scan (same shape as 0019).
# ---------------------------------------------------------------------------
SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then
    rm -rf "$SCAN_DIR"
    git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" \
        || { echo "ABORT: scan clone failed"; exit 4; }
    chmod +x "$SCAN_DIR/scan_linux"
fi
echo
echo "=== Phase 3: calibrate vs Scan (54 games, 1.0 s/move, master book) ==="
START_P3=$(date +%s)
python3 tools/calibrate_vs_scan.py \
    --jass         /root/jass/build/jass \
    --scan         "$SCAN_DIR/scan_linux" \
    --movetime     1.0 \
    --pairs        3 \
    --nnue         "$NNUE_FILE" \
    --jass-book    "$BOOK" \
    --scan-book    on \
    2>&1 | tee "$ART/calibrate.log"
RC3=${PIPESTATUS[0]}
WALL_P3=$(( $(date +%s) - START_P3 ))

echo
echo "=========================================================="
echo "       0022 MASTER-BOOK v1 + CALIBRATE SUMMARY"
echo "=========================================================="
echo "  NNUE:                $(basename "$NNUE_FILE")  ($NNUE_SOURCE)"
echo "  master pairs:        $(wc -l < "$PAIRS") rows (rating>=2000, plies<16, min_count=3)"
echo "  jass book:           $(basename "$BOOK") ($(stat -c%s "$BOOK") B)"
echo "  build wall:          ${WALL_P1}s"
echo "  calibrate wall:      ${WALL_P3}s"
echo "  result line:"
grep -E "score rate|ELO estimate|Jass=" "$ART/calibrate.log" | sed 's/^/    /' | tail -4
echo "=========================================================="
echo
echo "Delta vs 0019 (depth-12 0013 book): 0022 rate - 0019 rate"
echo "  0019 was 0.009 (0.5/54), ELO -812."
echo "  If 0022 > 0.05 the master book strictly beats the depth-12 build."
echo "  If 0022 still < 0.10 we move to v2 (hybrid: master + NNUE validation)."
exit "$RC3"
