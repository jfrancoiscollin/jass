#!/usr/bin/env python3
"""Fetch the immutable T1-bis input bundle from R2 and verify every SHA-256."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--remote", default="r2:jass-data/inputs/t1bis-adj-g1/v1")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--rclone", default="rclone")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    subprocess.run([args.rclone, "copyto", f"{args.remote}/manifest.json", str(manifest_path)], check=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "jass-t1bis-inputs-v1":
        raise SystemExit("invalid input manifest schema")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit("empty input manifest")
    for item in files:
        name = item["name"]
        expected = item["sha256"]
        target = args.out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([args.rclone, "copyto", f"{args.remote}/{name}", str(target)], check=True)
        actual = sha256(target)
        if actual != expected:
            target.unlink(missing_ok=True)
            raise SystemExit(f"sha256 mismatch for {name}: {actual} != {expected}")
    (args.out / "VERIFIED").write_text("ok\n", encoding="utf-8")
    print(json.dumps({"remote": args.remote, "files": len(files), "verified": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
