#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hardened entrypoint for runner v3.

The five-minute runner is a short-lived oneshot service.  A job must not remain
inside that service's cgroup because a later timer activation, service reload or
stop may signal the leftover process tree.  This entrypoint preserves runner_v3
semantics but intercepts the one detached job launch and asks PID 1 to create an
independent transient service for it.
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


def bootstrap_wrapper_command(wrapper: str, wrapper_pid_path: Path, ready_path: Path) -> str:
    pid = shlex.quote(str(wrapper_pid_path))
    ready = shlex.quote(str(ready_path))
    nested = shlex.quote(wrapper)
    return (
        f"printf '%s\\n' \"$$\" > {pid}; "
        "i=0; "
        f"while [ ! -f {ready} ]; do "
        "i=$((i+1)); [ \"$i\" -lt 600 ] || exit 125; sleep 0.05; done; "
        f"exec /usr/bin/bash -c {nested}"
    )


def systemd_run_command(
    unit: str,
    cwd: Path,
    wrapper: str,
    wrapper_pid_path: Path,
    ready_path: Path,
) -> list[str]:
    binary = shutil.which("systemd-run") or "/usr/bin/systemd-run"
    bootstrap = bootstrap_wrapper_command(wrapper, wrapper_pid_path, ready_path)
    return [
        binary,
        "--quiet",
        "--collect",
        f"--unit={unit}",
        "--property=Type=exec",
        "--property=KillMode=control-group",
        "--property=TimeoutStopSec=120s",
        "--property=RuntimeMaxSec=infinity",
        "--property=Restart=no",
        "--property=PrivateTmp=false",
        "--property=Nice=10",
        "--property=IOSchedulingClass=best-effort",
        "--property=IOSchedulingPriority=5",
        f"--property=WorkingDirectory={cwd}",
        "--property=StandardInput=null",
        "--property=StandardOutput=null",
        "--property=StandardError=null",
        "/usr/bin/bash",
        "-c",
        bootstrap,
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
    raise RuntimeError(
        f"{unit}: {last_error}; systemctl rc={status.returncode}: "
        f"{status.stdout[-4000:]} {status.stderr[-2000:]}"
    )


def _stop_unit(unit: str, original_popen: Callable[..., subprocess.Popen]) -> None:
    client = original_popen(
        ["systemctl", "stop", unit],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    client.communicate(timeout=30)


def launch_transient(
    args: list[str] | tuple[str, ...],
    kwargs: dict[str, Any],
    original_popen: Callable[..., subprocess.Popen],
) -> SimpleNamespace:
    wrapper = str(args[2])
    cwd = Path(kwargs.get("cwd") or ".").resolve()
    wrapper_pid_path = extract_wrapper_pid_path(wrapper)
    ready_path = wrapper_pid_path.parent / "launcher.ready"
    wrapper_pid_path.unlink(missing_ok=True)
    ready_path.unlink(missing_ok=True)
    unit = transient_unit_name(wrapper_pid_path)
    command = systemd_run_command(unit, cwd, wrapper, wrapper_pid_path, ready_path)
    client = original_popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = client.communicate()
    if client.returncode != 0:
        raise RuntimeError(
            f"systemd-run failed rc={client.returncode} unit={unit}: "
            f"{stdout[-4000:]} {stderr[-4000:]}"
        )
    pid = _wait_for_wrapper_pid(wrapper_pid_path, unit)
    launch_report = {
        "schema": 2,
        "launcher": "systemd-transient-service",
        "unit": unit,
        "wrapper_pid": pid,
        "working_directory": str(cwd),
        "kill_mode": "control-group",
        "runtime_max": "infinity",
        "parent_runner_cgroup_isolated": True,
        "start_barrier": str(ready_path),
        "job_released": False,
    }
    artefacts = wrapper_pid_path.parent / "artefacts"
    artefacts.mkdir(parents=True, exist_ok=True)
    report_path = artefacts / "runner-launch.json"
    report_path.write_text(
        json.dumps(launch_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return SimpleNamespace(
        pid=pid,
        systemd_unit=unit,
        ready_path=ready_path,
        report_path=report_path,
        launch_report=launch_report,
    )


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
            launch_state.update({
                "unit": proc.systemd_unit,
                "ready_path": proc.ready_path,
                "report_path": proc.report_path,
                "launch_report": proc.launch_report,
            })
            return proc
        return original_popen(args, *pargs, **kwargs)

    R.subprocess.Popen = intercept
    try:
        info = _ORIGINAL_START_JOB(cfg, script)
    except Exception:
        unit = launch_state.get("unit")
        if unit:
            _stop_unit(unit, original_popen)
        raise
    finally:
        R.subprocess.Popen = original_popen

    unit = launch_state.get("unit")
    ready_path = launch_state.get("ready_path")
    if not unit or not isinstance(ready_path, Path):
        raise RuntimeError("job launch was not intercepted into a transient unit")
    try:
        info["systemd_unit"] = unit
        info["launcher"] = "systemd-transient-service"
        info["parent_runner_cgroup_isolated"] = True
        R.write_json(R.in_flight_path(cfg), info)
        metadata_path = Path(info["run_dir"]) / "metadata.json"
        metadata = R.read_json(metadata_path) or {}
        metadata.update({
            "systemd_unit": unit,
            "launcher": "systemd-transient-service",
            "parent_runner_cgroup_isolated": True,
        })
        R.write_json(metadata_path, metadata)
        report = dict(launch_state["launch_report"])
        report["job_released"] = True
        report["released_at"] = R.utcnow()
        R.write_json(launch_state["report_path"], report)
        ready_path.write_text("ready\n", encoding="utf-8")
    except Exception:
        _stop_unit(unit, original_popen)
        raise
    return info


def main() -> int:
    R.start_job = start_job_hardened
    return R.main()


if __name__ == "__main__":
    raise SystemExit(main())
