#!/usr/bin/env python3
"""Render the D4b stable-hoist move-order treatment into an isolated search.cpp."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import d3_runtime_render as d3

INCLUDE_REPLACEMENT = d3.INCLUDE_ANCHOR + '#include "d4b_runtime_move_order.hpp"\n'

NEW_ORDER = r'''// Sort moves in historical order first. D4b is an isolated, internal-node-only
// stable hoist over the first up-to-four legacy non-TT siblings. OFF mode is
// exactly the historical ordering path.
inline void order_moves(MoveList& moves, const Searcher& s,
                        const Position& parent, int depth, int ply,
                        int alpha, int beta, const Move& tt_move, bool tt_hit,
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
    for (std::size_t i = 0; i < n; ++i) {
        std::size_t best = i;
        for (std::size_t j = i + 1; j < n; ++j) {
            if (scores[j] > scores[best]) best = j;
        }
        if (best != i) {
            std::swap(moves[i], moves[best]);
            std::swap(scores[i], scores[best]);
        }
    }

    const auto& rt = d4b_runtime_order::runtime();
    const int pieces = popcount(parent.occupied());
    const int phase = d4b_runtime_order::phase_index(pieces);
    if (!rt.active || ply < 1 || phase < 0 || depth < 3 || n < 2 || n > 16) return;

    std::array<std::size_t, 4> candidate_index{};
    int count = 0;
    for (std::size_t i = 0; i < n && count < 4; ++i) {
        if (tt_hit && moves[i] == tt_move) continue;
        candidate_index[static_cast<std::size_t>(count++)] = i;
    }
    if (count < 2) return;
    d4b_runtime_order::note_eligible();

    auto squash = [](int value) noexcept -> double {
        const double v = static_cast<double>(value);
        return v / (std::abs(v) + 16384.0);
    };
    auto canonical_square = [&parent](Square square) noexcept -> Square {
        return parent.side_to_move() == Color::White
            ? static_cast<Square>(51 - static_cast<int>(square)) : square;
    };

    std::array<double, 4> logits{};
    for (int rank0 = 0; rank0 < count; ++rank0) {
        const Move& candidate = moves[candidate_index[static_cast<std::size_t>(rank0)]];
        std::array<double, 24> f{};
        const int rank = rank0 + 1;
        f[0] = static_cast<double>(rank - 1) / 3.0;
        f[1] = static_cast<double>(std::min(depth, 16)) / 16.0;
        f[2] = static_cast<double>(std::min(ply, 64)) / 64.0;
        f[3] = static_cast<double>(std::min<int>(static_cast<int>(n), 16)) / 16.0;
        f[4] = static_cast<double>(pieces) / 40.0;
        f[5] = moves[0].is_capture() ? 1.0 : 0.0;
        f[6] = (beta - alpha <= 1) ? 1.0 : 0.0;
        f[7] = candidate.is_capture() ? 1.0 : 0.0;
        f[8] = static_cast<double>(std::min<int>(candidate.num_captures, 10)) / 10.0;
        f[9] = candidate.promotes ? 1.0 : 0.0;
        f[10] = is_king(parent.piece_at(candidate.from)) ? 1.0 : 0.0;
        if (ply <= MAX_PLY) {
            f[11] = candidate == s.killers[static_cast<std::size_t>(ply)][0] ? 1.0 : 0.0;
            f[12] = candidate == s.killers[static_cast<std::size_t>(ply)][1] ? 1.0 : 0.0;
        }
        bool cmatch = false;
        if (prev_move.from != 0) {
            const Move& cm = s.countermove[static_cast<std::size_t>(prev_move.from)]
                                         [static_cast<std::size_t>(prev_move.to)];
            cmatch = cm.from != 0 && candidate == cm;
        }
        f[13] = cmatch ? 1.0 : 0.0;
        f[14] = squash(s.history[static_cast<std::size_t>(candidate.from)]
                                [static_cast<std::size_t>(candidate.to)]);
        int cv = 0;
        if (s.params.use_conthist && prev_move.from != 0)
            cv = s.ch(prev_move.to, candidate.from, candidate.to);
        f[15] = squash(cv);
        const Square cf = canonical_square(candidate.from);
        const Square ct = canonical_square(candidate.to);
        const int fr = row_of(cf), fc = col_of(cf), tr = row_of(ct), tc = col_of(ct);
        f[16] = static_cast<double>(fr) / 9.0;
        f[17] = static_cast<double>(fc) / 9.0;
        f[18] = static_cast<double>(tr) / 9.0;
        f[19] = static_cast<double>(tc) / 9.0;
        f[20] = static_cast<double>(std::abs(tr - fr)) / 9.0;
        f[21] = static_cast<double>(std::abs(tc - fc)) / 9.0;
        f[22] = (tr == 0 || tr == 9 || tc == 0 || tc == 9) ? 1.0 : 0.0;
        f[23] = 1.0 - std::min(1.0,
            (std::abs(static_cast<double>(tr) - 4.5)
             + std::abs(static_cast<double>(tc) - 4.5)) / 9.0);
        logits[static_cast<std::size_t>(rank0)] = d4b_runtime_order::logit(rt, phase, rank, f);
    }
    int best = 0;
    for (int i = 1; i < count; ++i)
        if (logits[static_cast<std::size_t>(i)] > logits[static_cast<std::size_t>(best)]) best = i;
    if (best == 0) return;
    const Move selected = moves[candidate_index[static_cast<std::size_t>(best)]];
    for (int i = best; i > 0; --i)
        moves[candidate_index[static_cast<std::size_t>(i)]] = moves[candidate_index[static_cast<std::size_t>(i - 1)]];
    moves[candidate_index[0]] = selected;
    d4b_runtime_order::note_hoist();
}
'''

CALL_NEW = 'order_moves(moves, *this, pos, depth, ply, alpha, beta, tt_move, tt_move_valid, prev_move);'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"D4B_RUNTIME_RENDER_INVALID {label} count={n}")
    return text.replace(old, new, 1)


def render(src: Path, out: Path) -> None:
    text = src.read_text(encoding="utf-8")
    text = replace_once(text, d3.INCLUDE_ANCHOR, INCLUDE_REPLACEMENT, "include")
    text = replace_once(text, d3.OLD_ORDER, NEW_ORDER, "order body")
    text = replace_once(text, d3.CALL_OLD, CALL_NEW, "recursive call")
    if text.count("d4b_runtime_order::logit") != 1 or "D4b is an isolated" not in text:
        raise RuntimeError("D4B_RUNTIME_RENDER_INVALID treatment cardinality")
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--src", type=Path, required=True); ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(); render(a.src, a.out); print("D4B_RUNTIME_RENDER_COMPLETE_V1"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
