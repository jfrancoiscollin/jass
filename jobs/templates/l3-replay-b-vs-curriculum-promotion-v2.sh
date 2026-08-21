#!/usr/bin/env bash
# Technical launcher for the preregistered B-vs-CURRICULUM promotion gate.
#
# v1 is retained as the complete auditable protocol renderer. This launcher
# pins its exact Git blob and repairs one self-check token that was named more
# broadly than the actual readout executable. No scientific source, pool,
# seed, budget, threshold, bootstrap, engine setting or promotion guard changes.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
cd "$JASS_CODE_DIR"

EXPECTED_V1_BLOB="a2691c7221bc9dd89b3835fda5007da37a914451"
BASE="$JASS_RESULT_DIR/l3-replay-b-vs-curriculum-promotion-v1.certified.sh"
PATCHED="$JASS_RESULT_DIR/l3-replay-b-vs-curriculum-promotion-v2.generated.sh"
REPORT="$JASS_ARTEFACT_DIR/promotion-v2-technical-normalization.json"

git cat-file blob "$EXPECTED_V1_BLOB" >"$BASE"
[ "$(git hash-object "$BASE")" = "$EXPECTED_V1_BLOB" ] || {
  echo "promotion v1 template blob drift" >&2
  exit 1
}

python3 - "$BASE" "$PATCHED" "$REPORT" <<'PY'
import json
import sys
from pathlib import Path

src, dst, report = map(Path, sys.argv[1:4])
text = src.read_text(encoding="utf-8")
old = '    "JASS_REPLAY25_B_VS_CURRICULUM", "historical_exclusion_count",'
new = '    "l3_replay_b_promotion_readout.py", "historical_exclusion_count",'
if text.count(old) != 1:
    raise SystemExit(f"promotion v1 self-check anchor drift: count={text.count(old)}")
text = text.replace(old, new)
if "JASS_REPLAY25_B_VS_CURRICULUM" in text:
    raise SystemExit("obsolete broad self-check token survived")

# Make the complete two-stage renderer executable in CI without launching the
# scientific job. Runtime behaviour is unchanged unless the explicit test-only
# environment flag is present.
exec_anchor = 'exec bash "$PATCHED"'
render_only = '''if [ "${JASS_PROMOTION_RENDER_ONLY:-0}" = 1 ]; then
  cp "$PATCHED" "$JASS_ARTEFACT_DIR/promotion-rendered.sh"
  exit 0
fi
exec bash "$PATCHED"'''
if text.count(exec_anchor) != 1:
    raise SystemExit(f"promotion v1 exec anchor drift: count={text.count(exec_anchor)}")
text = text.replace(exec_anchor, render_only)

required = (
    "EXPECTED_BASE_BLOB=\"ffec746c56930c6236017fe0742017969d27aa5b\"",
    "NOPEN=3000",
    "CANDIDATES=40000",
    "BOOTSTRAP=200000",
    "POOL_SEED_1=2026082201",
    "POOL_SEED_2=2026082202",
    "pool-replay-doe-1451-pool1",
    "pool-replay-doe-1451-pool2",
    "--pattern-a \"$W/B.pjtw\" --pattern-b \"$W/curriculum.pjtw\"",
    "promotion_review_recommended",
    "PROMOTION_AUTHORIZED__FALSE",
    "for forbidden in (\"fit_arm A \", \"stage sequential-four-arm-fits\", \"--prior-mean\", \"--target wdl\")",
)
for token in required:
    if token not in text:
        raise SystemExit(f"promotion v2 scientific lock missing: {token}")

# Do not scan the renderer source for its own forbidden-token literals. The
# inner v1 renderer performs that check on the final generated scientific
# script, after the source-only control code has disappeared.
dst.write_text(text, encoding="utf-8")
report.write_text(json.dumps({
    "schema": "jass.l3_replay_b_promotion_v2_normalization.v2",
    "source_v1_blob": "a2691c7221bc9dd89b3835fda5007da37a914451",
    "technical_change_only": True,
    "scientific_protocol_changed": False,
    "models_reused": 2,
    "refits": 0,
    "new_selfplay": 0,
    "frozen_read": False,
    "automatic_promotion": False,
    "changes": [
        {
            "kind": "self_check_token_specificity",
            "old": "JASS_REPLAY25_B_VS_CURRICULUM",
            "new": "l3_replay_b_promotion_readout.py"
        },
        {
            "kind": "test_only_render_mode",
            "environment_flag": "JASS_PROMOTION_RENDER_ONLY",
            "runtime_default_changed": False
        },
        {
            "kind": "remove_self_referential_outer_forbidden_scan",
            "inner_generated_script_scan_preserved": True
        }
    ]
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

bash -n "$PATCHED"
chmod +x "$PATCHED"
diff -u "$BASE" "$PATCHED" >"$JASS_ARTEFACT_DIR/promotion-v2.patch" || true
exec bash "$PATCHED"
