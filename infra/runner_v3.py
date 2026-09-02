#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Jass GitOps runner v3: develop code, separate control plane, external results."""
from __future__ import annotations

import json
import os
import re
import shlex
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
    resolve_pinned_code_sha,
)
from runner_v3_store import prepare_run_dir, result_store


# Only small, explicitly scientific JSON artefacts are copied into the GitOps
# status.  Full logs, weights and corpora stay in object storage.  This keeps
# jass-control useful to reviewers without turning it into a result store or
# risking publication of arbitrary job output.
STATUS_SUMMARY_NAMES = frozenset({
    "attempt-diagnostic.json",
    "c0-decision.json",
    "mtc-audit.json",
    "mtc-verification.json",
    "mtc_audit.json",
    "p3-holdout-decision.json",
    "p3-holdout-manifest.json",
    "p3-power.json",
    "promotion.json",
    "scientific-summary.json",
    "sparring-smoke-decision.json",
    "sparring-decision.json",
    "teacher-confirmation-decision.json",
    "teacher-smoke-decision.json",
    "teacher-smoke-precheck.json",
    "teacher-summary.json",
})
STATUS_SUMMARY_MAX_FILE_BYTES = 64 * 1024
STATUS_SUMMARY_MAX_TOTAL_BYTES = 256 * 1024

EXPECTED_CODE_SHA_RE = re.compile(
    r"^[ \t]*(?:export[ \t]+)?EXPECTED_CODE_SHA="
    r"(?P<quote>['\"]?)(?P<sha>[0-9a-f]{40})(?P=quote)[ \t]*(?:#.*)?$",
    re.MULTILINE,
)
JOB_NAME_SHA_RE = re.compile(r"(?:^|-)at-([0-9a-f]{8,40})(?:-|$)")


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
    # Interdit le clone de code legacy /root/jass (les jobs doivent utiliser
    # $JASS_CODE_DIR), MAIS pas les installs voisines légitimes /root/jass-scan
    # (binaire Scan) ni /root/jass-runner : ne matche /root/jass que comme
    # composant de chemin (suivi de /, guillemet, espace ou fin), pas /root/jass-*.
    if not cfg.allow_legacy_job_paths and re.search(r"/root/jass(?![\w-])", text):
        forbidden.append("hard-coded /root/jass")
    for token in ("origin/main", "HEAD:main", "refs/heads/main"):
        if token in text:
            forbidden.append(token)
    if forbidden:
        raise RuntimeError(f"{script.name}: forbidden legacy references: {', '.join(forbidden)}")


def expected_code_sha(script: Path) -> str:
    """Read the literal immutable code pin without executing the job script."""
    text = script.read_text(encoding="utf-8", errors="replace")
    matches = {match.group("sha") for match in EXPECTED_CODE_SHA_RE.finditer(text)}
    if not matches:
        raise RuntimeError(
            f"{script.name}: missing literal full EXPECTED_CODE_SHA assignment"
        )
    if len(matches) != 1:
        raise RuntimeError(f"{script.name}: conflicting EXPECTED_CODE_SHA assignments")
    code_sha = matches.pop()
    visible_pin = JOB_NAME_SHA_RE.search(script.stem)
    if visible_pin and not code_sha.startswith(visible_pin.group(1)):
        raise RuntimeError(
            f"{script.name}: filename pin {visible_pin.group(1)} "
            f"does not match EXPECTED_CODE_SHA {code_sha}"
        )
    return code_sha


RCLONE_JOB_ENV_NAMES = frozenset({
    "RCLONE_BIN",
    "RCLONE_CONF_B64",
    "RCLONE_CONFIG",
})


