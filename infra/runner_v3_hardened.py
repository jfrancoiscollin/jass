#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hardened entrypoint for runner v3.

Scientific jobs run in independent transient systemd services.  They therefore
cannot be killed when the five-minute oneshot runner service stops or starts its
next tick.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import runner_v3 as R

_ORIGINAL_START_JOB = R.start_job


def extract_wrapper_pid_path(wrapper: str) -> Path:
    marker = "echo $$ > "
    if marker not in wrapper or "; source " not in wrapper:
        raise ValueError("runner wrapper does not expose wrapper.pid")
    fragment = wrapper.split(marker, 1)[1].split("; source ", 1)[0]
    tokens = shlex.split(fragment)
    if len(tokens) != 1:
        raise ValueError(f"cannot parse wrapper.pid path from {fragment!r}")
    return Path(tokens[0])


def is_runner_job_launch(args: Any, kwargs: dict[str, Any]) -> bool:
    return bool(
        isinstance(args, (list, tuple))
        and len(args) == 3
        and args[0] in {"bash", "/usr/bin/bash", "/bin/bash"}
        and args[1] == "-c"
        and isinstance(args[2], str)
        and "wrapper.pid" in args[2]
        and "output.log.raw" in args[2]
        and kwargs.get("start_new_session") is True
    )


def transient_unit_name(wrapper_pid_path: Path) -> str:
    digest = hashlib.sha256(str(wrapper_pid_path.parent).encode("utf-8")).hexdigest()[:20]
    return f"jass-job-{digest}.service"


def systemd_run_command(unit: str, cwd: Path, wrapper: str) -> list[str]:
    """Return the smallest proven non-blocking transient-service command.

    The job wrapper already redirects stdin/stdout/stderr and records its PID,
    so extra Standard* and scheduler properties only add compatibility risk.
    Omitting RuntimeMaxSec means systemd's default infinity.
    """
    binary = shutil.which("systemd-run") or "/usr/bin/systemd-run"
    return [
        binary,
        "--quiet",
        "--no-block",
        "--collect",
        f"--unit={unit}",
        "--property=Type=exec",
        "--property=KillMode=control-group",
        "--property=TimeoutStopSec=120s",
        "--property=ProtectSystem=false",
        "--property=PrivateTmp=false",
        "--property=NoNewPrivileges=false",
        f"--property=WorkingDirectory={cwd}",
        "/usr/bin/bash",
        "-c",
        wrapper,
    ]


def _wait_for_wrapper_pid(path: Path, unit: str, timeout: float = 30.0) -> int:
    deadline = time.monotonic() + timeout
    last_error = "wrapper.pid not created"
    while time.monotonic() < deadline:
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
            if pid > 0:
                return pid
        except (OSError, ValueError) as exc:
            last_error = str(exc)
        time.sleep(0.1)
    status = subprocess.run(
        ["systemctl", "status", unit, "--no-pager", "--full"],
        text=True,
        capture_output=True,
        check=False,
    )
    journal = subprocess.run(
        ["journalctl", "-u", unit, "-n", "100", "--no-pager", "-o", "short-iso-precise"],
        text=True,
        capture_output=True,
        check=False,
    )
    raise RuntimeError(
        f"{unit}: {last_error}; systemctl rc={status.returncode}: "
        f"{status.stdout[-6000:]} {status.stderr[-2000:]}; "
        f"journal: {journal.stdout[-10000:]} {journal.stderr[-2000:]}"
    )


def persist_launch_contract(wrapper_pid_path: Path, report: dict[str, Any]) -> None:
    """Publish the isolation contract before PID 1 may start the job."""
    run_dir = wrapper_pid_path.parent
    metadata_path = run_dir / "metadata.json"
    metadata = R.read_json(metadata_path) or {}
    metadata.update({
        "systemd_unit": report["unit"],
        "launcher": report["launcher"],
        "launcher_state": report["state"],
        "parent_runner_cgroup_isolated": True,
    })
    if report.get("wrapper_pid"):
        metadata["wrapper_pid"] = int(report["wrapper_pid"])
    R.write_json(metadata_path, metadata)

    artefacts = run_dir / "artefacts"
    artefacts.mkdir(parents=True, exist_ok=True)
    (artefacts / "runner-launch.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def launch_transient(
    args: list[str] | tuple[str, ...],
    kwargs: dict[str, Any],
    original_popen: Callable[..., subprocess.Popen],
) -> SimpleNamespace:
    wrapper = str(args[2])
    cwd = Path(kwargs.get("cwd") or ".").resolve()
    wrapper_pid_path = extract_wrapper_pid_path(wrapper)
    unit = transient_unit_name(wrapper_pid_path)
    command = systemd_run_command(unit, cwd, wrapper)
    report: dict[str, Any] = {
        "schema": 3,
        "launcher": "systemd-transient-service",
        "state": "launching",
        "unit": unit,
        "wrapper_pid": None,
        "working_directory": str(cwd),
        "kill_mode": "control-group",
        "runtime_max": "infinity",
        "parent_runner_cgroup_isolated": True,
        "systemd_run_mode": "no-block-minimal",
    }

    persist_launch_contract(wrapper_pid_path, report)
    client = original_popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = client.communicate()
    if client.returncode != 0:
        report.update({
            "state": "launch_failed",
            "systemd_run_returncode": client.returncode,
            "systemd_run_stdout_tail": stdout[-6000:],
            "systemd_run_stderr_tail": stderr[-6000:],
        })
        persist_launch_contract(wrapper_pid_path, report)
        raise RuntimeError(
            f"systemd-run failed rc={client.returncode} unit={unit}: "
            f"{stdout[-4000:]} {stderr[-4000:]}"
        )

    try:
        pid = _wait_for_wrapper_pid(wrapper_pid_path, unit)
    except Exception as exc:
        report.update({"state": "launch_failed", "launch_error": str(exc)[-16000:]})
        persist_launch_contract(wrapper_pid_path, report)
        raise
    report.update({"state": "running", "wrapper_pid": pid})
    persist_launch_contract(wrapper_pid_path, report)
    return SimpleNamespace(pid=pid, systemd_unit=unit)


