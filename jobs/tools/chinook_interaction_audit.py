#!/usr/bin/env python3
"""Preregistered Chinook interaction audit over frozen 512 CLS roots."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import chinook_error_mining as miner
from jobs.tools import fetch_result_files as fetch
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

SCHEMA = "jass.chinook_interaction_audit.v1"
TERMINAL = "CHINOOK_INTERACTION_AUDIT_COMPLETE_V1"
PHASES = ["authenticate-historical-inputs", "evaluate-fixed-interactions", "publish-diagnostic"]

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
    proc = subprocess.run(
        [rclone, "lsf", f"r2:jass-data/runs/{job_id}/", "--dirs-only"],
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
    )
    attempts = sorted({x.strip().rstrip("/") for x in proc.stdout.splitlines() if x.strip()})
    completed = []
    for attempt in attempts:
        prefix = f"r2:jass-data/runs/{job_id}/{attempt}"
        try:
            inv = fetch.inspect_result_inventory(rclone=rclone, prefix=prefix)
        except Exception:
            continue
        if inv.get("job_id") == job_id and inv.get("result_state") == "completed" and inv.get("exit_code") == 0:
            completed.append(attempt)
    need(len(completed) == 1, f"{job_id}: expected one completed attempt, got {len(completed)}")
    return completed[0]

def fetch_one(job_id: str, attempt_id: str, code_sha: str, remote: str, local: str, out: Path) -> dict:
    report = fetch.fetch_files(
        rclone=os.environ.get("RCLONE_BIN", "rclone"),
        prefix=f"r2:jass-data/runs/{job_id}/{attempt_id}",
        selections=[(remote, local)],
        out_dir=out,
    )
    need(report.get("job_id") == job_id, "job identity drift")
    need(report.get("attempt_id") == attempt_id, "attempt identity drift")
    need(report.get("code_sha") == code_sha, "code identity drift")
    need(report.get("result_state") == "completed" and report.get("exit_code") == 0, "source state drift")
    return report

def fixed_interactions(f: dict[str, str]) -> dict[str, bool]:
    phase23 = f["phase"] in {"P2", "P3"}
    mobility = f["legal_moves"] == "5-8"
    behind = f["stm_material_status"] == "behind"
    men47 = 4 <= int(f["white_men"]) <= 7 and 4 <= int(f["black_men"]) <= 7
    return {
        "CORE": phase23 and mobility and behind,
        "CORE_MEN_4_7": phase23 and mobility and behind and men47,
        "PHASE_MOBILITY": phase23 and mobility,
        "MOBILITY_BEHIND": mobility and behind,
        "PHASE_BEHIND": phase23 and behind,
        "P2_CORE": f["phase"] == "P2" and mobility and behind,
        "P3_CORE": f["phase"] == "P3" and mobility and behind,
    }

def analyze(diag: list[dict[str, str]], siblings: list[dict[str, str]]) -> dict:
    need(len(diag) == miner.NROOTS, "diagnostic root count")
    by_root: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in siblings:
        by_root[row["parent_id"]].append(row)
    ids = [r["root_id"] for r in diag]
    need(len(set(ids)) == miner.NROOTS and set(ids).issubset(by_root), "root coverage")

    regrets = {r["root_id"]: int(r[miner.PRIMARY]) for r in diag}
    delta = {r["root_id"]: int(r[miner.DELTA]) for r in diag}
    threshold = sorted(regrets.values(), reverse=True)[miner.TAIL - 1]
    gross = {rid for rid, v in regrets.items() if v >= threshold}
    baseline = len(gross) / miner.NROOTS
    features = {rid: miner.descriptors(by_root[rid]) for rid in ids}

    memberships = {name: [] for name in fixed_interactions(next(iter(features.values())))}
    for rid, f in features.items():
        for name, hit in fixed_interactions(f).items():
            if hit:
                memberships[name].append(rid)

    rows = []
    for name, rids in memberships.items():
        gc = sum(r in gross for r in rids)
        rate = gc / len(rids) if rids else 0.0
        vals = [regrets[r] for r in rids]
        rows.append({
            "interaction": name,
            "support": len(rids),
            "gross_error_count": gc,
            "gross_error_rate": rate,
            "baseline_gross_error_rate": baseline,
            "lift": (rate / baseline) if baseline and rids else 0.0,
            "mean_curriculum_regret_centi_scan": statistics.fmean(vals) if vals else None,
            "median_curriculum_regret_centi_scan": statistics.median(vals) if vals else None,
            "mean_hier_minus_curriculum_centi_scan": statistics.fmean(delta[r] for r in rids) if rids else None,
        })
    return {
        "schema": SCHEMA,
        "classification": "EXPLORATORY_CONSUMED_DATA",
        "diagnostic_only": True,
        "scientific_verdict": None,
        "causal_claim_authorized": False,
        "feature_implementation_authorized": False,
        "promotion_authorized": False,
        "new_scan_searches": 0,
        "new_jass_searches": 0,
        "fits": 0,
        "strength_games": 0,
        "roots": miner.NROOTS,
        "gross_tail_nominal_roots": miner.TAIL,
        "gross_tail_tie_inclusive_roots": len(gross),
        "gross_tail_threshold_centi_scan": threshold,
        "baseline_gross_error_rate": baseline,
        "interactions": rows,
    }

def main() -> int:
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    work = Path(os.environ["JASS_RESULT_DIR"]) / "work" / "chinook-interaction-audit-v1"
    art.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=False)
    evidence = StageEvidence(art, os.environ["LAUNCH_MODE"])
    try:
        evidence.begin(PHASES[0])
        attempt = unique_completed_attempt(REFERENCE_JOB)
        ref_dir, sel_dir = work / "reference", work / "selection"
        auth_ref = fetch_one(REFERENCE_JOB, attempt, REFERENCE_CODE, "artefacts/all-512-scan-reference.tsv", "all-512-scan-reference.tsv", ref_dir)
        auth_sel = fetch_one(SELECTION[0], SELECTION[1], SELECTION[2], "artefacts/siblings.tsv", "siblings.tsv", sel_dir)
        evidence.complete()

        evidence.begin(PHASES[1])
        result = analyze(miner.read_tsv(ref_dir / "all-512-scan-reference.tsv"), miner.read_tsv(sel_dir / "siblings.tsv"))
        evidence.complete()

        evidence.begin(PHASES[2])
        atomic_json(art / "chinook-interaction-audit-v1.json", result)
        with (art / "chinook-interactions-v1.csv").open("x", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(result["interactions"][0]), lineterminator="\n")
            w.writeheader(); w.writerows(result["interactions"])
        atomic_json(art / "source-authentication.json", {
            "schema": SCHEMA,
            "reference": auth_ref,
            "selection": auth_sel,
            "reference_attempt": attempt,
            "reference_sha256": sha(ref_dir / "all-512-scan-reference.tsv"),
            "siblings_sha256": sha(sel_dir / "siblings.tsv"),
        })
        atomic_json(art / "scientific-summary.json", {
            **result,
            "state": "completed",
            "terminal": TERMINAL,
            "next_stage": "INTERPRET_FIXED_INTERACTIONS_THEN_PREREGISTER_CAUSAL_FEATURE_TEST",
        })
        (art / "RESULTS.md").write_text("# Chinook interaction audit V1\n\n" + json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        names = ["chinook-interaction-audit-v1.json","chinook-interactions-v1.csv","source-authentication.json","scientific-summary.json","RESULTS.md"]
        atomic_json(art / "manifest.json", {
            "schema": SCHEMA,
            "terminal": TERMINAL,
            "evidence": {n: {"sha256": sha(art/n), "size_bytes": (art/n).stat().st_size} for n in names},
            "scientific_side_effects": {"fits":0,"new_scan_searches":0,"new_jass_searches":0,"strength_games":0,"selfplay_games":0,"promotions":0,"bakes":0,"test_target_reads":0},
        })
        evidence.complete(); evidence.finish(); return 0
    except BaseException as exc:
        evidence.fail(exc)
        raise

if __name__ == "__main__":
    raise SystemExit(main())
