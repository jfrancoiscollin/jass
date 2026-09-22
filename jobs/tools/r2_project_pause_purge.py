#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.launch_runtime_v2 import StageEvidence

ART = Path(os.environ["JASS_ARTEFACT_DIR"])
RCLONE = os.environ.get("RCLONE_BIN", "rclone")
CAPSULE = "r2:jass-data/pause/jass-20260922"
MAX_CAPSULE_BYTES = 8 * 1024**3
MAX_FINAL_BYTES = 10 * 1024**3
TERMINAL = "R2_PROJECT_PAUSE_PURGE_COMPLETE_V1"
CHAMPION_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
HIER_SHA = "95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628"
TURNOVER_SHA = "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"

REQUIRED = {
    "champion": f"{CAPSULE}/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33/artefacts/D-c-prior-then-current.pjtw.gz",
    "context30": f"{CAPSULE}/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/20260814T123246Z-2ce07222/artefacts/current_2m-context30.npy.gz",
    "turnover": f"{CAPSULE}/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984/artefacts/turnover1to1.jnnw.gz",
    "hier": f"{CAPSULE}/runs/cpx62-2062-l3-cls-hier-l2-hier-candidate-rehearsal-v1/20260919T142226Z-a28f1049/artefacts/model.pjtw.gz",
    "scan_reference": f"{CAPSULE}/runs/cpx62-2065-l3-cls-hier-scan-reference-diagnostic-v1/20260919T230339Z-7b789a0c/artefacts/all-512-scan-reference.tsv",
}


def run(argv: list[str], *, timeout: int = 7200, capture: bool = True) -> str:
    proc = subprocess.run(argv, check=True, text=True, timeout=timeout,
                          stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.PIPE)
    return proc.stdout if capture else ""


def remote_size(prefix: str) -> dict:
    value = json.loads(run([RCLONE, "size", prefix, "--json"], timeout=1200))
    return {"bytes": int(value.get("bytes", 0)), "count": int(value.get("count", 0))}


def remote_json(path: str) -> dict:
    return json.loads(run([RCLONE, "cat", path], timeout=120))


def fetch(path: str, local: Path) -> None:
    run([RCLONE, "copyto", path, str(local), "--checksum"], timeout=1200, capture=False)
    if not local.is_file() or local.stat().st_size <= 0:
        raise ValueError(f"missing_required:{path}")


def gzip_raw_sha(path: Path) -> str:
    h = hashlib.sha256()
    with gzip.open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    mode = os.environ["LAUNCH_MODE"]
    evidence = StageEvidence(ART, mode)
    try:
        evidence.begin("verify-capsule")
        marker = remote_json(f"{CAPSULE}/CAPSULE_COMPLETE.json")
        if marker.get("terminal") != "R2_PAUSE_CAPSULE_READY_V1" or marker.get("ready_for_destructive_purge") is not True:
            raise ValueError("capsule_not_authorized")
        cap = remote_size(CAPSULE)
        if cap["bytes"] > MAX_CAPSULE_BYTES + (1 << 20):
            raise ValueError(f"capsule_over_budget:{cap['bytes']}")
        local = ART / "verify"
        local.mkdir(exist_ok=True)
        for name, path in REQUIRED.items():
            fetch(path, local / (name + Path(path).suffix))
        if gzip_raw_sha(local / "champion.gz") != CHAMPION_SHA:
            raise ValueError("champion_sha_mismatch")
        if gzip_raw_sha(local / "hier.gz") != HIER_SHA:
            raise ValueError("hier_sha_mismatch")
        if gzip_raw_sha(local / "turnover.gz") != TURNOVER_SHA:
            raise ValueError("turnover_sha_mismatch")
        evidence.complete()

        evidence.begin("snapshot-before-purge")
        before = remote_size("r2:jass-data")
        runs_before = remote_size("r2:jass-data/runs")
        hist_before = remote_size("r2:jass-data/historical")
        evidence.complete()

        evidence.begin("purge-bulk-history")
        if mode == "production":
            run([RCLONE, "purge", "r2:jass-data/runs", "--retries", "5", "--low-level-retries", "20"], timeout=10800, capture=False)
            run([RCLONE, "purge", "r2:jass-data/historical", "--retries", "5", "--low-level-retries", "20"], timeout=3600, capture=False)
        evidence.complete()

        evidence.begin("verify-final-size")
        if mode == "production":
            after = remote_size("r2:jass-data")
            final_bytes = after["bytes"]
        else:
            predicted = max(0, before["bytes"] - runs_before["bytes"] - hist_before["bytes"])
            after = {"bytes": predicted, "count": None, "predicted": True}
            final_bytes = predicted
        if final_bytes > MAX_FINAL_BYTES:
            raise ValueError(f"final_bucket_over_10GiB:{final_bytes}")
        if remote_size(CAPSULE)["bytes"] <= 0:
            raise ValueError("capsule_missing_after_purge")
        summary = {
            "schema": "jass.r2_project_pause_purge.v1",
            "terminal": "R2_PROJECT_PAUSE_PURGE_REHEARSAL_READY_V1" if mode == "rehearsal" else TERMINAL,
            "state": "completed",
            "mode": mode,
            "dry_run": mode == "rehearsal",
            "before": before,
            "purged_runs": runs_before if mode == "production" else {"planned": runs_before},
            "purged_historical": hist_before if mode == "production" else {"planned": hist_before},
            "after_before_runner_publish": after,
            "max_final_bytes": MAX_FINAL_BYTES,
            "capsule": cap,
            "kept_namespaces": ["pause/jass-20260922", "inputs", "runtime"],
        }
        payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
        (ART / "purge-summary.json").write_text(payload, encoding="utf-8")
        (ART / "scientific-summary.json").write_text(payload, encoding="utf-8")
        (ART / "RESULTS.md").write_text("# R2 project pause purge\n\n" + payload, encoding="utf-8")
        run([RCLONE, "copyto", str(ART / "purge-summary.json"), f"{CAPSULE}/PURGE_SUMMARY.json", "--checksum"], capture=False)
        evidence.complete()
        evidence.finish()
        return 0
    except BaseException as exc:
        evidence.fail(exc)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
