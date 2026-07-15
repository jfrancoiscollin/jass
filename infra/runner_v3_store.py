#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import shutil
import time
from pathlib import Path

from runner_v3_common import Config, run, utcnow, write_json


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_files(root: Path) -> list[dict]:
    result = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {"checksums.sha256", "_SUCCESS", "_FAILED"}:
            continue
        result.append({"path": str(path.relative_to(root)),
                       "size_bytes": path.stat().st_size,
                       "sha256": sha256_file(path)})
    return result


def write_checksums(root: Path, files: list[dict]) -> None:
    (root / "checksums.sha256").write_text(
        "".join(f"{item['sha256']}  {item['path']}\n" for item in files),
        encoding="utf-8")


def truncate_and_gzip(raw: Path, output: Path, max_bytes: int) -> None:
    data = b""
    if raw.exists():
        size = raw.stat().st_size
        with raw.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
                data = b"...[truncated]...\n" + handle.read()
            else:
                data = handle.read()
    with gzip.open(output, "wb", compresslevel=6) as handle:
        handle.write(data)


def remote_join(base: str, *parts: str) -> str:
    return base.rstrip("/") + "/" + "/".join(p.strip("/") for p in parts if p)


class ResultStore:
    def publish(self, run_dir: Path, job_id: str, attempt_id: str, success: bool) -> str:
        raise NotImplementedError


class FilesystemResultStore(ResultStore):
    def __init__(self, root: Path):
        self.root = root

    def publish(self, run_dir: Path, job_id: str, attempt_id: str, success: bool) -> str:
        destination = self.root / job_id / attempt_id
        shutil.rmtree(destination, ignore_errors=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(run_dir, destination)
        (destination / ("_SUCCESS" if success else "_FAILED")).write_text(
            utcnow() + "\n", encoding="utf-8")
        return destination.as_uri()


class RcloneResultStore(ResultStore):
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def publish(self, run_dir: Path, job_id: str, attempt_id: str, success: bool) -> str:
        remote = remote_join(self.cfg.objstore_remote, self.cfg.objstore_prefix,
                             job_id, attempt_id)
        marker_name = "_SUCCESS" if success else "_FAILED"
        marker = run_dir / marker_name
        marker.unlink(missing_ok=True)
        last_error = ""
        for attempt in range(1, self.cfg.upload_retries + 1):
            copy = run([self.cfg.rclone_bin, "copy", str(run_dir), remote,
                        "--checksum", "--immutable"], check=False)
            if copy.returncode == 0:
                check = run([self.cfg.rclone_bin, "check", str(run_dir), remote,
                             "--one-way", "--checksum"], check=False)
                if check.returncode == 0:
                    marker.write_text(utcnow() + "\n", encoding="utf-8")
                    final = run([self.cfg.rclone_bin, "copyto", str(marker),
                                 remote_join(remote, marker_name)], check=False)
                    if final.returncode == 0:
                        return remote
                    last_error = final.stderr or final.stdout
                else:
                    last_error = check.stderr or check.stdout
            else:
                last_error = copy.stderr or copy.stdout
            time.sleep(attempt * 2)
        raise RuntimeError(f"object-store publish failed: {last_error.strip()}")


def result_store(cfg: Config) -> ResultStore:
    return FilesystemResultStore(cfg.result_fs_root) if cfg.result_backend == "filesystem" else RcloneResultStore(cfg)


def prepare_run_dir(run_dir: Path, manifest: dict, max_log_bytes: int) -> None:
    raw = run_dir / "output.log.raw"
    truncate_and_gzip(raw, run_dir / "output.log.gz", max_log_bytes)
    raw.unlink(missing_ok=True)
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "inventory.json", {"files": inventory_files(run_dir)})
    write_checksums(run_dir, inventory_files(run_dir))
