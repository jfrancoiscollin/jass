#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Audited 2M/gen expansion of the merged TOP3 self-play runner.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
cd "$JASS_CODE_DIR"

SOURCE="$JASS_CODE_DIR/jobs/templates/l3-imbalance2-top3-selfplay-v1.sh"
TARGET="$JASS_RESULT_DIR/top3-selfplay-2m-expanded.sh"
[ -f "$SOURCE" ] || { echo "ABORT: missing base TOP3 runner" >&2; exit 2; }

python3 jobs/tests/test_l3_imbalance2_top3_2m_prepared.py \
  > "$JASS_RESULT_DIR/top3-2m-contract.log" 2>&1

python3 - "$SOURCE" "$TARGET" <<'PY'
from pathlib import Path
import sys

source, target = map(Path, sys.argv[1:])
text = source.read_text(encoding="utf-8")
replacements = [
    ('FRESH="${FRESH:-500000}"', 'FRESH="${FRESH:-2000000}"'),
    ('[ "$FRESH" -eq 500000 ] && [ "$GENERATIONS" -eq 4 ] || die "standard TOP3 requires 500000 records and four generations"',
     '[ "$FRESH" -eq 2000000 ] && [ "$GENERATIONS" -eq 4 ] || die "standard TOP3 requires 2000000 records and four generations"'),
    ('L3-IMBALANCE2-TOP3 P1 G1-G4 d8 ===', 'L3-IMBALANCE2-TOP3 P1 G1-G4 d8 corpus=2M/gen ==='),
]
for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"2M adapter: expected one occurrence of {old!r}, found {count}")
    text = text.replace(old, new)
if 'standard TOP3 requires 500000 records and four generations' in text:
    raise SystemExit('2M adapter: stale 500k guard remains')
target.write_text(text, encoding="utf-8")
PY

chmod 0755 "$TARGET"
exec bash "$TARGET"
