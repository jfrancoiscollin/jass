"""ED5 k=2 adapter: Q200k teacher sets over the unchanged ED4 choice-set math.

Only construction of A_p changes. Objective, derivatives and solver are imported
unchanged from ``ed4_choice_math`` so the implementation cannot silently fork
the scientific loss.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import numpy as np

from jobs.tools import ed4_choice_math as ed4

NODE_BUDGET = 200000
WIDTH = ed4.WIDTH
RIDGE = ed4.RIDGE
OPTIONS = ed4.OPTIONS
NumericalFailure = ed4.NumericalFailure


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _score(scores: Mapping, row: int) -> float:
    """Read one exact Q200k parent-POV score from the frozen teacher mapping."""
    if (row, NODE_BUDGET) in scores:
        value = scores[row, NODE_BUDGET]
    elif row in scores:
        value = scores[row]
    else:
        raise ValueError("missing_q200k_label")
    need(type(value) in (int, float, np.integer, np.floating) and np.isfinite(value), "nonfinite_q200k_label")
    return float(value)


def groups_from_q200k(groups: Sequence[dict], scores: Mapping) -> list[dict]:
    """Build V_p and exact-max A_p from Scan Q200k parent-POV scores.

    Terminals stay excluded exactly as in ED4. All exact Q200k ties at the
    maximum remain admissible; there is no epsilon, margin, ranking edge or
    fallback.
    """
    out: list[dict] = []
    for group in groups:
        rows = list(group["rows"])
        terminals = set(group.get("terminals", ()))
        need(
            type(group.get("id")) is int
            and type(group.get("stm")) is int
            and group["stm"] in (0, 1)
            and rows == sorted(rows)
            and len(set(rows)) == len(rows)
            and all(type(row) is int for row in rows)
            and terminals <= set(rows),
            "group_ownership",
        )
        V = [row for row in rows if row not in terminals]
        if V:
            values = {row: _score(scores, row) for row in V}
            best = max(values.values())
            A = [row for row in V if values[row] == best]
            need(bool(A), "empty_admissible_set")
        else:
            A = []
        out.append(
            {
                "id": group["id"],
                "stm": group["stm"],
                "rows": rows,
                "V": V,
                "A": A,
                "edges": [],
            }
        )
    return out


def design(phi, z, groups, replay_x, replay_z, y):
    return ed4.design(phi, z, groups, replay_x, replay_z, y)


def derivatives(beta, design):
    return ed4.derivatives(beta, design)


def fit(design):
    return ed4.fit(design)
