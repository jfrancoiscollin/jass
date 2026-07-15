#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Jass GitOps runner v3: develop code, separate control plane, external results."""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from runner_v3_common import (
    Config,
    TERMINAL_STATES,
    compact_utc,
    control_paths,
    host_filter,
    in_flight_path,
    local_state_dir,
    pending_upload_dir,
    read_json,
    status_path,
    utcnow,
    write_json,
)
from runner_v3_git import (
    claim_job,
    control_commit_push,
    create_worktree,
    ensure_git_repo,
    finalize_control_script,
    git_sha,
    git_sync_code,
    git_sync_control,
    remove_worktree,
)
from runner_v3_store import prepare_run_dir, result_store


def bootstrap_dirs(cfg: Config) -> None:
    cfg.spool_root.mkdir(parents=True, exist_ok=True)
    local_state_dir(cfg).mkdir(parents=True, exist_ok=True)
    pending_upload_dir(cfg).mkdir(parents=True, exist_ok=True)
    paths = control_paths(cfg)
    for path in (paths.queue_pending, paths.queue_running, paths.queue_done,
                 paths.status_root, paths.state_root):
        path.mkdir(parents=True, exist_ok=True)


def publish_status(cfg: Config, payload: dict) -> None:
    path = status_path(cfg, payload["job_id"])
    write_json(path, payload)
    if not control_commit_push(cfg, f"runner: {payload['state']} {payload['job_id']}", [path]):
        raise RuntimeError(f"failed to publish status for {payload['job_id']}")


def is_terminal_status(cfg: Config, job_id: str) -> bool:
    data = read_json(status_path(cfg, job_id))
    return bool(data and data.get("state") in TERMINAL_STATES)


def candidate_jobs(cfg: Config) -> list[Path]:
    queue = control_paths(cfg).queue_pending
    if not queue.exists():
        return []
    candidates = sorted(path for path in queue.glob("*.sh") if path.is_file())
    prefix = host_filter(cfg)
    if prefix:
        candidates = [path for path in candidates if path.stem.startswith(prefix)]
    if cfg.control_layout == "legacy":
        candidates = [path for path in candidates if not is_terminal_status(cfg, path.stem)]
    return candidates


def validate_job_script(cfg: Config, script: Path) -> None:
    text = script.read_text(encoding="utf-8", errors="replace")
    forbidden = []
    if not cfg.allow_legacy_job_paths and "/root/jass" in text:
        forbidden.append("hard-coded /root/jass")
    for token in ("origin/main", "HEAD:main", "refs/heads/main"):
        if token in text:
            forbidden.append(token)
    if forbidden:
        raise RuntimeError(f"{script.name}: forbidden legacy references: {', '.join(forbidden)}")


