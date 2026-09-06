#!/usr/bin/env python3
"""Authenticate terminal B3 parity evidence and replay the failed 1834 exclusion preflight.

This is a zero-fresh-data diagnostic stage.  It authenticates the four terminal
1833 B3 parity artefacts, proves the six all-exact zero-cost B2 parents are
unchanged (while separately accounting for exact-win zero-search shortcuts),
and replays the exact 1834 exclusion-preparation implementation on already
consumed identity evidence to expose an exact technical error if it still
reproduces.

It never generates a fresh B3 target, runs a teacher search, fits a model, plays
a strength game, promotes a candidate, or bakes an artefact.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import adaptive_sibling_b3_exclusion_prepare_v2 as exclusion_v2  # noqa: E402
from jobs.tools import adaptive_sibling_b3_parity as parity  # noqa: E402
from jobs.tools import adaptive_sibling_b3_parity_stage as parity_stage  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b3_post_parity_audit.v1"
VERDICT = "B3_POST_PARITY_AUTH_AND_1834_DIAGNOSTIC_COMPLETE_V1"
PARITY_VERDICT = "B3_REAL_ADAPTIVE_TEACHER_PARITY_ESTABLISHED_V1"
POLICY = {"M5": 100, "M50": 60, "minimum_survivors": 2}
BUDGETS = [5_000, 50_000, 200_000]

PARITY_JOB = "cpx62-1833-l3-decision-math-b3-real-adaptive-parity-rerun-v1"
PARITY_ATTEMPT = "20260906T124918Z-7756fac9"
PARITY_CODE = "7756fac99ed5d4767aa4bc5d6beff402884008a6"
PARITY_PREFIX = f"r2:jass-data/runs/{PARITY_JOB}/{PARITY_ATTEMPT}"
PARITY_TOOL_BLOB = "54352fb110145b2f5cfbc769d892ce423e026045"

FAILED_1834_CODE = "e27627918d521bdfc8cee778b72aeeb149ca0816"
EXCLUSION_BASE_BLOB = "4dad8a552a2cd76e2f43bdccbd1e9122002e12be"
EXCLUSION_V2_BLOB = "2822f20aa748a02df254e84a6c66bbe495d1de32"

EXPECTED_ALL_EXACT_ZERO_COST = [1216, 1544, 1614, 3510, 3526, 3924]
EXPECTED_ZERO_SEARCH = [1216, 1544, 1614, 3510, 3526, 3842, 3902, 3924]
EXPECTED_EXACT_WIN_ZERO_SEARCH = [3842, 3902]


class AuditError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def read_canonical(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"invalid JSON {path.name}: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical(value):
        raise AuditError(f"non-canonical JSON {path.name}")
    return value


def write_new(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise AuditError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def git_blob(path: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "hash-object", "--", path], cwd=ROOT, text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AuditError(f"cannot hash {path}: {exc}") from exc


def require_blob(path: str, expected: str) -> None:
    actual = git_blob(path)
    if actual != expected:
        raise AuditError(f"implementation blob drift {path}: expected {expected}, got {actual}")


def run(argv: Sequence[str], *, timeout: int = 600) -> None:
    completed = subprocess.run(list(argv), cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False, timeout=timeout)
    if completed.returncode != 0:
        detail = completed.stdout.decode(errors="replace")[-8000:]
        raise AuditError(f"command failed rc={completed.returncode}: {' '.join(argv)}\n{detail}")


def fetch_parity_artifacts(work: Path) -> dict[str, Path]:
    out = work / "parity-terminal"
    report = work / "parity-terminal-fetch.json"
    names = (
        "b3-real-adaptive-parity.json",
        "b3-teacher-aggregate.json",
        "b3-render-receipt.json",
        "scientific-summary.json",
    )
    argv = [sys.executable, "jobs/tools/fetch_result_files.py",
            "--prefix", PARITY_PREFIX, "--expected-state", "completed",
            "--out-dir", str(out), "--report", str(report)]
    for name in names:
        argv += ["--file", f"artefacts/{name}={name}"]
    run(argv)
    receipt = read_canonical(report)
    required = {
        "state": "verified",
        "result_state": "completed",
        "job_id": PARITY_JOB,
        "attempt_id": PARITY_ATTEMPT,
        "code_sha": PARITY_CODE,
        "prefix": PARITY_PREFIX,
    }
    for key, expected in required.items():
        if receipt.get(key) != expected:
            raise AuditError(f"1833 fetch receipt {key} mismatch")
    return {name: out / name for name in names}


def require_zero_side_effects(value: Mapping[str, Any], *, render: bool = False) -> None:
    if value.get("fits") != 0 or value.get("strength_games") != 0:
        raise AuditError("nonzero fit/strength side effect in parity evidence")
    if render:
        if value.get("promotion_authorized") is not False or value.get("bake_authorized") is not False:
            raise AuditError("render receipt authorizes promotion/bake")
    else:
        if value.get("promotions", 0) != 0 or value.get("bakes", 0) != 0:
            raise AuditError("nonzero promotion/bake side effect in parity evidence")


def authenticate_parity(paths: Mapping[str, Path]) -> dict[str, Any]:
    require_blob("jobs/tools/adaptive_sibling_b3_parity.py", PARITY_TOOL_BLOB)
    report = read_canonical(paths["b3-real-adaptive-parity.json"])
    aggregate = read_canonical(paths["b3-teacher-aggregate.json"])
    render = read_canonical(paths["b3-render-receipt.json"])
    summary = read_canonical(paths["scientific-summary.json"])

    if report.get("schema") != "jass.adaptive_sibling_b3_parity.v1" \
            or report.get("state") != "completed" or report.get("verdict") != PARITY_VERDICT:
        raise AuditError("1833 parity report terminal verdict mismatch")
    if report.get("parents") != 4000 or report.get("mismatches") != [] \
            or report.get("mismatch_count_capped") != 0:
        raise AuditError("1833 parity population/mismatch contract failed")
    if report.get("projection_policy") != POLICY:
        raise AuditError("1833 parity policy drift")
    if report.get("fresh_b3_generation_authorized") is not True:
        raise AuditError("1833 parity did not authorize prospective B3 preparation")
    if report.get("elapsed_fields_compared") is not False:
        raise AuditError("1833 parity unexpectedly compared wall-clock fields")
    require_zero_side_effects(report)

    if summary.get("schema") != "jass.adaptive_sibling_b3_parity_stage.v1" \
            or summary.get("state") != "completed" or summary.get("verdict") != PARITY_VERDICT:
        raise AuditError("1833 scientific summary terminal mismatch")
    if summary.get("b2_terminal_prerequisite") != "B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1" \
            or summary.get("b2_parents_replayed") != 4000 or summary.get("fresh_b3_parents") != 0:
        raise AuditError("1833 prerequisite/population contract mismatch")
    if summary.get("policy") != POLICY or summary.get("budgets_nodes") != BUDGETS:
        raise AuditError("1833 summary policy/budget drift")
    if summary.get("fresh_b3_generation_authorized") is not True:
        raise AuditError("1833 summary fresh preparation authorization missing")
    require_zero_side_effects(summary)

    if aggregate != summary.get("teacher"):
        raise AuditError("1833 teacher aggregate differs from scientific summary")
    searches = report.get("actual_searches")
    nodes = report.get("actual_nodes")
    if searches != summary.get("parity", {}).get("actual_searches") \
            or nodes != summary.get("parity", {}).get("actual_nodes"):
        raise AuditError("1833 parity counts differ between report and summary")
    if report.get("total_nodes") != summary.get("parity", {}).get("total_nodes"):
        raise AuditError("1833 parity total nodes differ between report and summary")
    if type(searches) is not dict or type(nodes) is not dict:
        raise AuditError("1833 horizon accounting missing")
    expected_searches = {"5": 37789, "50": 25854, "200": 21420}
    expected_nodes = {"5": 185536452, "50": 1271148094, "200": 4191356664}
    if searches != expected_searches or nodes != expected_nodes or report.get("total_nodes") != 5648041210:
        raise AuditError("1833 authenticated horizon counts/nodes differ from terminal evidence")
    if aggregate.get("engine_constructions") != sum(expected_searches.values()):
        raise AuditError("1833 Engine construction count differs from real search count")
    if (aggregate.get("cheap_searches"), aggregate.get("screen_searches"), aggregate.get("teacher_searches")) \
            != (expected_searches["5"], expected_searches["50"], expected_searches["200"]):
        raise AuditError("1833 teacher search counts differ from parity report")
    if (aggregate.get("cheap_nodes"), aggregate.get("screen_nodes"), aggregate.get("teacher_nodes")) \
            != (expected_nodes["5"], expected_nodes["50"], expected_nodes["200"]):
        raise AuditError("1833 teacher node counts differ from parity report")

    render_required = {
        "schema": "jass.adaptive_sibling_b3_teacher_source_adapter.v1",
        "policy": POLICY,
        "budgets_nodes": BUDGETS,
        "fresh_engine_each_search": True,
        "fresh_tt_each_search": True,
        "book_enabled": False,
        "threads_per_search": 1,
        "node_limit_mode": "exact",
        "q200_used_before_s50_seal": False,
        "search_decision_trace_affects_allocation": False,
    }
    for key, expected in render_required.items():
        if render.get(key) != expected:
            raise AuditError(f"1833 render receipt {key} mismatch")
    require_zero_side_effects(render, render=True)
    if render.get("rendered_source_sha256") != summary.get("rendered_source_sha256"):
        raise AuditError("1833 rendered source identity mismatch")

    return {
        "verdict": PARITY_VERDICT,
        "parents": 4000,
        "mismatch_count": 0,
        "per_parent_real_node_cost_parity_authenticated": True,
        "policy": POLICY,
        "budgets_nodes": BUDGETS,
        "actual_searches": searches,
        "actual_nodes": nodes,
        "total_nodes": report["total_nodes"],
        "engine_constructions": aggregate["engine_constructions"],
        "fresh_b3_generation_authorized_by_parity": True,
        "rendered_source_sha256": render["rendered_source_sha256"],
    }


def classify_zero_cost(b2_groups: Path, b2_receipts: Path,
                       parity_paths: Mapping[str, Path]) -> dict[str, Any]:
    rows, _header = parity.read_tsv(b2_groups)
    receipts = parity.read_jsonl(b2_receipts)
    by_parent: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_parent[int(row["parent_id"])].append(row)
    receipt_by_parent = {int(value["parent_id"]): value for value in receipts}
    if set(by_parent) != set(range(4000)) or set(receipt_by_parent) != set(range(4000)):
        raise AuditError("B2 parent population mismatch during zero-cost audit")

    zero_search = sorted(parent for parent, value in receipt_by_parent.items()
                         if value.get("shadow_nodes_total") == 0)
    all_exact: list[int] = []
    exact_win_mixed: list[int] = []
    for parent in zero_search:
        prows = by_parent[parent]
        exact_flags = [int(row["child_rule_terminal"]) == 1 or int(row["child_tb_exact"]) == 1
                       for row in prows]
        if all(exact_flags):
            all_exact.append(parent)
        else:
            reason = receipt_by_parent[parent].get("exact_shortcut_reason")
            if reason != "EXACT_WIN" or not any(exact_flags):
                raise AuditError(f"zero-search mixed parent {parent} is not an authenticated EXACT_WIN shortcut")
            exact_win_mixed.append(parent)

    parity_report = read_canonical(parity_paths["b3-real-adaptive-parity.json"])
    if parity_report.get("zero_cost_parent_ids") != zero_search:
        raise AuditError("1833 zero-search parent list differs from sealed B2 receipts")
    if zero_search != EXPECTED_ZERO_SEARCH:
        raise AuditError(f"unexpected B2 zero-search parents: {zero_search}")
    if all_exact != EXPECTED_ALL_EXACT_ZERO_COST:
        raise AuditError(f"all-exact zero-cost parent set changed: {all_exact}")
    if exact_win_mixed != EXPECTED_EXACT_WIN_ZERO_SEARCH:
        raise AuditError(f"mixed EXACT_WIN zero-search parent set changed: {exact_win_mixed}")
    return {
        "all_exact_zero_cost_parent_ids": all_exact,
        "all_exact_zero_cost_parent_count": len(all_exact),
        "zero_search_parent_ids": zero_search,
        "zero_search_parent_count": len(zero_search),
        "mixed_exact_win_zero_search_parent_ids": exact_win_mixed,
        "interpretation": "six all-exact zero-cost parents are unchanged; two additional zero-search parents are mixed EXACT_WIN shortcuts",
    }


def diagnose_1834(work: Path) -> dict[str, Any]:
    require_blob("jobs/tools/adaptive_sibling_b3_exclusion_prepare.py", EXCLUSION_BASE_BLOB)
    require_blob("jobs/tools/adaptive_sibling_b3_exclusion_prepare_v2.py", EXCLUSION_V2_BLOB)
    replay_work = work / "1834-replay-work"
    replay_artifacts = work / "1834-replay-artifacts"
    try:
        summary = exclusion_v2.run(replay_work, replay_artifacts)
    except Exception as exc:  # diagnostic boundary deliberately preserves exact type/message
        return {
            "source_job": "cpx62-1834-l3-decision-math-b3-fresh-exclusion-prep-v1",
            "source_code_sha": FAILED_1834_CODE,
            "reproduced": True,
            "outcome": "FAILED_WITH_EXACT_ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc)[:4000],
            "fresh_positions_generated": 0,
            "teacher_searches": 0,
        }
    return {
        "source_job": "cpx62-1834-l3-decision-math-b3-fresh-exclusion-prep-v1",
        "source_code_sha": FAILED_1834_CODE,
        "reproduced": False,
        "outcome": "EXACT_1834_IMPLEMENTATION_PASSED_ON_REPLAY",
        "replay_verdict": summary.get("verdict"),
        "combined_unique": summary.get("combined_unique"),
        "exclusion_union_sha256": summary.get("exclusion_union_sha256"),
        "exclusion_manifest_sha256": summary.get("exclusion_manifest_sha256"),
        "fresh_positions_generated": 0,
        "teacher_searches": 0,
    }


def execute(work: Path, artifacts: Path) -> dict[str, Any]:
    if work.exists() or work.is_symlink():
        raise AuditError("work-dir must be absent")
    work.mkdir(parents=True)
    if artifacts.is_symlink():
        raise AuditError("artifact-dir cannot be a symlink")
    artifacts.mkdir(parents=True, exist_ok=True)

    parity_paths = fetch_parity_artifacts(work)
    parity_auth = authenticate_parity(parity_paths)
    _parents, b2_groups, b2_receipts = parity_stage.fetch_b2_inputs(work / "b2-audit")
    zero_cost = classify_zero_cost(b2_groups, b2_receipts, parity_paths)
    diagnostic = diagnose_1834(work)

    report = {
        "schema": SCHEMA,
        "state": "completed",
        "verdict": VERDICT,
        "parity_authentication": parity_auth,
        "zero_cost_authentication": zero_cost,
        "exclusion_1834_diagnostic": diagnostic,
        "fresh_b3_generation_authorized": False,
        "fresh_b3_parents": 0,
        "new_teacher_searches": 0,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        "next_stage": "B3_1834_TECHNICAL_REPAIR_OR_PREREG_FREEZE_AFTER_DIAGNOSIS",
    }
    write_new(artifacts / "b3-post-parity-audit.json", report)
    write_new(artifacts / "scientific-summary.json", report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = execute(args.work_dir, args.artifact_dir)
    except Exception as exc:
        print(f"adaptive_sibling_b3_post_parity_audit: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"state": result["state"], "verdict": result["verdict"],
                      "next_stage": result["next_stage"]}, sort_keys=True,
                     separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
