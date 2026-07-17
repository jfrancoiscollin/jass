#!/usr/bin/env python3
"""Fetch selected files from a completed runner-v3 result, fail closed.

Every selected path must agree across ``inventory.json`` and
``checksums.sha256``.  The run identity/state is checked before any payload is
accepted.  This is the generic read-only counterpart to the promotion-specific
chain verification in ``fetch_t1bis_inputs.py``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_t1bis_inputs as base  # noqa: E402


def fetch_files(
    *,
    rclone: str,
    prefix: str,
    selections: list[tuple[str, str]],
    out_dir: Path,
    expected_state: str = "completed",
) -> dict:
    if not selections:
        raise RuntimeError("at least one result file must be selected")
    remote_names = [remote for remote, _ in selections]
    local_names = [local for _, local in selections]
    if (
        len(set(remote_names)) != len(remote_names)
        or len(set(local_names)) != len(local_names)
    ):
        raise RuntimeError("duplicate remote path or local output name")

    if expected_state not in {"completed", "failed"}:
        raise RuntimeError(f"unsupported expected result state: {expected_state!r}")
    prefix = prefix.rstrip("/")
    marker = "_SUCCESS" if expected_state == "completed" else "_FAILED"
    base.remote_bytes(rclone, prefix + "/" + marker)
    manifest, manifest_raw = base.remote_json(rclone, prefix + "/manifest.json")
    base.verify_result_identity(prefix, manifest, expected_state=expected_state)
    inventory, inventory_raw = base.remote_json(rclone, prefix + "/inventory.json")
    checksums_raw = base.remote_bytes(rclone, prefix + "/checksums.sha256")
    checksums = base.parse_checksums(checksums_raw)
    files = base.inventory_map(inventory)
    if checksums.get("inventory.json") != hashlib.sha256(inventory_raw).hexdigest():
        raise RuntimeError("inventory.json digest differs from checksums.sha256")
    meta = files.get("manifest.json")
    if (
        not meta
        or meta["sha256"] != hashlib.sha256(manifest_raw).hexdigest()
        or meta["size_bytes"] != len(manifest_raw)
        or checksums.get("manifest.json") != meta["sha256"]
    ):
        raise RuntimeError("manifest.json metadata is inconsistent")

    out_dir.mkdir(parents=True, exist_ok=True)
    report_files = []
    for remote_path, local_name in selections:
        path = Path(remote_path)
        if (not remote_path or path.is_absolute() or ".." in path.parts
                or local_name != Path(local_name).name):
            raise RuntimeError(f"unsafe selection: {remote_path!r}:{local_name!r}")
        item = files.get(remote_path)
        if item is None or item["size_bytes"] <= 0:
            raise RuntimeError(f"missing/empty result file: {remote_path}")
        if checksums.get(remote_path) != item["sha256"]:
            raise RuntimeError(f"checksum metadata mismatch: {remote_path}")
        target = out_dir / local_name
        base.download_verified(
            rclone,
            prefix + "/" + remote_path,
            target,
            item["sha256"],
            item["size_bytes"],
        )
        report_files.append({
            "path": remote_path,
            "local_name": local_name,
            **item,
        })
    return {
        "schema": 1,
        "state": "verified",
        "prefix": prefix,
        "job_id": manifest["job_id"],
        "attempt_id": manifest["attempt_id"],
        "code_sha": manifest.get("code_sha"),
        "host": manifest.get("host"),
        "result_state": manifest.get("state"),
        "exit_code": manifest.get("exit_code"),
        "files": report_files,
    }


def parse_selection(value: str) -> tuple[str, str]:
    if "=" in value:
        remote, local = value.split("=", 1)
    else:
        remote, local = value, Path(value).name
    return remote, local


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--file", action="append", required=True,
                        help="result/path[=local-name]; repeatable")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--rclone-bin", default=os.environ.get("RCLONE_BIN", "rclone"))
    parser.add_argument(
        "--expected-state",
        choices=("completed", "failed"),
        default="completed",
        help="verify _SUCCESS/exit 0 or _FAILED/non-zero before reading payloads",
    )
    args = parser.parse_args(argv)
    try:
        report = fetch_files(
            rclone=args.rclone_bin,
            prefix=args.prefix,
            selections=[parse_selection(item) for item in args.file],
            out_dir=args.out_dir,
            expected_state=args.expected_state,
        )
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception as exc:  # fail-closed CLI boundary
        print(f"fetch_result_files: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
