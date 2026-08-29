#!/usr/bin/env python3
"""R0-v4 frozen T3 plus data-free ZERO Python/native parity readout."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from jobs.tools.t3_f6_runtime_parity_v2 import verify as verify_frozen
from jobs.tools.t3_f6_zero_artifact_v4 import canonical_bytes, payload

ZERO_SHA = "160489327d419e3d7bbbbda900d6e0ec7bc960111149fc0a45cc27aaa55bf6aa"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(args: argparse.Namespace) -> dict[str, object]:
    frozen = verify_frozen(
        args.native_tsv, args.reference_rffd, args.model, args.curriculum)
    if args.zero.read_bytes() != canonical_bytes() or sha(args.zero) != ZERO_SHA:
        raise ValueError("canonical ZERO artifact bytes/SHA drift")
    zero = json.loads(args.zero.read_text(encoding="utf-8"))
    if zero != payload():
        raise ValueError("ZERO artifact payload drift")
    contract = json.loads(args.wrapper_contract.read_text(encoding="utf-8"))
    if (contract.get("schema") != "jass.t3_f6_runtime_wrapper_contract.v4"
            or contract.get("zero_sha256") != ZERO_SHA
            or contract.get("zero_leaf_mismatch_count") != 0
            or contract.get("zero_nonfinite_count") != 0
            or contract.get("zero_saturation_count") != 0):
        raise ValueError("native ZERO parity receipt failed")
    return {
        "schema": "jass.t3_f6_runtime_parity.v4",
        "passed": True,
        "verdict": "R0_V4_PYTHON_NATIVE_PARITY_PASS",
        "rows": frozen["rows"],
        "feature_coordinates": frozen["feature_coordinates"],
        "feature_bitwise_mismatches": frozen["feature_bitwise_mismatches"],
        "normalized_feature_coordinates": frozen["normalized_feature_coordinates"],
        "normalized_bitwise_mismatches": frozen["normalized_bitwise_mismatches"],
        "max_residual_abs_error": frozen["max_residual_abs_error"],
        "max_t3_float_abs_error": frozen["max_t3_float_abs_error"],
        "residual_tolerance": frozen["residual_tolerance"],
        "integer_score_mismatches": frozen["integer_score_mismatches"],
        "rounding": frozen["rounding"],
        "scale_cp": 1.0,
        "clamp_cp": [-20000, 20000],
        "saturations": frozen["saturations"],
        "zero_sha256": ZERO_SHA,
        "zero_residual_bitwise_positive_zero": True,
        "zero_engine_mismatches": contract["zero_leaf_mismatch_count"],
        "model_sha256": frozen["model_sha256"],
        "curriculum_sha256": frozen["curriculum_sha256"],
        "deep_label_reads": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-tsv", type=Path, required=True)
    parser.add_argument("--reference-rffd", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--zero", type=Path, required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--wrapper-contract", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args)
    except Exception as error:
        report = {
            "schema": "jass.t3_f6_runtime_parity.v4",
            "passed": False,
            "verdict": "R0_V4_PYTHON_NATIVE_PARITY_FAILED",
            "error": str(error),
            "zero_sha256": ZERO_SHA,
            "deep_label_reads": 0,
        }
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
