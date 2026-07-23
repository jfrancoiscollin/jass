#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fingerprint the exact Scan runtime files and forced HUB parameters."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Mapping, Sequence


ACTIVE_FILES = ("scan_linux", "scan.ini", "data/eval")
SCAN_EVAL_BYTES = 8_503_280
HUB_PARAMS = {
    "variant": "normal",
    "book": "false",
    "book-ply": "4",
    "book-margin": "4",
    "ponder": "false",
    "threads": "1",
    "tt-size": "24",
    "bb-size": "0",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(payload: Mapping) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")


def build_manifest(scan_dir: Path) -> dict:
    root = scan_dir.resolve()
    files = []
    for relative in ACTIVE_FILES:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"missing active Scan runtime file: {relative}")
        files.append({
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    eval_record = next(row for row in files if row["path"] == "data/eval")
    if eval_record["bytes"] != SCAN_EVAL_BYTES:
        raise ValueError(
            f"data/eval has {eval_record['bytes']} bytes, expected {SCAN_EVAL_BYTES}"
        )
    payload = {
        "schema": 1,
        "engine": {"name": "Scan", "version": "3.1"},
        "active_files": files,
        "hub_params": HUB_PARAMS,
    }
    return {
        **payload,
        "runtime_sha256": hashlib.sha256(canonical_bytes(payload)).hexdigest(),
    }


def atomic_write_json(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    manifest = build_manifest(Path(args.scan_dir))
    if args.output:
        atomic_write_json(Path(args.output), manifest)
    print(manifest["runtime_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
