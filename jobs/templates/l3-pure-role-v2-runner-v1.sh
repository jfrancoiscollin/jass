#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# L3-PURE role-aware V2: reuse the frozen C1-Q1 runner while changing only
# the post-split training resampling for exact two-men/equal-kings positions.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_JOB_ID:?runner v3 must provide JASS_JOB_ID}"
: "${L3_ROLE_V2_BOX:?set ccx33 or cpx62 in the prepared wrapper}"
: "${L3_ROLE_V2_RUN_KIND:?set primary or replication in the prepared wrapper}"

[ "$L3_ROLE_V2_BOX" = ccx33 ] || [ "$L3_ROLE_V2_BOX" = cpx62 ] || {
  echo "ABORT: L3_ROLE_V2_BOX must be ccx33 or cpx62" >&2
  exit 2
}
[ "$L3_ROLE_V2_RUN_KIND" = primary ] || [ "$L3_ROLE_V2_RUN_KIND" = replication ] || {
  echo "ABORT: L3_ROLE_V2_RUN_KIND must be primary or replication" >&2
  exit 2
}

BASE_RUNNER="$JASS_CODE_DIR/jobs/templates/l3-pure-runner-v4.sh"
PATCHED_RUNNER="$JASS_RESULT_DIR/l3-pure-role-v2-patched-runner.sh"
[ -f "$BASE_RUNNER" ] || { echo "ABORT: frozen L3-PURE runner missing" >&2; exit 2; }

python3 -m py_compile \
  "$JASS_CODE_DIR/jobs/tools/prepare_imbalance2_training.py" \
  "$JASS_CODE_DIR/jobs/tests/test_l3_pure_role_v2_prepared.py"
python3 "$JASS_CODE_DIR/jobs/tests/test_l3_pure_role_v2_prepared.py" \
  > "$JASS_RESULT_DIR/l3-pure-role-v2-contract.log" 2>&1

# Generate an auditable, job-local derivative of runner-v4. The source runner is
# not edited: two exact replacements insert the role-aware resampling between
# split and feature extraction, then point the trainer at the weighted corpus.
python3 - "$BASE_RUNNER" "$PATCHED_RUNNER" <<'PY'
from pathlib import Path
import sys

source_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
text = source_path.read_text(encoding="utf-8")

needle_dump = '''  "$J" --dump-eval-features "$W/g${generation}.fit.jnnw" \\
    "$W/g${generation}.feat" > "$W/g${generation}-features.log" 2>&1
'''
replacement_dump = '''  IMBALANCE2_REWEIGHT_POLICY=role-aware-v2 python3 \\
    jobs/tools/prepare_imbalance2_training.py reweight \\
      --input "$W/g${generation}.fit.jnnw" \\
      --output "$W/g${generation}.weighted.jnnw" \\
      --holdout-count "$HOLDOUT_COUNT" \\
      --win-weight 1 --draw-weight 2 --loss-weight 4 \\
      --seed $((BASE_SEED + generation)) \\
      --report "$ART/g${generation}-role-v2-reweight.json"
  TRAIN_DATA="$W/g${generation}.weighted.jnnw"
  "$J" --dump-eval-features "$TRAIN_DATA" \\
    "$W/g${generation}.feat" > "$W/g${generation}-features.log" 2>&1
'''
needle_train = '''      --data "$W/g${generation}.fit.jnnw" \\
'''
replacement_train = '''      --data "$TRAIN_DATA" \\
'''

if text.count(needle_dump) != 1:
    raise SystemExit("frozen runner dump-feature insertion point changed")
if text.count(needle_train) != 1:
    raise SystemExit("frozen runner train-data insertion point changed")
text = text.replace(needle_dump, replacement_dump)
text = text.replace(needle_train, replacement_train)
out_path.write_text(text, encoding="utf-8")
out_path.chmod(0o755)
PY

bash -n "$PATCHED_RUNNER"
bash "$PATCHED_RUNNER"

