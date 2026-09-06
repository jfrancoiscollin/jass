#!/usr/bin/env python3
"""Authenticate B3 fresh corpus and publish contemporaneous transfer diagnostics.

This readout joins the real adaptive corpus (1841), the identity-only audit subset
(1842), and the physically separate full-ladder reference audit (1843). It is
measurement-only: reference values can be used to compute diagnostics but can
never be copied into or used to relabel the adaptive corpus.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import adaptive_sibling_b2_readout as b2_readout  # noqa: E402
from jobs.tools import adaptive_sibling_b3_fresh_audit_subset as audit_subset  # noqa: E402
from jobs.tools import adaptive_sibling_b3_parity_stage as parity_stage  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b3_fresh_transfer_readout.v1"
PUBLICATION_SCHEMA = "jass.adaptive_sibling_b3_fresh_corpus_publication.v1"
VERDICT = "B3_FRESH_CORPUS_AUTHENTICATED_TRANSFER_DIAGNOSTICS_COMPLETE_V1"
ADAPTIVE_VERDICT = "B3_FRESH_ADAPTIVE_TEACHER_COMPLETE_V1"
AUDIT_VERDICT = "B3_FRESH_AUDIT_SUBSET_SEALED_V1"
FULL_VERDICT = "B3_FRESH_FULL_LADDER_AUDIT_COMPLETE_V1"
ADAPTIVE_FIELDS = list(b2_readout.GROUP_FIELDS) + [
    "searched5", "searched50", "searched200", "survived5", "survived50",
    "selected", "exact_shortcut_reason", "sole_survivor_reason", "uncertified",
]
STRUCTURAL_FIELDS = [
    "parent_fingerprint", "parent_stm", "parent_pieces", "from", "to",
    "num_captures", "promotes", "moving_king", "captured_kings",
    "material_count_delta_parent", "child_pieces", "child_legal_moves",
    "child_forced_capture", "child_rule_terminal", "child_tb_exact",
    "exact_parent_utility", "t_baseline_parent",
]
HORIZONS = {
    "5": ("searched5", "q5k_parent", "nodes5k", "completed_depth5k",
          "effective_depth5k", "aborted5k", "stop5k", "pv5k_enters_egdb"),
    "50": ("searched50", "q50_parent", "nodes50k", "completed_depth50k",
           "effective_depth50k", "aborted50k", "stop50k", "pv50k_enters_egdb"),
    "200": ("searched200", "q200_parent", "nodes200k", "completed_depth200k",
            "effective_depth200k", "aborted200k", "stop200k", "pv200k_enters_egdb"),
}


class ReadoutError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return parity_stage.canonical(value)


def write_new(path: Path, raw: bytes) -> None:
    parity_stage.write_new(path, raw)


def _int(text: str, label: str, lo: int = -(1 << 63), hi: int = (1 << 63) - 1) -> int:
    if not isinstance(text, str) or not text or not text.isascii():
        raise ReadoutError(f"{label} is not canonical integer text")
    if text.startswith("-"):
        digits = text[1:]
        if not digits or not digits.isdigit() or digits.startswith("0"):
            raise ReadoutError(f"{label} is not canonical integer text")
    elif not text.isdigit() or (len(text) > 1 and text.startswith("0")):
        raise ReadoutError(f"{label} is not canonical integer text")
    value = int(text)
    if not lo <= value <= hi:
        raise ReadoutError(f"{label} outside range")
    return value


def _flag(row: Mapping[str, str], key: str) -> bool:
    value = row.get(key)
    if value not in {"0", "1"}:
        raise ReadoutError(f"{key} is not 0/1")
    return value == "1"


def _load_tsv(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise ReadoutError(f"non-canonical LF TSV: {path.name}")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), delimiter="\t")
    except UnicodeError as exc:
        raise ReadoutError(f"non-UTF8 TSV: {path.name}") from exc
    if reader.fieldnames != list(fields):
        raise ReadoutError(f"TSV field drift: {path.name}")
    rows = list(reader)
    if any(set(row) != set(fields) for row in rows):
        raise ReadoutError(f"TSV row field drift: {path.name}")
    return rows


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReadoutError(f"invalid JSON {path.name}") from exc
    if not isinstance(value, dict):
        raise ReadoutError(f"JSON object required: {path.name}")
    return value


def _fetch(args: argparse.Namespace, work: Path) -> dict[str, Path]:
    roots = {"adaptive": work / "adaptive", "subset": work / "subset", "full": work / "full"}
    parity_stage.fetch_completed(
        args.adaptive_prefix, job=args.adaptive_job, attempt=args.adaptive_attempt,
        expected_code=args.adaptive_code_sha,
        mappings=[
            ("artefacts/b3-fresh-adaptive-groups.tsv", "adaptive-groups.tsv"),
            ("artefacts/scientific-summary.json", "adaptive-summary.json"),
        ], out_dir=roots["adaptive"], report=work / "adaptive-fetch.json")
    parity_stage.fetch_completed(
        args.subset_prefix, job=args.subset_job, attempt=args.subset_attempt,
        expected_code=args.subset_code_sha,
        mappings=[
            ("artefacts/b3-fresh-audit-subset-seal.json", "subset-seal.json"),
            ("artefacts/b3-fresh-audit-parents.tsv", "subset-parents.tsv"),
            ("artefacts/b3-fresh-audit-source-parent-ids.txt", "source-parent-ids.txt"),
        ], out_dir=roots["subset"], report=work / "subset-fetch.json")
    parity_stage.fetch_completed(
        args.full_prefix, job=args.full_job, attempt=args.full_attempt,
        expected_code=args.full_code_sha,
        mappings=[
            ("artefacts/b3-fresh-full-ladder-audit-groups.tsv", "full-groups.tsv"),
            ("artefacts/scientific-summary.json", "full-summary.json"),
        ], out_dir=roots["full"], report=work / "full-fetch.json")
    return {
        "adaptive_groups": roots["adaptive"] / "adaptive-groups.tsv",
        "adaptive_summary": roots["adaptive"] / "adaptive-summary.json",
        "subset_seal": roots["subset"] / "subset-seal.json",
        "subset_parents": roots["subset"] / "subset-parents.tsv",
        "source_ids": roots["subset"] / "source-parent-ids.txt",
        "full_groups": roots["full"] / "full-groups.tsv",
        "full_summary": roots["full"] / "full-summary.json",
    }


def _verify_summaries(paths: Mapping[str, Path]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    adaptive = _load_json(paths["adaptive_summary"])
    subset = _load_json(paths["subset_seal"])
    full = _load_json(paths["full_summary"])
    if adaptive.get("state") != "completed" or adaptive.get("verdict") != ADAPTIVE_VERDICT:
        raise ReadoutError("adaptive terminal verdict mismatch")
    if adaptive.get("fresh_b3_parents") != 4000 or adaptive.get("reference_audit_reads") != 0 \
            or adaptive.get("full_ladder_backfill") is not False:
        raise ReadoutError("adaptive corpus barrier/population mismatch")
    if adaptive.get("policy") != {"M5": 100, "M50": 60, "minimum_survivors": 2} \
            or adaptive.get("budgets_nodes") != [5000, 50000, 200000]:
        raise ReadoutError("adaptive policy/budget drift")
    if subset.get("state") != "completed" or subset.get("verdict") != AUDIT_VERDICT:
        raise ReadoutError("audit subset terminal verdict mismatch")
    if subset.get("audit") != {
        "seed": 2026110817, "parents": 1000, "per_cell": 125,
        "selection": "sha256(seed_decimal:canonical_fingerprint), lowest per cell",
        "tie_break": ["canonical_fingerprint_ascii", "source_parent_id_uint"],
        "target_blind": True,
    }:
        raise ReadoutError("audit subset preregistered contract mismatch")
    if any(subset.get(key) != 0 for key in (
        "teacher_score_reads", "teacher_label_reads", "reference_audit_reads",
        "fits", "strength_games", "promotions", "bakes")):
        raise ReadoutError("audit subset forbidden read/side effect")
    if full.get("state") != "completed" or full.get("verdict") != FULL_VERDICT:
        raise ReadoutError("full-ladder terminal verdict mismatch")
    if full.get("audit_parents") != 1000 or full.get("audit_seed") != 2026110817 \
            or full.get("full_ladder_executed") is not True \
            or full.get("reference_only") is not True \
            or full.get("full_ladder_backfill_authorized") is not False \
            or full.get("adaptive_corpus_reads") != 0 or full.get("adaptive_corpus_writes") != 0:
        raise ReadoutError("full-ladder isolation/population mismatch")
    return adaptive, subset, full


def _blocks(rows: Sequence[dict[str, str]], parent_limit: int) -> dict[int, list[dict[str, str]]]:
    result: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        parent = _int(row["parent_id"], "parent_id", 0, parent_limit - 1)
        result[parent].append(row)
    if set(result) != set(range(parent_limit)):
        raise ReadoutError("parent population is not exhaustive")
    for parent, block in result.items():
        indices = [_int(row["row_index"], "row_index", 0) for row in block]
        if indices != sorted(indices) or len(set(indices)) != len(indices):
            raise ReadoutError(f"row order/uniqueness invalid for parent {parent}")
    return result


def _exact(row: Mapping[str, str]) -> tuple[bool, int | None]:
    rule = _flag(row, "child_rule_terminal")
    tb = _flag(row, "child_tb_exact")
    if rule and tb:
        raise ReadoutError("rule/TB exact contradiction")
    utility = _int(row["exact_parent_utility"], "exact_parent_utility", -1, 2)
    if rule and utility != 1:
        raise ReadoutError("rule-terminal utility contradiction")
    if tb and utility not in {-1, 0, 1}:
        raise ReadoutError("TB utility contradiction")
    if not rule and not tb and utility != 2:
        raise ReadoutError("nonexact utility sentinel contradiction")
    return rule or tb, utility if (rule or tb) else None


def _reference_index(full: Sequence[dict[str, str]]) -> int:
    exact = [_exact(row) for row in full]
    wins = [index for index, (is_exact, utility) in enumerate(exact) if is_exact and utility == 1]
    if wins:
        return wins[0]
    nonexact = [index for index, (is_exact, _utility) in enumerate(exact) if not is_exact]
    if nonexact:
        return min(nonexact, key=lambda index: (-_int(full[index]["q200_parent"], "q200", -30000, 30000), index))
    draws = [index for index, (_is_exact, utility) in enumerate(exact) if utility == 0]
    return (draws or list(range(len(full))))[0]


def _value_equivalent(reference: Mapping[str, str], selected: Mapping[str, str]) -> bool:
    rexact, rutil = _exact(reference)
    sexact, sutil = _exact(selected)
    if rexact and sexact:
        return rutil == sutil
    if not rexact and not sexact:
        return _int(reference["q200_parent"], "ref q200", -30000, 30000) == \
               _int(selected["q200_parent"], "selected q200", -30000, 30000)
    return False


def _validate_observation_match(adaptive: Mapping[str, str], full: Mapping[str, str]) -> None:
    for horizon, fields in HORIZONS.items():
        searched_key, score_key, nodes_key, completed_key, effective_key, aborted_key, stop_key, pv_key = fields
        if _flag(adaptive, searched_key):
            for key in (score_key, nodes_key, completed_key, effective_key, aborted_key, stop_key, pv_key):
                if adaptive[key] != full[key]:
                    raise ReadoutError(f"executed q{horizon} observation differs from contemporaneous full ladder")
        else:
            if _int(adaptive[nodes_key], nodes_key, 0) != 0:
                raise ReadoutError(f"unsearched q{horizon} carries nonzero nodes")


def _ratio(num: int, den: int) -> float:
    return 0.0 if den == 0 else num / den


def analyze(paths: Mapping[str, Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    adaptive_summary, subset_seal, full_summary = _verify_summaries(paths)
    adaptive_rows = _load_tsv(paths["adaptive_groups"], ADAPTIVE_FIELDS)
    full_rows = _load_tsv(paths["full_groups"], b2_readout.GROUP_FIELDS)
    subset_rows = _load_tsv(paths["subset_parents"], audit_subset.TSV_FIELDS)
    if len(adaptive_rows) != 38053 or len(full_rows) != 9409 or len(subset_rows) != 1000:
        raise ReadoutError("terminal row counts differ from sealed evidence")
    adaptive_blocks = _blocks(adaptive_rows, 4000)
    full_blocks = _blocks(full_rows, 1000)
    raw_ids = paths["source_ids"].read_text(encoding="ascii")
    if "\r" in raw_ids or not raw_ids.endswith("\n"):
        raise ReadoutError("source-parent id mapping is not canonical LF")
    source_ids = [_int(item, "source_parent_id", 0, 3999) for item in raw_ids.splitlines()]
    if len(source_ids) != 1000 or len(set(source_ids)) != 1000:
        raise ReadoutError("audit source-parent mapping cardinality/uniqueness mismatch")

    totals = defaultdict(int)
    per_cell: dict[str, defaultdict[str, int]] = {
        cell: defaultdict(int) for cell in audit_subset.selector.CELL_ORDER
    }
    numeric_deltas: list[int] = []
    selected_mismatches: list[dict[str, Any]] = []

    for audit_id, meta in enumerate(subset_rows):
        if _int(meta["audit_parent_id"], "audit_parent_id", 0, 999) != audit_id:
            raise ReadoutError("audit TSV parent ids are not row-ordered")
        source_id = _int(meta["source_parent_id"], "source_parent_id", 0, 3999)
        if source_id != source_ids[audit_id]:
            raise ReadoutError("audit TSV/source-parent-id mapping mismatch")
        cell = meta["cell"]
        if cell not in per_cell or cell != f"{meta['phase']}_stm{meta['parent_stm']}":
            raise ReadoutError("audit cell metadata mismatch")
        adaptive = adaptive_blocks[source_id]
        full = full_blocks[audit_id]
        legal = _int(meta["legal_moves"], "legal_moves", 2, 16)
        if len(adaptive) != legal or len(full) != legal or len(adaptive) != len(full):
            raise ReadoutError("action-set cardinality mismatch")
        selected = [index for index, row in enumerate(adaptive) if _flag(row, "selected")]
        if len(selected) != 1:
            raise ReadoutError("adaptive parent must have exactly one selected action")
        selected_index = selected[0]
        reference_index = _reference_index(full)
        cell_stats = per_cell[cell]
        totals["parents"] += 1
        cell_stats["parents"] += 1
        for index, (arow, frow) in enumerate(zip(adaptive, full)):
            if arow["parent_fingerprint"] != meta["raw_fingerprint"] \
                    or frow["parent_fingerprint"] != meta["raw_fingerprint"]:
                raise ReadoutError("parent fingerprint join mismatch")
            for key in STRUCTURAL_FIELDS:
                if arow[key] != frow[key]:
                    raise ReadoutError(f"structural/action mismatch on {key}")
            _validate_observation_match(arow, frow)
            totals["siblings"] += 1
            cell_stats["siblings"] += 1
            for horizon in ("5", "50", "200"):
                if _flag(arow, f"searched{horizon}"):
                    totals[f"searched{horizon}"] += 1
                    cell_stats[f"searched{horizon}"] += 1
            if _flag(arow, "survived5"):
                totals["survived5"] += 1
                cell_stats["survived5"] += 1
            if _flag(arow, "survived50"):
                totals["survived50"] += 1
                cell_stats["survived50"] += 1
            for key in ("nodes5k", "nodes50k", "nodes200k"):
                totals["adaptive_nodes"] += _int(arow[key], key, 0)
                cell_stats["adaptive_nodes"] += _int(arow[key], key, 0)
                totals["full_nodes"] += _int(frow[key], key, 0)
                cell_stats["full_nodes"] += _int(frow[key], key, 0)
        same_row = selected_index == reference_index
        equivalent = _value_equivalent(full[reference_index], full[selected_index])
        totals["same_row"] += int(same_row)
        totals["value_equivalent"] += int(equivalent)
        cell_stats["same_row"] += int(same_row)
        cell_stats["value_equivalent"] += int(equivalent)
        if not same_row:
            selected_mismatches.append({
                "audit_parent_id": audit_id, "source_parent_id": source_id, "cell": cell,
                "selected_local_index": selected_index, "reference_local_index": reference_index,
                "value_equivalent": equivalent,
            })
        rexact, _ = _exact(full[reference_index])
        sexact, _ = _exact(full[selected_index])
        if not rexact and not sexact:
            ref = _int(full[reference_index]["q200_parent"], "ref q200", -30000, 30000)
            sel = _int(full[selected_index]["q200_parent"], "selected q200", -30000, 30000)
            if abs(ref) <= 20000 and abs(sel) <= 20000:
                delta = max(0, ref - sel)
                numeric_deltas.append(delta)
                totals["numeric_eligible"] += 1
                totals["numeric_delta_sum"] += delta
                totals["numeric_ge100"] += int(delta >= 100)
                cell_stats["numeric_eligible"] += 1
                cell_stats["numeric_delta_sum"] += delta
                cell_stats["numeric_ge100"] += int(delta >= 100)

    if totals["parents"] != 1000 or totals["siblings"] != 9409:
        raise ReadoutError("joined audit population mismatch")
    if full_summary["teacher"]["cheap_nodes"] + full_summary["teacher"]["screen_nodes"] \
            + full_summary["teacher"]["teacher_nodes"] != totals["full_nodes"]:
        raise ReadoutError("full-ladder node total differs from joined rows")

    def metrics(stats: Mapping[str, int]) -> dict[str, Any]:
        siblings = stats["siblings"]
        parents = stats["parents"]
        full_nodes = stats["full_nodes"]
        adaptive_nodes = stats["adaptive_nodes"]
        return {
            "parents": parents, "siblings": siblings,
            "adaptive_nodes": adaptive_nodes, "full_ladder_nodes": full_nodes,
            "node_saving_fraction": 0.0 if full_nodes == 0 else 1.0 - adaptive_nodes / full_nodes,
            "search_rates": {h: _ratio(stats[f"searched{h}"], siblings) for h in ("5", "50", "200")},
            "survivor_rates": {"after5": _ratio(stats["survived5"], siblings),
                               "after50": _ratio(stats["survived50"], siblings)},
            "selected_row_equality_rate": _ratio(stats["same_row"], parents),
            "selected_value_equivalence_rate": _ratio(stats["value_equivalent"], parents),
            "numeric_eligible_parents": stats["numeric_eligible"],
            "conditional_numeric_delta_mean": _ratio(stats["numeric_delta_sum"], stats["numeric_eligible"]),
            "conditional_numeric_ge100_rate": _ratio(stats["numeric_ge100"], stats["numeric_eligible"]),
            "decisions_per_million_adaptive_nodes": 0.0 if adaptive_nodes == 0 else parents * 1_000_000 / adaptive_nodes,
        }

    corpus_teacher = adaptive_summary["teacher"]
    corpus_nodes = corpus_teacher["cheap_nodes"] + corpus_teacher["screen_nodes"] + corpus_teacher["teacher_nodes"]
    diagnostics = {
        "schema": SCHEMA,
        "audit": metrics(totals),
        "cells": {cell: metrics(per_cell[cell]) for cell in audit_subset.selector.CELL_ORDER},
        "numeric_delta_max": max(numeric_deltas, default=0),
        "selected_row_mismatches": selected_mismatches,
        "corpus": {
            "parents": 4000, "siblings": len(adaptive_rows), "adaptive_nodes": corpus_nodes,
            "decisions_per_million_adaptive_nodes": 4000 * 1_000_000 / corpus_nodes,
        },
        "interpretation": "diagnostic_only_no_posthoc_gate_or_retuning",
    }
    publication = {
        "schema": PUBLICATION_SCHEMA,
        "state": "completed",
        "verdict": VERDICT,
        "fresh_b3_parents": 4000,
        "adaptive_rows": len(adaptive_rows),
        "audit_parents": 1000,
        "audit_rows": len(full_rows),
        "policy": {"M5": 100, "M50": 60, "minimum_survivors": 2},
        "budgets_nodes": [5000, 50000, 200000],
        "structural_identity_checks": "PASS",
        "action_set_checks": "PASS",
        "exact_result_consistency_checks": "PASS",
        "executed_search_replay_checks": "PASS",
        "reference_backfill": False,
        "adaptive_corpus_mutated": False,
        "transfer_diagnostics": diagnostics,
        "sibling_dataset_v2_creation_authorized": True,
        "fits_authorized": False,
        "model_search_authorized": False,
        "strength_games_authorized": False,
        "promotion_authorized": False,
        "bake_authorized": False,
        "next_stage": "C_SIBLING_DATASET_V2_PREREGISTRATION",
    }
    return diagnostics, publication


def run_stage(args: argparse.Namespace) -> dict[str, Any]:
    if args.work_dir.exists() or args.work_dir.is_symlink():
        raise ReadoutError("work-dir must be absent")
    args.work_dir.mkdir(parents=True)
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    paths = _fetch(args, args.work_dir)
    diagnostics, publication = analyze(paths)
    write_new(args.artifact_dir / "b3-fresh-transfer-diagnostics.json", canonical(diagnostics))
    write_new(args.artifact_dir / "b3-fresh-corpus-publication.json", canonical(publication))
    write_new(args.artifact_dir / "scientific-summary.json", canonical(publication))
    return publication


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    for prefix in ("adaptive", "subset", "full"):
        parser.add_argument(f"--{prefix}-job", required=True)
        parser.add_argument(f"--{prefix}-attempt", required=True)
        parser.add_argument(f"--{prefix}-code-sha", required=True)
        parser.add_argument(f"--{prefix}-prefix", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        result = run_stage(parse_args(argv))
    except Exception as exc:
        print(f"adaptive_sibling_b3_fresh_transfer_readout: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"state": result["state"], "verdict": result["verdict"],
                      "next_stage": result["next_stage"]},
                     sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
