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
import time
from pathlib import Path

REPO_DIR    = Path("/root/jass")
QUEUE_DIR   = REPO_DIR / "jobs" / "queue"
RESULTS_DIR = REPO_DIR / "jobs" / "results"
STATE_DIR   = REPO_DIR / "jobs" / "state"
IN_FLIGHT   = STATE_DIR / "in-flight.json"
KILL_FLAG   = STATE_DIR / "kill-in-flight"

MAX_LOG_BYTES       = 1_000_000   # tail kept in jobs/results/<id>/output.log

# Per-file cap for auto-committing artefacts to git. Files above this
# stay on the server (artefacts.src/) and are noted in status.json
# under "artefacts_server_path" — recoverable only if the host survives.
#
# GitHub blocks pushes containing any file > 100 MB (hard limit). We set
# the cap below that with a 5 MB safety margin so a slightly oversized
# JNNW or NNUE artefact doesn't break the runner's commit step.
#
# History:
#   50 MB until 2026-05-18: fit the depth-20 1M dataset (38 MB) but not
#                           Cycle 8 master-game JNNW outputs (~50-300 MB
#                           depending on the rating filter and game pool).
#   95 MB from 2026-05-18:  fits master-2000.jnnw (rated >=2000, a few
#                           tens of thousands of games) in most cases.
#                           Larger master-1600 files stay server-only.
MAX_ARTEFACT_BYTES  = 95_000_000


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

    # Multi-host scope filter. When set, each host only picks scripts
    # whose stem starts with the given prefix — that's how we keep two
    # CCX23 hosts in a single GitOps repo from racing for the same job.
    #
    # Set on the host via the systemd unit's EnvironmentFile (typically
    # `/etc/jass-runner/host.env` containing a line like
    # `JASS_HOST_FILTER=0020a-`). When unset (default), every host picks
    # every job — the single-host behaviour we've had since day one.
    host_filter = os.environ.get("JASS_HOST_FILTER", "").strip()
    if host_filter:
        before = len(candidates)
        candidates = [c for c in candidates if c.stem.startswith(host_filter)]
        print(f"runner: JASS_HOST_FILTER={host_filter!r} keeps "
              f"{len(candidates)}/{before} candidate jobs", flush=True)

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


