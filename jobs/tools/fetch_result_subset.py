#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fetch a verified, path-preserving subset of one runner-v3 result.

Unlike :mod:`fetch_result_files`, this helper performs one ``rclone copy`` for
an arbitrarily large immutable file list.  Every requested path must be
present and byte-authenticated by both ``inventory.json`` and
``checksums.sha256`` before it is accepted locally.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_t1bis_inputs as base  # noqa: E402


def _safe_paths(path: Path) -> list[str]:
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        value = raw.strip()
        if not value:
            continue
        parsed = PurePosixPath(value)
        if parsed.is_absolute() or ".." in parsed.parts or value != parsed.as_posix():
            raise RuntimeError(f"unsafe result subset path: {value!r}")
        rows.append(value)
    if not rows or len(rows) != len(set(rows)):
        raise RuntimeError("result subset path list is empty or contains duplicates")
    return rows


def _metadata(
    *, rclone: str, prefix: str, expected_state: str
) -> tuple[dict, dict[str, dict], dict[str, str]]:
    marker = "_SUCCESS" if expected_state == "completed" else "_FAILED"
    base.remote_bytes(rclone, f"{prefix}/{marker}")
    manifest, manifest_raw = base.remote_json(rclone, f"{prefix}/manifest.json")
    base.verify_result_identity(prefix, manifest, expected_state=expected_state)
    inventory, inventory_raw = base.remote_json(rclone, f"{prefix}/inventory.json")
    checksums_raw = base.remote_bytes(rclone, f"{prefix}/checksums.sha256")
    files = base.inventory_map(inventory)
    checksums = base.parse_checksums(checksums_raw)
    if checksums.get("inventory.json") != hashlib.sha256(inventory_raw).hexdigest():
        raise RuntimeError("inventory.json digest differs from checksums.sha256")
    manifest_meta = files.get("manifest.json")
    if (
        not manifest_meta
        or manifest_meta["sha256"] != hashlib.sha256(manifest_raw).hexdigest()
        or manifest_meta["size_bytes"] != len(manifest_raw)
        or checksums.get("manifest.json") != manifest_meta["sha256"]
    ):
        raise RuntimeError("manifest.json metadata is inconsistent")
    return manifest, files, checksums


def fetch_subset(
    *,
    rclone: str,
    prefix: str,
    paths: list[str],
    out_dir: Path,
    expected_state: str = "completed",
) -> dict:
    if expected_state not in {"completed", "failed"}:
        raise RuntimeError(f"unsupported expected result state: {expected_state!r}")
    prefix = prefix.rstrip("/")
    manifest, files, checksums = _metadata(
        rclone=rclone, prefix=prefix, expected_state=expected_state
    )
    selected = []
    for value in paths:
        item = files.get(value)
        if item is None or int(item["size_bytes"]) <= 0:
            raise RuntimeError(f"missing/empty result file: {value}")
        if checksums.get(value) != item["sha256"]:
            raise RuntimeError(f"checksum metadata mismatch: {value}")
        selected.append((value, item))

    out_dir.mkdir(parents=True, exist_ok=True)
    for value, _item in selected:
        target = out_dir.joinpath(*PurePosixPath(value).parts)
        target.unlink(missing_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", delete=False,
        prefix="jass-result-subset-", suffix=".txt"
    ) as handle:
        list_path = Path(handle.name)
        handle.write("".join(f"{value}\n" for value, _item in selected))
    try:
        proc = subprocess.run(
            [
                rclone, "copy", prefix, str(out_dir),
                "--files-from", str(list_path), "--no-traverse",
                "--retries", "8", "--low-level-retries", "10",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    finally:
        list_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        tail = proc.stderr[-2000:].decode("utf-8", "replace")
        raise RuntimeError(f"subset download failed rc={proc.returncode}: {tail}")

    report_files = []
    for value, item in selected:
        target = out_dir.joinpath(*PurePosixPath(value).parts)
        if not target.is_file():
            raise RuntimeError(f"subset download did not create file: {value}")
        size = target.stat().st_size
        digest = base.sha256_file(target)
        if size != item["size_bytes"] or digest != item["sha256"]:
            target.unlink(missing_ok=True)
            raise RuntimeError(
                f"subset verification failed: {value}; got={size}/{digest} "
                f"expected={item['size_bytes']}/{item['sha256']}"
            )
        report_files.append({"path": value, **item})
    return {
        "schema": "jass.verified_result_subset.v1",
        "state": "verified",
        "prefix": prefix,
        "job_id": manifest["job_id"],
        "attempt_id": manifest["attempt_id"],
        "code_sha": manifest.get("code_sha"),
        "host": manifest.get("host"),
        "result_state": manifest.get("state"),
        "exit_code": manifest.get("exit_code"),
        "requested_files": len(report_files),
        "files": report_files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--paths-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--rclone-bin", default=os.environ.get("RCLONE_BIN", "rclone"))
    parser.add_argument("--expected-state", choices=("completed", "failed"), default="completed")
    args = parser.parse_args(argv)
    try:
        paths = _safe_paths(args.paths_file)
        report = fetch_subset(
            rclone=args.rclone_bin,
            prefix=args.prefix,
            paths=paths,
            out_dir=args.out_dir,
            expected_state=args.expected_state,
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"state": "verified", "files": len(paths)}, sort_keys=True))
        return 0
    except Exception as exc:  # fail-closed CLI boundary
        print(f"fetch_result_subset: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
