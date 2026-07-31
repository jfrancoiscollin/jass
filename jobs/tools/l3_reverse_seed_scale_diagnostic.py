#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compare immutable reverse-seed 2M/4M corpora and fitted model geometry.

The report is descriptive only.  Atlas rows are correlated record diagnostics,
record-order prefixes are not randomized learning curves, and model-vector
geometry is not a force proxy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

import numpy as np


CODE_SHA_RE = re.compile(r"[0-9a-f]{40}")
PJTW_HEADER = struct.Struct("<5I")
PJTW_MAGIC = 0x57544A50
VERSION_MASK = 0xFF


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def _parse_assignment(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected LABEL=PATH")
    label, raw_path = value.split("=", 1)
    if not label or not raw_path:
        raise argparse.ArgumentTypeError("expected non-empty LABEL=PATH")
    return label, Path(raw_path)


def _assignments(values: list[tuple[str, Path]], kind: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for label, path in values:
        if label in result:
            raise ValueError(f"duplicate {kind} label {label}")
        result[label] = path
    return result


def _load_model(path: Path) -> tuple[tuple[int, ...], np.ndarray, str]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        raw = handle.read(PJTW_HEADER.size)
    if len(raw) != PJTW_HEADER.size:
        raise ValueError(f"{path}: truncated PJTW header")
    header = PJTW_HEADER.unpack(raw)
    magic, version, _scale, n_pat, n_ext = header
    if magic != PJTW_MAGIC or (version & VERSION_MASK) != 3:
        raise ValueError(f"{path}: unsupported PJTW header {header}")
    count = 2 * (n_pat + n_ext)
    expected = PJTW_HEADER.size + 4 * count
    if size != expected:
        raise ValueError(f"{path}: size {size} != expected {expected}")
    weights = np.memmap(path, dtype="<i4", mode="r", offset=PJTW_HEADER.size, shape=(count,))
    return header, weights, _sha256(path)


def _vector_stats(delta: np.ndarray) -> dict:
    work = np.asarray(delta, dtype=np.float64)
    return {
        "l2": float(np.linalg.norm(work)),
        "rms": float(np.sqrt(np.mean(work * work))),
        "mean": float(np.mean(work)),
        "max_abs": float(np.max(np.abs(work), initial=0.0)),
        "nonzero": int(np.count_nonzero(work)),
    }


def _cosine(left: np.ndarray, right: np.ndarray) -> float | None:
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator == 0.0:
        return None
    return float(np.dot(a, b) / denominator)


def _model_geometry(paths: dict[str, Path]) -> dict:
    required = {
        "parent", "stage2_control", "stage2_treatment",
        "stage4_control", "stage4_treatment",
    }
    if set(paths) != required:
        raise ValueError(f"model labels {sorted(paths)} != {sorted(required)}")
    loaded = {label: _load_model(path) for label, path in paths.items()}
    headers = {value[0] for value in loaded.values()}
    if len(headers) != 1:
        raise ValueError("PJTW geometry mismatch")
    parent = loaded["parent"][1]
    offsets: dict[str, np.ndarray] = {}
    offset_stats = {}
    for label in sorted(required - {"parent"}):
        delta = loaded[label][1].astype(np.float64) - parent
        offsets[label] = delta
        offset_stats[label] = _vector_stats(delta)
    pair2 = loaded["stage2_treatment"][1].astype(np.float64) - loaded["stage2_control"][1]
    pair4 = loaded["stage4_treatment"][1].astype(np.float64) - loaded["stage4_control"][1]
    return {
        "header": {
            "magic": next(iter(headers))[0],
            "version": next(iter(headers))[1],
            "scale": next(iter(headers))[2],
            "n_pat": next(iter(headers))[3],
            "n_ext": next(iter(headers))[4],
        },
        "sha256": {label: loaded[label][2] for label in sorted(loaded)},
        "offset_from_parent": offset_stats,
        "treatment_minus_control": {
            "stage2": _vector_stats(pair2),
            "stage4": _vector_stats(pair4),
            "cosine_stage2_vs_stage4": _cosine(pair2, pair4),
        },
        "same_arm_cross_stage_cosine": {
            "control": _cosine(offsets["stage2_control"], offsets["stage4_control"]),
            "treatment": _cosine(offsets["stage2_treatment"], offsets["stage4_treatment"]),
        },
        "force_proxy_authorized": False,
    }


def _validate_source(summary: dict, stage: str, records: int) -> None:
    expected = {
        "stage2": "L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY",
        "stage4": "L3_PURE_REVERSE_SEED_SCALE4M_CAUSAL_AB_ARMS_READY",
    }[stage]
    if (
        summary.get("verdict") != expected
        or summary.get("design", {}).get("records_per_arm") != records
        or summary.get("primary_contrast")
           != "HARD_SEED_SELFPLAY minus MATCHED_RANDOM_SEED_SELFPLAY"
        or summary.get("promotion_authorized") is not False
        or summary.get("automatic_next_job", "missing") is not None
    ):
        raise ValueError(f"{stage}: source summary contract mismatch")
    for arm in ("control", "treatment"):
        if not summary.get("arms", {}).get(arm, {}).get("fit", {}).get("converged"):
            raise ValueError(f"{stage}: {arm} fit not converged")


def _validate_readout(readout: dict, stage: str, records: int, source: dict) -> None:
    expected = {
        "stage2": "L3_PURE_REVERSE_SEED_ABOVE_MATCHED_CONTROL_IC95",
        "stage4": "L3_PURE_REVERSE_SEED_SCALE4M_BELOW_MATCHED_CONTROL",
    }[stage]
    if (
        readout.get("verdict") != expected
        or readout.get("protocol", {}).get("records_per_arm") != records
        or readout.get("protocol", {}).get("fresh_disjoint_openings") is not True
        or readout.get("force_views_summed", {}).get("n") != 6000
        or readout.get("scientific_result") is not True
        or readout.get("promotion_authorized") is not False
        or readout.get("automatic_next_job", "missing") is not None
    ):
        raise ValueError(f"{stage}: readout contract mismatch")
    models = readout.get("models", {})
    for arm in ("control", "treatment"):
        expected_sha = source["arms"][arm]["model_sha256"]
        if models.get(f"{arm}_sha256") != expected_sha:
            raise ValueError(f"{stage}: {arm} readout/source model mismatch")


def _atlas_rows(atlas: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in atlas["atlas"]:
        grouped.setdefault(row["dimension"], []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: row["bucket"])
    return grouped


def _jsd(left: list[float], right: list[float]) -> float:
    total = 0.0
    for p, q in zip(left, right, strict=True):
        midpoint = 0.5 * (p + q)
        if p:
            total += 0.5 * p * math.log2(p / midpoint)
        if q:
            total += 0.5 * q * math.log2(q / midpoint)
    return total


def _corpus_summary(atlas: dict) -> dict:
    rows = _atlas_rows(atlas)["phase"]
    wins = sum(row["wdl_stm_records"]["win"] for row in rows)
    draws = sum(row["wdl_stm_records"]["draw"] for row in rows)
    losses = sum(row["wdl_stm_records"]["loss"] for row in rows)
    eligible = sum(row["conversion"]["eligible_records"] for row in rows)
    converted = sum(row["conversion"]["converted_records"] for row in rows)
    return {
        "records": atlas["records"],
        "games": atlas["games"],
        "openings": atlas["openings"],
        "record_wdl": {"wins": wins, "draws": draws, "losses": losses},
        "record_wdl_score": (wins + 0.5 * draws) / atlas["records"],
        "material_lead_conversion": {
            "eligible_records": eligible,
            "converted_records": converted,
            "rate": converted / eligible if eligible else None,
        },
    }


def _pair_comparison(control: dict, treatment: dict) -> dict:
    if control["records"] != treatment["records"]:
        raise ValueError("paired atlas record count mismatch")
    crows, trows = _atlas_rows(control), _atlas_rows(treatment)
    if set(crows) != set(trows):
        raise ValueError("paired atlas dimensions mismatch")
    dimensions = {}
    for dimension in sorted(crows):
        if [row["bucket"] for row in crows[dimension]] != [row["bucket"] for row in trows[dimension]]:
            raise ValueError(f"{dimension}: paired atlas buckets mismatch")
        shifts = [
            {
                "bucket": c["bucket"],
                "control_share": c["record_share"],
                "treatment_share": t["record_share"],
                "treatment_minus_control": t["record_share"] - c["record_share"],
            }
            for c, t in zip(crows[dimension], trows[dimension], strict=True)
        ]
        top = sorted(shifts, key=lambda row: (-abs(row["treatment_minus_control"]), row["bucket"]))[:3]
        dimensions[dimension] = {
            "jensen_shannon_bits": _jsd(
                [row["record_share"] for row in crows[dimension]],
                [row["record_share"] for row in trows[dimension]],
            ),
            "largest_absolute_share_shifts": top,
        }
    return {
        "records_per_arm": control["records"],
        "control": _corpus_summary(control),
        "treatment": _corpus_summary(treatment),
        "dimensions": dimensions,
    }


def _cross_stage(left: dict, right: dict) -> dict:
    lrows, rrows = _atlas_rows(left), _atlas_rows(right)
    dimensions = {}
    for dimension in sorted(lrows):
        if [x["bucket"] for x in lrows[dimension]] != [x["bucket"] for x in rrows[dimension]]:
            raise ValueError(f"{dimension}: cross-stage atlas buckets mismatch")
        dimensions[dimension] = {
            "jensen_shannon_bits": _jsd(
                [x["record_share"] for x in lrows[dimension]],
                [x["record_share"] for x in rrows[dimension]],
            )
        }
    return {
        "left_records": left["records"],
        "right_records": right["records"],
        "left": _corpus_summary(left),
        "right": _corpus_summary(right),
        "dimensions": dimensions,
    }


def build_report(args: argparse.Namespace) -> dict:
    if not CODE_SHA_RE.fullmatch(args.code_sha):
        raise ValueError("--code-sha must be a lowercase 40-hex SHA")
    atlas_paths = _assignments(args.atlas, "atlas")
    model_paths = _assignments(args.model, "model")
    required_atlases = {
        *(f"stage2_{arm}_{records}" for arm in ("control", "treatment") for records in (1_000_000, 2_000_000)),
        *(f"stage4_{arm}_{records}" for arm in ("control", "treatment") for records in (1_000_000, 2_000_000, 3_000_000, 4_000_000)),
    }
    if set(atlas_paths) != required_atlases:
        raise ValueError(f"atlas labels {sorted(atlas_paths)} != required contract")
    atlases = {label: _read_json(path) for label, path in atlas_paths.items()}
    for label, atlas in atlases.items():
        expected_records = int(label.rsplit("_", 1)[1])
        if (
            atlas.get("schema") != "l3_blind_spot_atlas"
            or atlas.get("records") != expected_records
            or atlas.get("code_sha") != args.code_sha
            or atlas.get("diagnostic_only") is not True
            or atlas.get("gate_authorized") is not False
            or atlas.get("promotion_authorized") is not False
        ):
            raise ValueError(f"{label}: atlas contract mismatch")

    source2 = _read_json(args.stage2_summary)
    source4 = _read_json(args.stage4_summary)
    readout2 = _read_json(args.readout2)
    readout4 = _read_json(args.readout4)
    _validate_source(source2, "stage2", 2_000_000)
    _validate_source(source4, "stage4", 4_000_000)
    _validate_readout(readout2, "stage2", 2_000_000, source2)
    _validate_readout(readout4, "stage4", 4_000_000, source4)

    geometry = _model_geometry(model_paths)
    for stage, source in (("stage2", source2), ("stage4", source4)):
        for arm in ("control", "treatment"):
            label = f"{stage}_{arm}"
            if geometry["sha256"][label] != source["arms"][arm]["model_sha256"]:
                raise ValueError(f"{label}: model SHA mismatch")
    if geometry["sha256"]["parent"] != source2["parent"]["model_sha256"]:
        raise ValueError("parent model SHA mismatch")
    if source2["parent"]["model_sha256"] != source4["parent"]["model_sha256"]:
        raise ValueError("parent changed between stages")

    paired = {}
    for stage, checkpoints in (("stage2", (1_000_000, 2_000_000)), ("stage4", (1_000_000, 2_000_000, 3_000_000, 4_000_000))):
        paired[stage] = {
            str(records): _pair_comparison(
                atlases[f"{stage}_control_{records}"],
                atlases[f"{stage}_treatment_{records}"],
            )
            for records in checkpoints
        }
    cross_stage = {
        arm: {
            str(records): _cross_stage(
                atlases[f"stage2_{arm}_{records}"],
                atlases[f"stage4_{arm}_{records}"],
            )
            for records in (1_000_000, 2_000_000)
        }
        for arm in ("control", "treatment")
    }

    return {
        "schema": 1,
        "verdict": "L3_PURE_REVERSE_SEED_SCALE_DIAGNOSTIC_COMPLETE",
        "code_sha": args.code_sha,
        "question": "describe corpus and fitted-vector changes associated with the 2M positive / 4M negative force inversion",
        "authenticated_force": {
            "stage2": readout2["force_views_summed"],
            "stage4": readout4["force_views_summed"],
        },
        "atlas_inputs": {label: {"path_label": label, "sha256": _sha256(path)} for label, path in sorted(atlas_paths.items())},
        "paired_prefix_diagnostics": paired,
        "cross_stage_same_arm_diagnostics": cross_stage,
        "model_geometry": geometry,
        "interpretation_constraints": {
            "record_order_prefixes_are_randomized_learning_curves": False,
            "atlas_record_rates_are_independent_game_estimates": False,
            "holdout_or_model_geometry_selects_force": False,
            "causal_attribution_authorized": False,
            "training_or_promotion_decision_authorized": False,
        },
        "external_teacher_inputs": 0,
        "self_play_games_generated": 0,
        "models_fitted": 0,
        "scientific_result": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", action="append", type=_parse_assignment, default=[])
    parser.add_argument("--model", action="append", type=_parse_assignment, default=[])
    parser.add_argument("--stage2-summary", required=True, type=Path)
    parser.add_argument("--stage4-summary", required=True, type=Path)
    parser.add_argument("--readout2", required=True, type=Path)
    parser.add_argument("--readout4", required=True, type=Path)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_report(args)
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.out.exists():
            raise ValueError(f"refusing to replace {args.out}")
        args.out.write_text(payload, encoding="utf-8", newline="\n")
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"l3_reverse_seed_scale_diagnostic: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
