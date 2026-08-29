#!/usr/bin/env python3
"""Inference-only T0/D1/RF1/T3-A scorer for Scan-ceiling siblings."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.deep_sibling_pairwise import load_feat  # noqa: E402
from jobs.tools import residual_feature_probe as rf  # noqa: E402
from jobs.tools import t3_rf1_joint_ab as t3  # noqa: E402

T0_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
D1_SHA = "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"
RF1_SHA = "0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b"
T3_A_SHA = "16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2"
MOVE_FEATURE_NAMES = [
    "num_captures", "captured_kings", "promotes", "moving_king",
    "from_norm", "to_norm",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def authenticate(path: Path, expected: str, label: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"{label} SHA drift: {actual} != {expected}")


def load_groups(path: Path) -> dict[str, np.ndarray]:
    names = [
        "row_index", "parent_id", "parent_stm", "parent_phase", "from", "to",
        "num_captures", "captured_kings", "promotes", "moving_king", "t0_parent",
        "child_rule_terminal", "child_tb_exact", "exact_parent_utility",
    ]
    columns: dict[str, list[str]] = {name: [] for name in names}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None or not set(names).issubset(reader.fieldnames):
            raise ValueError(f"sibling group fields drift: {reader.fieldnames!r}")
        for row in reader:
            for name in names:
                columns[name].append(row[name])
    count = len(columns["row_index"])
    if [int(value) for value in columns["row_index"]] != list(range(count)):
        raise ValueError("sibling row_index drift")
    phases = np.asarray(columns["parent_phase"], dtype=object)
    if not set(phases).issubset({"P0", "P1", "P2", "P3"}):
        raise ValueError("invalid parent phase")
    result = {
        "parent_id": np.asarray(columns["parent_id"], dtype=np.int32),
        "stm": np.asarray(columns["parent_stm"], dtype=np.int8),
        "phase": phases,
        "from": np.asarray(columns["from"], dtype=np.float64),
        "to": np.asarray(columns["to"], dtype=np.float64),
        "num_captures": np.asarray(columns["num_captures"], dtype=np.float64),
        "captured_kings": np.asarray(columns["captured_kings"], dtype=np.float64),
        "promotes": np.asarray(columns["promotes"], dtype=np.float64),
        "moving_king": np.asarray(columns["moving_king"], dtype=np.float64),
        "t0": np.asarray(columns["t0_parent"], dtype=np.float64),
        "terminal_exact": np.asarray(columns["child_rule_terminal"], dtype=np.int8),
        "tb_exact": np.asarray(columns["child_tb_exact"], dtype=np.int8),
        "exact_parent_utility": np.asarray(columns["exact_parent_utility"], dtype=np.int8),
    }
    if not np.all((result["stm"] == 0) | (result["stm"] == 1)):
        raise ValueError("invalid parent STM")
    exact = (result["terminal_exact"] == 1) | (result["tb_exact"] == 1)
    if (np.any((result["terminal_exact"] < 0) | (result["terminal_exact"] > 1))
            or np.any((result["tb_exact"] < 0) | (result["tb_exact"] > 1))
            or np.any((result["terminal_exact"] + result["tb_exact"]) > 1)
            or np.any(~np.isin(result["exact_parent_utility"][exact], (-1, 0, 1)))
            or np.any(result["exact_parent_utility"][~exact] != 2)):
        raise ValueError("static exact-priority metadata drift")
    return result


def load_d1(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    authenticate(path, D1_SHA, "D1")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (payload.get("schema") != "jass.deep_sibling_policy.v1"
            or payload.get("usable") is not True
            or payload.get("eval_feature_width") != 120
            or payload.get("move_feature_names") != MOVE_FEATURE_NAMES
            or payload.get("score_convention") != "higher_is_better_for_parent"):
        raise ValueError("sealed D1 contract drift")
    white = np.asarray(payload["weights"]["white_parent"], dtype=np.float64)
    black = np.asarray(payload["weights"]["black_parent"], dtype=np.float64)
    if white.shape != (126,) or black.shape != (126,):
        raise ValueError("D1 feature width drift")
    return white, black, payload


def d1_scores(features: np.ndarray, groups: dict[str, np.ndarray], weights: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    move = np.column_stack([
        groups["num_captures"], groups["captured_kings"], groups["promotes"],
        groups["moving_king"], groups["from"] / 50.0, groups["to"] / 50.0,
    ])
    design = np.concatenate([features, move], axis=1)
    if design.shape[1] != 126:
        raise ValueError("D1 design width drift")
    out = np.empty(len(design), dtype=np.float64)
    white = groups["stm"] == 0
    out[white] = design[white] @ weights[0]
    out[~white] = design[~white] @ weights[1]
    return out


def load_t3(path: Path) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, dict[str, object]]:
    authenticate(path, T3_A_SHA, "T3-A")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (payload.get("schema") != t3.SCHEMA or payload.get("arm") != "T3_F6_ONLY"
            or payload.get("input_width") != 66
            or payload.get("score_convention") != "higher_is_better_for_parent"):
        raise ValueError("T3-A artifact contract drift")
    provenance = payload.get("provenance", {})
    if provenance.get("t0_sha256") != T0_SHA or provenance.get("rf1_sha256") != RF1_SHA:
        raise ValueError("T3-A upstream provenance drift")
    mean = np.asarray(payload["normalization"]["mean"], dtype=np.float64)
    std = np.asarray(payload["normalization"]["std"], dtype=np.float64)
    model = {name: np.asarray(value, dtype=np.float64) for name, value in payload["params"].items()}
    expected = {
        "W0": (66, 256), "b0": (256,), "W1": (256, 128), "b1": (128,),
        "W2": (128, 64), "b2": (64,), "W3": (64, 1), "b3": (1,),
    }
    if mean.shape != (66,) or std.shape != (66,) or np.any(std <= 0):
        raise ValueError("T3-A normalization drift")
    for name, shape in expected.items():
        if name not in model or model[name].shape != shape:
            raise ValueError(f"T3-A parameter shape drift: {name}")
    return model, mean, std, payload


def compute(
    groups: dict[str, np.ndarray],
    features: np.ndarray,
    rffd: np.ndarray,
    d1_path: Path,
    rf1_path: Path,
    t3_path: Path,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    count = len(groups["t0"])
    if features.shape != (count, 120) or rffd.shape != (count, rf.TOTAL_WIDTH):
        raise ValueError("static feature/group geometry drift")
    d1w, d1b, _ = load_d1(d1_path)
    d1 = d1_scores(features, groups, (d1w, d1b))
    authenticate(rf1_path, RF1_SHA, "RF1")
    rf1_artifact = rf.load_artifact(rf1_path)
    if rf1_artifact.family != "F6_ALL_NEW" or rf1_artifact.d1_sha256 != D1_SHA:
        raise ValueError("RF1 family/upstream drift")
    f6 = rf.family_matrix(rffd, "F6_ALL_NEW")
    rf1_score = rf1_artifact.predict(f6, d1)
    model, mean, std, _ = load_t3(t3_path)
    t3_score = t3.parent_scores(model, f6, groups["t0"], mean, std)
    scores = {
        "t0": groups["t0"].copy(), "d1": d1,
        "rf1": rf1_score, "t3_a": t3_score,
    }
    terminal = groups["terminal_exact"] == 1
    tb_exact = groups["tb_exact"] == 1
    exact = terminal | tb_exact
    exact_score = groups["exact_parent_utility"].astype(np.float64) * (30_000 - 64 - 1)
    exact_score[terminal] = groups["exact_parent_utility"][terminal].astype(np.float64) * 30_000
    for value in scores.values():
        value[exact] = exact_score[exact]
    if not all(np.all(np.isfinite(value)) for value in scores.values()):
        raise ValueError("nonfinite frozen static score")
    receipt = {
        "rows": count,
        "features_shape": list(features.shape),
        "rffd_shape": list(rffd.shape),
    }
    return scores, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--rffd", type=Path, required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--d1", type=Path, required=True)
    parser.add_argument("--rf1", type=Path, required=True)
    parser.add_argument("--t3-a", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    authenticate(args.curriculum, T0_SHA, "CURRICULUM")
    groups = load_groups(args.groups)
    features = load_feat(args.features)
    rffd = rf.read_rffd(args.rffd)
    first, receipt = compute(groups, features, rffd, args.d1, args.rf1, args.t3_a)
    second, _ = compute(groups, features, rffd, args.d1, args.rf1, args.t3_a)
    replay = all(np.array_equal(first[name], second[name]) for name in first)
    if not replay:
        raise ValueError("frozen static replay drift")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["row_index", "t0_parent", "d1_parent", "rf1_parent", "t3_a_parent"])
        for row in range(receipt["rows"]):
            writer.writerow([
                row,
                format(float(first["t0"][row]), ".17g"),
                format(float(first["d1"][row]), ".17g"),
                format(float(first["rf1"][row]), ".17g"),
                format(float(first["t3_a"][row]), ".17g"),
            ])
    payload = {
        "schema": "jass.scan_ceiling_static_scores.v1",
        "benchmark_only": True,
        "score_convention": "higher_is_better_for_parent",
        "rows": receipt["rows"],
        "feature_geometry": receipt,
        "exact_priority": {
            "terminal_rows": int(np.sum(groups["terminal_exact"] == 1)),
            "egdb_rows": int(np.sum(groups["tb_exact"] == 1)),
            "terminal_parent_score_magnitude": 30000,
            "egdb_parent_score_magnitude": 29935,
        },
        "artifacts": {
            "curriculum": T0_SHA, "d1": D1_SHA, "rf1": RF1_SHA, "t3_a": T3_A_SHA,
        },
        "groups_sha256": sha256(args.groups),
        "features_sha256": sha256(args.features),
        "rffd_sha256": sha256(args.rffd),
        "output_sha256": sha256(args.output),
        "deterministic_replay_exact": replay,
        "fits": 0, "refits": 0, "calibrations": 0,
        "feature_selections": 0, "model_selections": 0,
        "strength_games": 0, "promotion_authorized": False,
        "training_allowed": False, "tuning_allowed": False,
        "calibration_allowed": False, "model_selection_allowed": False,
        "runtime_scale_selection_allowed": False,
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": receipt["rows"], "replay": replay}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
