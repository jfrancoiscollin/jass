#!/usr/bin/env python3
"""Materialize the preregistered Discovery A causal search arms."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ARM_ORDER = (
    "J0",
    "J1_SCAN_VERIFY",
    "J2_SCAN_THREAT_REENTRY",
    "J3_SCAN_SINGLE_REPLY",
    "J4_SCAN_LMR",
    "J5_SCAN_ORDERING",
    "J6_NO_NULL_MOVE",
)

AXIS_ORDER = ARM_ORDER[1:]

OVERRIDES: dict[str, dict[str, int]] = {
    "J0": {},
    "J1_SCAN_VERIFY": {"scan_verify_pruning": 1},
    "J2_SCAN_THREAT_REENTRY": {
        "qs_threat_ext": 0,
        "scan_threat_reentry": 1,
    },
    "J3_SCAN_SINGLE_REPLY": {"ext_single_reply": 1},
    "J4_SCAN_LMR": {"scan_lmr_semantics": 1},
    "J5_SCAN_ORDERING": {"scan_probabilistic_ordering": 1},
    "J6_NO_NULL_MOVE": {"disable_null_move": 1},
}

SOURCE_ANCHORS = {
    "J1_SCAN_VERIFY": "scan:src/search.cpp:1137-1160",
    "J2_SCAN_THREAT_REENTRY": "scan:src/search.cpp:1332-1336",
    "J3_SCAN_SINGLE_REPLY": "scan:src/search.cpp:1405-1423",
    "J4_SCAN_LMR": "scan:src/search.cpp:1248-1293,1425-1440",
    "J5_SCAN_ORDERING": "scan:src/sort.cpp:14-55",
    "J6_NO_NULL_MOVE": "scan:src/search.cpp:no-null-move",
}


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def build_manifest(code_sha: str, evaluator_sha: str) -> dict[str, object]:
    if len(code_sha) != 40 or any(c not in "0123456789abcdef" for c in code_sha):
        raise ValueError("code SHA must be lowercase 40-hex")
    if len(evaluator_sha) != 64 or any(c not in "0123456789abcdef" for c in evaluator_sha):
        raise ValueError("evaluator SHA must be lowercase 64-hex")

    arms: dict[str, object] = {}
    for arm in ARM_ORDER:
        payload = {
            "arm": arm,
            "overrides": OVERRIDES[arm],
            "code_sha": code_sha,
            "evaluator_sha256": evaluator_sha,
        }
        arms[arm] = {
            **payload,
            "arm_semantics_sha256": sha_text(canonical_json(payload)),
            "changed_keys": sorted(OVERRIDES[arm]),
            "source_anchor": SOURCE_ANCHORS.get(arm),
        }

    changed = [set(OVERRIDES[arm]) for arm in AXIS_ORDER]
    if any(not keys for keys in changed):
        raise AssertionError("every causal axis must change at least one key")
    for i, left in enumerate(changed):
        for right in changed[i + 1:]:
            if left & right:
                raise AssertionError("causal arms overlap in mutable keys")

    return {
        "schema": "jass.search_semantics_attribution_variants.v1",
        "protocol": "L3_JASS_SCAN_SEARCH_SEMANTICS_ATTRIBUTION_V1_20260829",
        "code_sha": code_sha,
        "evaluator_sha256": evaluator_sha,
        "arm_order": list(ARM_ORDER),
        "axis_order": list(AXIS_ORDER),
        "arms": arms,
        "axis_count": 6,
        "single_axis_per_treatment": True,
        "parameter_sweeps": 0,
        "training_allowed": False,
        "tuning_allowed": False,
        "strength_games": 0,
        "bake": False,
        "promotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--evaluator-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_manifest(args.code_sha, args.evaluator_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("SEARCH_SEMANTICS_ATTRIBUTION_VARIANTS_FROZEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