def start_job(cfg: Config, script: Path) -> dict:
    validate_job_script(cfg, script)
    job_id = script.stem
    code_sha = git_sha(cfg.code_repo_dir, f"{cfg.code_remote}/{cfg.code_ref}")
    attempt_id = f"{compact_utc()}-{code_sha[:8]}"
    workspace = create_worktree(cfg, job_id, attempt_id, code_sha)
    run_dir = cfg.spool_root / "runs" / job_id / attempt_id
    artefact_dir = run_dir / "artefacts"
    artefact_dir.mkdir(parents=True, exist_ok=True)
    script_copy = run_dir / "job.sh"
    shutil.copy2(script, script_copy)
    script_copy.chmod(0o755)

    started = utcnow()
    metadata = {
        "job_id": job_id,
        "attempt_id": attempt_id,
        "started_at": started,
        "host": socket.gethostname(),
        "code_ref": cfg.code_ref,
        "code_sha": code_sha,
        "control_ref": cfg.control_ref,
        "control_sha": git_sha(cfg.control_repo_dir),
        "runner_sha": git_sha(cfg.code_repo_dir),
        "script_name": script.name,
    }
    write_json(run_dir / "metadata.json", metadata)

    raw_log = run_dir / "output.log.raw"
    exit_code = run_dir / "exit_code"
    wrapper_pid = run_dir / "wrapper.pid"
    env_file = run_dir / "job.env"
    env_file.write_text(
        "\n".join([
            f"export JASS_CODE_DIR={workspace}",
            f"export JASS_JOB_ID={job_id}",
            f"export JASS_ATTEMPT_ID={attempt_id}",
            f"export JASS_RESULT_DIR={run_dir}",
            f"export JASS_ARTEFACT_DIR={artefact_dir}",
        ]) + "\n",
        encoding="utf-8",
    )
    wrapper = (
        "set +e; "
        f"exec >{raw_log} 2>&1; "
        f"echo $$ > {wrapper_pid}; "
        f"source {env_file}; cd {workspace}; "
        f"bash {script_copy}; rc=$?; echo $rc > {exit_code}; exit $rc"
    )
    proc = subprocess.Popen(
        ["bash", "-c", wrapper], cwd=workspace,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )
    info = {**metadata, "pid": proc.pid, "workspace": str(workspace),
            "run_dir": str(run_dir), "claimed_script": str(script)}
    write_json(in_flight_path(cfg), info)
    publish_status(cfg, {**metadata, "state": "running", "pid": proc.pid})
    return info


def read_in_flight(cfg: Config) -> dict | None:
    return read_json(in_flight_path(cfg))


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def wrapper_pid(info: dict) -> int:
    try:
        return int((Path(info["run_dir"]) / "wrapper.pid").read_text().strip())
    except (OSError, ValueError):
        return int(info.get("pid", -1))


def queue_pending_upload(cfg: Config, info: dict, rc: int,
                         final_state: str, error: str) -> None:
    write_json(
        pending_upload_dir(cfg) / f"{info['job_id']}--{info['attempt_id']}.json",
        {"info": info, "exit_code": rc, "final_state": final_state,
         "last_error": error, "queued_at": utcnow()},
    )


def publish_run(cfg: Config, info: dict, rc: int,
                final_state: str) -> tuple[str | None, str | None]:
    run_dir = Path(info["run_dir"])
    manifest = {
        key: info.get(key) for key in (
            "job_id", "attempt_id", "started_at", "host", "code_ref",
            "code_sha", "control_ref", "control_sha", "runner_sha",
            "script_name")
    }
    manifest.update({"ended_at": utcnow(), "exit_code": rc, "state": final_state})
    prepare_run_dir(run_dir, manifest, cfg.max_log_bytes)
    try:
        uri = result_store(cfg).publish(run_dir, info["job_id"],
                                        info["attempt_id"], rc == 0)
        return uri, None
    except Exception as exc:
        queue_pending_upload(cfg, info, rc, final_state, str(exc))
        return None, str(exc)


def clear_in_flight(cfg: Config) -> None:
    in_flight_path(cfg).unlink(missing_ok=True)


def reap_finished_job(cfg: Config) -> bool:
    info = read_in_flight(cfg)
    if not info:
        return False
    pid = wrapper_pid(info)
    if pid > 0 and alive(pid):
        return False
    try:
        rc = int((Path(info["run_dir"]) / "exit_code").read_text().strip())
    except (OSError, ValueError):
        rc = -1
    final_state = "completed" if rc == 0 else "failed"
    uri, upload_error = publish_run(cfg, info, rc, final_state)
    status = {
        "job_id": info["job_id"], "attempt_id": info["attempt_id"],
        "state": final_state if uri else "upload_failed", "exit_code": rc,
        "started_at": info.get("started_at"), "ended_at": utcnow(),
        "host": info.get("host"), "code_ref": info.get("code_ref"),
        "code_sha": info.get("code_sha"), "result_uri": uri,
    }
    if upload_error:
        status["upload_error"] = upload_error
    publish_status(cfg, status)
    finalize_control_script(cfg, Path(info["claimed_script"]), info["job_id"])
    remove_worktree(cfg, Path(info["workspace"]))
    clear_in_flight(cfg)
    if uri and not cfg.keep_local_results:
        shutil.rmtree(Path(info["run_dir"]), ignore_errors=True)
    return True


