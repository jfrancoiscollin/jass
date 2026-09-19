#!/usr/bin/env python3
"""Independent-evaluator, historical-data diagnostic; never a G0 retry.

Join every frozen 2063 decision to previously published Scan sibling scores.
No engine process, model read, training, resampling, tuning or promotion path.
"""
from __future__ import annotations

from collections import Counter
import csv
from decimal import Decimal
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "jass.cls_hier_scan_reference_diagnostic.v1"
TERMINAL = "CLS_HIER_SCAN_REFERENCE_DIAGNOSTIC_COMPLETE_V1"
PHASES = ["authenticate-frozen-decisions", "seal-scan-blind-join", "read-historical-scan", "describe-all-roots"]
BUDGETS = (1_000_000, 2_000_000)
PRIMARY = 2_000_000
NROOTS = 512
NPHASE = 128
CANDIDATE = "95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628"
PARENT = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
COHORT = "478abc0fe2fe1fcd8c2157f532ba796745c645ff4f03dac8fd21c2ff851f137e"
SCAN_COMMIT = "7aae17e7b7bfc47744601afb1ee7655e18983ce5"
SCAN_BINARY = "96b80c6aec1592f856a78ad7617ca6224b26be926800a6e37ede3b26f4e9cfa1"
G0 = ("cpx62-2063-l3-cls-g0-hier-runtime-rehearsal-v1", "20260919T155826Z-a6f9fa6f", "a6f9fa6fbdc66f8d89dd7a5e8c196422cf98a28a")
SELECTION = ("home-1651-l3-scan-ceiling-selection-v1", "20260829T133348Z-28e12fba", "28e12fba0ead14def244ffc442b15937f65edc0e")
SCAN = ("home-1658-l3-scan-ceiling-scan-deep-v1", "20260829T152036Z-46623b26", "46623b26b8d684f5685475d81fbb36f215ba4ac2")
G0_RECEIPT = "a5b9a83a6a7932920ca23cf1cd7d15f67855c12835ddecb18c4f67bc9b0d6e59"
G0_FILES = ("probe.tsv", "probe-report.json", "g0-root-ids.txt", "g0-deep512.tsv", "scientific-summary.json", "launch-receipt.json")
SELECTION_FILES = ("siblings.tsv", "sibling-manifest.json", "deep512-row-ids.txt", "selection-report.json", "JASS_CONTROL_SUMMARY.json")
SCAN_FILES = tuple(f"scores/scan-deep-shard-{s:02d}-{suffix}" for s in range(16) for suffix in ("scores.tsv.gz", "report.json"))
FILE_LIMIT = 32 * 1024 * 1024
TOTAL_LIMIT = 64 * 1024 * 1024
QUARANTINE = ("training_allowed", "tuning_allowed", "calibration_allowed", "model_selection_allowed", "runtime_scale_selection_allowed")


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    need(isinstance(value, dict), "JSON object required")
    return value


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as out:
        out.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def table(path: Path) -> list[dict]:
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as stream:
            raw = stream.read(FILE_LIMIT + 1)
        need(len(raw) <= FILE_LIMIT, "expanded table exceeds bound")
        text = raw.decode("utf-8")
    else:
        need(path.stat().st_size <= FILE_LIMIT, "table exceeds bound")
        text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter="\t")
    need(reader.fieldnames is not None and len(set(reader.fieldnames)) == len(reader.fieldnames), "table headers")
    rows = list(reader)
    need(bool(rows) and all(None not in r and None not in r.values() for r in rows), "empty/malformed table")
    return rows


def fetch_source(desc: tuple[str, str, str], names: tuple[str, ...], out: Path) -> dict:
    from jobs.tools import fetch_result_files as fetch
    prefix = f"r2:jass-data/runs/{desc[0]}/{desc[1]}"
    rclone = os.environ.get("RCLONE_BIN", "rclone")
    inv = fetch.inspect_result_inventory(rclone=rclone, prefix=prefix)
    need(tuple(inv.get(k) for k in ("job_id", "attempt_id", "code_sha", "result_state", "exit_code")) == (*desc, "completed", 0), "source identity/state drift")
    meta = {v["path"]: v for v in inv["files"]}
    sizes = [int(meta[f"artefacts/{name}"]["size_bytes"]) for name in names]
    need(all(0 < s <= FILE_LIMIT for s in sizes) and sum(sizes) <= TOTAL_LIMIT, "source read bounds")
    got = fetch.fetch_files(rclone=rclone, prefix=prefix, selections=[(f"artefacts/{n}", n) for n in names], out_dir=out)
    need(tuple(got.get(k) for k in ("job_id", "attempt_id", "code_sha", "result_state", "exit_code")) == (*desc, "completed", 0), "fetch identity drift")
    return got


