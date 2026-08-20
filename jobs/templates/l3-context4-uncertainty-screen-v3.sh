#!/usr/bin/env bash
# Technical v3 wrapper for the preregistered CTX4 Phase-1 screen.
#
# Diagnostic 1435 proved that 1434 failed because the runner-controlled 1428
# JASS_CONTROL_SUMMARY wrapper does not carry the scientific top-level
# promotion_authorized field.  The immutable scientific force readout does,
# and was independently authenticated by 1430.  This wrapper changes only that
# source-authentication boundary; all scientific sources, samples, seeds,
# depths, <=20 cp band, bootstrap and pass gates remain byte-for-byte v2.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

BASE="jobs/templates/l3-context4-uncertainty-screen-v2.sh"
PATCHED="$JASS_RESULT_DIR/l3-context4-uncertainty-screen-v3.generated.sh"
PATCHLOG="$JASS_ARTEFACT_DIR/context4-v3-auth-substitutions.json"

python3 - "$BASE" "$PATCHED" "$PATCHLOG" <<'PY'
import json, re, sys
from pathlib import Path
src, dst, log = map(Path, sys.argv[1:4])
text = src.read_text(encoding="utf-8")
original = text
changes = []


def one(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one substitution, got {count}")
    text = text.replace(old, new)
    changes.append({"label": label, "count": count, "old": old, "new": new})


# Runner nomenclature only: the scientific template remains the v2 protocol.
one(
    r"^cpx62-[0-9]+-l3-context4-uncertainty-screen-v2$",
    r"^cpx62-[0-9]+-l3-context4-uncertainty-screen-v3$",
    "job_nomenclature",
)

# Fetch the immutable scientific 1428 readout in addition to the runner summary.
one(
    "fetch \"$FORCE_ROOT\" verified-1428.json \\\n  --file artefacts/JASS_CONTROL_SUMMARY.json=force-summary.json \\\n",
    "fetch \"$FORCE_ROOT\" verified-1428.json \\\n  --file artefacts/JASS_CONTROL_SUMMARY.json=force-summary.json \\\n  --file artefacts/context3-two-pool-force-readout.json=force-readout.json \\\n",
    "fetch_scientific_force_readout",
)

one(
    "from jobs.tools.l3_context4_source_contract import validate_1428_force_summary",
    "from jobs.tools.l3_context4_source_contract import (validate_1428_force_readout, validate_1428_force_summary)",
    "import_scientific_readout_validator",
)
one(
    "force=json.load(open(src/'force-summary.json'))\nreadout=json.load(open(src/'readout.json'))",
    "force=json.load(open(src/'force-summary.json'))\nforce_readout=json.load(open(src/'force-readout.json'))\nreadout=json.load(open(src/'readout.json'))",
    "load_scientific_force_readout",
)
one(
    "try:\n    validate_1428_force_summary(force)\nexcept ValueError as exc:\n    raise SystemExit(str(exc)) from exc",
    "try:\n    validate_1428_force_summary(force)\n    validate_1428_force_readout(force_readout)\nexcept ValueError as exc:\n    raise SystemExit(str(exc)) from exc",
    "validate_both_1428_schemas",
)
one(
    "if force.get('promotion_authorized') is not False:\n    raise SystemExit('1428 promotion scope drift')\n",
    "",
    "remove_invalid_runner_wrapper_promotion_check",
)

# Fail closed against accidental scientific drift in this technical wrapper.
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
    before = re.findall(rf"(?m)^{re.escape(key)}=(\S+)$", original)
    after = re.findall(rf"(?m)^{re.escape(key)}=(\S+)$", text)
    if before != [expected] or after != [expected]:
        raise SystemExit(f"scientific parameter drift: {key} before={before} after={after}")

for required in (
    "context3-two-pool-force-readout.json=force-readout.json",
    "validate_1428_force_readout(force_readout)",
    "UNCERTAINTY_CP=20",
    "SELECTION_SEED=2026082007",
    "SHUFFLE_SEED=2026082008",
    "BOOTSTRAP_SEED=2026082009",
):
    if required not in text:
        raise SystemExit(f"missing v3 technical guard: {required}")
if "1428 promotion scope drift" in text:
    raise SystemExit("obsolete runner-wrapper promotion check survived")

dst.write_text(text, encoding="utf-8")
log.write_text(
    json.dumps(
        {
            "schema": "jass.ctx4_phase1_v3_auth_substitutions.v1",
            "base_template": str(src),
            "changes": changes,
            "scientific_protocol_changed": False,
            "diagnostic_source": "cpx62-1435-l3-context4-1434-diagnostic-v1",
            "technical_root_cause": "runner_summary_missing_scientific_promotion_field",
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

bash -n "$PATCHED"
chmod +x "$PATCHED"
diff -u "$BASE" "$PATCHED" >"$JASS_ARTEFACT_DIR/context4-v3-auth.patch" || true
exec bash "$PATCHED"
