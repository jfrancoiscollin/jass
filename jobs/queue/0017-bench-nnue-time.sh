#!/usr/bin/env bash
# id: 0017-bench-nnue-time
# description: Bench the freshly-trained NNUE (from 0016) against the
#              handcrafted eval at 1.0 s/move. This is the *progress*
#              KPI we needed but couldn't get from calibrate-vs-Scan:
#              that one clamps at 0/N (ELO -800) whenever Jass is more
#              than ~400 ELO weaker than Scan, which has been every
#              single run so far — making it useless as a delta metric
#              between training iterations.
#
#              By contrast, the handcrafted eval is a stable reference:
#              the engine code and weights haven't changed since long
#              before NNUE training began. So a "NNUE score rate" vs
#              handcrafted at 1 s/move is a fine-grained signal that
#              moves whenever any of {trainer, data, encoding, arch,
#              search} changes meaningfully.
#
#              Reads the best NNUE produced by 0016 (the train-with-
#              master-blend job) — falls back to 0011's pre-Cycle-8
#              NNUE if 0016 hasn't run yet, so this job is useful
#              even before Cycle 8 finalizes.
# expected_duration: ~45-90 min on 4 vCPU CCX23 (54 games × 1s/move ×
#                    ~50-100 plies/game; same shape as 0012 but two
#                    Jass subprocesses are lighter than Jass + Scan).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0017-bench-nnue-time"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

# Prefer 0016's NNUE (Cycle 8 master-blend); fall back to 0011's
# (pre-master-blend baseline) if 0016 hasn't run. Either gives a
# usable bench number — and running the same script against both
# in sequence (manual re-queue between) lets us measure the
# Cycle 8 delta directly.
#
# Path note: 0016's script was renamed from 0015 → 0016 in PR #47 but
# its internal OUT_BASE still says 0015 (a stale literal). Until that
# is fixed in a follow-up PR, the Cycle-8 master-blend NNUE actually
# lands under the 0015-* path on disk. We probe both locations and use
# whichever has the freshest *-q.bin.
NNUE_0016=$(ls -t /root/jass/jobs/results/0016-train-with-master-blend/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
NNUE_0015=$(ls -t /root/jass/jobs/results/0015-train-with-master-blend/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
NNUE_0011=$(ls -t /root/jass/jobs/results/0011-train-and-bench/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

if [ -n "$NNUE_0016" ] && [ -f "$NNUE_0016" ]; then
    NNUE="$NNUE_0016"
    SOURCE="0016 (Cycle 8 master-blend, post-rename path)"
elif [ -n "$NNUE_0015" ] && [ -f "$NNUE_0015" ]; then
    NNUE="$NNUE_0015"
    SOURCE="0016 (Cycle 8 master-blend, stale-0015 path)"
elif [ -n "$NNUE_0011" ] && [ -f "$NNUE_0011" ]; then
    NNUE="$NNUE_0011"
    SOURCE="0011 (pre-master-blend baseline)"
else
    echo "ABORT: no quantised NNUE found from 0016/0015/0011."
    echo "       Looked at:"
    echo "         /root/jass/jobs/results/0016-…/artefacts.src/nnue-*-q.bin"
    echo "         /root/jass/jobs/results/0015-…/artefacts.src/nnue-*-q.bin"
    echo "         /root/jass/jobs/results/0011-…/artefacts.src/nnue-*-q.bin"
    echo "Re-queue this job once at least one training run has finished."
    exit 3
fi

echo "=== host facts ==="
echo "host:     $(hostname)"
echo "nproc:    $(nproc)"
echo "mem:      $(free -h | awk '/^Mem:/ {print $2}')"

echo
echo "=== rebuilding jass (no-op if src/ unchanged) ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass:     $(./build/jass --version 2>/dev/null || echo '(no --version)')"

echo
echo "=== NNUE under test ==="
echo "  source:   $SOURCE"
echo "  path:     $NNUE"
echo "  size:     $(ls -lh "$NNUE" | awk '{print $5}')"

echo
echo "=== running bench (NNUE vs Handcrafted, 1.0 s/move, 54 games) ==="
START=$(date +%s)
python3 tools/bench_nnue_time.py \
    --jass     /root/jass/build/jass \
    --nnue     "$NNUE" \
    --movetime 1.0 \
    --pairs    3 \
    2>&1 | tee "$ART/bench.log"
RC=${PIPESTATUS[0]}
WALL=$(( $(date +%s) - START ))

echo
echo "=========================================================="
echo "             0017 BENCH-NNUE-TIME SUMMARY"
echo "=========================================================="
echo "  NNUE source:      $SOURCE"
echo "  NNUE file:        $(basename "$NNUE")"
echo "  budget:           1.0 s/move"
echo "  games:            54 (9 openings × 3 pairs × 2 colours)"
echo "  wall:             ${WALL}s ($(python3 -c "print(round($WALL/60,1))") min)"
echo "  rc:               $RC"
echo "  result line:"
grep -E "score rate|ELO estimate|NNUE=" "$ART/bench.log" | tail -3 | sed 's/^/    /'
echo "=========================================================="
exit "$RC"
