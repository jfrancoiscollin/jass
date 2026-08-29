#!/usr/bin/env python3
"""Snapshot pre-cutoff T3-A runtime pools from the runner control plane."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


RUNTIME_RE = re.compile(
    r"^cpx62-[0-9]+-l3-t3-f6-runtime-(?:r0|strength-pool1|strength-pool2)-v1$"
)
POOL_FILES = {"r0-corpus.fen", "pool1-openings.fen", "pool2-openings.fen"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={root}", "-C", str(root), *args], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def git_path_exists(root: Path, commit: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={root}", "-C", str(root),
         "cat-file", "-e", f"{commit}:{path}"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def git_text(root: Path, commit: str, path: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={root}", "-C", str(root),
         "show", f"{commit}:{path}"],
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


def queue_state(root: Path, commit: str, job_id: str) -> list[str]:
    return [state for state in ("pending", "running", "done", "failed")
            if git_path_exists(root, commit, f"queue/{state}/{job_id}.sh")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--specs", type=Path, required=True)
    parser.add_argument("--ref", default="origin/" + "main")
    args = parser.parse_args()
    root = args.control_dir.resolve()
    if not (root / ".git").exists():
        raise ValueError("control plane is not a Git checkout")
    commit = git(root, "rev-parse", args.ref)
    cutoff = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, object]] = []
    specs: set[tuple[str, str]] = set()
    status_paths = git(root, "ls-tree", "-r", "--name-only", commit, "status").splitlines()
    for status_name in sorted(path for path in status_paths if path.endswith(".json")):
        job_id = Path(status_name).stem
        if not RUNTIME_RE.fullmatch(job_id):
            continue
        raw_status = git_text(root, commit, status_name)
        payload = json.loads(raw_status)
        if payload.get("job_id") != job_id:
            raise ValueError(f"status identity drift: {status_name}")
        result_uri = payload.get("result_uri")
        visible: list[str] = []
        for item in payload.get("artefacts", []):
            path = str(item.get("path", "")) if isinstance(item, dict) else str(item)
            if Path(path).name in POOL_FILES:
                visible.append(path)
                if not isinstance(result_uri, str) or not result_uri.startswith("r2:"):
                    raise ValueError(f"observable runtime pool lacks result_uri: {job_id}")
                specs.add((result_uri.rstrip("/"), f"artefacts/{path}" if not path.startswith("artefacts/") else path))
        rows.append({
            "job_id": job_id, "state": payload.get("state"),
            "attempt_id": payload.get("attempt_id"), "result_uri": result_uri,
            "started_at": payload.get("started_at"), "ended_at": payload.get("ended_at"),
            "queue_locations": queue_state(root, commit, job_id),
            "observable_pool_artifacts_at_cutoff": sorted(set(visible)),
            "status_sha256": hashlib.sha256(raw_status.encode()).hexdigest(),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.specs.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "jass.scan_ceiling_runtime_exclusion_snapshot.v1",
        "benchmark_only": True,
        "cutoff_utc": cutoff,
        "control_plane_ref": args.ref,
        "control_plane_head": commit,
        "control_plane_local_head": git(root, "rev-parse", "HEAD"),
        "control_plane_branch": git(root, "branch", "--show-current"),
        "control_plane_dirty": bool(git(root, "status", "--porcelain")),
        "runtime_jobs": rows,
        "observable_pool_artifacts": len(specs),
        "observation_rule": "status artefacts materialized at cutoff; later artifacts do not alter cohort",
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with args.specs.open("w", encoding="utf-8", newline="") as stream:
        stream.write("label\tprefix\tremote_path\n")
        for index, (prefix, remote_path) in enumerate(sorted(specs)):
            stream.write(f"runtime-precutoff-{index:02d}\t{prefix}\t{remote_path}\n")
    print(json.dumps({"control_plane_head": commit, "runtime_pool_artifacts": len(specs)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
