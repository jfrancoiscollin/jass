#!/usr/bin/env python3
"""Post-terminal descriptive audit of ALL frozen 2063 roots; never rerun G0.

Read only authenticated published tables/receipts. A completed depth below d*
proves a depth shortfall; reaching d* without its qualifying receipt does NOT
identify which trace predicate failed. Full attempt traces were not published.
No new search, fit, threshold, significance test, ranking or promotion.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
JOB = "cpx62-2063-l3-cls-g0-hier-runtime-rehearsal-v1"
ATTEMPT = "20260919T155826Z-a6f9fa6f"
CODE = "a6f9fa6fbdc66f8d89dd7a5e8c196422cf98a28a"
PREFIX = f"r2:jass-data/runs/{JOB}/{ATTEMPT}"
RECEIPT_SHA = "a5b9a83a6a7932920ca23cf1cd7d15f67855c12835ddecb18c4f67bc9b0d6e59"
CANDIDATE_SHA = "95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628"
PARENT_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
COHORT_SHA = "478abc0fe2fe1fcd8c2157f532ba796745c645ff4f03dac8fd21c2ff851f137e"
FROZEN_FAIL = "CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1"
TERMINAL = "CLS_G0_2063_ALL_ROOTS_DIAGNOSTIC_COMPLETE_V1"
PHASE = "read-published-2063-all-roots"
FILES = ("probe.tsv", "probe-report.json", "g0-root-ids.txt", "g0-deep512.tsv",
         "g0-deep-reference.tsv", "scientific-summary.json", "launch-receipt.json")
PER_FILE_LIMIT = 512 * 1024
TOTAL_LIMIT = 2 * 1024 * 1024
CATEGORIES = ("RECEIPT_PRESENT", "DEPTH_BELOW_TARGET", "TARGET_REACHED_NO_QUALIFYING_RECEIPT")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"not a JSON object: {path.name}")
    return value


def write_json(path: Path, value: dict) -> None:
    # Never overwrite a previous diagnostic or terminal payload.
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def table(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    require(bool(rows) and all(None not in r and None not in r.values() for r in rows),
            f"empty/malformed table: {path.name}")
    return rows


def distribution(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "not_estimable": True}
    require(all(math.isfinite(v) for v in values), "nonfinite descriptive value")
    return {"n": len(values), "mean": statistics.fmean(values),
            "median": statistics.median(values), "min": min(values), "max": max(values)}


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    counts = Counter(r["category"] for r in rows)
    depth = [r["depth_delta"] for r in rows]
    comparable = [r["nodes_ratio_observed"] for r in rows if r["nodes_ratio_observed"] is not None]
    return {
        "n": n, "categories": {c: counts[c] for c in CATEGORIES},
        "depth_delta": distribution(depth),
        "depth_delta_counts": dict(sorted(Counter(depth).items())),
        "shallower": sum(v < 0 for v in depth), "equal_depth": sum(v == 0 for v in depth),
        "deeper": sum(v > 0 for v in depth),
        "nps_ratio": distribution([r["nps_ratio"] for r in rows]),
        "moves_same_as_parent": sum(r["same_move"] for r in rows),
        "parent_matches_reference": sum(r["parent_matches_reference"] for r in rows),
        "candidate_matches_reference": sum(r["candidate_matches_reference"] for r in rows),
        "reference_matches_gained": sum(r["candidate_matches_reference"] and not r["parent_matches_reference"] for r in rows),
        "reference_matches_lost": sum(r["parent_matches_reference"] and not r["candidate_matches_reference"] for r in rows),
        "nodes_ratio_observed_subset": distribution(comparable),
        "nodes_ratio_population_estimate": None,
        "reference_is_curriculum_1m_not_ground_truth": True,
    }


def analyze(probe: list[dict], phases: list[dict], deep: list[dict], ids: list[str],
            report: dict, *, roots_per_phase: int = 128) -> tuple[dict, list[dict]]:
    require(len(ids) == 4 * roots_per_phase and len(set(ids)) == len(ids), "root count/duplicates")
    require([r["parent_id"] for r in phases] == ids, "phase root order")
    require([r["root_id"] for r in deep] == ids, "reference root order")
    require(Counter(r["phase"] for r in phases) == {f"P{i}": roots_per_phase for i in range(4)}, "phase quota")
    require([(r["root_id"], r["arm"]) for r in probe] == [(i, a) for i in ids for a in ("parent", "candidate")], "paired probe root order")
    require(all(int(r["budget"]) == 1_000_000 and r["bestmove_canonical"] for r in deep), "deep budget/move")
    rows = []
    parent_missing, candidate_missing = [], []
    for ordinal, rid in enumerate(ids):
        p, c = probe[2 * ordinal:2 * ordinal + 2]
        pd, cd = int(p["completed_nominal_depth"]), int(c["completed_nominal_depth"])
        target = int(p["target_depth"])
        require(pd >= 0 and cd >= 0 and target == max(1, pd - 1) == int(c["target_depth"]), "target-depth contract")
        values = []
        for arm, row, depth in (("parent", p, pd), ("candidate", c, cd)):
            nodes, wall, nps = int(row["nodes_observed"]), int(row["wall_us"]), float(row["nps"])
            require(0 < nodes <= 200_000 and wall > 0 and math.isfinite(nps) and nps > 0, "runtime numeric contract")
            require(int(row["trace_attempts"]) > 0 and row["bestmove_canonical"], "trace/move missing")
            receipt = None if row["nodes_to_target"] == "" else int(row["nodes_to_target"])
            require(receipt is None or (0 < receipt <= nodes and depth >= target), "invalid qualifying receipt")
            if receipt is None:
                (parent_missing if arm == "parent" else candidate_missing).append(rid)
            values.append(receipt)
        pn, cn = values
        category = "RECEIPT_PRESENT" if cn is not None else (
            "DEPTH_BELOW_TARGET" if cd < target else "TARGET_REACHED_NO_QUALIFYING_RECEIPT")
        reference = deep[ordinal]["bestmove_canonical"]
        rows.append({
            "root_id": rid, "phase": phases[ordinal]["phase"], "parent_depth": pd,
            "candidate_depth": cd, "target_depth": target, "depth_delta": cd - pd,
            "candidate_minus_target": cd - target, "category": category,
            "parent_nodes_to_target": pn, "candidate_nodes_to_target": cn,
            "nodes_ratio_observed": cn / pn if cn is not None and pn is not None else None,
            "nps_ratio": float(c["nps"]) / float(p["nps"]),
            "parent_move": p["bestmove_canonical"], "candidate_move": c["bestmove_canonical"],
            "reference_move": reference, "same_move": p["bestmove_canonical"] == c["bestmove_canonical"],
            "parent_matches_reference": p["bestmove_canonical"] == reference,
            "candidate_matches_reference": c["bestmove_canonical"] == reference,
            "candidate_trace_attempts": int(c["trace_attempts"]),
        })
    for name, expected in (("parent_nodes_to_depth_missing_roots", parent_missing),
                           ("candidate_nodes_to_depth_missing_roots", candidate_missing)):
        require([str(i) for i in report[name]] == expected, f"missing inventory drift: {name}")
    hard = [i for i in ids if i in set(parent_missing + candidate_missing)]
    require([str(i) for i in report["hard_nodes_to_depth_failure_roots"]] == hard, "hard root order")
    require(report["hard_nodes_to_depth_failure_count"] == len(hard), "hard count")
    require(report["nodes_to_depth_surrogate_used"] is False, "surrogate used")
    audit = {
        "all_roots": summarize(rows),
        "by_phase": {f"P{i}": summarize([r for r in rows if r["phase"] == f"P{i}"]) for i in range(4)},
        "missing_receipt_subset": summarize([r for r in rows if r["category"] != "RECEIPT_PRESENT"]),
        "observed_receipt_subset": summarize([r for r in rows if r["category"] == "RECEIPT_PRESENT"]),
        "parent_missing_count": len(parent_missing),
        "missing_rows": [r for r in rows if r["category"] != "RECEIPT_PRESENT"],
        "full_attempt_trace_available": False,
        "receipt_filter_root_cause": "UNRESOLVED_WITH_PUBLISHED_AGGREGATES",
    }
    return audit, rows


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from jobs.tools import fetch_result_files as fetch
    from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    work = Path(os.environ["JASS_RESULT_DIR"]) / "work" / "read-only-2063"
    work.mkdir(parents=True, exist_ok=False)
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, os.environ["LAUNCH_MODE"])
    evidence.begin(PHASE)
    try:
        require(shutil.disk_usage(work).free >= 512 * 1024 * 1024, "insufficient scratch space")
        rclone = os.environ.get("RCLONE_BIN", "rclone")
        inventory = fetch.inspect_result_inventory(rclone=rclone, prefix=PREFIX)
        identity = (inventory["job_id"], inventory["attempt_id"], inventory["code_sha"], inventory["result_state"], inventory["exit_code"])
        require(identity == (JOB, ATTEMPT, CODE, "completed", 0), "source identity/state")
        selected = {item["path"]: item for item in inventory["files"]}
        sizes = [int(selected[f"artefacts/{name}"]["size_bytes"]) for name in FILES]
        require(all(0 < size <= PER_FILE_LIMIT for size in sizes) and sum(sizes) <= TOTAL_LIMIT, "bounded read size")
        authenticated = fetch.fetch_files(rclone=rclone, prefix=PREFIX,
                                         selections=[(f"artefacts/{n}", n) for n in FILES], out_dir=work)
        require(sha(work / "launch-receipt.json") == RECEIPT_SHA, "launch receipt SHA")
        source = load(work / "scientific-summary.json")
        expected = {"terminal": FROZEN_FAIL, "scientific_verdict": "FAIL", "state": "completed",
                    "candidate_arm": "HIER", "candidate_sha256": CANDIDATE_SHA,
                    "direct_parent_sha256": PARENT_SHA, "cohort_identity_sha256": COHORT_SHA,
                    "roots": 512, "budget_nodes": 200000, "trace_parity_mismatches": 0,
                    "new_jass_searches": 1536, "strength_games": 0, "alpha_spent": 0}
        for key, value in expected.items():
            require(source.get(key) == value, f"source terminal contract: {key}")
        report = load(work / "probe-report.json")
        for key, value in {"roots": 512, "budget_nodes": 200000, "threads": 1,
                           "tt_mb": 16, "trace_parity_mismatches": 0}.items():
            require(report.get(key) == value, f"probe contract: {key}")
        ids = (work / "g0-root-ids.txt").read_text().splitlines()
        audit, rows = analyze(table(work / "probe.tsv"), table(work / "g0-deep512.tsv"),
                              table(work / "g0-deep-reference.tsv"), ids, report)
        hard = source["gate"]["hard_nodes_to_depth_failure"]
        require(hard["count"] == 30 == audit["missing_receipt_subset"]["n"] and audit["parent_missing_count"] == 0, "frozen 2063 failure count")
        require([str(i) for i in hard["candidate_missing_roots"]] == [r["root_id"] for r in audit["missing_rows"]], "terminal/root cross-check")
        write_json(art / "all-roots-diagnostic.json", audit)
        with (art / "all-512-roots.tsv").open("x", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        write_json(art / "source-authentication.json", authenticated)
        summary = {
            "schema": "jass.cls_g0_2063_all_roots_diagnostic.v1", "terminal": TERMINAL,
            "state": "completed", "classification": "EXPLORATORY_CONSUMED_DATA",
            "scientific_verdict": None, "source_job": JOB, "source_attempt": ATTEMPT,
            "frozen_source_verdict": "FAIL", "frozen_source_terminal": FROZEN_FAIL,
            "all_roots": audit["all_roots"], "by_phase_categories": {p: a["categories"] for p, a in audit["by_phase"].items()},
            "missing_receipt_subset": audit["missing_receipt_subset"],
            "parent_missing_count": 0, "full_attempt_trace_available": False,
            "new_jass_searches": 0, "new_scan_searches": 0, "fits": 0, "strength_games": 0,
            "selfplay_games": 0, "target_reads": 0, "alpha_spent": 0, "promotions": 0, "bakes": 0,
            "published_probe_rows_read": len(rows) * 2, "published_reference_rows_read": len(rows),
            "promotion_authorized": False, "bake_authorized": False,
            "gate_reevaluated": False, "next_stage": "INTERPRET_DIAGNOSTIC_NO_AUTOMATIC_REPLAY",
        }
        atomic_json(art / "scientific-summary.json", summary)
        text = ("# Diagnostic descriptif des 512 racines HIER / 2063\n\n"
                "Le FAIL original reste inchange. Aucun nouveau fit, search ou match.\n\n"
                + json.dumps(audit["all_roots"], ensure_ascii=False, indent=2)
                + "\n\nLa reference CURRICULUM 1M n'est pas une verite terrain. "
                "Le ratio nodes-to-target porte seulement sur les recus observes, jamais sur les manquants. "
                "Les traces detaillees ne sont pas publiees : aucun diagnostic de predicat absent n'est invente.\n")
        (art / "RESULTS.md").write_text(text, encoding="utf-8")
        write_json(art / "manifest.json", {"schema": "jass.cls_g0_2063_diagnostic_manifest.v1",
                    "terminal": TERMINAL, "source_job": JOB, "source_attempt": ATTEMPT,
                    "frozen_source_terminal": FROZEN_FAIL, "gate_reevaluated": False,
                    "outputs": {n: {"sha256": sha(art / n), "size_bytes": (art / n).stat().st_size}
                                for n in ("all-roots-diagnostic.json", "all-512-roots.tsv", "source-authentication.json", "scientific-summary.json", "RESULTS.md")}})
        evidence.complete()
        evidence.finish()
    except BaseException as exc:
        evidence.fail(exc)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
