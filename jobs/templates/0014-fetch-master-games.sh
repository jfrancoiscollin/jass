#!/usr/bin/env bash
# id: 0014-fetch-master-games
# description: Cycle 8-pre — populate /root/jass/data/expert_games.db with
#              Lidraughts games (rating 1600–2300, standard variant) and
#              convert the result to a JNNW training-record file consumable
#              by train_v3.py --master-data on the next cycle.
#
#              Idempotent: re-running picks up where it left off via the
#              UNIQUE (source, source_id) constraint in expert_games and the
#              `fetcher_state.drained_users` checkpoint. Long-running OK —
#              the runner heartbeat tracks the artefacts directory.
#
#              See README "Roadmap — extraction de master games" for the
#              wider context. This job does NOT trigger training; that's a
#              separate downstream job (Cycle 8 proper) that consumes the
#              produced master.jnnw.
#
# expected_duration: highly variable. Discovery + downloads dominated by
#                    Lidraughts API latency at the configured --rate-sleep.
#                    100K games target × ~0.5 s/user round-trip ÷ 200 games
#                    per user ≈ 500 users × 0.5 s ≈ 4 min discovery + the
#                    actual game payload (~1–5 GB compressed-text over the
#                    wire). Plan for ~6–24 h end-to-end including the
#                    pdn_to_jnnw conversion pass.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0014-fetch-master-games"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART" /root/jass/data

DB="/root/jass/data/expert_games.db"
SCHEMA="/root/jass/data/expert_games.schema.sql"

# Target: 100K games at rating 1600-2300, standard variant. Adjust here
# if a future re-queue wants a different goal.
TARGET_GAMES=100000
MIN_RATING=1600
MAX_RATING=2300
PER_USER_CAP=200
RATE_SLEEP=0.5   # seconds between per-user requests, polite to Lidraughts

echo "=== host facts ==="
echo "host:   $(hostname)"
echo "nproc:  $(nproc)"
echo "disk:   $(df -h /root | awk 'NR==2{print $4\" free of \"$2}')"
echo "python: $(python3 --version)"

echo
echo "=== rebuilding jass (no-op if src/ unchanged) ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass:   $(./build/jass --version 2>/dev/null || echo '(no --version)')"

echo
echo "=== ensuring python deps (requests, numpy) ==="
python3 -c "import requests, numpy" 2>/dev/null || pip3 install --quiet requests numpy
python3 -c "import requests; print('requests', requests.__version__)"

echo
if [ -f "$DB" ]; then
    echo "=== existing DB found ==="
    sqlite3 "$DB" "SELECT 'rows: ' || COUNT(*) FROM expert_games;" || true
    sqlite3 "$DB" "SELECT 'distinct sources: ' || GROUP_CONCAT(DISTINCT source) FROM expert_games;" || true
else
    echo "=== fresh DB will be created at $DB ==="
fi

echo
echo "=== Phase 1: fetch Lidraughts games (target $TARGET_GAMES at rating $MIN_RATING-$MAX_RATING) ==="
START=$(date +%s)
python3 tools/fetch_lidraughts_games.py \
    --db "$DB" \
    --schema "$SCHEMA" \
    --min-rating "$MIN_RATING" \
    --max-rating "$MAX_RATING" \
    --target-games "$TARGET_GAMES" \
    --max-games-per-user "$PER_USER_CAP" \
    --rate-sleep "$RATE_SLEEP" \
    2>&1 | tee "$ART/fetch.log"
FETCH_RC=${PIPESTATUS[0]}
FETCH_WALL=$(( $(date +%s) - START ))

echo
echo "=== DB state after fetch ==="
sqlite3 "$DB" "SELECT 'total rows: ' || COUNT(*) FROM expert_games;" | tee -a "$ART/fetch.log"
sqlite3 "$DB" "SELECT 'lidraughts rows: ' || COUNT(*) FROM expert_games WHERE source='lidraughts';" | tee -a "$ART/fetch.log"
sqlite3 "$DB" "SELECT 'rating ≥1600: ' || COUNT(*) FROM expert_games WHERE MIN(white_rating, black_rating) >= 1600;" | tee -a "$ART/fetch.log"
sqlite3 "$DB" "SELECT 'rating ≥2000: ' || COUNT(*) FROM expert_games WHERE MIN(white_rating, black_rating) >= 2000;" | tee -a "$ART/fetch.log"
sqlite3 "$DB" "SELECT 'std variant: ' || COUNT(*) FROM expert_games WHERE variant='standard';" | tee -a "$ART/fetch.log"

if [ "$FETCH_RC" -ne 0 ]; then
    echo "ABORT: fetcher returned rc=$FETCH_RC, skipping conversion"
    exit "$FETCH_RC"
fi

echo
echo "=== Phase 2: convert to JNNW (master.jnnw for train_v3 --master-data) ==="
START2=$(date +%s)
# Two exports: "wide" (rating ≥1600, max volume) and "strict" (rating ≥2000,
# cleaner signal). train_v3 can A/B them.
python3 tools/pdn_to_jnnw.py \
    --db "$DB" --out "$ART/master-1600.jnnw" \
    --jass ./build/jass \
    --min-rating 1600 --variant standard --min-plies 20 \
    2>&1 | tee -a "$ART/convert.log"
CONV_RC1=${PIPESTATUS[0]}

python3 tools/pdn_to_jnnw.py \
    --db "$DB" --out "$ART/master-2000.jnnw" \
    --jass ./build/jass \
    --min-rating 2000 --variant standard --min-plies 20 \
    2>&1 | tee -a "$ART/convert.log"
CONV_RC2=${PIPESTATUS[0]}

CONV_WALL=$(( $(date +%s) - START2 ))

echo
echo "=========================================================="
echo "             0014 FETCH-MASTER-GAMES SUMMARY"
echo "=========================================================="
echo "  DB path:        $DB"
echo "  DB size:        $(ls -lh \"$DB\" | awk '{print $5}')"
echo "  fetch wall:     ${FETCH_WALL}s ($(python3 -c "print(round($FETCH_WALL/3600,1))")h)"
echo "  convert wall:   ${CONV_WALL}s"
echo "  master-1600:    $(ls -lh \"$ART/master-1600.jnnw\" 2>/dev/null | awk '{print $5}' || echo MISSING)"
echo "  master-2000:    $(ls -lh \"$ART/master-2000.jnnw\" 2>/dev/null | awk '{print $5}' || echo MISSING)"
echo "  fetch rc:       $FETCH_RC"
echo "  convert rc:     $CONV_RC1 / $CONV_RC2"
echo "=========================================================="

# Note: the .jnnw files will likely exceed the 50 MB runner artefact cap
# at 100K games (a single JNNW record is 38 B, 100K games × ~80 plies
# = 8M records ≈ 305 MB).  They'll be referenced via
# `artefacts_server_path` in status.json, kept on the server, and
# consumed by the downstream training job on the same machine.

# Exit with the worst non-zero rc so the job is flagged as failed
# whenever any stage failed.
if [ "$CONV_RC1" -ne 0 ]; then exit "$CONV_RC1"; fi
if [ "$CONV_RC2" -ne 0 ]; then exit "$CONV_RC2"; fi
exit 0
