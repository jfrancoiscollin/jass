#!/usr/bin/env bash
# Technical launcher for the preregistered REPLAY25 context30 target gate.
#
# v1 remains the complete auditable scientific renderer.  This launcher pins
# its exact Git blob and adds only a test-only render mode, allowing CI to run
# v2 -> v1 -> final scientific script and inspect that final script without
# starting corpus reconstruction, fitting or force games.  Runtime defaults and
# every scientific source, target, seed, pool, budget and threshold are unchanged.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
cd "$JASS_CODE_DIR"

EXPECTED_V1_BLOB="b0f32aae0c4b8326568a694b981ef1abd300e82d"
BASE="$JASS_RESULT_DIR/l3-replay-context30-target-gate-v1.certified.sh"
PATCHED="$JASS_RESULT_DIR/l3-replay-context30-target-gate-v2.generated.sh"
REPORT="$JASS_ARTEFACT_DIR/replay-context30-v2-technical-normalization.json"

git cat-file blob "$EXPECTED_V1_BLOB" >"$BASE"
[ "$(git hash-object "$BASE")" = "$EXPECTED_V1_BLOB" ] || {
  echo "replay context30 v1 template blob drift" >&2
  exit 1
}

python3 - "$BASE" "$PATCHED" "$REPORT" <<'PY'
import json
import sys
from pathlib import Path

src, dst, report = map(Path, sys.argv[1:4])
text = src.read_text(encoding="utf-8")

# Make the complete two-stage renderer executable in CI without launching the
# scientific job.  The default path remains the original `exec bash` exactly.
exec_anchor = 'exec bash "$PATCHED"'
render_only = '''if [ "${JASS_REPLAY_CONTEXT30_RENDER_ONLY:-0}" = 1 ]; then
  cp "$PATCHED" "$JASS_ARTEFACT_DIR/replay-context30-rendered.sh"
  exit 0
fi
exec bash "$PATCHED"'''
if text.count(exec_anchor) != 1:
    raise SystemExit(f"replay context30 v1 exec anchor drift: count={text.count(exec_anchor)}")
text = text.replace(exec_anchor, render_only)

required = (
    'EXPECTED_BASE_BLOB="ffec746c56930c6236017fe0742017969d27aa5b"',
    'NOPEN=3000',
    'CANDIDATES=40000',
    'BOOTSTRAP=200000',
    'POOL_SEED_1=2026082211',
    'POOL_SEED_2=2026082212',
    'B_REPLAY25_CONTEXT30',
    'B_REPLAY25_NATIVE',
    'CONTEXT_30_ALIGNED_alpha_0.30',
    'pool-replay-doe-1451-pool1',
    'pool-replay-doe-1451-pool2',
    'pool-replay-b-promotion-1454-pool1',
    'pool-replay-b-promotion-1454-pool2',
    '--target external',
    '--sample-weights',
    '--prior-mean "$W/curriculum.pjtw"',
    'REFITS__1',
    'NEW_SELFPLAY__0',
    'FROZEN_COHORTS_READ__0',
    'PROMOTION_AUTHORIZED__FALSE',
    'for forbidden in (',
)
for token in required:
    if token not in text:
        raise SystemExit(f"replay context30 v2 scientific lock missing: {token}")

# Do not scan the v1 renderer source for its own forbidden-token literals.  The
# inner renderer performs that check on the final generated scientific script,
# after source-only control code has disappeared.
dst.write_text(text, encoding="utf-8")
report.write_text(json.dumps({
    "schema": "jass.l3_replay_context30_v2_normalization.v1",
    "source_v1_blob": "b0f32aae0c4b8326568a694b981ef1abd300e82d",
    "technical_change_only": True,
    "scientific_protocol_changed": False,
    "runtime_default_changed": False,
    "test_only_render_mode": {
        "environment_flag": "JASS_REPLAY_CONTEXT30_RENDER_ONLY",
        "output": "replay-context30-rendered.sh"
    },
    "models_reused": 1,
    "refits": 1,
    "new_selfplay": 0,
    "frozen_read": False,
    "automatic_promotion": False,
    "inner_generated_script_forbidden_scan_preserved": True
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

bash -n "$PATCHED"
chmod +x "$PATCHED"
diff -u "$BASE" "$PATCHED" >"$JASS_ARTEFACT_DIR/replay-context30-v2.patch" || true
exec bash "$PATCHED"
