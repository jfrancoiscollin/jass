#!/usr/bin/env bash
# id: 0029-diag-book-jass-vs-jass
# description: Diagnostic for the --book bug. 0019, 0022, 0023 all
#              finalised at EXACTLY 0/53/1 = -812 ELO vs Scan, with
#              three completely different books (depth-12 build,
#              master-frequency) and with/without Scan's native book.
#              That bit-identical result rules out the obvious
#              hypotheses (jass-book quality, Scan-book strength) and
#              points at a bug inside jass's `--book` codepath itself.
#
#              This job isolates the variable: SAME jass binary on BOTH
#              sides of the match, SAME v5 NNUE, the only difference is
#              one side has `--book master-book.bok` loaded and the
#              other doesn't. If jass-with-book loses to jass-without-
#              book in the same engine, the book chain is corrupting
#              state somewhere; the per-game move log pinpoints the
#              failure ply.
#
#              Setup: 18 games (9 openings × 2 colours × 1 pair),
#              depth-controlled via movetime=1.0s per move so we match
#              the calibrate_vs_scan compute budget. Should finish in
#              ~30 min wall on 4 vCPU.
#
#              Reads:
#                jobs/results/0022-build-master-book-and-calibrate/
#                  artefacts/master-book.bok          (the v1 book)
#                jobs/results/0018-train-with-master-bce/
#                  artefacts.src/nnue-*-q.bin          (v5 NNUE)
# expected_duration: ~25-30 min on 4 vCPU CCX23.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0029-diag-book-jass-vs-jass"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NNUE_FILE=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
BOOK_FILE="/root/jass/jobs/results/0022-build-master-book-and-calibrate/artefacts/master-book.bok"

if [ -z "$NNUE_FILE" ] || [ ! -f "$NNUE_FILE" ]; then
    echo "ABORT: v5 NNUE not found (0018)"; exit 3
fi
if [ ! -f "$BOOK_FILE" ]; then
    echo "ABORT: master book not found (0022)"; exit 3
fi

echo "=== host facts ==="
echo "host:  $(hostname)"
echo "nproc: $(nproc)"
echo "NNUE:  $NNUE_FILE"
echo "book:  $BOOK_FILE ($(stat -c%s "$BOOK_FILE") B)"

echo
echo "=== rebuilding jass ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass: $(./build/jass --version)"

echo
echo "=== diag: jass+book vs jass-no-book (same binary, same NNUE) ==="
START=$(date +%s)
python3 tools/diag_book_jass_vs_jass.py \
    --jass     /root/jass/build/jass \
    --book     "$BOOK_FILE" \
    --nnue     "$NNUE_FILE" \
    --movetime 1.0 \
    --pairs    1 \
    -o         "$ART/trace.log" \
    2>&1 | tee "$ART/diag.log"
RC=${PIPESTATUS[0]}
WALL=$(( $(date +%s) - START ))

echo
echo "=========================================================="
echo "       0029 DIAG BOOK JASS-VS-JASS SUMMARY"
echo "=========================================================="
echo "  budget:     1.0 s/move (matches calibrate_vs_scan)"
echo "  games:      18 (9 openings × 2 colours × 1 pair)"
echo "  wall:       ${WALL}s ($(python3 -c "print(round($WALL/60,1))") min)"
echo "  trace tail (last 80 lines of move-by-move):"
tail -80 "$ART/trace.log" | sed 's/^/    /'
echo "=========================================================="
echo
echo "Look in $ART/trace.log for the per-game move sequences. If"
echo "book-side rate is much below 0.50, the book corrupts jass."
echo "The first plies of any losing game show whether the book is"
echo "returning bad moves or if the loss happens post-book."
exit "$RC"
