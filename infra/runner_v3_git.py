#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Iterable

from runner_v3_common import Config, control_paths, run


def ensure_git_repo(path: Path, label: str) -> None:
    if not (path / ".git").exists():
        raise RuntimeError(f"{label} repository missing at {path}")


def git_sync_code(path: Path, remote: str, ref: str) -> None:
    ensure_git_repo(path, "code")
    run(["git", "fetch", "--prune", remote, ref], cwd=path)
    run(["git", "reset", "--hard", f"{remote}/{ref}"], cwd=path)
    run(["git", "clean", "-fd"], cwd=path)


def git_sync_control(path: Path, remote: str, ref: str) -> None:
    ensure_git_repo(path, "control")
    dirty = run(["git", "status", "--porcelain"], cwd=path).stdout.strip()
    if dirty:
        raise RuntimeError(f"control repository has uncommitted changes: {dirty[:200]}")
    run(["git", "fetch", "--prune", remote, ref], cwd=path)
    pull = run(["git", "pull", "--rebase", remote, ref], cwd=path, check=False)
    if pull.returncode != 0:
        run(["git", "rebase", "--abort"], cwd=path, check=False)
        raise RuntimeError(f"control sync failed: {(pull.stderr or pull.stdout).strip()}")
    push = run(["git", "push", remote, f"HEAD:{ref}"], cwd=path, check=False)
    if push.returncode != 0:
        raise RuntimeError(f"control push failed: {(push.stderr or push.stdout).strip()}")


def git_sha(path: Path, ref: str = "HEAD") -> str:
    return run(["git", "rev-parse", ref], cwd=path).stdout.strip()


def resolve_pinned_code_sha(cfg: Config, requested_sha: str) -> str:
    """Resolve an immutable job pin and require it to belong to develop.

    The control-plane job is allowed to target an older develop commit.  This
    is what makes an already queued job immune to an unrelated later push.
    """
    if len(requested_sha) != 40 or any(
        ch not in "0123456789abcdef" for ch in requested_sha
    ):
        raise RuntimeError("EXPECTED_CODE_SHA must be a full lowercase 40-hex SHA")

    commit_ref = f"{requested_sha}^{{commit}}"
    resolved = run(
        ["git", "rev-parse", "--verify", commit_ref],
        cwd=cfg.code_repo_dir,
        check=False,
    )
    if resolved.returncode != 0:
        # The control repository can move after the code sync at the beginning
        # of a tick.  Refresh develop once before declaring a valid new pin
        # unavailable locally.
        run(
            ["git", "fetch", "--prune", cfg.code_remote, cfg.code_ref],
            cwd=cfg.code_repo_dir,
        )
        resolved = run(
            ["git", "rev-parse", "--verify", commit_ref],
            cwd=cfg.code_repo_dir,
            check=False,
        )
    if resolved.returncode != 0:
        raise RuntimeError(f"pinned code SHA is unavailable: {requested_sha}")

    canonical = resolved.stdout.strip()
    if canonical != requested_sha:
        raise RuntimeError(
            f"pinned code SHA resolved unexpectedly: {requested_sha} -> {canonical}"
        )
    ancestor = run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            requested_sha,
            f"{cfg.code_remote}/{cfg.code_ref}",
        ],
        cwd=cfg.code_repo_dir,
        check=False,
    )
    if ancestor.returncode != 0:
        raise RuntimeError(
            f"pinned code SHA is not on {cfg.code_remote}/{cfg.code_ref}: "
            f"{requested_sha}"
        )
    return canonical


def control_commit_push(cfg: Config, message: str, paths: Iterable[Path]) -> bool:
    paths = list(paths)
    if not paths:
        return True
    rel = [str(path.relative_to(cfg.control_repo_dir)) for path in paths]
    for attempt in range(1, cfg.git_retries + 1):
        run(["git", "add", "--", *rel], cwd=cfg.control_repo_dir, check=False)
        staged = run(["git", "diff", "--cached", "--quiet"],
                     cwd=cfg.control_repo_dir, check=False).returncode
        if staged != 0:
            if run(["git", "commit", "-m", message], cwd=cfg.control_repo_dir,
                   check=False).returncode != 0:
                return False
        pull = run(["git", "pull", "--rebase", "--autostash", cfg.control_remote,
                    cfg.control_ref], cwd=cfg.control_repo_dir, check=False)
        if pull.returncode == 0:
            push = run(["git", "push", cfg.control_remote, f"HEAD:{cfg.control_ref}"],
                       cwd=cfg.control_repo_dir, check=False)
            if push.returncode == 0:
                return True
        run(["git", "rebase", "--abort"], cwd=cfg.control_repo_dir, check=False)
        time.sleep(attempt * 2)
    return False


def claim_job(cfg: Config, script: Path) -> Path:
    if cfg.control_layout == "legacy":
        return script
    paths = control_paths(cfg)
    paths.queue_running.mkdir(parents=True, exist_ok=True)
    claimed = paths.queue_running / script.name
    os.replace(script, claimed)
    if control_commit_push(cfg, f"runner: claim {script.stem}",
                           [paths.queue_pending, paths.queue_running]):
        return claimed
    run(["git", "reset", "--hard", f"{cfg.control_remote}/{cfg.control_ref}"],
        cwd=cfg.control_repo_dir, check=False)
    raise RuntimeError(f"failed to publish claim for {script.stem}")


def finalize_control_script(cfg: Config, claimed: Path, job_id: str) -> None:
    if cfg.control_layout != "v3":
        return
    paths = control_paths(cfg)
    done = paths.queue_done / claimed.name
    paths.queue_done.mkdir(parents=True, exist_ok=True)
    if claimed.exists():
        os.replace(claimed, done)
        if not control_commit_push(cfg, f"runner: done {job_id}",
                                   [paths.queue_running, paths.queue_done]):
            raise RuntimeError(f"failed to move {job_id} to done")


def create_worktree(cfg: Config, job_id: str, attempt_id: str, code_sha: str) -> Path:
    workspace = cfg.spool_root / "work" / job_id / attempt_id / "repo"
    workspace.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(workspace, ignore_errors=True)
    run(["git", "worktree", "add", "--detach", str(workspace), code_sha],
        cwd=cfg.code_repo_dir)
    return workspace


def remove_worktree(cfg: Config, workspace: Path) -> None:
    run(["git", "worktree", "remove", "--force", str(workspace)],
        cwd=cfg.code_repo_dir, check=False)
    shutil.rmtree(workspace, ignore_errors=True)