def validate_g0(summary: dict, report: dict) -> None:
    expected = {"state": "completed", "terminal": "CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1", "scientific_verdict": "FAIL", "candidate_arm": "HIER", "candidate_sha256": CANDIDATE, "direct_parent_sha256": PARENT, "fixed_curriculum_anchor_sha256": PARENT, "cohort_identity_sha256": COHORT, "roots": NROOTS, "budget_nodes": 200000, "trace_parity_mismatches": 0, "strength_games": 0, "alpha_spent": 0}
    for key, value in expected.items():
        need(summary.get(key) == value, f"frozen G0 drift:{key}")
    for key, value in {"roots": NROOTS, "budget_nodes": 200000, "threads": 1, "tt_mb": 16, "trace_parity_mismatches": 0, "nodes_to_depth_surrogate_used": False}.items():
        need(report.get(key) == value, f"frozen probe drift:{key}")
    hard = summary["gate"]["hard_nodes_to_depth_failure"]
    need(hard["count"] == 30 and hard["parent_missing_roots"] == [], "frozen failure inventory")
    need([str(v) for v in hard["candidate_missing_roots"]] == [str(v) for v in report["candidate_nodes_to_depth_missing_roots"]], "failure roots differ")


def validate_selection(folder: Path) -> None:
    summary, selected, siblings = (load(folder / n) for n in ("JASS_CONTROL_SUMMARY.json", "selection-report.json", "sibling-manifest.json"))
    need(summary.get("verdict") == "SCAN_COHORT_FROZEN_BENCHMARK_ONLY" and summary.get("passed") is True, "selection not frozen")
    need(all(summary.get(k) is False for k in QUARANTINE), "benchmark quarantine")
    need(selected.get("cohort_identity_sha256") == summary.get("cohort_identity_sha256") == COHORT, "cohort drift")
    need(selected.get("deep512") == 512 and selected.get("deep512_by_phase") == {f"P{i}": 128 for i in range(4)}, "deep512 quota")
    for field, name in (("selection_report_sha256", "selection-report.json"), ("sibling_manifest_sha256", "sibling-manifest.json")):
        need(summary.get(field) == sha(folder / name), "selection hash chain")
    for field, name in (("groups_sha256", "siblings.tsv"), ("deep_row_ids_sha256", "deep512-row-ids.txt")):
        need(siblings.get(field) == sha(folder / name), "sibling hash chain")


def raw_move(row: dict) -> str:
    # G0's bestmove_canonical serializes RAW board coordinates plus captured set;
    # do not substitute symmetry-canonical_from/to from sibling metadata.
    f, t, cap = int(row["from"]), int(row["to"]), int(row["captured_hex"], 16)
    need(1 <= f <= 50 and 1 <= t <= 50 and 0 <= cap < 1 << 50, "move geometry")
    need(cap.bit_count() == int(row["num_captures"]), "capture-count drift")
    if not cap:
        return f"{f}-{t}"
    return f"{f}x{t}|caps=" + ",".join(str(bit + 1) for bit in range(50) if cap & (1 << bit))


