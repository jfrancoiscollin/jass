#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.launch_runtime_v2 import StageEvidence

CONTROL = Path(os.environ.get("JASS_CONTROL_REPO_DIR", "/srv/jass/control"))
ART = Path(os.environ["JASS_ARTEFACT_DIR"])
RCLONE = os.environ.get("RCLONE_BIN", "rclone")
TARGET = "r2:jass-data/pause/jass-20260922"
MAX_CAPSULE_BYTES = 8 * 1024**3
TERMINAL = "R2_PAUSE_CAPSULE_READY_V1"

KEEP_JOBS = [
    "home-0977-l3-pure-turnover1to1-train-v1",
    "cpx62-1340-jass-megacorpus-comparative-fit-v1",
    "cpx62-1341-jass-megacorpus-arm-d-fit-v1",
    "cpx62-1637-l3-t3-rf1-joint-ab-train-freeze-v1",
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
    "cpx62-2085-r2-retention-plan-v2",
]


def run(argv: list[str], *, timeout: int = 1800, capture: bool = True) -> str:
    proc = subprocess.run(argv, check=True, text=True, timeout=timeout,
                          stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.PIPE)
    return proc.stdout if capture else ""


def remote_size(prefix: str) -> dict:
    value = json.loads(run([RCLONE, "size", prefix, "--json"], timeout=600))
    return {"bytes": int(value.get("bytes", 0)), "count": int(value.get("count", 0))}


def publish_index(files: dict[str, Path]) -> None:
    publish = ART / "publish"
    publish.mkdir(exist_ok=True)
    for remote_name, source in files.items():
        dest = publish / remote_name
        dest.write_bytes(source.read_bytes())
    run([RCLONE, "copy", str(publish), TARGET, "--checksum", "--immutable",
         "--retries", "5", "--low-level-retries", "20"], timeout=1200, capture=False)
    run([RCLONE, "check", str(publish), TARGET, "--one-way", "--checksum"],
        timeout=1200, capture=False)


def status_for(job: str) -> dict:
    p = CONTROL / "status" / f"{job}.json"
    if not p.is_file():
        raise ValueError(f"missing_status:{job}")
    value = json.loads(p.read_text(encoding="utf-8"))
    if value.get("job_id") != job:
        raise ValueError(f"status_identity:{job}")
    uri = value.get("result_uri")
    if not isinstance(uri, str) or not uri.startswith(f"r2:jass-data/runs/{job}/"):
        raise ValueError(f"result_uri:{job}")
    if value.get("state") not in ("completed", "failed"):
        raise ValueError(f"terminal_state:{job}:{value.get('state')}")
    return value


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(ART, os.environ["LAUNCH_MODE"])
    try:
        evidence.begin("authenticate-sources")
        statuses = [status_for(job) for job in KEEP_JOBS]
        selected = []
        selected_bytes = 0
        for st in statuses:
            sz = remote_size(st["result_uri"])
            selected_bytes += sz["bytes"]
            selected.append({
                "job_id": st["job_id"],
                "attempt_id": st.get("attempt_id"),
                "code_sha": st.get("code_sha"),
                "state": st.get("state"),
                "source_uri": st["result_uri"],
                "source_bytes": sz["bytes"],
                "source_objects": sz["count"],
            })
        if selected_bytes > MAX_CAPSULE_BYTES:
            raise ValueError(f"selected_sources_exceed_capsule_budget:{selected_bytes}")
        evidence.complete()

        evidence.begin("copy-capsule")
        for item in selected:
            dest = f"{TARGET}/runs/{item['job_id']}/{item['attempt_id']}"
            run([RCLONE, "copy", item["source_uri"], dest, "--checksum", "--immutable",
                 "--retries", "5", "--low-level-retries", "20"], timeout=2400, capture=False)
            run([RCLONE, "check", item["source_uri"], dest, "--one-way", "--checksum"],
                timeout=1200, capture=False)
        evidence.complete()

        evidence.begin("publish-capsule-index")
        jass_sha = run(["git", "rev-parse", "HEAD"], timeout=10).strip()
        control_sha = run(["git", "-C", str(CONTROL), "rev-parse", "HEAD"], timeout=10).strip()
        manifest = {
            "schema": "jass.pause_capsule.v1",
            "terminal": TERMINAL,
            "target": TARGET,
            "created_from_jass_sha": jass_sha,
            "created_from_control_sha": control_sha,
            "purpose": "minimal restart capsule before project pause; source code and methods remain in GitHub",
            "selected_jobs": selected,
            "outside_capsule_kept_temporarily": ["r2:jass-data/inputs", "r2:jass-data/runtime"],
            "planned_purge_after_verification": ["r2:jass-data/runs", "r2:jass-data/historical"],
            "hard_post_purge_target_bytes": 10 * 1024**3,
        }
        manifest_path = ART / "capsule-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        readme = ART / "CAPSULE_README.md"
        readme.write_text(
            "# Jass pause capsule — 2026-09-22\n\n"
            "This capsule keeps the exact champion lineage inputs and models needed for a practical restart, "
            "plus the latest scientific decision chain. Source code, preregistrations, job definitions, seeds "
            "and broader historical documentation remain in GitHub and are intentionally not duplicated here.\n\n"
            "Core retained lineage: TURNOVER source (0977), MegaCorpus CURRENT_2M/CONTEXT30 (1340), "
            "CURRICULUM champion (1341), T3/F6 terminal chain, Scan ceiling selection/reference, HIER model, "
            "CLS strength evidence, and Chinook error-mining/interaction/hybrid boundary work.\n",
            encoding="utf-8",
        )
        publish_index({"CAPSULE_MANIFEST.json": manifest_path, "README.md": readme})
        evidence.complete()

        evidence.begin("verify-capsule-budget")
        cap = remote_size(TARGET)
        if cap["bytes"] > MAX_CAPSULE_BYTES:
            raise ValueError(f"capsule_over_budget:{cap['bytes']}")
        complete = {
            "schema": "jass.pause_capsule_complete.v1",
            "terminal": TERMINAL,
            "capsule_bytes": cap["bytes"],
            "capsule_objects": cap["count"],
            "max_capsule_bytes": MAX_CAPSULE_BYTES,
            "selected_job_count": len(selected),
            "ready_for_destructive_purge": True,
        }
        complete_path = ART / "capsule-complete.json"
        complete_path.write_text(json.dumps(complete, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        publish_index({"CAPSULE_COMPLETE.json": complete_path})
        summary = {**complete, "target": TARGET, "selected_source_bytes": selected_bytes, "selected_jobs": KEEP_JOBS}
        payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
        (ART / "scientific-summary.json").write_text(payload, encoding="utf-8")
        (ART / "RESULTS.md").write_text("# R2 pause capsule\n\n" + payload, encoding="utf-8")
        evidence.complete()
        evidence.finish()
        return 0
    except BaseException as exc:
        evidence.fail(exc)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
