#!/usr/bin/env python3
"""Build aligned, bounded sample weights for failed-conversion rows.

The v1 formula is deliberately narrow: within the certified train partition,
rows where one colour has a material advantage but does not win receive one
fixed multiplier. Every other row, including the complete holdout tail,
receives weight 1. The trainer remains responsible for train-only mean-one
normalisation and for evaluating the holdout without weights.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import struct
import tempfile
from pathlib import Path

import numpy as np

from tools import selfplay_frontier as frontier


SCHEMA = "l3_failed_conversion_sample_weights"
SCHEMA_VERSION = 1
FORMULA = "train_failed_conversion_fixed_multiplier_v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _publish_pair(
    weights_temporary: Path,
    weights_target: Path,
    report_temporary: Path,
    report_target: Path,
) -> None:
    """Publish the two outputs without leaving a one-file partial result."""

    created: list[Path] = []
    try:
        for source, target in (
            (weights_temporary, weights_target),
            (report_temporary, report_target),
        ):
            try:
                os.link(source, target)
            except FileExistsError as exc:
                raise ValueError(
                    f"refusing to overwrite existing output: {target}"
                ) from exc
            except OSError as exc:
                raise ValueError(f"cannot atomically publish {target}: {exc}") from exc
            created.append(target)
    except Exception:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise
    weights_temporary.unlink()
    report_temporary.unlink()


def _validate_record(record: bytes, index: int) -> None:
    if len(record) != frontier.JNNW_REC:
        raise ValueError(f"record {index}: truncated JNNW row")
    stm = record[32]
    wdl = struct.unpack_from("<b", record, 37)[0]
    if stm not in (0, 1):
        raise ValueError(f"record {index}: invalid side-to-move {stm}")
    if wdl not in (-1, 0, 1):
        raise ValueError(f"record {index}: invalid WDL {wdl}")


def build_weights(
    *,
    data_path: Path,
    split_path: Path,
    output_path: Path,
    report_path: Path,
    failed_weight: float,
    code_sha: str,
) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", code_sha):
        raise ValueError("code SHA must be full lowercase 40-hex")
    if not math.isfinite(failed_weight) or not 1.0 <= failed_weight <= 4.0:
        raise ValueError("failed weight must be finite and in [1, 4]")
    if output_path.resolve() == report_path.resolve():
        raise ValueError("weights and report outputs must be distinct")
    for path in (output_path, report_path):
        if path.exists():
            raise ValueError(f"refusing to overwrite existing output: {path}")

    total = frontier._counted_file_count(
        data_path, frontier.JNNW_MAGIC, frontier.JNNW_REC
    )
    split, train_count = frontier._load_split_manifest(split_path, total)
    holdout_count = total - train_count
    if train_count <= 0 or holdout_count <= 0:
        raise ValueError("non-empty train and holdout partitions are required")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.tmp-", dir=output_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()

    failed = 0
    converted = 0
    equal = 0
    initial_stat = data_path.stat()
    try:
        weights = np.lib.format.open_memmap(
            temporary, mode="w+", dtype=np.float32, shape=(total,)
        )
        with data_path.open("rb") as stream:
            header = stream.read(8)
            if (
                len(header) != 8
                or header[:4] != frontier.JNNW_MAGIC
                or struct.unpack_from("<I", header, 4)[0] != total
            ):
                raise ValueError(f"{data_path}: JNNW header changed during read")
            for index in range(total):
                record = stream.read(frontier.JNNW_REC)
                _validate_record(record, index)
                if index < train_count:
                    advantaged = frontier._material(record)[0]
                    winner = frontier._winner(record)
                    is_failed = advantaged is not None and winner != advantaged
                    weights[index] = failed_weight if is_failed else 1.0
                    if advantaged is None:
                        equal += 1
                    elif is_failed:
                        failed += 1
                    else:
                        converted += 1
                else:
                    # The formula is fit-only. The tail cannot influence either
                    # weight construction or train-only normalisation.
                    weights[index] = 1.0
            if stream.read(1):
                raise ValueError(f"{data_path}: unexpected trailing bytes")
        weights.flush()
        del weights
        final_stat = data_path.stat()
        if (
            initial_stat.st_size != final_stat.st_size
            or initial_stat.st_mtime_ns != final_stat.st_mtime_ns
        ):
            raise ValueError(f"{data_path}: input changed while weights were built")

        raw_train_sum = train_count + failed * (failed_weight - 1.0)
        raw_train_mean = raw_train_sum / train_count
        sum_squares = (
            (train_count - failed) * 1.0
            + failed * failed_weight * failed_weight
        )
        ess = raw_train_sum * raw_train_sum / sum_squares
        output_sha = _sha256(temporary)
        payload = {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "operation": "build_sample_weights",
            "formula": {
                "name": FORMULA,
                "failed_conversion_definition": (
                    "material leader from men=1/kings=3 does not win terminal WDL"
                ),
                "train_failed_conversion_weight": failed_weight,
                "train_other_weight": 1.0,
                "holdout_weight": 1.0,
                "clipping_applied": False,
                "outcome_used_only_inside_train": True,
            },
            "code_sha": code_sha,
            "input": {
                "data_sha256": _sha256(data_path),
                "split_sha256": _sha256(split_path),
                "records": total,
            },
            "split": {
                "train_records": train_count,
                "holdout_records": holdout_count,
                "tail_is_holdout": split["tail_is_holdout"],
                "holdout_mod": split["holdout_mod"],
                "seed": split["seed"],
            },
            "train_counts": {
                "failed_conversion": failed,
                "converted_material_leader": converted,
                "equal_material": equal,
            },
            "holdout": {
                "formula_evaluated_for_weighting": False,
                "all_raw_weights_one": True,
            },
            "raw_train_weights": {
                "dtype": "float32",
                "minimum": 1.0,
                "maximum": failed_weight if failed else 1.0,
                "mean": raw_train_mean,
            },
            "effective_sample_size_before_normalization": {
                "kind": "kish_row_level",
                "ess": ess,
                "ess_fraction": ess / train_count,
            },
            "trainer_contract": {
                "normalization": "mean-train-1",
                "holdout_weighted": False,
                "oversampling": False,
            },
            "output": {
                "sha256": output_sha,
                "dtype": "float32",
                "shape": [total],
            },
            "external_teacher_inputs": 0,
            "promotion_authorized": False,
            "automatic_next_job": None,
        }
        report_bytes = (
            json.dumps(payload, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")

        report_descriptor, report_temporary_name = tempfile.mkstemp(
            prefix=f".{report_path.name}.tmp-", dir=report_path.parent
        )
        report_temporary = Path(report_temporary_name)
        try:
            with os.fdopen(report_descriptor, "wb") as stream:
                stream.write(report_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            _publish_pair(
                temporary,
                output_path,
                report_temporary,
                report_path,
            )
        finally:
            report_temporary.unlink(missing_ok=True)
        return payload
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--failed-weight", type=float, required=True)
    parser.add_argument("--code-sha", required=True)
    args = parser.parse_args(argv)
    try:
        payload = build_weights(
            data_path=args.data,
            split_path=args.split_manifest,
            output_path=args.out,
            report_path=args.report,
            failed_weight=args.failed_weight,
            code_sha=args.code_sha,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