def seal_join(probe: list[dict], phases: list[dict], ids: list[str], groups: list[dict], deep_ids: list[int], report: dict, *, nphase: int = NPHASE) -> tuple[list[dict], dict[int, dict]]:
    need(len(ids) == nphase * 4 and len(set(ids)) == len(ids), "root cardinality")
    need([r["parent_id"] for r in phases] == ids, "phase order")
    need(Counter(r["phase"] for r in phases) == {f"P{i}": nphase for i in range(4)}, "phase quota")
    need([(r["root_id"], r["arm"]) for r in probe] == [(rid, a) for rid in ids for a in ("parent", "candidate")], "probe order/duplicates")
    need([int(g["row_index"]) for g in groups] == list(range(len(groups))), "sibling row order")
    need(len({g["sibling_identity"] for g in groups}) == len(groups), "sibling identity duplicates")
    wanted = set(ids)
    selected = {int(g["row_index"]): g for g in groups if g["parent_id"] in wanted}
    need(len(deep_ids) == len(set(deep_ids)) and set(deep_ids) == set(selected), "deep sibling coverage")
    by_parent = {rid: [] for rid in ids}
    for g in selected.values():
        by_parent[g["parent_id"]].append(g)
    joined = []
    missing = []
    for ordinal, rid in enumerate(ids):
        p, c = probe[ordinal * 2:ordinal * 2 + 2]
        sibling_rows = by_parent[rid]
        need(2 <= len(sibling_rows) <= 16, "legal moves support")
        for g in sibling_rows:
            need(int(g["parent_legal_moves"]) == len(sibling_rows) and g["parent_phase"] == phases[ordinal]["phase"] and g["parent_canonical"] == phases[ordinal]["canonical_fingerprint"], "parent/cohort identity")
        moves = {raw_move(g): int(g["row_index"]) for g in sibling_rows}
        need(len(moves) == len(sibling_rows), "ambiguous raw move mapping")
        pm, cm = p["bestmove_canonical"], c["bestmove_canonical"]
        need(pm in moves and cm in moves, "chosen move not in frozen legal catalogue")
        pd, cd, target = int(p["completed_nominal_depth"]), int(c["completed_nominal_depth"]), int(p["target_depth"])
        need(target == int(c["target_depth"]) == max(1, pd - 1), "target depth drift")
        miss = c["nodes_to_target"] == ""
        if miss:
            missing.append(rid)
        joined.append({"root_id": rid, "phase": phases[ordinal]["phase"], "canonical_fingerprint": phases[ordinal]["canonical_fingerprint"], "parent_move": pm, "hier_move": cm, "parent_row": moves[pm], "hier_row": moves[cm], "disagreement": pm != cm, "missing_g0_receipt": miss, "depth_delta": cd - pd, "sibling_rows": sorted(moves.values())})
    need(missing == [str(i) for i in report["candidate_nodes_to_depth_missing_roots"]], "missing probe inventory")
    return joined, selected


def parse_scores(shard_rows: list[list[dict]], shard_reports: list[dict], groups: dict[int, dict], group_sha: str, *, nshards: int = 16) -> dict[tuple[int, int], int]:
    need(len(shard_rows) == len(shard_reports) == nshards, "shard count")
    values = {}
    for shard, (rows, report) in enumerate(zip(shard_rows, shard_reports)):
        expect_rows = {i for i in groups if i % nshards == shard}
        expected = {"schema": "jass.scan_ceiling_scan_ladder.v1", "benchmark_only": True, "source_commit": SCAN_COMMIT, "scan_binary_sha256": SCAN_BINARY, "groups_sha256": group_sha, "shard": shard, "nshards": nshards, "budgets_nodes": list(BUDGETS), "processed_rows": len(expect_rows), "output_rows": 2 * len(expect_rows), "selected_rows": len(groups), "book_enabled": False, "threads_per_search": 1, "bb_size": 0, "mode": "go analyze", "fresh_state": "new-game before every sibling/budget", "scan_source_algorithms_modified": False, "requested_nodes_exactly_configured": True}
        for key, value in expected.items():
            need(report.get(key) == value, f"Scan report drift:{key}")
        need(len(rows) == 2 * len(expect_rows), "shard output count")
        terminal_count = 0
        for row in rows:
            index, budget = int(row["row_index"]), int(row["budget_nodes"])
            key = (index, budget)
            need(index in expect_rows and budget in BUDGETS and key not in values, "duplicate/out-of-scope Scan score")
            group = groups[index]
            need(row["sibling_identity"] == group["sibling_identity"], "Scan sibling identity")
            val = Decimal(row["child_score_token"]) * 100
            need(val.is_finite() and val == val.to_integral_value(), "Scan score precision/nonfinite")
            score = int(row["parent_score_centi"])
            need(score == -int(val), "Scan POV sign")
            terminal = int(row["terminal_exact"])
            need(terminal in (0, 1) and terminal == int(group["child_rule_terminal"]), "Scan terminal identity")
            observed = int(row["last_info_nodes"])
            need(int(row["requested_nodes"]) == budget, "Scan requested budget")
            need(int(row["snapshot_upper_bound"]) == (0 if terminal else budget), "Scan snapshot bound")
            need(int(row["snapshot_above_requested"]) == 0, "Scan snapshot overshoot")
            need((observed == 0 and score == 10000 and int(group["child_legal_moves"]) == 0) if terminal else (0 < observed <= budget), "Scan node/terminal receipt")
            terminal_count += terminal
            values[key] = score
        need(report.get("terminal_exact_output_rows") == terminal_count and report.get("searches") == len(rows) - terminal_count, "Scan historical work accounting")
    need(set(values) == {(i, b) for i in groups for b in BUDGETS}, "incomplete Scan ladder")
    return values


