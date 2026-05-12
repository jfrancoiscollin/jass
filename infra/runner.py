#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Jass GitOps runner.

Tick (every 5 min by the systemd timer):
  1. `git pull --rebase` /root/jass against origin/main.
  2. If a job is already in flight (`jobs/state/in-flight.json` exists
     and its PID is alive), exit silently — long-running jobs span
     many ticks.
  3. Otherwise pick the oldest unprocessed `jobs/queue/*.sh` file
     (sorted by name; numeric prefixes like `0001-...` recommended).
  4. Detach a background runner that executes the job, captures
     stdout+stderr, then commits the result + pushes.
  5. Exit the tick — the background job continues on its own.

Job format (each file in `jobs/queue/` is a shell script):
    #!/usr/bin/env bash
    # id: 0001-gen-depth20-200k       (optional override; default = filename stem)
    # description: ...                (free-text)
    # expected_duration: 8h           (free-text, only used in summaries)
    set -euo pipefail
    cd /root/jass
    ./build/jass --gen-data-wdl 200000 /root/jass/jobs/results/0001-gen-depth20-200k/data.bin 20 4 200 1

Result layout (committed back to origin/main):
    jobs/results/<id>/
        status.json           {"state": "running|completed|failed", ...}
        output.log            tail -n 5000 of stdout+stderr (truncated to 1 MB)
        artefacts/            small artefacts (< 50 MB total) copied here
                              after success; large artefacts stay on the
                              server only (path noted in status.json)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path

REPO_DIR    = Path("/root/jass")
QUEUE_DIR   = REPO_DIR / "jobs" / "queue"
RESULTS_DIR = REPO_DIR / "jobs" / "results"
STATE_DIR   = REPO_DIR / "jobs" / "state"
IN_FLIGHT   = STATE_DIR / "in-flight.json"

