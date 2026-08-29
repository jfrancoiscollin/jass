#!/usr/bin/env python3
"""R0 exactness verifier for the frozen T3-A/F6 native evaluator."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np

from jobs.tools import residual_feature_probe as rf
from jobs.tools import t3_rf1_joint_ab as t3

MODEL_SHA = "16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2"
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bits_to_float(text: str) -> np.float32:
    return np.float32(struct.unpack("<f", struct.pack("<I", int(text, 16)))[0])


def round_away_and_clamp(value: float) -> int:
    if not math.isfinite(value):
        raise ValueError("nonfinite T3 score")
    rounded = math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)
    return max(-20000, min(20000, int(rounded)))


def verify(native_tsv: Path, reference_rffd: Path, model_path: Path,
           curriculum_path: Path) -> dict[str, object]:
    if sha256(model_path) != MODEL_SHA:
        raise ValueError("frozen T3-A SHA drift")
    if sha256(curriculum_path) != CURRICULUM_SHA:
        raise ValueError("CURRICULUM SHA drift")
    artifact = json.loads(model_path.read_text(encoding="utf-8"))
    if artifact.get("arm") != "T3_F6_ONLY" or artifact.get("input_width") != 66:
        raise ValueError("T3-A artifact contract drift")
    params = {key: np.asarray(value, dtype=np.float64)
              for key, value in artifact["params"].items()}
    mean = np.asarray(artifact["normalization"]["mean"], dtype=np.float64)
    std = np.asarray(artifact["normalization"]["std"], dtype=np.float64)
    with native_tsv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    reference = rf.family_matrix(rf.read_rffd(reference_rffd), "F6_ALL_NEW")
    if len(rows) != len(reference):
        raise ValueError("native/reference row count drift")

    native_features = np.empty((len(rows), 66), dtype=np.float32)
    for i, row in enumerate(rows):
        if int(row["row"]) != i:
            raise ValueError("native row order drift")
        for j in range(66):
            native_features[i, j] = bits_to_float(row[f"f{j:02d}_bits"])
    ref_f32 = np.asarray(reference, dtype=np.float32)
    feature_mismatches = int(np.count_nonzero(
        native_features.view(np.uint32) != ref_f32.view(np.uint32)))
    if feature_mismatches:
        raise ValueError(f"F6 bitwise parity failed: {feature_mismatches} coordinates")

    predicted = t3.forward(params, (native_features.astype(np.float64) - mean) / std)[0]
    max_residual_abs = 0.0
    max_t3_float_abs = 0.0
    integer_mismatches = 0
    saturations = 0
    for i, row in enumerate(rows):
        native_residual = float(row["residual_parent"])
        native_float = float(row["t3_float"])
        py_residual = float(predicted[i])
        py_float = int(row["t0_int"]) - py_residual
        residual_diff = abs(native_residual - py_residual)
        float_diff = abs(native_float - py_float)
        max_residual_abs = max(max_residual_abs, residual_diff)
        max_t3_float_abs = max(max_t3_float_abs, float_diff)
        tolerance = 1e-8 + 1e-12 * abs(py_residual)
        if residual_diff > tolerance or float_diff > tolerance:
            raise ValueError(f"Python/native float parity failed at row {i}")
        expected_int = round_away_and_clamp(py_float)
        native_int = int(row["t3_int"])
        integer_mismatches += native_int != expected_int
        saturations += abs(native_int) == 20000
    if integer_mismatches:
        raise ValueError(f"integer score parity failed: {integer_mismatches}")
    if saturations:
        raise ValueError(f"R0 saturation gate failed: {saturations}")
    return {
        "schema": "jass.t3_f6_runtime_parity.v1",
        "passed": True,
        "rows": len(rows),
        "feature_coordinates": len(rows) * 66,
        "feature_bitwise_mismatches": feature_mismatches,
        "max_residual_abs_error": max_residual_abs,
        "max_t3_float_abs_error": max_t3_float_abs,
        "residual_tolerance": "1e-8 + 1e-12 * abs(python)",
        "integer_score_mismatches": integer_mismatches,
        "rounding": "std::llround_ties_away_from_zero",
        "scale_cp": 1.0,
        "clamp_cp": [-20000, 20000],
        "saturations": saturations,
        "model_sha256": MODEL_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "deep_label_reads": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-tsv", type=Path, required=True)
    parser.add_argument("--reference-rffd", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.native_tsv, args.reference_rffd, args.model, args.curriculum)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