python3 - "$JASS_ARTEFACT_DIR" "$L3_ROLE_V2_BOX" "$L3_ROLE_V2_RUN_KIND" <<'PY'
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

art = Path(sys.argv[1])
box = sys.argv[2]
run_kind = sys.argv[3]
manifest_path = art / "l3-pure-manifest.json"
if not manifest_path.exists():
    raise SystemExit("role-aware L3-PURE manifest missing")
reports = sorted(art.glob("g*-role-v2-reweight.json"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
expected_generations = int(manifest.get("generations", 0))
if len(reports) != expected_generations:
    raise SystemExit(
        f"expected {expected_generations} role reports, found {len(reports)}"
    )

source = Counter()
resampled = Counter()
domain_records = 0
anchor_records = 0
for path in reports:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("policy") != "role-aware-v2":
        raise SystemExit(f"{path}: wrong role policy")
    if payload.get("mode") != "deterministic_role_domain_resample":
        raise SystemExit(f"{path}: wrong resampling mode")
    domain = payload.get("domain", {})
    if domain.get("men_gap") != 2 or domain.get("equal_king_counts") is not True:
        raise SystemExit(f"{path}: wrong exact-domain contract")
    matrix = payload.get("weight_semantics", {}).get("matrix_side_to_move_pov")
    expected = {
        "up": {"win": 1.0, "draw": 2.0, "loss": 4.0},
        "down": {"win": 4.0, "draw": 2.0, "loss": 1.0},
    }
    if matrix != expected:
        raise SystemExit(f"{path}: wrong conversion/resilience matrix")
    if payload.get("holdout_records_untouched", 0) <= 0:
        raise SystemExit(f"{path}: holdout proof missing")
    source.update(payload.get("source_training_buckets", {}))
    resampled.update(payload.get("resampled_training_buckets", {}))
    domain_records += int(domain.get("records", 0))
    anchor_records += int(domain.get("outside_domain_anchor_records", 0))

if domain_records <= 0:
    raise SystemExit("no naturally reached exact two-men/equal-kings positions")

manifest["schema"] = max(3, int(manifest.get("schema", 0)))
manifest["lineage"] = "L3-PURE-ROLE-V2"
manifest["parent_lineage"] = "L3-PURE C1-Q1 Q00_CAPTURE"
manifest["execution_box"] = box
manifest["replication_kind"] = run_kind
manifest["role_weighting"] = {
    "policy": "role-aware-v2",
    "activation": "per-position abs(men_gap)==2 and equal king counts",
    "conversion_weights_stm_pov": {"win": 1, "draw": 2, "loss": 4},
    "resilience_weights_stm_pov": {"win": 4, "draw": 2, "loss": 1},
    "outside_domain_anchor_weight": 1,
    "holdout_weighted": False,
    "output_record_count_unchanged": True,
    "deep_teacher_used_for_weighting": False,
    "per_move_criticality_relabel": False,
    "reports": [path.name for path in reports],
    "source_training_buckets": dict(sorted(source.items())),
    "resampled_training_buckets": dict(sorted(resampled.items())),
    "exact_domain_records": domain_records,
    "outside_domain_anchor_records": anchor_records,
}
manifest.setdefault("fit", {})["role_domain_resampling"] = manifest["role_weighting"]
manifest_path.write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
summary = {
    "schema": 1,
    "lineage": manifest["lineage"],
    "execution_box": box,
    "replication_kind": run_kind,
    "base_seed": manifest.get("base_seed"),
    "generation_reports": [path.name for path in reports],
    "exact_domain_records": domain_records,
    "outside_domain_anchor_records": anchor_records,
    "source_training_buckets": dict(sorted(source.items())),
    "resampled_training_buckets": dict(sorted(resampled.items())),
}
(art / "l3-pure-role-v2-summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

printf '%s\n' \
  "L3-PURE role-aware-v2 complete: exact ±2 domain weighted; holdout untouched; no promotion" \
  | tee -a "$JASS_ARTEFACT_DIR/RESULTS.txt"