def write_job_env(path: Path, values: dict[str, str]) -> None:
    """Write the minimal job environment, including rclone credentials.

    Transient systemd services do not inherit the runner process environment.
    Forward only rclone's documented configuration variables, never the full
    runner environment, and protect the resulting per-attempt file.
    """
    forwarded = {
        name: value
        for name, value in os.environ.items()
        if name in RCLONE_JOB_ENV_NAMES or name.startswith("RCLONE_CONFIG_")
    }
    entries = {**values, **forwarded}
    path.write_text(
        "".join(
            f"export {name}={shlex.quote(str(value))}\n"
            for name, value in sorted(entries.items())
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def build_job_wrapper(
    exit_code: Path,
    raw_log: Path,
    wrapper_pid: Path,
    env_file: Path,
    workspace: Path,
    script_copy: Path,
) -> str:
    """Build a wrapper that records catchable signals as terminal failures."""
    return (
        "set +e; "
        f"exit_file={shlex.quote(str(exit_code))}; "
        "trap 'rc=$?; printf \"%s\\n\" \"$rc\" > \"$exit_file\"' EXIT; "
        "trap 'exit 143' TERM; trap 'exit 130' INT; "
        f"exec >{shlex.quote(str(raw_log))} 2>&1; "
        f"echo $$ > {shlex.quote(str(wrapper_pid))}; "
        f"source {shlex.quote(str(env_file))}; cd {shlex.quote(str(workspace))}; "
        f"bash {shlex.quote(str(script_copy))}"
    )


def start_job(cfg: Config, script: Path) -> dict:
    validate_job_script(cfg, script)
    job_id = script.stem
    code_sha = resolve_pinned_code_sha(cfg, expected_code_sha(script))
    attempt_id = f"{compact_utc()}-{code_sha[:8]}"
    workspace = create_worktree(cfg, job_id, attempt_id, code_sha)
    run_dir = cfg.spool_root / "runs" / job_id / attempt_id
    artefact_dir = run_dir / "artefacts"
    artefact_dir.mkdir(parents=True, exist_ok=True)
    # PrivateTmp=true + Type=oneshot: once the runner service exits, systemd
    # tears down the private /tmp mount while the detached job keeps running,
    # so anything using /tmp (gcc, cmake try-compile, tempfile) fails with
    # ENOENT. Point TMPDIR at a per-attempt directory that always exists.
    tmp_dir = run_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
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
    write_job_env(env_file, {
        "JASS_CODE_DIR": str(workspace),
        "JASS_JOB_ID": job_id,
        "JASS_ATTEMPT_ID": attempt_id,
        "JASS_RESULT_DIR": str(run_dir),
        "JASS_ARTEFACT_DIR": str(artefact_dir),
        "TMPDIR": str(tmp_dir),
    })
    # The EXIT trap records the shell status even when the job script exits
    # early or receives a catchable signal.  A genuinely absent file now means
    # that the wrapper itself vanished (SIGKILL, host loss, cgroup kill, ...),
    # which is surfaced as a diagnostic instead of an opaque ``-1``.
    wrapper = build_job_wrapper(
        exit_code,
        raw_log,
        wrapper_pid,
        env_file,
        workspace,
        script_copy,
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
    except (OSError, OverflowError):
        return False


def wrapper_pid(info: dict) -> int:
    candidates: list[object] = []
    try:
        candidates.append((Path(info["run_dir"]) / "wrapper.pid").read_text().strip())
    except (OSError, ValueError):
        pass
    candidates.append(info.get("pid", -1))
    for candidate in candidates:
        try:
            pid = int(candidate)
        except (TypeError, ValueError, OverflowError):
            continue
        # Linux pid_t is a signed C int.  Reject corrupted concatenations such
        # as "27270302727030" before they reach os.kill(), and fall back to the
        # immutable PID recorded in the in-flight metadata.
        if 0 < pid <= 2_147_483_647:
            return pid
    return -1


def process_observation(info: dict, pid: int) -> dict:
    """Return a small, non-secret process snapshot for failure attribution."""
    observation = {
        "observed_at": utcnow(),
        "pid": pid,
        "alive": pid > 0 and alive(pid),
    }
    if pid <= 0:
        return observation
    status = Path(f"/proc/{pid}/status")
    allowed = {"Name", "State", "PPid", "Threads", "VmPeak", "VmRSS", "VmHWM"}
    try:
        values = {}
        for line in status.read_text(encoding="utf-8", errors="replace").splitlines():
            key, separator, value = line.partition(":")
            if separator and key in allowed:
                values[key] = value.strip()
        observation["proc_status"] = values
    except OSError:
        pass
    return observation


def record_process_observation(info: dict) -> dict:
    observation = process_observation(info, wrapper_pid(info))
    write_json(Path(info["run_dir"]) / "runner-process-observation.json", observation)
    return observation


def read_exit_code(info: dict) -> tuple[int, str | None]:
    path = Path(info["run_dir"]) / "exit_code"
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return -1, "missing_exit_code"
    try:
        return int(raw), None
    except ValueError:
        return -1, "invalid_exit_code"


def write_attempt_diagnostic(info: dict, reason: str) -> None:
    run_dir = Path(info["run_dir"])
    previous = read_json(run_dir / "runner-process-observation.json")
    write_json(run_dir / "artefacts" / "attempt-diagnostic.json", {
        "schema": 1,
        "job_id": info.get("job_id"),
        "attempt_id": info.get("attempt_id"),
        "host": info.get("host"),
        "code_sha": info.get("code_sha"),
        "classification": "wrapper_terminated_without_exit_status",
        "reason": reason,
        "last_process_observation": previous,
        "reaped_at": utcnow(),
    })


def artefact_status_payload(artefact_dir: Path) -> dict:
    """List artefacts and inline an allow-list of small JSON summaries."""
    payload: dict[str, object] = {"artefacts": []}
    if not artefact_dir.exists():
        return payload
    root = artefact_dir.resolve()
    summaries: dict[str, object] = {}
    total = 0
    for path in sorted(artefact_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
            size = path.stat().st_size
        except (OSError, ValueError):
            continue
        relative = str(path.relative_to(artefact_dir))
        payload["artefacts"].append({"path": relative, "size_bytes": size})
        if (
            path.name not in STATUS_SUMMARY_NAMES
            or size <= 0
            or size > STATUS_SUMMARY_MAX_FILE_BYTES
            or total + size > STATUS_SUMMARY_MAX_TOTAL_BYTES
        ):
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, (dict, list)):
            continue
        summaries[relative] = value
        total += size
    if summaries:
        payload["scientific_summaries"] = summaries
    return payload


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
    rc, exit_error = read_exit_code(info)
    if exit_error:
        write_attempt_diagnostic(info, exit_error)
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
    status.update(artefact_status_payload(Path(info["run_dir"]) / "artefacts"))
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
        status = {
            "job_id": info["job_id"], "attempt_id": info["attempt_id"],
            "state": payload["final_state"], "exit_code": rc,
            "started_at": info.get("started_at"), "ended_at": utcnow(),
            "host": info.get("host"), "code_ref": info.get("code_ref"),
            "code_sha": info.get("code_sha"), "result_uri": uri,
            "upload_recovered": True,
        }
        status.update(artefact_status_payload(Path(info["run_dir"]) / "artefacts"))
        publish_status(cfg, status)
        pending.unlink()
        if not cfg.keep_local_results:
            shutil.rmtree(Path(info["run_dir"]), ignore_errors=True)
        successes += 1
    return successes


def heartbeat(cfg: Config, info: dict) -> None:
    run_dir = Path(info["run_dir"])
    record_process_observation(info)
    snapshot = {
        "job_id": info["job_id"], "attempt_id": info["attempt_id"],
        "state": "running", "snapshot_at": utcnow(),
        "started_at": info.get("started_at"), "host": info.get("host"),
        "code_sha": info.get("code_sha"),
    }
    snapshot.update(artefact_status_payload(run_dir / "artefacts"))
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
