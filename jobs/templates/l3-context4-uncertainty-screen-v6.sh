#!/usr/bin/env bash
# Technical v6 wrapper for the preregistered CTX4 Phase-1 screen.
#
# Read-only diagnostic 1445 identified the exact pre-verdict abort in 1441:
# validate_1428_force_summary expected a fictional nested runner-wrapper schema,
# while the certified immutable 1428 template explicitly copies the scientific
# readout byte-for-byte to JASS_CONTROL_SUMMARY.json.  The source-contract
# validator now authenticates that real schema.  This wrapper changes only the
# immutable job nomenclature from v5 to v6; every scientific parameter remains
# locked and unchanged.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

BASE="jobs/templates/l3-context4-uncertainty-screen-v5.sh"
PATCHED="$JASS_RESULT_DIR/l3-context4-uncertainty-screen-v6.generated.sh"
PATCHLOG="$JASS_ARTEFACT_DIR/context4-v6-auth-substitutions.json"
EXPECTED_BASE_BLOB="14ff09418f1f3bb3ee572a61267ede645257a716"
[ "$(git hash-object "$BASE")" = "$EXPECTED_BASE_BLOB" ] || {
  echo "certified CTX4 v5 wrapper blob drift" >&2
  exit 1
}

python3 - "$BASE" "$PATCHED" "$PATCHLOG" <<'PY'
import json
import re
import sys
from pathlib import Path

src, dst, log = map(Path, sys.argv[1:4])
text = src.read_text(encoding="utf-8")
original = text
old = 'r"^cpx62-[0-9]+-l3-context4-uncertainty-screen-v5$"'
new = 'r"^cpx62-[0-9]+-l3-context4-uncertainty-screen-v6$"'
if text.count(old) != 1:
    raise SystemExit(f"job nomenclature anchor drift: count={text.count(old)}")
text = text.replace(old, new)

locked = {
    "PER_POOL": "256",
    "CHOICE_DEPTH": "9",
    "JUDGE_DEPTH": "12",
    "UNCERTAINTY_CP": "20",
    "SELECTION_SEED": "2026082007",
    "SHUFFLE_SEED": "2026082008",
    "BOOTSTRAP_SEED": "2026082009",
    "BOOTSTRAP": "100000",
    "MIN_TOTAL": "48",
    "MIN_PER_POOL": "16",
    "MIN_ALIGNED_FLIPS": "12",
}
for key, expected in locked.items():
    before = re.findall(rf'"{re.escape(key)}": "(\S+)"', original)
    after = re.findall(rf'"{re.escape(key)}": "(\S+)"', text)
    if before != [expected] or after != [expected]:
        raise SystemExit(
            f"scientific parameter drift: {key} before={before} after={after}"
        )

for required in (
    "validate_1428_force_summary(force)",
    "validate_1428_force_readout(force_readout)",
    "validate_equivalent_1428_pool_certificates(pools, published_pool)",
    "technical_repair",
):
    if required not in text:
        raise SystemExit(f"missing inherited v5 guard: {required}")

payload = {
    "schema": "jass.ctx4_phase1_v6_auth_substitutions.v1",
    "base_template": str(src),
    "base_blob": "14ff09418f1f3bb3ee572a61267ede645257a716",
    "diagnostic_source": (
        "cpx62-1445-l3-context4-1441-auth-guard-diagnostic-v4/"
        "20260820T184542Z-0e47923b"
    ),
    "diagnostic_first_failed_check": "1428_force_summary_contract",
    "diagnostic_first_failed_error": "1428 unexpectedly refit",
    "certified_1428_generation_contract": (
        "context3-two-pool-force-readout.json copied byte-for-byte to "
        "JASS_CONTROL_SUMMARY.json"
    ),
    "source_contract_repair": (
        "validate JASS_CONTROL_SUMMARY with the exact scientific readout schema"
    ),
    "job_nomenclature_change": {"from": "v5", "to": "v6"},
    "scientific_protocol_changed": False,
}

dst.write_text(text, encoding="utf-8")
log.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

bash -n "$PATCHED"
chmod +x "$PATCHED"
diff -u "$BASE" "$PATCHED" >"$JASS_ARTEFACT_DIR/context4-v6-auth.patch" || true
exec bash "$PATCHED"