def kill_in_flight_if_requested() -> None:
    """GitOps kill: if `jobs/state/kill-in-flight` is committed, SIGTERM
    then SIGKILL the wrapper's process group, delete the flag, and let
    the next reap finalize the job as failed normally.

    Lets us stop a stuck or runaway job (e.g. a Scan engine hanging on a
    bad set-param) without SSH'ing into the host. Commit the flag file,
    push, wait one tick (~5 min); the runner kills the wrapper, removes
    the flag (so we don't kill the next job too), and the tick after
    that picks the next queued script normally.
    """
    if not KILL_FLAG.exists():
        return
    info = read_in_flight()
    if not info:
        # No job to kill — still clean up the flag so it doesn't sit
        # around and slay an unrelated future job.
        KILL_FLAG.unlink()
        commit_and_push("runner: drop stale kill-in-flight (no job running)",
                        [STATE_DIR])
        return
    job_id = info["job_id"]
    out_dir = RESULTS_DIR / job_id
    wrapper_pid_file = out_dir / "wrapper.pid"
    wrapper_pid = info.get("pid", -1)
    if wrapper_pid_file.exists():
        try:
            wrapper_pid = int(wrapper_pid_file.read_text().strip())
        except ValueError:
            pass
    if wrapper_pid > 0 and alive(wrapper_pid):
        try:
            pgid = os.getpgid(wrapper_pid)
        except ProcessLookupError:
            pgid = wrapper_pid
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        # Give the process group a moment to clean up, then SIGKILL.
        time.sleep(2)
        if alive(wrapper_pid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    KILL_FLAG.unlink()
    commit_and_push(
        f"runner: killed {job_id} via kill-in-flight flag",
        [STATE_DIR])


def reap_finished_job() -> None:
    """If in-flight pid is dead, finalize the result and push."""
    info = read_in_flight()
    if not info:
        return
    # The wrapper writes its own PID into out_dir/wrapper.pid at startup
    # (echo $$). That file is the source of truth: it's immune to the
    # caller-side surprises that affect Popen.pid (e.g. an old in-memory
    # copy of runner.py wrapping bash with an extra `setsid` command,
    # which double-forks and leaves p.pid pointing at a process that
    # dies in milliseconds). Fall back to info["pid"] only if the file
    # is missing — that means the wrapper never even got to its first
    # line, which is a genuine launch failure.
    job_id  = info["job_id"]
    out_dir = RESULTS_DIR / job_id
    wrapper_pid_file = out_dir / "wrapper.pid"
    wrapper_pid = info.get("pid", -1)
    if wrapper_pid_file.exists():
        try:
            wrapper_pid = int(wrapper_pid_file.read_text().strip())
        except ValueError:
            pass
    if alive(wrapper_pid):
        return  # still running, no-op
    # Process is gone. Read its tail log + exit code from the result dir.
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
    # IMPORTANT: the very first thing the wrapper does is record its
    # own PID into wrapper.pid. The reaper uses that file as the
    # source of truth, instead of Popen.pid, so the alive-check is
    # robust even if a stale in-memory copy of this very file wraps
    # bash with an extra `setsid` (which double-forks and leaves
    # Popen.pid pointing at a process that exits in milliseconds).
    raw_log     = out_dir / "output.log.raw"
    exit_code   = out_dir / "exit_code"
    wrapper_pid = out_dir / "wrapper.pid"
    wrapper = (
        f'exec >{raw_log} 2>&1; '
        f'echo $$ > {wrapper_pid}; '
        f'bash {script}; echo $? > {exit_code}'
    )

    # Detach via Python's start_new_session=True (calls os.setsid() in
    # the child before exec). Do NOT also invoke the external `setsid`
    # command: when the child is already a session leader, setsid(1)
    # double-forks and Popen's p.pid points at the short-lived setsid
    # process instead of the real wrapper bash — so the next tick sees
    # `alive(p.pid) == False` and reaps the job as failed while the
    # actual wrapper is still chugging happily in the background.
    p = subprocess.Popen(
        ["bash", "-c", wrapper],
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


def heartbeat(info: dict) -> None:
    """Snapshot in-flight job progress into out_dir/progress.json and push.

    Lets you watch a long-running job's progress via `git pull` without
    SSH'ing into the host. Called on every tick where a job is still
    running (i.e. reap_finished_job kept it).
    """
    job_id  = info["job_id"]
    out_dir = RESULTS_DIR / job_id
    started = info.get("started_at")
    now     = utcnow()
    try:
        elapsed = int(
            (dt.datetime.fromisoformat(now)
             - dt.datetime.fromisoformat(started)).total_seconds()
        )
    except (TypeError, ValueError):
        elapsed = None

    snapshot: dict = {
        "job_id":          job_id,
        "snapshot_at":     now,
        "started_at":      started,
        "elapsed_seconds": elapsed,
        "artefacts":       [],
    }
    art_src = out_dir / "artefacts.src"
    if art_src.exists():
        for f in sorted(art_src.iterdir()):
            if not f.is_file():
                continue
            sz = f.stat().st_size
            entry = {"name": f.name, "size_bytes": sz}
            # JNNW records are 38 bytes after an 8-byte header.
            if f.suffix == ".bin" and sz >= 8:
                entry["records"] = (sz - 8) // 38
            snapshot["artefacts"].append(entry)

    wrapper_pid_file = out_dir / "wrapper.pid"
    if wrapper_pid_file.exists():
        try:
            wpid = int(wrapper_pid_file.read_text().strip())
            ps = subprocess.run(
                ["ps", "-o", "pid,ppid,etime,pcpu,pmem,comm", "-g", str(wpid)],
                capture_output=True, text=True, check=False)
            snapshot["ps_session"] = ps.stdout
        except (ValueError, FileNotFoundError):
            pass

    (out_dir / "progress.json").write_text(
        json.dumps(snapshot, indent=2) + "\n")

    commit_and_push(f"runner: heartbeat {job_id}", [out_dir])


def main() -> int:
    if not REPO_DIR.exists():
        print(f"missing {REPO_DIR}", file=sys.stderr)
        return 1
    git_pull()
    # GitOps kill: honour the kill-in-flight flag before reaping, so
    # the wrapper is killed first and the reap sees a dead PID and
    # finalizes the job as failed normally.
    kill_in_flight_if_requested()
    # Always reap a finished job and heartbeat a still-running one,
    # even if the runner is paused — we want in-flight work to
    # complete cleanly and stay visible via progress.json.
    reap_finished_job()
    info = read_in_flight()
    if info:
        heartbeat(info)
        return 0  # still busy, drop out
    # Pause flag: when `jobs/state/runner-paused` is present in the
    # repo, the runner finishes any reap/heartbeat but does NOT pick
    # new work from the queue. To pause, commit the file; to resume,
    # `git rm` it. This is the GitOps equivalent of `systemctl disable`
    # but doesn't require SSH to flip back — a single PR is enough.
    if (STATE_DIR / "runner-paused").exists():
        return 0
    job = pick_next_job()
    if not job:
        return 0
    start_job(job)
    return 0


if __name__ == "__main__":
    sys.exit(main())
