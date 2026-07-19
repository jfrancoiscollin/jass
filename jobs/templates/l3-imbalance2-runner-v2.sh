#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# L3-IMBALANCE2 role-aware V2: exact-domain conversion + resilience weighting.
set -Eeuo pipefail

: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${PHASE:?set PHASE=P1, P2, P3 or P4}"

# Backward-compatible switch consumed only by prepare_imbalance2_training.py.
# The V1 runner remains frozen; this wrapper validates and upgrades its manifest
# after every generation has emitted a role-aware report.
export IMBALANCE2_REWEIGHT_POLICY=role-aware-v2
mkdir -p "$JASS_RESULT_DIR"
python3 jobs/tests/test_l3_imbalance2_role_v2_prepared.py \
  > "$JASS_RESULT_DIR/role-v2-contract.log" 2>&1

bash jobs/templates/l3-imbalance2-runner-v1.sh

python3 - "$JASS_ARTEFACT_DIR" "$PHASE" <<'PY'
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

art = Path(sys.argv[1])
phase = sys.argv[2]
reports = sorted(art.glob("g*-reweight.json"))
if not reports:
    raise SystemExit("role-aware-v2: no generation reweight reports found")

source = Counter()
resampled = Counter()
domain_records = 0
anchor_records = 0
for path in reports:
    payload = json.loads(path.read_text())
    if payload.get("mode") != "deterministic_role_domain_resample":
        raise SystemExit(f"{path}: expected deterministic_role_domain_resample")
    if payload.get("policy") != "role-aware-v2":
        raise SystemExit(f"{path}: expected role-aware-v2 policy")
    domain = payload.get("domain", {})
    if domain.get("men_gap") != 2 or domain.get("equal_king_counts") is not True:
        raise SystemExit(f"{path}: wrong exact-domain contract")
    if payload.get("holdout_records_untouched", 0) <= 0:
        raise SystemExit(f"{path}: holdout proof missing")
    matrix = payload.get("weight_semantics", {}).get("matrix_side_to_move_pov")
    expected = {
        "up": {"win": 1.0, "draw": 2.0, "loss": 4.0},
        "down": {"win": 4.0, "draw": 2.0, "loss": 1.0},
    }
    if matrix != expected:
        raise SystemExit(f"{path}: role matrix differs from preregistered 1/2/4 symmetry")
    source.update(payload.get("source_training_buckets", {}))
    resampled.update(payload.get("resampled_training_buckets", {}))
    domain_records += int(domain.get("records", 0))
    anchor_records += int(domain.get("outside_domain_anchor_records", 0))

if domain_records <= 0:
    raise SystemExit("role-aware-v2: exact-domain corpus is empty")

manifest = art / f"l3-imbalance2-{phase.lower()}-manifest.json"
if not manifest.exists():
    raise SystemExit(f"role-aware-v2: base manifest missing: {manifest}")
payload = json.loads(manifest.read_text())
payload["schema"] = 3
payload["lineage"] = "L3-IMBALANCE2-ROLE-V2"
payload["parent_recipe"] = "L3-IMBALANCE2 V1 exact-TB lineage"
payload["training_semantics"] = {
    "policy": "role-aware-v2",
    "classification": "per-position current material and side-to-move",
    "specialist_domain": {"men_gap": 2, "equal_king_counts": True},
    "conversion_weights_stm_pov": {"win": 1, "draw": 2, "loss": 4},
    "resilience_weights_stm_pov": {"win": 4, "draw": 2, "loss": 1},
    "outside_domain_anchor_weight": 1,
    "holdout_weighted": False,
    "output_record_count_unchanged": True,
    "per_move_criticality_relabel": False,
    "deep_teacher_used_for_weighting": False,
}
fit = payload.setdefault("recipe", {}).setdefault("fit", {})
fit.pop("material_up_outcome_resampling", None)
fit["role_domain_resampling"] = payload["training_semantics"]
payload["role_weighting_reports"] = [path.name for path in reports]
payload["role_weighting_totals"] = {
    "source_training_buckets": dict(sorted(source.items())),
    "resampled_training_buckets": dict(sorted(resampled.items())),
    "exact_domain_records": domain_records,
    "outside_domain_anchor_records": anchor_records,
}
manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

summary = {
    "schema": 1,
    "lineage": payload["lineage"],
    "phase": phase,
    "generation_reports": [path.name for path in reports],
    "source_training_buckets": dict(sorted(source.items())),
    "resampled_training_buckets": dict(sorted(resampled.items())),
    "exact_domain_records": domain_records,
    "outside_domain_anchor_records": anchor_records,
    "manifest": manifest.name,
}
(art / f"l3-imbalance2-role-v2-{phase.lower()}-summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n"
)
PY

printf '%s\n' "role-aware-v2 manifest validated: exact two-men/equal-kings conversion+resilience matrix" \
  | tee -a "$JASS_ARTEFACT_DIR/RESULTS.txt"
