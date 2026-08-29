#!/usr/bin/env python3
"""Authenticate identity-only exclusion sources for Attribution V1 Discovery A."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.scan_ceiling_select import load_exclusions, sha256  # noqa: E402

REQUIRED_STATIC = {"train-a", "train-b", "train-c", "m2", "m3", "m5", "q1", "t2", "rf1", "t3"}
REQUIRED_COVERAGE = {"M1", "M2", "M3", "M4", "M5", "RICH_D_FRESH", "DSSD_CONFIRMATION", "SCAN_CEILING_1651_1660"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != "jass.search_semantics_exclusion_sources.v1":
        raise ValueError("exclusion source manifest schema drift")
    if manifest.get("control_cutoff_ref") != "2c581c640876269cf18d70906b5b6051394e89b1":
        raise ValueError("control cutoff ref drift")
    if manifest.get("jass_code_floor") != "cb91bec5c64b60f1084adb7c0c5459846f4624b1":
        raise ValueError("jass code floor drift")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("empty exclusion source manifest")
    labels = {str(x.get("label")) for x in sources}
    if not REQUIRED_STATIC.issubset(labels) or "scan-ceiling-consumed-1651" not in labels:
        raise ValueError("mandatory static/Scan ceiling exclusion source missing")
    coverage = set(map(str, manifest.get("coverage_claims", [])))
    if not REQUIRED_COVERAGE.issubset(coverage):
        raise ValueError("mandatory scientific-cohort coverage claim missing")
    merged: set[str] = set(); receipts = []
    for item in sources:
        label = str(item.get("label", "")); kind = str(item.get("kind", "")); path = Path(str(item.get("local_path", "")))
        if kind not in {"tsv", "fen"} or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"exclusion source unavailable: {label}")
        identities, _ = load_exclusions([path] if kind == "fen" else [], [path] if kind == "tsv" else [])
        if not identities:
            raise ValueError(f"exclusion source has zero canonical identities: {label}")
        before = len(merged); merged.update(identities)
        receipts.append({
            "label": label, "kind": kind, "source_uri": item.get("source_uri"),
            "job_id": item.get("job_id"), "attempt_id": item.get("attempt_id"),
            "code_sha": item.get("code_sha"), "cohort_sha256": item.get("cohort_sha256"),
            "remote_path": item.get("remote_path"), "local_sha256": sha256(path),
            "canonical_identity_count": len(identities), "new_unique_identities": len(merged) - before,
            "covers": item.get("covers", []),
        })
    dynamic = [x for x in receipts if str(x["label"]).startswith("runtime-precutoff-")]
    if int(manifest.get("expected_dynamic_runtime_sources", -1)) != len(dynamic):
        raise ValueError("dynamic runtime exclusion inventory drift")
    sorted_hash = hashlib.sha256(("\n".join(sorted(merged)) + "\n").encode()).hexdigest()
    payload = {
        "schema": "jass.search_semantics_exclusion_inventory.v1", "passed": True,
        "protocol": "L3_JASS_SCAN_SEARCH_SEMANTICS_ATTRIBUTION_V1_20260829",
        "identity_only": True, "scores_read": 0, "labels_read": 0,
        "cutoff_local": "2026-08-29T18:40:13+02:00",
        "control_cutoff_ref": manifest["control_cutoff_ref"], "jass_code_floor": manifest["jass_code_floor"],
        "coverage_claims": sorted(coverage), "sources": receipts,
        "source_count": len(receipts), "merged_canonical_count": len(merged),
        "sorted_exclusion_set_sha256": sorted_hash,
        "fits": 0, "calibrations": 0, "strength_games": 0,
        "training_allowed": False, "tuning_allowed": False, "promotion_authorized": False,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"sources": len(receipts), "canonical_exclusions": len(merged), "sha256": sorted_hash}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
