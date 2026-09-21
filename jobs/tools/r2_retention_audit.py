#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.launch_runtime_v2 import StageEvidence

CONTROL = Path(os.environ.get("JASS_CONTROL_REPO_DIR", "/srv/jass/control"))
ART = Path(os.environ["JASS_ARTEFACT_DIR"])
SCHEMA = "jass.r2_retention_audit.v1"
TERMINAL = "R2_RETENTION_AUDIT_COMPLETE_V1"
JOB_RE = re.compile(r"\b(?:cpx62|ccx33|home)-[A-Za-z0-9._-]+\b")


def collect_refs(root: Path) -> set[str]:
    out: set[str] = set()
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if not p.is_file() or p.is_symlink():
            continue
        try:
            if p.stat().st_size > 4 * 1024 * 1024:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        out.update(JOB_RE.findall(text))
    return out


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(ART, os.environ["LAUNCH_MODE"])
    try:
        evidence.begin("inventory-r2")
        rclone = os.environ.get("RCLONE_BIN", "rclone")
        proc = subprocess.run(
            [rclone, "lsf", "r2:jass-data", "--recursive", "--files-only", "--format", "sp", "--separator", ";"],
            check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800,
        )

        by_job = defaultdict(lambda: {"bytes": 0, "objects": 0})
        by_top = defaultdict(lambda: {"bytes": 0, "objects": 0})
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            size_s, path = line.split(";", 1)
            size = int(size_s)
            top = path.split("/", 1)[0]
            by_top[top]["bytes"] += size
            by_top[top]["objects"] += 1
            if path.startswith("runs/"):
                parts = path.split("/")
                if len(parts) >= 3:
                    job = parts[1]
                    by_job[job]["bytes"] += size
                    by_job[job]["objects"] += 1

        refs = collect_refs(ROOT) | collect_refs(CONTROL)
        decisions = []
        keep_bytes = 0
        delete_bytes = 0
        for job, stat in sorted(by_job.items(), key=lambda kv: kv[1]["bytes"], reverse=True):
            keep = job in refs
            decisions.append({
                "job_id": job,
                "decision": "KEEP" if keep else "DELETE_CANDIDATE",
                "reason": "referenced_by_current_repo_or_control" if keep else "unreferenced_run_candidate",
                "bytes": stat["bytes"],
                "objects": stat["objects"],
            })
            if keep:
                keep_bytes += stat["bytes"]
            else:
                delete_bytes += stat["bytes"]

        with (ART / "r2-job-retention.csv").open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["job_id", "decision", "reason", "bytes", "objects"])
            writer.writeheader()
            writer.writerows(decisions)

        summary = {
            "schema": SCHEMA,
            "state": "completed",
            "terminal": TERMINAL,
            "read_only": True,
            "bucket": "jass-data",
            "total_bytes": sum(x["bytes"] for x in by_top.values()),
            "total_objects": sum(x["objects"] for x in by_top.values()),
            "top_level": dict(sorted(by_top.items())),
            "run_jobs": len(by_job),
            "referenced_jobs": sum(d["decision"] == "KEEP" for d in decisions),
            "delete_candidate_jobs": sum(d["decision"] == "DELETE_CANDIDATE" for d in decisions),
            "referenced_run_bytes": keep_bytes,
            "delete_candidate_run_bytes": delete_bytes,
            "policy": {
                "non_runs": "KEEP_BY_DEFAULT",
                "runs_referenced_by_current_jass_or_control": "KEEP",
                "unreferenced_runs": "DELETE_CANDIDATE_ONLY_NO_DELETION",
            },
        }
        payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
        (ART / "r2-retention-summary.json").write_text(payload, encoding="utf-8")
        (ART / "scientific-summary.json").write_text(payload, encoding="utf-8")
        (ART / "RESULTS.md").write_text("# R2 retention audit\n\n" + payload, encoding="utf-8")
        evidence.complete()
        evidence.finish()
        return 0
    except BaseException as exc:
        evidence.fail(exc)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
