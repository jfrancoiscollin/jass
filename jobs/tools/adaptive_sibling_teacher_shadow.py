#!/usr/bin/env python3
"""Shadow-simulate a staged sibling teacher on existing deep-teacher tables.

This tool performs NO search and NO fit.  It replays the already-produced
q5k/q50/q200 columns from ``deep_sibling_teacher.cpp`` and asks how many nodes
a fixed staged policy would have spent, then measures the retrospective q200
move/regret cost of that allocation.

Selection invariants:

* q200 is never an input to 5k->50k or 50k->200k survival decisions;
* exact terminal/TB wins resolve a parent immediately at zero simulated search;
* semantic row order is the deterministic tie-break;
* the v1 margins are constants for SHADOW diagnostics only and are not an
  authorization to run a real adaptive teacher.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

M5_CP = 100
M50_CP = 60
CATASTROPHIC_REGRET_CP = 100
REQUIRED_COLUMNS = {
    "row_index",
    "parent_id",
    "child_rule_terminal",
    "child_tb_exact",
    "exact_parent_utility",
    "q5k_parent",
    "q50_parent",
    "q200_parent",
    "nodes5k",
    "nodes50k",
    "nodes200k",
}


@dataclass(frozen=True)
class Row:
    row_index: int
    parent_id: int
    exact: bool
    exact_utility: int | None
    q5: int
    q50: int
    q200: int
    n5: int
    n50: int
    n200: int


@dataclass(frozen=True)
class ParentResult:
    parent_id: int
    siblings: int
    exact_siblings: int
    survivors50: tuple[int, ...]
    survivors200: tuple[int, ...]
    shadow_choice: int
    reference_choice: int
    full_nodes: int
    shadow_nodes: int
    regret_cp: int
    exact_win_shortcut: bool
    uncertified_shadow: bool


def _as_int(record: dict[str, str], name: str) -> int:
    try:
        return int(record[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid integer column {name!r}: {record.get(name)!r}") from exc


def load_groups(path: Path) -> list[Row]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError("missing TSV header")
        missing = sorted(REQUIRED_COLUMNS.difference(reader.fieldnames))
        if missing:
            raise ValueError("missing required columns: " + ", ".join(missing))
        rows: list[Row] = []
        seen_row_indices: set[int] = set()
        for record in reader:
            row_index = _as_int(record, "row_index")
            if row_index in seen_row_indices:
                raise ValueError(f"duplicate row_index {row_index}")
            seen_row_indices.add(row_index)
            terminal = _as_int(record, "child_rule_terminal") != 0
            tb_exact = _as_int(record, "child_tb_exact") != 0
            raw_utility = _as_int(record, "exact_parent_utility")
            exact = terminal or tb_exact
            utility: int | None = raw_utility if exact else None
            if exact and utility not in (-1, 0, 1):
                raise ValueError(
                    f"row {row_index}: exact sibling has utility {raw_utility}, expected -1/0/1"
                )
            rows.append(
                Row(
                    row_index=row_index,
                    parent_id=_as_int(record, "parent_id"),
                    exact=exact,
                    exact_utility=utility,
                    q5=_as_int(record, "q5k_parent"),
                    q50=_as_int(record, "q50_parent"),
                    q200=_as_int(record, "q200_parent"),
                    n5=_as_int(record, "nodes5k"),
                    n50=_as_int(record, "nodes50k"),
                    n200=_as_int(record, "nodes200k"),
                )
            )
    if not rows:
        raise ValueError("groups TSV contains no rows")
    return rows


def _top_with_margin(rows: Iterable[Row], attr: str, margin: int, minimum: int = 2) -> list[Row]:
    ranked = sorted(rows, key=lambda r: (-getattr(r, attr), r.row_index))
    if not ranked:
        return []
    best = getattr(ranked[0], attr)
    survivors = [r for r in ranked if best - getattr(r, attr) <= margin]
    floor = min(minimum, len(ranked))
    selected = {r.row_index for r in survivors}
    for row in ranked[:floor]:
        selected.add(row.row_index)
    return [r for r in ranked if r.row_index in selected]


def _reference_choice(rows: list[Row]) -> Row:
    exact_wins = [r for r in rows if r.exact_utility == 1]
    if exact_wins:
        return min(exact_wins, key=lambda r: r.row_index)
    unresolved = [r for r in rows if not r.exact]
    if unresolved:
        return min(unresolved, key=lambda r: (-r.q200, r.row_index))
    exact_draws = [r for r in rows if r.exact_utility == 0]
    if exact_draws:
        return min(exact_draws, key=lambda r: r.row_index)
    return min(rows, key=lambda r: r.row_index)


def _regret_cp(reference: Row, chosen: Row) -> int:
    # Exact WDL is categorical and cannot be converted honestly to centipawns.
    # Report zero only when both choices have the same exact utility; otherwise
    # use a conservative catastrophic sentinel so the mismatch cannot look safe.
    if reference.exact or chosen.exact:
        if reference.exact and chosen.exact and reference.exact_utility == chosen.exact_utility:
            return 0
        return CATASTROPHIC_REGRET_CP
    return max(0, reference.q200 - chosen.q200)


def simulate_parent(parent_id: int, rows: list[Row]) -> ParentResult:
    rows = sorted(rows, key=lambda r: r.row_index)
    if len(rows) < 2:
        raise ValueError(f"parent {parent_id} has fewer than two siblings")

    reference = _reference_choice(rows)
    full_nodes = sum(0 if r.exact else r.n5 + r.n50 + r.n200 for r in rows)

    exact_wins = [r for r in rows if r.exact_utility == 1]
    if exact_wins:
        chosen = min(exact_wins, key=lambda r: r.row_index)
        return ParentResult(
            parent_id=parent_id,
            siblings=len(rows),
            exact_siblings=sum(r.exact for r in rows),
            survivors50=(),
            survivors200=(),
            shadow_choice=chosen.row_index,
            reference_choice=reference.row_index,
            full_nodes=full_nodes,
            shadow_nodes=0,
            regret_cp=_regret_cp(reference, chosen),
            exact_win_shortcut=True,
            uncertified_shadow=False,
        )

    unresolved = [r for r in rows if not r.exact]
    if not unresolved:
        chosen = _reference_choice(rows)
        return ParentResult(
            parent_id=parent_id,
            siblings=len(rows),
            exact_siblings=len(rows),
            survivors50=(),
            survivors200=(),
            shadow_choice=chosen.row_index,
            reference_choice=reference.row_index,
            full_nodes=full_nodes,
            shadow_nodes=0,
            regret_cp=_regret_cp(reference, chosen),
            exact_win_shortcut=False,
            uncertified_shadow=False,
        )

    # Stage 5k: every unresolved action gets the cheap search.
    shadow_nodes = sum(r.n5 for r in unresolved)
    survive50 = _top_with_margin(unresolved, "q5", M5_CP, minimum=2)

    # Stage 50k: only the q5 survivors get the screen search.
    shadow_nodes += sum(r.n50 for r in survive50)
    survive200 = _top_with_margin(survive50, "q50", M50_CP, minimum=2)

    # Stage 200k: only the q50 survivors get the teacher search.
    shadow_nodes += sum(r.n200 for r in survive200)
    uncertified = len(survive200) == 1
    chosen_pool = survive200 if survive200 else survive50 if survive50 else unresolved
    chosen = min(chosen_pool, key=lambda r: (-r.q200, r.row_index))

    return ParentResult(
        parent_id=parent_id,
        siblings=len(rows),
        exact_siblings=sum(r.exact for r in rows),
        survivors50=tuple(r.row_index for r in survive50),
        survivors200=tuple(r.row_index for r in survive200),
        shadow_choice=chosen.row_index,
        reference_choice=reference.row_index,
        full_nodes=full_nodes,
        shadow_nodes=shadow_nodes,
        regret_cp=_regret_cp(reference, chosen),
        exact_win_shortcut=False,
        uncertified_shadow=uncertified,
    )


def percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    w = pos - lo
    return float(ordered[lo] * (1.0 - w) + ordered[hi] * w)


def build_report(rows: list[Row]) -> tuple[dict[str, object], list[ParentResult]]:
    grouped: dict[int, list[Row]] = defaultdict(list)
    for row in rows:
        grouped[row.parent_id].append(row)
    results = [simulate_parent(parent_id, grouped[parent_id]) for parent_id in sorted(grouped)]

    full_nodes = sum(r.full_nodes for r in results)
    shadow_nodes = sum(r.shadow_nodes for r in results)
    regrets = [r.regret_cp for r in results]
    matched = sum(r.shadow_choice == r.reference_choice for r in results)
    catastrophic = sum(r.regret_cp >= CATASTROPHIC_REGRET_CP for r in results)
    exact_shortcuts = sum(r.exact_win_shortcut for r in results)
    exact_mixed = sum(0 < r.exact_siblings < r.siblings for r in results)
    fully_nonexact = sum(r.exact_siblings == 0 for r in results)
    survivor_patterns: dict[str, int] = defaultdict(int)
    for r in results:
        survivor_patterns[f"{len(r.survivors50)}->{len(r.survivors200)}"] += 1

    ratio = shadow_nodes / full_nodes if full_nodes else 0.0
    report: dict[str, object] = {
        "schema": "jass.adaptive_sibling_teacher_shadow.v1",
        "policy": {
            "m5_cp": M5_CP,
            "m50_cp": M50_CP,
            "minimum_survivors_each_stage": 2,
            "terminal_tb_search_cost": 0,
            "q200_used_for_survival": False,
            "real_adaptive_teacher_authorized": False,
        },
        "parents": len(results),
        "rows": len(rows),
        "fully_nonexact_parents": fully_nonexact,
        "mixed_exact_nonexact_parents": exact_mixed,
        "exact_win_shortcut_parents": exact_shortcuts,
        "full_ladder_nodes": full_nodes,
        "shadow_nodes": shadow_nodes,
        "node_ratio": ratio,
        "teacher_node_saving": 1.0 - ratio if full_nodes else 0.0,
        "best_move_match_vs_full_q200": matched / len(results),
        "mean_q200_regret_cp": sum(regrets) / len(regrets),
        "p95_q200_regret_cp": percentile(regrets, 0.95),
        "catastrophic_regret_threshold_cp": CATASTROPHIC_REGRET_CP,
        "catastrophic_regret_rate": catastrophic / len(results),
        "uncertified_shadow_parents": sum(r.uncertified_shadow for r in results),
        "survivor_patterns": dict(sorted(survivor_patterns.items())),
        "fits": 0,
        "searches": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    return report, results


def write_decisions(path: Path, results: list[ParentResult]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "parent_id",
                "siblings",
                "exact_siblings",
                "survivors50",
                "survivors200",
                "shadow_choice",
                "reference_choice",
                "full_nodes",
                "shadow_nodes",
                "regret_cp",
                "exact_win_shortcut",
                "uncertified_shadow",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    r.parent_id,
                    r.siblings,
                    r.exact_siblings,
                    ",".join(map(str, r.survivors50)),
                    ",".join(map(str, r.survivors200)),
                    r.shadow_choice,
                    r.reference_choice,
                    r.full_nodes,
                    r.shadow_nodes,
                    r.regret_cp,
                    int(r.exact_win_shortcut),
                    int(r.uncertified_shadow),
                ]
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--decisions-out", type=Path)
    args = parser.parse_args(argv)

    rows = load_groups(args.groups)
    report, results = build_report(rows)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.decisions_out is not None:
        write_decisions(args.decisions_out, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
