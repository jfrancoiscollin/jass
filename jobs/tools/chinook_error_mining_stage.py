#!/usr/bin/env python3
"""Authenticated, zero-effect CPX stage for Chinook-style error mining."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import chinook_error_mining as miner
from jobs.tools import fetch_result_files as fetch
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

SCHEMA = "jass.chinook_error_mining_stage.v1"
TERMINAL = "CHINOOK_ERROR_MINING_COMPLETE_V1"
PHASES = ["authenticate-historical-inputs", "mine-gross-error-motifs", "publish-diagnostic"]

REFERENCE_JOB = "cpx62-2065-l3-cls-hier-scan-reference-diagnostic-v1"
REFERENCE_CODE = "7b789a0c675ce08868fe4a8fcef0becaa4193286"
SELECTION = (
    "home-1651-l3-scan-ceiling-selection-v1",
    "20260829T133348Z-28e12fba",
    "28e12fba0ead14def244ffc442b15937f65edc0e",
)

def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def unique_completed_attempt(job_id: str) -> str:
    rclone = os.environ.get("RCLONE_BIN", "rclone")
    prefix = f"r2:jass-data/runs/{job_id}/"
    proc = subprocess.run(
        [rclone, "lsf", prefix, "--dirs-only"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    attempts = sorted({line.strip().rstrip("/") for line in proc.stdout.splitlines() if line.strip()})
    completed = []
    for attempt in attempts:
        candidate = f"r2:jass-data/runs/{job_id}/{attempt}"
        try:
            inv = fetch.inspect_result_inventory(rclone=rclone, prefix=candidate)
        except Exception:
            continue
        if inv.get("job_id") == job_id and inv.get("result_state") == "completed" and inv.get("exit_code") == 0:
            completed.append((attempt, inv))
    need(len(completed) == 1, f"{job_id}: expected exactly one completed attempt, got {len(completed)}")
    return completed[0][0]

def fetch_source(job_id: str, attempt_id: str, code_sha: str, remote: str, local: str, out: Path) -> dict:
    prefix = f"r2:jass-data/runs/{job_id}/{attempt_id}"
    report = fetch.fetch_files(
        rclone=os.environ.get("RCLONE_BIN", "rclone"),
        prefix=prefix,
        selections=[(remote, local)],
        out_dir=out,
    )
    need(report.get("job_id") == job_id, "job identity drift")
    need(report.get("attempt_id") == attempt_id, "attempt identity drift")
    need(report.get("code_sha") == code_sha, "code identity drift")
    need(report.get("result_state") == "completed" and report.get("exit_code") == 0, "source not completed")
    return report

def write_patterns(path: Path, rows: list[dict]) -> None:
    with path.open("x", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def main() -> int:
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    work = Path(os.environ["JASS_RESULT_DIR"]) / "work" / "chinook-error-mining-v1"
    art.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=False)
    evidence = StageEvidence(art, os.environ["LAUNCH_MODE"])
    try:
        evidence.begin(PHASES[0])
        ref_attempt = unique_completed_attempt(REFERENCE_JOB)
        ref_dir = work / "reference"
        sel_dir = work / "selection"
        auth_ref = fetch_source(
            REFERENCE_JOB,
            ref_attempt,
            REFERENCE_CODE,
            "artefacts/all-512-scan-reference.tsv",
            "all-512-scan-reference.tsv",
            ref_dir,
        )
        auth_sel = fetch_source(
            SELECTION[0],
            SELECTION[1],
            SELECTION[2],
            "artefacts/siblings.tsv",
            "siblings.tsv",
            sel_dir,
        )
        evidence.complete()

        evidence.begin(PHASES[1])
        diag = miner.read_tsv(ref_dir / "all-512-scan-reference.tsv")
        siblings = miner.read_tsv(sel_dir / "siblings.tsv")
        summary, patterns = miner.analyze(diag, siblings)
        need(summary["roots"] == 512, "root count drift")
        need(summary["new_scan_searches"] == 0 and summary["new_jass_searches"] == 0, "nonzero search effects")
        evidence.complete()

        evidence.begin(PHASES[2])
        atomic_json(art / "chinook-error-mining-v1.json", summary)
        write_patterns(art / "chinook-error-patterns-v1.csv", patterns)
        source_auth = {
            "schema": SCHEMA,
            "reference": auth_ref,
            "selection": auth_sel,
            "reference_attempt_discovered_uniquely": ref_attempt,
            "reference_sha256": sha(ref_dir / "all-512-scan-reference.tsv"),
            "siblings_sha256": sha(sel_dir / "siblings.tsv"),
        }
        atomic_json(art / "source-authentication.json", source_auth)
        terminal = {
            "schema": SCHEMA,
            "state": "completed",
            "terminal": TERMINAL,
            **summary,
            "source_reference_job": REFERENCE_JOB,
            "source_reference_attempt": ref_attempt,
            "source_selection_job": SELECTION[0],
            "next_stage": "INTERPRET_MOTIFS_AND_PREREGISTER_CAUSAL_TEST_ONLY",
        }
        atomic_json(art / "scientific-summary.json", terminal)
        (art / "RESULTS.md").write_text(
            "# Chinook-style error mining V1\n\n"
            "Exploratory consumed-data diagnostic only. Scan is not ground truth. "
            "No new search, fit, self-play, match, promotion or bake.\n\n"
            + json.dumps(summary, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        names = [
            "chinook-error-mining-v1.json",
            "chinook-error-patterns-v1.csv",
            "source-authentication.json",
            "scientific-summary.json",
            "RESULTS.md",
        ]
        atomic_json(
            art / "manifest.json",
            {
                "schema": SCHEMA,
                "terminal": TERMINAL,
                "evidence": {
                    name: {"sha256": sha(art / name), "size_bytes": (art / name).stat().st_size}
                    for name in names
                },
                "scientific_side_effects": {
                    "fits": 0,
                    "new_scan_searches": 0,
                    "new_jass_searches": 0,
                    "strength_games": 0,
                    "selfplay_games": 0,
                    "promotions": 0,
                    "bakes": 0,
                    "test_target_reads": 0,
                },
            },
        )
        evidence.complete()
        evidence.finish()
        return 0
    except BaseException as exc:
        evidence.fail(exc)
        raise

if __name__ == "__main__":
    raise SystemExit(main())