def retry_pending_uploads(cfg: Config) -> int:
    root = pending_upload_dir(cfg)
    successes = 0
    for pending in sorted(root.glob("*.json")) if root.exists() else []:
        payload = read_json(pending)
        if not payload:
            continue
        info, rc = payload["info"], int(payload["exit_code"])
        try:
            uri = result_store(cfg).publish(Path(info["run_dir"]), info["job_id"],
                                            info["attempt_id"], rc == 0)
        except Exception as exc:
            payload.update({"last_error": str(exc), "last_attempt_at": utcnow()})
            write_json(pending, payload)
            continue
        publish_status(cfg, {
            "job_id": info["job_id"], "attempt_id": info["attempt_id"],
            "state": payload["final_state"], "exit_code": rc,
            "started_at": info.get("started_at"), "ended_at": utcnow(),
            "host": info.get("host"), "code_ref": info.get("code_ref"),
            "code_sha": info.get("code_sha"), "result_uri": uri,
            "upload_recovered": True,
        })
        pending.unlink()
        if not cfg.keep_local_results:
            shutil.rmtree(Path(info["run_dir"]), ignore_errors=True)
        successes += 1
    return successes


def heartbeat(cfg: Config, info: dict) -> None:
    run_dir = Path(info["run_dir"])
    snapshot = {
        "job_id": info["job_id"], "attempt_id": info["attempt_id"],
        "state": "running", "snapshot_at": utcnow(),
        "started_at": info.get("started_at"), "host": info.get("host"),
        "code_sha": info.get("code_sha"), "artefacts": [],
    }
    artefact_dir = run_dir / "artefacts"
    if artefact_dir.exists():
        for path in sorted(artefact_dir.rglob("*")):
            if path.is_file():
                snapshot["artefacts"].append({
                    "path": str(path.relative_to(artefact_dir)),
                    "size_bytes": path.stat().st_size,
                })
    publish_status(cfg, snapshot)


def kill_requested_path(cfg: Config) -> Path | None:
    state = control_paths(cfg).state_root
    for path in (state / f"kill-in-flight-{socket.gethostname()}",
                 state / "kill-in-flight"):
        if path.exists():
            return path
    return None


def handle_kill(cfg: Config) -> None:
    flag = kill_requested_path(cfg)
    if flag is None:
        return
    info = read_in_flight(cfg)
    if info:
        pid = wrapper_pid(info)
        if pid > 0 and alive(pid):
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(2)
                if alive(pid):
                    os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    flag.unlink(missing_ok=True)
    control_commit_push(cfg, "runner: consume kill flag", [control_paths(cfg).state_root])


def paused(cfg: Config) -> bool:
    state = control_paths(cfg).state_root
    return (state / "runner-paused").exists() and not (
        state / "host-active" / socket.gethostname()).exists()


def main() -> int:
    try:
        cfg = Config.from_env()
        ensure_git_repo(cfg.code_repo_dir, "code")
        ensure_git_repo(cfg.control_repo_dir, "control")
        git_sync_code(cfg.code_repo_dir, cfg.code_remote, cfg.code_ref)
        git_sync_control(cfg.control_repo_dir, cfg.control_remote, cfg.control_ref)
        bootstrap_dirs(cfg)
        retry_pending_uploads(cfg)
        handle_kill(cfg)
        reap_finished_job(cfg)
        info = read_in_flight(cfg)
        if info:
            heartbeat(cfg, info)
            return 0
        if paused(cfg):
            print("runner-v3: paused", flush=True)
            return 0
        jobs = candidate_jobs(cfg)
        if jobs:
            start_job(cfg, claim_job(cfg, jobs[0]))
        return 0
    except Exception as exc:
        print(f"runner-v3: ERROR: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