MAX_LOG_BYTES       = 1_000_000   # tail kept in jobs/results/<id>/output.log
MAX_ARTEFACT_BYTES  = 50_000_000  # > 50 MB → not committed, noted in status


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a shell command, fail loudly. Use for tooling (git, etc.)."""
    return subprocess.run(cmd, cwd=REPO_DIR, check=True,
                          capture_output=True, text=True, **kw)


def sh_ok(cmd: list[str]) -> bool:
    """Run, return True/False — no raise."""
    return subprocess.run(cmd, cwd=REPO_DIR,
                          capture_output=True).returncode == 0


def git_pull() -> None:
    # Best-effort: ignore failure (next tick will retry).
    subprocess.run(["git", "fetch", "--prune", "origin", "main"],
                   cwd=REPO_DIR, check=False, capture_output=True)
    subprocess.run(["git", "reset", "--hard", "origin/main"],
                   cwd=REPO_DIR, check=False, capture_output=True)


def commit_and_push(message: str, paths: list[Path]) -> bool:
    """Stage `paths`, commit, push. Returns True on push success."""
    if not paths:
        return True
    rel = [str(p.relative_to(REPO_DIR)) for p in paths]
    sh_ok(["git", "add", "--", *rel])
    # Nothing to commit if the index matches HEAD.
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"],
                          cwd=REPO_DIR).returncode
    if diff == 0:
        return True
    sh_ok(["git", "commit", "-m", message])
    # Pull-rebase to absorb any concurrent changes before pushing.
    sh_ok(["git", "pull", "--rebase", "--autostash", "origin", "main"])
    return sh_ok(["git", "push", "origin", "HEAD:main"])


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def read_in_flight() -> dict | None:
    if not IN_FLIGHT.exists():
        return None
    try:
        return json.loads(IN_FLIGHT.read_text())
    except json.JSONDecodeError:
        return None


def clear_in_flight() -> None:
    if IN_FLIGHT.exists():
        IN_FLIGHT.unlink()


def pick_next_job() -> Path | None:
    if not QUEUE_DIR.exists():
        return None
    # Sorted by filename so 0001-* runs before 0002-*.
    candidates = sorted(p for p in QUEUE_DIR.glob("*.sh") if p.is_file())
    for c in candidates:
        # A job is "already processed" if jobs/results/<id>/status.json
        # exists with state in {completed, failed}.
        job_id = c.stem
        status = RESULTS_DIR / job_id / "status.json"
        if status.exists():
            try:
                state = json.loads(status.read_text()).get("state")
            except json.JSONDecodeError:
                state = None
            if state in ("completed", "failed"):
                continue
        return c
    return None


def reap_finished_job() -> None:
    """If in-flight pid is dead, finalize the result and push."""
    info = read_in_flight()
    if not info:
        return
    if alive(info.get("pid", -1)):
        return  # still running, no-op
    # Process is gone. Read its tail log + exit code from the result dir.
    job_id = info["job_id"]
    out_dir = RESULTS_DIR / job_id
    exit_file = out_dir / "exit_code"
    if exit_file.exists():
        try:
            rc = int(exit_file.read_text().strip())
        except ValueError:
            rc = -1
    else:
        # The script never wrote its exit code → assume crash.
        rc = -1
    state = "completed" if rc == 0 else "failed"
    status = {
        "job_id":     job_id,
        "state":      state,
        "exit_code":  rc,
        "started_at": info.get("started_at"),
        "ended_at":   utcnow(),
        "host":       socket.gethostname(),
    }
    # Truncate the live log to the last MAX_LOG_BYTES.
    raw_log = out_dir / "output.log.raw"
    out_log = out_dir / "output.log"
    if raw_log.exists():
        size = raw_log.stat().st_size
        if size <= MAX_LOG_BYTES:
            shutil.copyfile(raw_log, out_log)
        else:
            with raw_log.open("rb") as f:
                f.seek(size - MAX_LOG_BYTES)
                tail = f.read()
            out_log.write_bytes(b"...[truncated]...\n" + tail)
    # Move/copy small artefacts if any.
    art_src = out_dir / "artefacts.src"
    if art_src.exists():
        for f in art_src.iterdir():
            if f.is_file() and f.stat().st_size <= MAX_ARTEFACT_BYTES:
                (out_dir / "artefacts").mkdir(exist_ok=True)
                shutil.copy2(f, out_dir / "artefacts" / f.name)
        # Always note where the originals live on the server.
        status["artefacts_server_path"] = str(art_src)
    (out_dir / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    clear_in_flight()
    commit_and_push(
        f"runner: finalize {job_id} ({state}, rc={rc})",
        [out_dir, STATE_DIR])


def start_job(script: Path) -> None:
    """Launch the script in a detached process, record state."""
    job_id  = script.stem
    out_dir = RESULTS_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Wrapper that runs the script, writes its exit code, and stays
    # alive across systemd-runner ticks (setsid → new session).
    raw_log = out_dir / "output.log.raw"
    exit_code = out_dir / "exit_code"
    wrapper = (
        f'exec >{raw_log} 2>&1; '
        f'bash {script}; echo $? > {exit_code}'
    )

    p = subprocess.Popen(
        ["setsid", "bash", "-c", wrapper],
        cwd=REPO_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    started = utcnow()
    info = {
        "job_id":     job_id,
        "script":     str(script.relative_to(REPO_DIR)),
        "pid":        p.pid,
        "started_at": started,
        "host":       socket.gethostname(),
    }
    IN_FLIGHT.write_text(json.dumps(info, indent=2) + "\n")

    status = {
        "job_id":     job_id,
        "state":      "running",
        "started_at": started,
        "host":       socket.gethostname(),
        "pid":        p.pid,
    }
    (out_dir / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    commit_and_push(
        f"runner: start {job_id}",
        [out_dir, STATE_DIR])


def main() -> int:
    if not REPO_DIR.exists():
        print(f"missing {REPO_DIR}", file=sys.stderr)
        return 1
    git_pull()
    # Always check whether a previous job finished while we were away.
    reap_finished_job()
    if read_in_flight():
        return 0  # still busy, drop out
    job = pick_next_job()
    if not job:
        return 0
    start_job(job)
    return 0


if __name__ == "__main__":
    sys.exit(main())
