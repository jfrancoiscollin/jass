#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a resumable, adaptively sharded R2 object index without payload reads."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
from typing import Any


SCHEMA = "jass.megacorpus.r2_sharded_census.v1"
CONTROL_NAMES = {
    "manifest.json",
    "inventory.json",
    "checksums.sha256",
    "_SUCCESS",
    "_FAILED",
}


def normalize_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid R2 path: {value!r}")
    value = value.replace("\\", "/")
    raw_parts = value.split("/")
    if value.startswith("/") or value.endswith("/") or any(
        part in {"", ".", ".."} for part in raw_parts
    ):
        raise ValueError(f"unsafe R2 path: {value!r}")
    path = PurePosixPath(value)
    if not value or path.is_absolute():
        raise ValueError(f"unsafe R2 path: {value!r}")
    return str(path)


def joined(prefix: str, relative: object) -> str:
    child = normalize_path(relative)
    return normalize_path(f"{prefix}/{child}" if prefix else child)


def shard_name(prefix: str, mode: str) -> str:
    label = prefix or "__root__"
    digest = hashlib.sha256(f"{mode}\0{label}".encode()).hexdigest()[:20]
    return f"{digest}.json.gz"


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_shard(root: Path, prefix: str, mode: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("IsDir") is True:
            continue
        path = joined(prefix, item.get("Path"))
        size = item.get("Size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"invalid object size for {path}: {size!r}")
        modtime = item.get("ModTime")
        if modtime is not None and not isinstance(modtime, str):
            raise ValueError(f"invalid ModTime for {path}")
        rows.append({"Path": path, "Size": size, "ModTime": modtime})
    rows.sort(key=lambda row: row["Path"])
    name = shard_name(prefix, mode)
    output = root / "shards" / name
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with gzip.open(temporary, "wb", compresslevel=6) as handle:
        handle.write(raw)
    os.replace(temporary, output)
    return {
        "file": f"shards/{name}",
        "object_count": len(rows),
        "object_bytes": sum(row["Size"] for row in rows),
        "sha256_uncompressed": hashlib.sha256(raw).hexdigest(),
    }


def read_shard(root: Path, descriptor: dict[str, Any]) -> list[dict[str, Any]]:
    path = root / descriptor["file"]
    with gzip.open(path, "rb") as handle:
        raw = handle.read()
    if hashlib.sha256(raw).hexdigest() != descriptor["sha256_uncompressed"]:
        raise ValueError(f"checkpoint shard digest mismatch: {path}")
    rows = json.loads(raw)
    if not isinstance(rows, list):
        raise ValueError(f"checkpoint shard is not a list: {path}")
    return rows


def rclone_json(
    remote: str,
    prefix: str,
    *,
    recursive: bool,
    files_only: bool,
    dirs_only: bool,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    target = remote.rstrip("/") + (f"/{prefix}" if prefix else "")
    command = ["rclone", "lsjson", target, "--no-mimetype"]
    if recursive:
        command.append("--recursive")
    if files_only:
        command.append("--files-only")
    if dirs_only:
        command.append("--dirs-only")
    last_error = ""
    for attempt in range(1, 4):
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if completed.returncode == 0:
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"rclone returned invalid JSON for {target}: {exc}") from exc
            if not isinstance(payload, list):
                raise RuntimeError(f"rclone did not return a JSON list for {target}")
            return payload
        last_error = completed.stderr[-1000:]
        if attempt < 3:
            time.sleep(attempt)
    raise RuntimeError(f"rclone rc={completed.returncode} target={target}: {last_error}")


def load_state(root: Path, remote: str, split_depth: int, max_depth: int) -> dict[str, Any]:
    path = root / "state.json"
    if not path.exists():
        return {
            "schema": SCHEMA,
            "remote": remote.rstrip("/"),
            "split_depth": split_depth,
            "max_depth": max_depth,
            "prefixes": {},
        }
    state = json.loads(path.read_text(encoding="utf-8"))
    if (
        state.get("schema") != SCHEMA
        or state.get("remote") != remote.rstrip("/")
        or state.get("split_depth") != split_depth
        or state.get("max_depth") != max_depth
    ):
        raise ValueError("resume checkpoint contract differs from requested census")
    return state


def split_prefix(
    remote: str,
    root: Path,
    prefix: str,
    timeout_seconds: int,
) -> tuple[list[str], dict[str, Any]]:
    files = rclone_json(
        remote, prefix, recursive=False, files_only=True, dirs_only=False,
        timeout_seconds=timeout_seconds,
    )
    dirs = rclone_json(
        remote, prefix, recursive=False, files_only=False, dirs_only=True,
        timeout_seconds=timeout_seconds,
    )
    children = sorted({joined(prefix, str(item["Path"]).rstrip("/")) for item in dirs})
    direct = write_shard(root, prefix, "direct", files)
    return children, direct


def census(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint = Path(args.checkpoint_dir)
    checkpoint.mkdir(parents=True, exist_ok=True)
    state = load_state(checkpoint, args.remote, args.split_depth, args.max_depth)
    queue = [""]
    while queue:
        prefix = queue.pop(0)
        entry = state["prefixes"].get(prefix)
        if entry and entry["state"] == "done":
            continue
        if entry and entry["state"] == "split":
            queue.extend(child for child in entry["children"] if child not in queue)
            continue
        depth = 0 if not prefix else len(PurePosixPath(prefix).parts)
        force_split = depth < args.split_depth
        if not force_split:
            try:
                items = rclone_json(
                    args.remote, prefix, recursive=True, files_only=True,
                    dirs_only=False, timeout_seconds=args.shard_timeout_seconds,
                )
                descriptor = write_shard(checkpoint, prefix, "recursive", items)
                state["prefixes"][prefix] = {
                    "state": "done", "mode": "recursive", "shard": descriptor,
                }
                atomic_json(checkpoint / "state.json", state)
                print(f"done prefix={prefix or '/'} objects={descriptor['object_count']}", flush=True)
                continue
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                if depth >= args.max_depth:
                    raise RuntimeError(
                        f"unsplittable census shard failed at depth {depth}: {prefix}: {exc}"
                    ) from exc
                print(f"split-after-failure prefix={prefix or '/'} reason={exc}", flush=True)
        children, direct = split_prefix(
            args.remote, checkpoint, prefix, args.discovery_timeout_seconds
        )
        if children:
            state["prefixes"][prefix] = {
                "state": "split", "mode": "direct", "shard": direct,
                "children": children,
            }
        else:
            state["prefixes"][prefix] = {
                "state": "done", "mode": "direct", "shard": direct,
            }
        atomic_json(checkpoint / "state.json", state)
        queue.extend(children)
        print(
            f"{'split' if children else 'done-direct'} prefix={prefix or '/'} "
            f"direct={direct['object_count']} children={len(children)}",
            flush=True,
        )
    return merge_checkpoint(checkpoint, Path(args.object_index), Path(args.metadata_files))


def is_control_metadata(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if len(parts) >= 4 and parts[0] == "runs" and parts[-1] in CONTROL_NAMES:
        return True
    if parts and parts[0] == "historical":
        lower = path.lower()
        return lower.endswith(".json") or lower.endswith("/manifests/paths.jsonl.gz")
    return False


def merge_checkpoint(root: Path, object_index: Path, metadata_files: Path) -> dict[str, Any]:
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    seen_shards: set[str] = set()
    for entry in state["prefixes"].values():
        descriptor = entry.get("shard")
        if not descriptor or descriptor["file"] in seen_shards:
            continue
        seen_shards.add(descriptor["file"])
        rows.extend(read_shard(root, descriptor))
    rows.sort(key=lambda row: row["Path"])
    paths = [row["Path"] for row in rows]
    if len(paths) != len(set(paths)):
        raise ValueError("sharded R2 census contains duplicate object paths")
    object_index.parent.mkdir(parents=True, exist_ok=True)
    object_index.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    controls = [path for path in paths if is_control_metadata(path)]
    metadata_files.write_text("".join(f"{path}\n" for path in controls), encoding="utf-8")
    summary = {
        "schema": SCHEMA,
        "object_count": len(rows),
        "object_bytes": sum(row["Size"] for row in rows),
        "checkpoint_shard_count": len(seen_shards),
        "metadata_object_count": len(controls),
        "completed_prefix_count": sum(
            entry["state"] == "done" for entry in state["prefixes"].values()
        ),
        "split_prefix_count": sum(
            entry["state"] == "split" for entry in state["prefixes"].values()
        ),
    }
    atomic_json(root / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--checkpoint-dir", required=True)
    parser.add_argument("--object-index", required=True)
    parser.add_argument("--metadata-files", required=True)
    parser.add_argument("--split-depth", type=int, default=2)
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--shard-timeout-seconds", type=int, default=900)
    parser.add_argument("--discovery-timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    if not (1 <= args.split_depth < args.max_depth <= 12):
        parser.error("require 1 <= split-depth < max-depth <= 12")
    try:
        summary = census(args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"jass_megacorpus_r2_shards: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
