#!/usr/bin/env bash
# Exploratory post-CTX4 fresh 2M corpus generator.
#
# This wraps the certified 1409 corpus recipe byte-for-byte and changes only:
#   1. immutable job nomenclature;
#   2. the preregistered generation seed;
#   3. explicit exploratory provenance/verdict metadata.
#
# CTX4 remains scientifically failed.  This job cannot rehabilitate CTX4 and
# performs no fit, force game, frozen read or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

BASE="jobs/templates/l3-context2-intervention-corpus-v1.sh"
PATCHED="$JASS_RESULT_DIR/l3-context2-intervention-corpus-fresh2m-exploratory-v2.generated.sh"
PATCHLOG="$JASS_ARTEFACT_DIR/exploratory-fresh2m-substitutions.json"
EXPECTED_BASE_BLOB="3b52e23f2de4e526347a22fe68a280d48107be31"
OLD_SEED=2026081805
NEW_SEED=2026082105

[ "$(git hash-object "$BASE")" = "$EXPECTED_BASE_BLOB" ] || {
  echo "certified 1409 corpus template blob drift" >&2
  exit 1
}

python3 - "$BASE" "$PATCHED" "$PATCHLOG" "$OLD_SEED" "$NEW_SEED" <<'PY'
import json
import sys
from pathlib import Path

src, dst, log = map(Path, sys.argv[1:4])
old_seed, new_seed = map(int, sys.argv[4:6])
text = src.read_text(encoding="utf-8")
changes = []


def one(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one substitution, got {count}")
    text = text.replace(old, new)
    changes.append({"label": label, "count": count, "old": old, "new": new})


one(
    r"^cpx62-([0-9]+)-l3-context2-intervention-corpus-v1$",
    r"^cpx62-([0-9]+)-l3-context2-intervention-corpus-fresh2m-exploratory-v2$",
    "job_nomenclature",
)
one(
    f"LABEL_DEPTH=4; MAXPLIES=260; FRESH_SEED={old_seed}",
    f"LABEL_DEPTH=4; MAXPLIES=260; FRESH_SEED={new_seed}",
    "fresh_generation_seed",
)

audit_anchor = '''"$PY" jobs/tools/l3_context2_intervention_corpus_audit.py "${cell_args[@]}" \\
  --unified "$W/context2-intervention-2m.jnnw" --code-sha "$EXPECTED_CODE_SHA" \\
  --fresh-seed "$FRESH_SEED" --out "$ART/JASS_CONTROL_SUMMARY.json" | tee -a "$RES"
'''
if text.count(audit_anchor) != 1:
    raise SystemExit(f"audit metadata anchor drift: count={text.count(audit_anchor)}")
metadata_block = r'''"$PY" - "$ART/JASS_CONTROL_SUMMARY.json" "$FRESH_SEED" <<'PY_META'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
fresh_seed = int(sys.argv[2])
payload = json.loads(path.read_text(encoding="utf-8"))
original_verdict = payload.get("verdict")
if original_verdict != "JASS_CONTEXT2_INTERVENTION_CORPUS_READY":
    raise SystemExit(f"certified generator audit verdict drift: {original_verdict!r}")
payload["generator_recipe_verdict"] = original_verdict
payload["verdict"] = "JASS_EXPLORATORY_FRESH2M_D2_READY"
payload["experiment_class"] = "EXPLORATORY_POST_CTX4"
payload["corpus_role"] = "D2_FRESH_2M"
payload["fresh_seed"] = fresh_seed
payload["source_recipe"] = {
    "job_id": "cpx62-1409-l3-context2-intervention-corpus-v1",
    "attempt_id": "20260818T184956Z-3465ec72",
    "template_blob": "3b52e23f2de4e526347a22fe68a280d48107be31",
    "only_generation_change": "fresh_seed",
}
payload["ctx4_terminal_reference"] = {
    "job_id": "cpx62-1446-l3-context4-uncertainty-screen-v6",
    "attempt_id": "20260820T193737Z-f206a837",
    "verdict": "JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED",
    "next_stage_authorized": False,
    "verdict_unchanged_by_this_experiment": True,
}
payload["downstream_fit_doe"] = {
    "issue": 544,
    "target_semantics": "native_JNNW_WDL_identical_for_D1_and_D2",
    "arms": ["CURRENT", "REPLAY25", "REPLAY25_NO_PRIOR", "FULL_HISTORY_NO_PRIOR"],
    "confirmatory_claim_authorized": False,
}
payload["promotion_authorized"] = False
payload["automatic_next_job"] = None
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_META
'''
text = text.replace(audit_anchor, audit_anchor + metadata_block)
changes.append({"label": "exploratory_provenance_metadata", "count": 1})

one(
    'touch "$ART/VERDICT__JASS_CONTEXT2_INTERVENTION_CORPUS_READY"',
    'touch "$ART/VERDICT__JASS_EXPLORATORY_FRESH2M_D2_READY"\n'
    'touch "$ART/EXPERIMENT_CLASS__EXPLORATORY_POST_CTX4"\n'
    'touch "$ART/CTX4_VERDICT_UNCHANGED__FAILED"\n'
    'touch "$ART/CONFIRMATORY_CLAIM_AUTHORIZED__FALSE"',
    "exploratory_verdict_markers",
)
one(
    'say "JASS_CONTEXT2_INTERVENTION_CORPUS_READY records=2000000 fresh=true fits=0 promotion=false"',
    'say "JASS_EXPLORATORY_FRESH2M_D2_READY records=2000000 fresh_seed=$FRESH_SEED exploratory_post_ctx4=true fits=0 promotion=false"',
    "terminal_message",
)

# Fail closed on any accidental scientific drift.  The exact base blob above
# already pins the complete recipe; these assertions make the intended delta
# human- and machine-auditable.
required = (
    "BASE 300000 8 8 60 0 0 8",
    "ROP16 600000 16 8 60 0 0 8",
    "EPS16 500000 8 16 60 0 0 8",
    "DECAY120 100000 8 8 120 0 0 8",
    "TOPK3M30 100000 8 8 60 3 30 8",
    "DEPTH10 400000 8 8 60 0 0 10",
    "CURRICULUM_SHA=\"319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1\"",
    "--wdl-zero-score",
    "--sample-meta-format jsm2",
    "--pair-openings",
    "--split-selfplay-rngs",
    "NO_AUTOMATIC_CONTINUATION",
)
for token in required:
    if token not in text:
        raise SystemExit(f"certified generation recipe token missing: {token}")
if str(old_seed) in text:
    raise SystemExit("old 1409 generation seed survived")
if text.count(str(new_seed)) != 1:
    raise SystemExit("new generation seed is not uniquely locked")
if len(changes) != 5:
    raise SystemExit(f"unexpected substitution count: {len(changes)}")

dst.write_text(text, encoding="utf-8")
log.write_text(
    json.dumps(
        {
            "schema": "jass.exploratory_fresh2m_substitutions.v2",
            "issue": 544,
            "experiment_class": "EXPLORATORY_POST_CTX4",
            "base_template": str(src),
            "base_blob": "3b52e23f2de4e526347a22fe68a280d48107be31",
            "old_seed": old_seed,
            "new_seed": new_seed,
            "scientific_generation_changes": ["fresh_seed"],
            "ctx4_verdict_reopened": False,
            "changes": changes,
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
diff -u "$BASE" "$PATCHED" >"$JASS_ARTEFACT_DIR/exploratory-fresh2m.patch" || true
exec bash "$PATCHED"
