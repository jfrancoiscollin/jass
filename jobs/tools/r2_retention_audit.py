#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
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

ART = Path(os.environ["JASS_ARTEFACT_DIR"])
SCHEMA = "jass.r2_retention_audit.v2"
TERMINAL = "R2_RETENTION_PLAN_COMPLETE_V2"
SMALL_LIMIT = 1 << 20

ESSENTIAL_JOBS = {
    "cpx62-1640-l3-t3-rf1-joint-ab-terminal-readout-v1",
    "home-1651-l3-scan-ceiling-selection-v1",
    "cpx62-2062-l3-cls-hier-l2-hier-candidate-rehearsal-v1",
    "cpx62-2065-l3-cls-hier-scan-reference-diagnostic-v1",
    "cpx62-2066-l3-cls-g0-strength-calibration-rehearsal-v1",
    "cpx62-2069-l3-cls-g0-strength-main-production-v1",
    "cpx62-2079-l3-chinook-error-mining-v1",
    "cpx62-2080-l3-chinook-interaction-audit-v1",
    "cpx62-2081-l3-chinook-hybrid-strength-rehearsal-v1",
    "cpx62-2084-r2-retention-audit-v1",
}

MODEL_SUFFIXES = (".pjtw", ".pjtw.gz", ".jnnw", ".jnnw.gz", ".pl8p", ".pl8p.gz", ".onnx", ".safetensors")
MODEL_WORDS = ("model", "weights", "candidate", "champion", "curriculum")


def keep_reason(path: str, size: int, job: str) -> str | None:
    if not path.startswith("runs/"):
        return "KEEP_NON_RUN_NAMESPACE"
    if job in ESSENTIAL_JOBS:
        return "KEEP_ESSENTIAL_JOB"
    lower = path.lower()
    if lower.endswith(MODEL_SUFFIXES) or any(word in Path(lower).name for word in MODEL_WORDS):
        return "KEEP_MODEL_ARTIFACT"
    if size <= SMALL_LIMIT:
        return "KEEP_SMALL_METADATA"
    return None


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(ART, os.environ["LAUNCH_MODE"])
    try:
        evidence.begin("inventory-r2")
        rclone = os.environ.get("RCLONE_BIN", "rclone")
        proc = subprocess.Popen(
            [rclone, "lsf", "r2:jass-data", "--recursive", "--files-only", "--format", "sp", "--separator", ";"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1,
        )
        assert proc.stdout is not None
        by_top = defaultdict(lambda: {"bytes": 0, "objects": 0})
        by_job = defaultdict(lambda: {"bytes": 0, "objects": 0, "delete_bytes": 0, "delete_objects": 0})
        by_reason = defaultdict(lambda: {"bytes": 0, "objects": 0})
        total_bytes = total_objects = 0
        delete_bytes = delete_objects = 0
        manifest_path = ART / "r2-delete-candidates.txt.gz"
        with gzip.open(manifest_path, "xt", encoding="utf-8", compresslevel=6) as manifest:
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                if not line:
                    continue
                size_s, path = line.split(";", 1)
                size = int(size_s)
                total_bytes += size
                total_objects += 1
                top = path.split("/", 1)[0]
                by_top[top]["bytes"] += size
                by_top[top]["objects"] += 1
                job = ""
                if path.startswith("runs/"):
                    parts = path.split("/")
                    if len(parts) >= 3:
                        job = parts[1]
                        by_job[job]["bytes"] += size
                        by_job[job]["objects"] += 1
                reason = keep_reason(path, size, job)
                if reason is None:
                    delete_bytes += size
                    delete_objects += 1
                    by_reason["DELETE_BULK_REPRODUCIBLE"]["bytes"] += size
                    by_reason["DELETE_BULK_REPRODUCIBLE"]["objects"] += 1
                    if job:
                        by_job[job]["delete_bytes"] += size
                        by_job[job]["delete_objects"] += 1
                    manifest.write(path + "\n")
                else:
                    by_reason[reason]["bytes"] += size
                    by_reason[reason]["objects"] += 1
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        rc = proc.wait(timeout=60)
        if rc != 0:
            raise RuntimeError(f"rclone_lsf_failed_rc_{rc}")

        job_rows = []
        for job, stat in sorted(by_job.items(), key=lambda kv: kv[1]["delete_bytes"], reverse=True):
            job_rows.append({
                "job_id": job,
                "decision": "KEEP_ALL" if job in ESSENTIAL_JOBS else ("TRIM_BULK" if stat["delete_bytes"] else "KEEP"),
                "bytes": stat["bytes"],
                "objects": stat["objects"],
                "delete_candidate_bytes": stat["delete_bytes"],
                "delete_candidate_objects": stat["delete_objects"],
            })
        with (ART / "r2-job-retention.csv").open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["job_id","decision","bytes","objects","delete_candidate_bytes","delete_candidate_objects"])
            writer.writeheader()
            writer.writerows(job_rows)

        summary = {
            "schema": SCHEMA,
            "state": "completed",
            "terminal": TERMINAL,
            "read_only": True,
            "bucket": "jass-data",
            "policy": {
                "non_run_namespaces": "KEEP_ALL",
                "essential_jobs": sorted(ESSENTIAL_JOBS),
                "all_models": "KEEP",
                "objects_le_1MiB": "KEEP",
                "other_run_objects_gt_1MiB": "DELETE_CANDIDATE",
            },
            "total_bytes": total_bytes,
            "total_objects": total_objects,
            "delete_candidate_bytes": delete_bytes,
            "delete_candidate_objects": delete_objects,
            "keep_bytes": total_bytes - delete_bytes,
            "keep_objects": total_objects - delete_objects,
            "top_level": dict(sorted(by_top.items())),
            "classification": dict(sorted(by_reason.items())),
            "run_jobs": len(by_job),
            "delete_manifest": "r2-delete-candidates.txt.gz",
        }
        payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
        (ART / "r2-retention-summary.json").write_text(payload, encoding="utf-8")
        (ART / "scientific-summary.json").write_text(payload, encoding="utf-8")
        (ART / "RESULTS.md").write_text("# R2 retention plan v2\n\n" + payload, encoding="utf-8")
        evidence.complete()
        evidence.finish()
        return 0
    except BaseException as exc:
        evidence.fail(exc)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
