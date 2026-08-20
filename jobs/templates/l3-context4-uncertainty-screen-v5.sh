#!/usr/bin/env bash
# Technical v5 wrapper for the preregistered CTX4 Phase-1 screen.
#
# Read-only diagnostic 1440 proved the immutable direct 1428 pool certificate
# and the copy embedded by authenticated 1430 are canonically identical:
# RAW_EQUAL=true, DIFF_COUNT=0 and identical canonical SHA-256.  The v4 abort
# therefore came from relying on a fragile raw Python object-equality boundary,
# not from scientific pool drift.  V5 replaces only that boundary with the
# tested scientific fingerprint contract; every CTX4 scientific parameter is
# unchanged.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

BASE="jobs/templates/l3-context4-uncertainty-screen-v2.sh"
PATCHED="$JASS_RESULT_DIR/l3-context4-uncertainty-screen-v5.generated.sh"
PATCHLOG="$JASS_ARTEFACT_DIR/context4-v5-auth-substitutions.json"

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
    r"^cpx62-[0-9]+-l3-context4-uncertainty-screen-v5$",
    "job_nomenclature",
)

# Preserve the already-certified v3 separation of runner and scientific readout.
one(
    "fetch \"$FORCE_ROOT\" verified-1428.json \\\n  --file artefacts/JASS_CONTROL_SUMMARY.json=force-summary.json \\\n",
    "fetch \"$FORCE_ROOT\" verified-1428.json \\\n  --file artefacts/JASS_CONTROL_SUMMARY.json=force-summary.json \\\n  --file artefacts/context3-two-pool-force-readout.json=force-readout.json \\\n",
    "fetch_scientific_force_readout",
)
one(
    "from jobs.tools.l3_context4_source_contract import validate_1428_force_summary",
    "from jobs.tools.l3_context4_source_contract import (validate_1428_force_readout, validate_1428_force_summary, validate_1428_pool_certificate, validate_equivalent_1428_pool_certificates)",
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

# 1440 authenticated both immutable pool objects and proved canonical equality.
# Cross-authenticate on the locked scientific fingerprint rather than fragile
# raw Python object equality.  Both inputs are independently validated first.
one(
    "if not pools.get('mutually_disjoint') or int(pools.get('historical_exclusion_count',-1))!=17:\n    raise SystemExit('1428 pool certificate drift')",
    "published_pool=readout.get('pool_certificate')\ntry:\n    validate_1428_pool_certificate(published_pool)\n    validate_equivalent_1428_pool_certificates(pools, published_pool)\nexcept ValueError as exc:\n    raise SystemExit(str(exc)) from exc",
    "cross_authenticate_1428_pool_certificate_by_scientific_fingerprint",
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
    "validate_equivalent_1428_pool_certificates(pools, published_pool)",
    "UNCERTAINTY_CP=20",
    "SELECTION_SEED=2026082007",
    "SHUFFLE_SEED=2026082008",
    "BOOTSTRAP_SEED=2026082009",
):
    if required not in text:
        raise SystemExit(f"missing v5 technical guard: {required}")
if "1428 promotion scope drift" in text:
    raise SystemExit("obsolete runner-wrapper promotion check survived")
if "if not pools.get('mutually_disjoint')" in text:
    raise SystemExit("obsolete direct-only pool certificate check survived")
if "pools != published_pool" in text:
    raise SystemExit("fragile raw pool object equality survived")

dst.write_text(text, encoding="utf-8")
log.write_text(
    json.dumps(
        {
            "schema": "jass.ctx4_phase1_v5_auth_substitutions.v1",
            "base_template": str(src),
            "changes": changes,
            "scientific_protocol_changed": False,
            "diagnostic_source": "cpx62-1440-l3-context4-1428-pool-structural-diff-v1",
            "diagnostic_result": {
                "raw_equal": True,
                "diff_count": 0,
                "canonical_sha256": "57ba665ebffde24e27c825a4f6a762068a9e4c579102d5915654843c3bbce290",
                "scientific_projection_equal": True,
            },
            "technical_repair": "replace_raw_dict_equality_with_tested_scientific_pool_fingerprint",
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
diff -u "$BASE" "$PATCHED" >"$JASS_ARTEFACT_DIR/context4-v5-auth.patch" || true
exec bash "$PATCHED"
