#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Technical terminal-child adapter for the sealed loss-first label protocol.

Immediate terminal children are exact rule outcomes, so Jass legitimately
returns depth=0/nodes=0 instead of completing d10/d12.  Treat those results as
exact at every requested teacher depth and give their PatternEval Jacobian a
zero vector.  All non-terminal label semantics and all scientific constants
remain owned by the frozen base module.
"""
from __future__ import annotations

from typing import Any

from jobs.tools import l3_context3_decision_flip_autopsy as ctx
from jobs.tools import l3_curriculum_error_learning as learning
from jobs.tools import l3_curriculum_error_loss_first_sibling_labels as base


_TERMINAL_FENS: set[str] = set()
_BaseExactFeatureExtractor = base.ExactFeatureExtractor


def _is_exact_terminal(result: dict[str, Any]) -> bool:
    """Accept only the engine's unambiguous no-legal-move root result."""
    return (
        int(result.get("depth", -1)) == 0
        and int(result.get("nodes", -1)) == 0
        and float(result.get("score", 0.0)) <= -29_000.0
    )


def _search_leaf(engine: Any, fen: str, depth: int) -> dict[str, Any]:
    _move, result = ctx._search(engine, fen, depth)
    completed = int(result.get("depth", -1))
    if completed != depth:
        if not _is_exact_terminal(result):
            raise ValueError("fixed-depth search did not complete requested depth")
        # A side with no legal move is an exact loss by the rules.  There is no
        # search frontier and no PatternEval contribution to this value.
        result = dict(result)
        result["terminal_exact"] = True
        result["requested_depth"] = depth
        result["pv_leaf_fen"] = fen
        _TERMINAL_FENS.add(fen)
    leaf = result.get("pv_leaf_fen")
    if not isinstance(leaf, str) or not leaf:
        raise ValueError("instrumented search did not publish pv_leaf_fen")
    learning._fen_bits(leaf)
    return result


class ExactFeatureExtractor(_BaseExactFeatureExtractor):
    """Return the exact zero derivative for terminal-rule scores."""

    def vector(self, fen: str):  # type: ignore[override]
        if fen in _TERMINAL_FENS:
            return {}, {"terminal_exact": True, "pattern_eval_jacobian": "zero"}
        return super().vector(fen)


def install() -> None:
    base._search_leaf = _search_leaf
    base.ExactFeatureExtractor = ExactFeatureExtractor


def main() -> int:
    install()
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