def stats(values: list[int]) -> dict:
    return {"n": len(values), "mean": statistics.fmean(values), "median": statistics.median(values), "min": min(values), "max": max(values)} if values else {"n": 0, "not_estimable": True}


def summarize(rows: list[dict], budget: int) -> dict:
    prefix = f"b{budget}_"
    delta = [r[prefix + "hier_minus_parent"] for r in rows]
    return {"n": len(rows), "hier_preferred": sum(v > 0 for v in delta), "parent_preferred": sum(v < 0 for v in delta), "score_ties": sum(v == 0 for v in delta), "same_move": sum(not r["disagreement"] for r in rows), "different_move_score_ties": sum(r["disagreement"] and r[prefix + "hier_minus_parent"] == 0 for r in rows), "hier_top_set_hits": sum(r[prefix + "hier_regret"] == 0 for r in rows), "parent_top_set_hits": sum(r[prefix + "parent_regret"] == 0 for r in rows), "hier_minus_parent_score_centi": stats(delta), "parent_regret_centi": stats([r[prefix + "parent_regret"] for r in rows]), "hier_regret_centi": stats([r[prefix + "hier_regret"] for r in rows])}


def evaluate(joined: list[dict], values: dict[tuple[int, int], int]) -> tuple[dict, list[dict]]:
    output = []
    signs = lambda x: (x > 0) - (x < 0)
    for item in joined:
        row = {k: v for k, v in item.items() if k != "sibling_rows"}
        top_sets = []
        for budget in BUDGETS:
            maximum = max(values[(i, budget)] for i in item["sibling_rows"])
            p, h = values[(item["parent_row"], budget)], values[(item["hier_row"], budget)]
            prefix = f"b{budget}_"
            row.update({prefix + "parent_score": p, prefix + "hier_score": h, prefix + "best_sibling_score": maximum, prefix + "hier_minus_parent": h - p, prefix + "parent_regret": maximum - p, prefix + "hier_regret": maximum - h})
            top_sets.append({i for i in item["sibling_rows"] if values[(i, budget)] == maximum})
        row["preference_sign_stable"] = signs(row["b1000000_hier_minus_parent"]) == signs(row["b2000000_hier_minus_parent"])
        row["scan_top_set_stable"] = top_sets[0] == top_sets[1]
        output.append(row)
    dis = [r for r in output if r["disagreement"]]
    subsets = {"all_roots": output, "disagreements": dis, "g0_missing": [r for r in output if r["missing_g0_receipt"]], "g0_observed": [r for r in output if not r["missing_g0_receipt"]]}
    result = {"primary_budget_nodes_per_child": PRIMARY, "budgets": {str(b): {name: summarize(rows, b) for name, rows in subsets.items()} for b in BUDGETS}, "by_phase_primary": {f"P{i}": summarize([r for r in output if r["phase"] == f"P{i}"], PRIMARY) for i in range(4)}, "disagreement_preference_stable": sum(r["preference_sign_stable"] for r in dis), "disagreement_preference_unstable": sum(not r["preference_sign_stable"] for r in dis), "all_root_scan_top_set_stable": sum(r["scan_top_set_stable"] for r in output), "preference_transition_counts": dict(sorted(Counter(f"{signs(r['b1000000_hier_minus_parent'])}->{signs(r['b2000000_hier_minus_parent'])}" for r in dis).items())), "score_units": "native Scan centi; not Elo, win probability, or Jass score units", "ties": "exact published integer precision", "reference_is_ground_truth": False, "independence": "external evaluator; same already-consumed cohort, not a fresh confirmation sample"}
    return result, output


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    work = Path(os.environ["JASS_RESULT_DIR"]) / "work" / "scan-reference"
    work.mkdir(parents=True, exist_ok=False)
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, os.environ["LAUNCH_MODE"])
    try:
        need(shutil.disk_usage(work).free >= 512 * 1024 * 1024, "scratch free space")
        evidence.begin(PHASES[0])
        g0 = work / "g0"
        auth_g0 = fetch_source(G0, G0_FILES, g0)
        need(sha(g0 / "launch-receipt.json") == G0_RECEIPT, "G0 launch receipt")
        summary, report = load(g0 / "scientific-summary.json"), load(g0 / "probe-report.json")
        validate_g0(summary, report)
        evidence.complete()
        evidence.begin(PHASES[1])
        sel = work / "selection"
        auth_sel = fetch_source(SELECTION, SELECTION_FILES, sel)
        validate_selection(sel)
        joined, selected = seal_join(table(g0 / "probe.tsv"), table(g0 / "g0-deep512.tsv"), (g0 / "g0-root-ids.txt").read_text().splitlines(), table(sel / "siblings.tsv"), [int(i) for i in (sel / "deep512-row-ids.txt").read_text().splitlines()], report)
        need(len(joined) == 512 and sum(r["disagreement"] for r in joined) == 168 and sum(r["missing_g0_receipt"] for r in joined) == 30, "frozen decision counts")
        write_json(art / "scan-blind-join.json", {"schema": SCHEMA, "cohort_sha256": COHORT, "primary_budget": PRIMARY, "secondary_budget": BUDGETS[0], "rows": joined, "scan_scores_read_before_seal": 0})
        evidence.complete()
        evidence.begin(PHASES[2])
        scan_dir = work / "scan"
        auth_scan = fetch_source(SCAN, SCAN_FILES, scan_dir)
        reports, shards = [], []
        for s in range(16):
            path = scan_dir / f"scores/scan-deep-shard-{s:02d}-scores.tsv.gz"
            reports.append(load(scan_dir / f"scores/scan-deep-shard-{s:02d}-report.json"))
            shards.append(table(path))
        values = parse_scores(shards, reports, selected, sha(sel / "siblings.tsv"))
        evidence.complete()
        evidence.begin(PHASES[3])
        result, rows = evaluate(joined, values)
        write_json(art / "scan-reference-diagnostic.json", result)
        with (art / "all-512-scan-reference.tsv").open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
            writer.writeheader(); writer.writerows(rows)
        write_json(art / "source-authentication.json", {"g0": auth_g0, "selection": auth_sel, "scan": auth_scan, "scan_blind_join_sha256": sha(art / "scan-blind-join.json")})
        boundary = {"classification": "EXPLORATORY_CONSUMED_DATA", "scientific_verdict": None, "frozen_g0_verdict": "FAIL", "gate_reevaluated": False, "new_scan_searches": 0, "new_jass_searches": 0, "fits": 0, "strength_games": 0, "selfplay_games": 0, "alpha_spent": 0, "promotions": 0, "bakes": 0, "promotion_authorized": False, "bake_authorized": False, "confirmation_target_reads": 0, "training_target_reads": 0, "historical_scan_score_rows_read": len(values), "historical_sibling_metadata_rows_read": len(table(sel / "siblings.tsv")), "next_stage": "INTERPRET_DIAGNOSTIC_NO_AUTOMATIC_REPLAY", **{k: False for k in QUARANTINE}}
        atomic_json(art / "scientific-summary.json", {"schema": SCHEMA, "state": "completed", "terminal": TERMINAL, "candidate_sha256": CANDIDATE, "parent_sha256": PARENT, "source_scan_job": SCAN[0], **boundary, **result})
        (art / "RESULTS.md").write_text("# HIER / CURRICULUM versus historical independent Scan references\n\nExploratory consumed-data diagnostic. G0 FAIL and CURRICULUM unchanged.\nScan is not ground truth. Budgets are per child, not per parent.\nNo new engine search, fit, match or promotion.\n\n" + json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        names = ("scan-blind-join.json", "scan-reference-diagnostic.json", "all-512-scan-reference.tsv", "source-authentication.json", "RESULTS.md")
        write_json(art / "manifest.json", {"schema": SCHEMA, "terminal": TERMINAL, "evidence": {n: {"sha256": sha(art / n), "size_bytes": (art / n).stat().st_size} for n in names}, **boundary})
        evidence.complete(); evidence.finish()
        return 0
    except BaseException as exc:
        evidence.fail(exc)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
