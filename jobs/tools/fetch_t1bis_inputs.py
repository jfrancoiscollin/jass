#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Download the immutable T1-bis scientific input set from R2 and verify it.

The input publisher writes all payload objects first, then a manifest, then `_SUCCESS`.
This consumer verifies the marker, manifest hash, exact role set, object sizes and
SHA-256 digests before exposing files to the scientific launcher.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REQUIRED_ROLES = {
    "parent_pattern",
    "fixed_pattern",
    "gen2_pattern",
    "seed_corpus",
    "g1_pool",
    "conversion_gauge",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_capture(args: list[str]) -> bytes:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        tail = proc.stderr[-1000:].decode("utf-8", "replace")
        raise RuntimeError(f"command failed rc={proc.returncode}: {args[0]} …; {tail}")
    return proc.stdout


def remote_json(rclone: str, remote: str) -> dict:
    raw = run_capture([rclone, "cat", remote])
    if not raw:
        raise RuntimeError(f"empty remote JSON: {remote}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError(f"remote JSON is not an object: {remote}")
    return value


def download_verified(rclone: str, remote: str, local: Path, expected_hash: str, expected_size: int) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    local.unlink(missing_ok=True)
    proc = subprocess.run(
        [rclone, "copyto", remote, str(local), "--checksum", "--retries", "8", "--low-level-retries", "10"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        tail = proc.stderr[-1000:].decode("utf-8", "replace")
        raise RuntimeError(f"download failed: {remote}; {tail}")
    if not local.is_file():
        raise RuntimeError(f"download did not create file: {remote}")
    size = local.stat().st_size
    digest = sha256_file(local)
    if size != expected_size or digest != expected_hash:
        local.unlink(missing_ok=True)
        raise RuntimeError(
            f"download verification failed: {remote}; got={size}/{digest} "
            f"expected={expected_size}/{expected_hash}"
        )


def resolve_prefix(cli_prefix: str | None) -> str:
    if cli_prefix:
        return cli_prefix.rstrip("/")
    base = os.environ.get("JASS_OBJSTORE_REMOTE", "").rstrip("/")
    if not base:
        raise RuntimeError("--remote-prefix or JASS_OBJSTORE_REMOTE is required")
    return base + "/inputs/t1bis-adj-g1/v1"


def resolve_manifest_name(success: dict) -> str:
    name = str(success.get("manifest_name") or "manifest.json")
    if not name or Path(name).name != name or name in {".", "..", "_SUCCESS"}:
        raise RuntimeError(f"unsafe manifest name in _SUCCESS: {name!r}")
    return name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-prefix")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--rclone-bin", default=os.environ.get("RCLONE_BIN", "rclone"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    prefix = resolve_prefix(args.remote_prefix)
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    success = remote_json(args.rclone_bin, prefix + "/_SUCCESS")
    if success.get("state") != "completed" or success.get("dataset") != "t1bis-adj-g1-inputs":
        raise RuntimeError("T1-bis input marker is not completed")
    if success.get("version") != "v1":
        raise RuntimeError(f"unsupported T1-bis input version: {success.get('version')!r}")

    manifest_name = resolve_manifest_name(success)
    manifest_raw = run_capture([args.rclone_bin, "cat", prefix + "/" + manifest_name])
    manifest_hash = hashlib.sha256(manifest_raw).hexdigest()
    if manifest_hash != success.get("manifest_sha256"):
        raise RuntimeError("manifest digest differs from _SUCCESS")
    if len(manifest_raw) != int(success.get("manifest_size_bytes", -1)):
        raise RuntimeError("manifest size differs from _SUCCESS")
    manifest = json.loads(manifest_raw)
    objects = manifest.get("objects")
    if not isinstance(objects, list) or not objects:
        raise RuntimeError("input manifest has no objects")

    roles = [str(item.get("role")) for item in objects]
    if set(roles) != REQUIRED_ROLES or len(roles) != len(REQUIRED_ROLES):
        raise RuntimeError(f"input role set mismatch: {sorted(roles)}")

    files: dict[str, str] = {}
    verified: list[dict] = []
    for item in objects:
        role = str(item["role"])
        name = str(item["target_name"])
        if Path(name).name != name:
            raise RuntimeError(f"unsafe target name: {name}")
        remote = str(item["remote"])
        if not remote.startswith(prefix + "/files/"):
            raise RuntimeError(f"object outside input prefix: {remote}")
        expected_hash = str(item["sha256"])
        expected_size = int(item["size_bytes"])
        if len(expected_hash) != 64 or expected_size <= 0:
            raise RuntimeError(f"invalid manifest metadata for role={role}")
        local = out_dir / name
        download_verified(args.rclone_bin, remote, local, expected_hash, expected_size)
        files[role] = str(local)
        verified.append({
            "role": role,
            "path": str(local),
            "size_bytes": expected_size,
            "sha256": expected_hash,
            "source_commit": item.get("source_commit"),
            "source_blob": item.get("source_blob"),
        })

    report = {
        "schema": 1,
        "state": "verified",
        "remote_prefix": prefix,
        "source_commit": manifest.get("source_commit"),
        "manifest_name": manifest_name,
        "manifest_sha256": manifest_hash,
        "files": files,
        "objects": verified,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path = args.report or (out_dir / "verified-inputs.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
