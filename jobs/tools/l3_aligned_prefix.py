#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copy an exact aligned prefix from counted JNNW/JSM1 files.

This is a diagnostic utility.  It never mutates its inputs and refuses to
replace outputs.  The prefix is record-order based; it is not a randomized
sample and must not be interpreted as a training learning curve.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path


HEADER = struct.Struct("<4sI")
FORMATS = {
    b"JNNW": 38,
    b"JSM1": 17,
}
CHUNK_RECORDS = 1 << 16


def _inspect(path: Path, expected_magic: bytes) -> tuple[int, int]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        raw = handle.read(HEADER.size)
    if len(raw) != HEADER.size:
        raise ValueError(f"{path}: truncated header")
    magic, count = HEADER.unpack(raw)
    if magic != expected_magic:
        raise ValueError(f"{path}: magic {magic!r}, expected {expected_magic!r}")
    record_size = FORMATS[expected_magic]
    expected = HEADER.size + count * record_size
    if size != expected:
        raise ValueError(f"{path}: size {size} != counted size {expected}")
    return count, record_size


def _stage_prefix(source: Path, destination: Path, magic: bytes, records: int) -> tuple[Path, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    record_size = FORMATS[magic]
    remaining = records
    try:
        with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
            reader.read(HEADER.size)
            header = HEADER.pack(magic, records)
            writer.write(header)
            digest.update(header)
            while remaining:
                take = min(remaining, CHUNK_RECORDS)
                payload = reader.read(take * record_size)
                if len(payload) != take * record_size:
                    raise ValueError(f"{source}: truncated while copying prefix")
                writer.write(payload)
                digest.update(payload)
                remaining -= take
            writer.flush()
            os.fsync(writer.fileno())
        return temporary, digest.hexdigest()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _publish_no_clobber(temporary: Path, destination: Path) -> None:
    try:
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise ValueError(f"refusing to replace {destination}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def slice_pair(data: Path, meta: Path, out_data: Path, out_meta: Path, records: int) -> dict:
    paths = [data.resolve(), meta.resolve(), out_data.resolve(), out_meta.resolve()]
    if len(set(paths)) != len(paths):
        raise ValueError("input and output paths must all be distinct")
    data_count, _ = _inspect(data, b"JNNW")
    meta_count, _ = _inspect(meta, b"JSM1")
    if data_count != meta_count:
        raise ValueError(f"data/meta count mismatch: {data_count} != {meta_count}")
    if records <= 0 or records > data_count:
        raise ValueError(f"records must be in [1,{data_count}], got {records}")
    if out_data.exists() or out_meta.exists():
        raise ValueError("refusing to replace an existing output")

    staged_data, data_sha = _stage_prefix(data, out_data, b"JNNW", records)
    staged_meta = None
    published_data = False
    try:
        staged_meta, meta_sha = _stage_prefix(meta, out_meta, b"JSM1", records)
        _publish_no_clobber(staged_data, out_data)
        published_data = True
        _publish_no_clobber(staged_meta, out_meta)
    except BaseException:
        staged_data.unlink(missing_ok=True)
        if staged_meta is not None:
            staged_meta.unlink(missing_ok=True)
        if published_data:
            out_data.unlink(missing_ok=True)
        raise

    return {
        "schema": 1,
        "operation": "aligned_record_order_prefix",
        "diagnostic_only": True,
        "randomized_sample": False,
        "learning_curve_authorized": False,
        "source_records": data_count,
        "records": records,
        "data_sha256": data_sha,
        "meta_sha256": meta_sha,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--meta", required=True, type=Path)
    parser.add_argument("--out-data", required=True, type=Path)
    parser.add_argument("--out-meta", required=True, type=Path)
    parser.add_argument("--records", required=True, type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = slice_pair(
            args.data, args.meta, args.out_data, args.out_meta, args.records
        )
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.report:
            if args.report.exists():
                raise ValueError(f"refusing to replace {args.report}")
            args.report.write_text(payload, encoding="utf-8", newline="\n")
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        print(f"l3_aligned_prefix: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
