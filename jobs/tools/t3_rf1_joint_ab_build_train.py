#!/usr/bin/env python3
"""Build the immutable historical A/B/C training union for T3 RF1 Joint A/B.

The source-priority and canonical-parent de-duplication rules are frozen in
docs/experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md.  This tool only converts
already-labelled historical cohorts into the three inputs consumed by
t3_rf1_joint_ab.py; it does not fit, score, select or inspect fresh data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from jobs.tools import residual_feature_historical_screen as hs
from jobs.tools import residual_feature_probe as rf
from jobs.tools import t3_rf1_joint_ab as t3


SOURCE_PRIORITY = ("TRAIN_A", "TRAIN_B", "TRAIN_C")


@dataclass(frozen=True)
class BaselineRow:
    row_index: int
    parent_id: int
    parent_stm: int
    t_baseline_parent: float


@dataclass
class UnionData:
    features: np.ndarray
    static_rows: list[dict[str, object]]
    pair_rows: list[dict[str, int]]
    receipt: dict[str, object]


def load_baselines(path: Path, cohort: hs.Cohort) -> list[BaselineRow]:
    out: list[BaselineRow] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"row_index", "parent_id", "parent_stm", "t_baseline_parent"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"baseline fields drift: {reader.fieldnames!r}")
        for raw in reader:
            out.append(
                BaselineRow(
                    row_index=int(raw["row_index"]),
                    parent_id=int(raw["parent_id"]),
                    parent_stm=int(raw["parent_stm"]),
                    t_baseline_parent=float(raw["t_baseline_parent"]),
                )
            )
    if len(out) != len(cohort.meta) or [row.row_index for row in out] != list(range(len(out))):
        raise ValueError("baseline row geometry drift")
    for row, sibling in zip(out, cohort.meta):
        if (row.parent_id, row.parent_stm) != (sibling.parent_id, sibling.parent_stm):
            raise ValueError("baseline/cohort identity drift")
        if not np.isfinite(row.t_baseline_parent):
            raise ValueError("nonfinite T0 baseline")
    return out


def assemble_union(
    cohorts: Sequence[tuple[str, hs.Cohort]],
    baselines: Mapping[str, Sequence[BaselineRow]],
) -> UnionData:
    names = tuple(name for name, _ in cohorts)
    if names != SOURCE_PRIORITY:
        raise ValueError(f"source priority drift: {names!r}")

    seen: dict[str, str] = {}
    features: list[np.ndarray] = []
    static_rows: list[dict[str, object]] = []
    pair_rows: list[dict[str, int]] = []
    source_stats: dict[str, dict[str, int]] = {}
    owner_lines: list[str] = []
    next_parent_id = 0

    for source_name, cohort in cohorts:
        source_baselines = list(baselines[source_name])
        if len(source_baselines) != len(cohort.meta):
            raise ValueError(f"{source_name} baseline geometry drift")
        kept = 0
        dropped = 0
        kept_rows = 0
        kept_pairs = 0
        for local_parent_id in sorted(cohort.parents):
            parent = cohort.parents[local_parent_id]
            if parent.canonical in seen:
                dropped += 1
                continue
            seen[parent.canonical] = source_name
            owner_lines.append(f"{parent.canonical}\t{source_name}")
            kept += 1
            row_map: dict[int, int] = {}
            for local_row in sorted(cohort.parent_rows[local_parent_id]):
                sibling = cohort.meta[local_row]
                baseline = source_baselines[local_row]
                if sibling.parent_id != local_parent_id or baseline.parent_id != local_parent_id:
                    raise ValueError("parent row ownership drift")
                global_row = len(features)
                row_map[local_row] = global_row
                features.append(np.asarray(cohort.features[local_row], dtype=np.float64))
                static_rows.append(
                    {
                        "parent_id": next_parent_id,
                        "parent_stm": parent.stm,
                        "phase": parent.phase,
                        "t_baseline_parent": baseline.t_baseline_parent,
                        "d1_parent": float(cohort.d1[local_row]),
                    }
                )
                kept_rows += 1
            for good, bad in cohort.pairs.get(local_parent_id, []):
                pair_rows.append(
                    {
                        "parent_id": next_parent_id,
                        "parent_stm": parent.stm,
                        "good_row": row_map[good],
                        "bad_row": row_map[bad],
                    }
                )
                kept_pairs += 1
            next_parent_id += 1
        source_stats[source_name] = {
            "parents_total": len(cohort.parents),
            "parents_retained": kept,
            "parents_deduplicated": dropped,
            "rows_retained": kept_rows,
            "stable_pairs_retained": kept_pairs,
        }

    matrix = np.asarray(features, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != rf.TOTAL_WIDTH:
        raise ValueError(f"union residual geometry drift: {matrix.shape}")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("nonfinite union residual feature")
    if not pair_rows:
        raise ValueError("empty T3 historical pair union")
    canonical_sha = hashlib.sha256(("\n".join(owner_lines) + "\n").encode()).hexdigest()
    receipt: dict[str, object] = {
        "schema": "jass.t3_rf1_joint_ab_train_union.v1",
        "source_priority": list(SOURCE_PRIORITY),
        "canonical_parent_count": len(seen),
        "canonical_owner_sha256": canonical_sha,
        "rows": len(static_rows),
        "stable_pairs": len(pair_rows),
        "sources": source_stats,
        "fresh_labels_read": 0,
        "q1_label_reads": 0,
        "q1_score_reads": 0,
        "t2_fresh_label_reads": 0,
        "t2_fresh_score_reads": 0,
        "rf1_fresh_label_reads": 0,
        "rf1_fresh_score_reads": 0,
    }
    return UnionData(matrix, static_rows, pair_rows, receipt)


def write_union(data: UnionData, rffd: Path, static_meta: Path, pairs: Path, receipt: Path) -> dict[str, object]:
    rffd.parent.mkdir(parents=True, exist_ok=True)
    matrix = np.ascontiguousarray(data.features, dtype="<f4")
    rffd.write_bytes(struct.pack("<4sII", b"RFFD", matrix.shape[0], matrix.shape[1]) + matrix.tobytes())

    with static_meta.open("w", newline="", encoding="utf-8") as handle:
        fields = ["parent_id", "parent_stm", "phase", "t_baseline_parent", "d1_parent"]
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(data.static_rows)
    with pairs.open("w", newline="", encoding="utf-8") as handle:
        fields = ["parent_id", "parent_stm", "good_row", "bad_row"]
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(data.pair_rows)

    meta = t3.load_static_meta(static_meta)
    loaded_pairs = t3.load_pairs(pairs, meta)
    xa, xb, base = t3.build_inputs(rffd, meta)
    if (xa.shape, xb.shape, base.shape) != ((len(meta), 66), (len(meta), 67), (len(meta),)):
        raise AssertionError("T3 reload geometry drift")
    if len(loaded_pairs) != len(data.pair_rows):
        raise AssertionError("T3 pair reload drift")

    payload = dict(data.receipt)
    payload.update(
        {
            "rffd_sha256": hashlib.sha256(rffd.read_bytes()).hexdigest(),
            "static_meta_sha256": hashlib.sha256(static_meta.read_bytes()).hexdigest(),
            "pairs_sha256": hashlib.sha256(pairs.read_bytes()).hexdigest(),
            "reload_exact": True,
        }
    )
    receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    for prefix in ("a", "b", "c"):
        parser.add_argument(f"--{prefix}-parents", type=Path, required=True)
        parser.add_argument(f"--{prefix}-groups", type=Path, required=True)
        parser.add_argument(f"--{prefix}-rffd", type=Path, required=True)
        parser.add_argument(f"--{prefix}-feat", type=Path, required=True)
    parser.add_argument("--d1", type=Path, required=True)
    parser.add_argument("--out-rffd", type=Path, required=True)
    parser.add_argument("--out-static-meta", type=Path, required=True)
    parser.add_argument("--out-pairs", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    policy = hs.load_d1(args.d1)
    cohorts: list[tuple[str, hs.Cohort]] = []
    baselines: dict[str, list[BaselineRow]] = {}
    for key, name in zip(("a", "b", "c"), SOURCE_PRIORITY):
        cohort = hs.make_cohort(
            name,
            getattr(args, f"{key}_parents"),
            getattr(args, f"{key}_groups"),
            getattr(args, f"{key}_rffd"),
            getattr(args, f"{key}_feat"),
            policy,
        )
        cohorts.append((name, cohort))
        baselines[name] = load_baselines(getattr(args, f"{key}_groups"), cohort)
    payload = write_union(
        assemble_union(cohorts, baselines),
        args.out_rffd,
        args.out_static_meta,
        args.out_pairs,
        args.receipt,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
