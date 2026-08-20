#!/usr/bin/env bash
# Technical v4 wrapper for the preregistered CTX4 Phase-1 screen.
#
# Diagnostic 1437 proved that 1436 still failed before scientific execution at
# the 1428 pool-certificate boundary.  The immutable 1430 publisher had already
# authenticated that direct 1428 pool certificate and embedded the exact JSON
# object in CTX3_1428_READOUT.json.  This wrapper therefore validates that
# independently authenticated copy, requires exact object equality with the
# directly fetched 1428 certificate, and changes no scientific parameter.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

BASE="jobs/templates/l3-context4-uncertainty-screen-v2.sh"
PATCHED="$JASS_RESULT_DIR/l3-context4-uncertainty-screen-v4.generated.sh"
PATCHLOG="$JASS_ARTEFACT_DIR/context4-v4-auth-substitutions.json"

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


one(
    r"^cpx62-[0-9]+-l3-context4-uncertainty-screen-v2$",
    r"^cpx62-[0-9]+-l3-context4-uncertainty-screen-v4$",
    "job_nomenclature",
)

# Keep the v3 scientific-readout authentication repair.
one(
    "fetch \"$FORCE_ROOT\" verified-1428.json \\\n  --file artefacts/JASS_CONTROL_SUMMARY.json=force-summary.json \\\n",
    "fetch \"$FORCE_ROOT\" verified-1428.json \\\n  --file artefacts/JASS_CONTROL_SUMMARY.json=force-summary.json \\\n  --file artefacts/context3-two-pool-force-readout.json=force-readout.json \\\n",
    "fetch_scientific_force_readout",
)
one(
    "from jobs.tools.l3_context4_source_contract import validate_1428_force_summary",
    "from jobs.tools.l3_context4_source_contract import (validate_1428_force_readout, validate_1428_force_summary, validate_1428_pool_certificate)",
    "import_certified_source_validators",
)
one(
    "force=json.load(open(src/'force-summary.json'))\nreadout=json.load(open(src/'readout.json'))",
    "force=json.load(open(src/'force-summary.json'))\nforce_readout=json.load(open(src/'force-readout.json'))\nreadout=json.load(open(src/'readout.json'))",
    "load_scientific_force_readout",
)
one(
    "try:\n    validate_1428_force_summary(force)\nexcept ValueError as exc:\n    raise SystemExit(str(exc)) from exc",
    "try:\n    validate_1428_force_summary(force)\n    validate_1428_force_readout(force_readout)\nexcept ValueError as exc:\n    raise SystemExit(str(exc)) from exc",
    "validate_1428_runner_and_scientific_schemas",
)
one(
    "if force.get('promotion_authorized') is not False:\n    raise SystemExit('1428 promotion scope drift')\n",
    "",
    "remove_invalid_runner_wrapper_promotion_check",
)

# Diagnostic 1437: use 1430's already-authenticated embedded pool certificate
# as the schema authority and require exact equality with the directly fetched
# immutable 1428 pool-certificate.json.  This is stricter than trusting either
# copy alone and leaves the opening files/pool science untouched.
one(
    "if not pools.get('mutually_disjoint') or int(pools.get('historical_exclusion_count',-1))!=17:\n    raise SystemExit('1428 pool certificate drift')",
    "published_pool=readout.get('pool_certificate')\ntry:\n    validate_1428_pool_certificate(published_pool)\nexcept ValueError as exc:\n    raise SystemExit(str(exc)) from exc\nif pools != published_pool:\n    raise SystemExit('1428 direct pool certificate differs from authenticated 1430 copy')",
    "cross_authenticate_1428_pool_certificate_via_1430",
)

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
    "validate_1428_pool_certificate(published_pool)",
    "pools != published_pool",
    "UNCERTAINTY_CP=20",
    "SELECTION_SEED=2026082007",
    "SHUFFLE_SEED=2026082008",
    "BOOTSTRAP_SEED=2026082009",
):
    if required not in text:
        raise SystemExit(f"missing v4 technical guard: {required}")
if "1428 promotion scope drift" in text:
    raise SystemExit("obsolete runner-wrapper promotion check survived")
if "if not pools.get('mutually_disjoint')" in text:
    raise SystemExit("obsolete direct-only pool certificate check survived")

dst.write_text(text, encoding="utf-8")
log.write_text(
    json.dumps(
        {
            "schema": "jass.ctx4_phase1_v4_auth_substitutions.v1",
            "base_template": str(src),
            "changes": changes,
            "scientific_protocol_changed": False,
            "diagnostic_source": "cpx62-1437-l3-context4-1436-diagnostic-v1",
            "diagnostic_error": "1428_pool_certificate_drift",
            "technical_repair": "cross_auth_direct_1428_pool_certificate_against_authenticated_1430_embedded_copy",
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
diff -u "$BASE" "$PATCHED" >"$JASS_ARTEFACT_DIR/context4-v4-auth.patch" || true
exec bash "$PATCHED"
