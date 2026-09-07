#!/usr/bin/env python3
"""Deterministically render the frozen D3 move-order treatment into search.cpp.

The repository source remains the pristine control.  CPX runtime stages copy the
source tree and apply this renderer only to the candidate build, which isolates
the causal intervention from the control executable.
"""
from __future__ import annotations

import argparse
from pathlib import Path

INCLUDE_ANCHOR = '#include "scan_sacs.hpp"\n'
INCLUDE_REPLACEMENT = INCLUDE_ANCHOR + '#include "d3_runtime_move_order.hpp"\n'

OLD_ORDER = r'''// Sort moves in place, descending by `order_score`. Selection sort: the move
// list is small (~30 in the worst case) and an in-place ordering keeps the
// hot loop cache-friendly.
inline void order_moves(MoveList& moves, const Searcher& s, int ply,
                        const Move& tt_move, bool tt_hit,
                        const Move& prev_move) {
    BD_TIME(move_ordering);
    const std::size_t n = moves.size();
    // Keep the allocation-free hot path for normal branching, but never index
    // past the fixed stack buffer when a pathological capture fan exceeds 256.
    std::array<int, 256> stack_scores{};
    std::vector<int> overflow_scores;
    int* scores = stack_scores.data();
    if (n > stack_scores.size()) {
        overflow_scores.resize(n);
        scores = overflow_scores.data();
    }
    for (std::size_t i = 0; i < n; ++i) {
        scores[i] = order_score(s, moves[i], ply, tt_move, tt_hit, prev_move);
    }
    for (std::size_t i = 0; i < n; ++i) {
        std::size_t best = i;
        for (std::size_t j = i + 1; j < n; ++j) {
            if (scores[j] > scores[best]) best = j;
        }
        if (best != i) {
            std::swap(moves[i],  moves[best]);
            std::swap(scores[i], scores[best]);
        }
    }
}
'''

NEW_ORDER = r'''// Sort moves in place. With D3 inactive or outside its frozen 9..40-piece
// support this is the historical byte-for-byte ordering path. With D3 active,
// a legal TT move remains absolute priority; all other siblings use the exact
// frozen D3 score, legacy order_score is the first tie-break, and semantic move
// identity is the final deterministic tie-break.
inline void order_moves(MoveList& moves, const Searcher& s,
                        const Position& parent, int ply,
                        const Move& tt_move, bool tt_hit,
                        const Move& prev_move) {
    BD_TIME(move_ordering);
    const std::size_t n = moves.size();
    std::array<int, 256> stack_scores{};
    std::vector<int> overflow_scores;
    int* scores = stack_scores.data();
    if (n > stack_scores.size()) {
        overflow_scores.resize(n);
        scores = overflow_scores.data();
    }
    for (std::size_t i = 0; i < n; ++i) {
        scores[i] = order_score(s, moves[i], ply, tt_move, tt_hit, prev_move);
    }

    const auto& d3 = d3_runtime_order::runtime();
    if (!d3.active || d3_runtime_order::phase_index(parent) < 0) {
        for (std::size_t i = 0; i < n; ++i) {
            std::size_t best = i;
            for (std::size_t j = i + 1; j < n; ++j) {
                if (scores[j] > scores[best]) best = j;
            }
            if (best != i) {
                std::swap(moves[i],  moves[best]);
                std::swap(scores[i], scores[best]);
            }
        }
        return;
    }

    std::array<double, 256> stack_d3{};
    std::vector<double> overflow_d3;
    double* d3score = stack_d3.data();
    if (n > stack_d3.size()) {
        overflow_d3.resize(n);
        d3score = overflow_d3.data();
    }
    for (std::size_t i = 0; i < n; ++i) {
        if (tt_hit && moves[i] == tt_move) {
            d3score[i] = std::numeric_limits<double>::infinity();
        } else {
            d3score[i] = d3_runtime_order::score(d3, parent, moves[i]);
        }
    }
    for (std::size_t i = 0; i < n; ++i) {
        std::size_t best = i;
        for (std::size_t j = i + 1; j < n; ++j) {
            bool better = d3score[j] > d3score[best];
            if (!better && d3score[j] == d3score[best]) {
                better = scores[j] > scores[best];
                if (!better && scores[j] == scores[best]) {
                    better = d3_runtime_order::semantic_less(moves[j], moves[best]);
                }
            }
            if (better) best = j;
        }
        if (best != i) {
            std::swap(moves[i], moves[best]);
            std::swap(scores[i], scores[best]);
            std::swap(d3score[i], d3score[best]);
        }
    }
}
'''

CALL_OLD = 'order_moves(moves, *this, ply, tt_move, tt_move_valid, prev_move);'
CALL_NEW = 'order_moves(moves, *this, pos, ply, tt_move, tt_move_valid, prev_move);'
ROOT_ANCHOR = '''    s.max_nodes = limits.max_nodes;
    s.node_limit_mode = limits.node_limit_mode;

    // ---------------------------------------------------------------------
    // Lazy SMP fan-out
'''
ROOT_REPLACEMENT = '''    s.max_nodes = limits.max_nodes;
    s.node_limit_mode = limits.node_limit_mode;

    // D3 supplies the root's underlying sibling order. The historical
    // iterative-deepening best-move hoist below remains authoritative on every
    // subsequent iteration. In OFF/unsupported mode this call preserves the
    // legacy generation order exactly.
    order_moves(root_moves, s, pos, 0, Move{}, false, Move{});

    // ---------------------------------------------------------------------
    // Lazy SMP fan-out
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"D3_RUNTIME_RENDER_INVALID: {label} count={count}")
    return text.replace(old, new, 1)


def render(src: Path, out: Path) -> None:
    text = src.read_text(encoding="utf-8")
    text = replace_once(text, INCLUDE_ANCHOR, INCLUDE_REPLACEMENT, "include anchor")
    text = replace_once(text, OLD_ORDER, NEW_ORDER, "order_moves body")
    text = replace_once(text, CALL_OLD, CALL_NEW, "recursive order_moves call")
    text = replace_once(text, ROOT_ANCHOR, ROOT_REPLACEMENT, "root order anchor")
    if text.count('d3_runtime_order::score') != 1:
        raise SystemExit("D3_RUNTIME_RENDER_INVALID: treatment score cardinality")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    render(args.src, args.out)
    print("D3_RUNTIME_RENDER_COMPLETE_V1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