def latest_attempt_dir(cfg: Any, job_id: str) -> Path | None:
    root = cfg.spool_root / "runs" / job_id
    candidates = [path for path in root.iterdir() if path.is_dir()] if root.exists() else []
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def record_launch_failure(cfg: Any, script: Path, exc: Exception) -> None:
    """Make launch failures terminal, visible and non-blocking for the queue."""
    job_id = script.stem
    run_dir = latest_attempt_dir(cfg, job_id)
    metadata = R.read_json(run_dir / "metadata.json") if run_dir else None
    launch = R.read_json(run_dir / "artefacts" / "runner-launch.json") if run_dir else None
    diagnostic = {
        "schema": 1,
        "classification": "transient_service_launch_failed",
        "exception_type": type(exc).__name__,
        "exception": str(exc)[-20000:],
        "launcher": launch,
        "recorded_at": R.utcnow(),
    }
    if run_dir:
        R.write_json(run_dir / "artefacts" / "attempt-diagnostic.json", diagnostic)
    status = {
        "job_id": job_id,
        "attempt_id": (metadata or {}).get("attempt_id"),
        "state": "failed",
        "phase": "launch",
        "exit_code": -1,
        "started_at": (metadata or {}).get("started_at"),
        "ended_at": R.utcnow(),
        "host": (metadata or {}).get("host"),
        "code_sha": (metadata or {}).get("code_sha"),
        "launch_diagnostic": diagnostic,
    }
    try:
        R.publish_status(cfg, status)
    finally:
        if script.exists():
            R.finalize_control_script(cfg, script, job_id)


def start_job_hardened(cfg: Any, script: Path) -> dict:
    mode = os.environ.get("JASS_JOB_LAUNCHER", "systemd").strip().lower()
    if mode not in {"systemd", "direct"}:
        raise RuntimeError(f"invalid JASS_JOB_LAUNCHER={mode!r}")
    if mode == "direct":
        return _ORIGINAL_START_JOB(cfg, script)
    if not Path("/run/systemd/system").is_dir() or not shutil.which("systemd-run"):
        raise RuntimeError("systemd transient launcher required but unavailable")

    original_popen = R.subprocess.Popen
    launch_state: dict[str, Any] = {}

    def intercept(args: Any, *pargs: Any, **kwargs: Any):
        if is_runner_job_launch(args, kwargs):
            proc = launch_transient(args, kwargs, original_popen)
            launch_state["unit"] = proc.systemd_unit
            return proc
        return original_popen(args, *pargs, **kwargs)

    R.subprocess.Popen = intercept
    try:
        info = _ORIGINAL_START_JOB(cfg, script)
    except Exception as exc:
        R.subprocess.Popen = original_popen
        record_launch_failure(cfg, script, exc)
        raise
    finally:
        R.subprocess.Popen = original_popen

    unit = launch_state.get("unit")
    if not unit:
        exc = RuntimeError("job launch was not intercepted into a transient unit")
        record_launch_failure(cfg, script, exc)
        raise exc
    info.update({
        "systemd_unit": unit,
        "launcher": "systemd-transient-service",
        "parent_runner_cgroup_isolated": True,
    })
    R.write_json(R.in_flight_path(cfg), info)
    metadata_path = Path(info["run_dir"]) / "metadata.json"
    metadata = R.read_json(metadata_path) or {}
    metadata.update({
        "systemd_unit": unit,
        "launcher": "systemd-transient-service",
        "launcher_state": "running",
        "parent_runner_cgroup_isolated": True,
    })
    R.write_json(metadata_path, metadata)
    return info


def main() -> int:
    R.start_job = start_job_hardened
    return R.main()


if __name__ == "__main__":
    raise SystemExit(main())
