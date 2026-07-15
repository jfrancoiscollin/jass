#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

TERMINAL_STATES = {"completed", "failed", "upload_failed"}


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def compact_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def run(cmd: Sequence[str], *, cwd: Path | None = None, check: bool = True,
        timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), cwd=cwd, check=check, text=True,
                          capture_output=True, timeout=timeout)


@dataclass(frozen=True)
class Config:
    code_repo_dir: Path
    code_remote: str
    code_ref: str
    control_repo_dir: Path
    control_remote: str
    control_ref: str
    control_layout: str
    spool_root: Path
    result_backend: str
    result_fs_root: Path
    objstore_remote: str
    objstore_prefix: str
    rclone_bin: str
    host_filter: str
    max_log_bytes: int
    upload_retries: int
    git_retries: int
    allow_legacy_job_paths: bool
    keep_local_results: bool

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls(
            code_repo_dir=Path(os.environ.get("JASS_CODE_REPO_DIR", "/srv/jass/code")),
            code_remote=os.environ.get("JASS_CODE_REMOTE", "origin"),
            code_ref=os.environ.get("JASS_CODE_REF", "develop"),
            control_repo_dir=Path(os.environ.get("JASS_CONTROL_REPO_DIR", "/srv/jass/control")),
            control_remote=os.environ.get("JASS_CONTROL_REMOTE", "origin"),
            control_ref=os.environ.get("JASS_CONTROL_REF", "main"),
            control_layout=os.environ.get("JASS_CONTROL_LAYOUT", "legacy"),
            spool_root=Path(os.environ.get("JASS_SPOOL_ROOT", "/var/lib/jass-runner")),
            result_backend=os.environ.get("JASS_RESULT_BACKEND", "filesystem"),
            result_fs_root=Path(os.environ.get("JASS_RESULT_FS_ROOT", "/var/lib/jass-runner/published")),
            objstore_remote=os.environ.get("JASS_OBJSTORE_REMOTE", ""),
            objstore_prefix=os.environ.get("JASS_OBJSTORE_PREFIX", "runs").strip("/"),
            rclone_bin=os.environ.get("RCLONE_BIN", "rclone"),
            host_filter=os.environ.get("JASS_HOST_FILTER", "").strip(),
            max_log_bytes=int(os.environ.get("JASS_MAX_LOG_BYTES", "1000000")),
            upload_retries=int(os.environ.get("JASS_UPLOAD_RETRIES", "3")),
            git_retries=int(os.environ.get("JASS_GIT_RETRIES", "5")),
            allow_legacy_job_paths=env_bool("JASS_ALLOW_LEGACY_JOB_PATHS"),
            keep_local_results=env_bool("JASS_KEEP_LOCAL_RESULTS"),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.code_ref != "develop":
            raise ValueError("JASS_CODE_REF must be develop")
        if self.code_repo_dir.resolve() == self.control_repo_dir.resolve():
            raise ValueError("code and control repositories must be separate clones")
        if self.control_layout not in {"legacy", "v3"}:
            raise ValueError("JASS_CONTROL_LAYOUT must be legacy or v3")
        if self.result_backend not in {"filesystem", "rclone"}:
            raise ValueError("JASS_RESULT_BACKEND must be filesystem or rclone")
        if self.result_backend == "rclone" and not self.objstore_remote:
            raise ValueError("JASS_OBJSTORE_REMOTE is required for rclone")
        if min(self.max_log_bytes, self.upload_retries, self.git_retries) < 1:
            raise ValueError("limits and retries must be positive")


@dataclass(frozen=True)
class ControlPaths:
    queue_pending: Path
    queue_running: Path
    queue_done: Path
    status_root: Path
    state_root: Path


def control_paths(cfg: Config) -> ControlPaths:
    root = cfg.control_repo_dir
    if cfg.control_layout == "legacy":
        return ControlPaths(root / "jobs/queue", root / "jobs/queue", root / "jobs/queue",
                            root / "jobs/results", root / "jobs/state")
    return ControlPaths(root / "queue/pending", root / "queue/running", root / "queue/done",
                        root / "status", root / "state")


def status_path(cfg: Config, job_id: str) -> Path:
    root = control_paths(cfg).status_root
    return root / job_id / "status.json" if cfg.control_layout == "legacy" else root / f"{job_id}.json"


def local_state_dir(cfg: Config) -> Path:
    return cfg.spool_root / "state"


def in_flight_path(cfg: Config) -> Path:
    return local_state_dir(cfg) / f"in-flight-{socket.gethostname()}.json"


def pending_upload_dir(cfg: Config) -> Path:
    return cfg.spool_root / "pending-uploads"


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def host_filter(cfg: Config) -> str:
    if cfg.host_filter:
        return cfg.host_filter
    path = control_paths(cfg).state_root / "host-filter" / socket.gethostname()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
