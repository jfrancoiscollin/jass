#!/usr/bin/env python3
"""Render passive D4 beta-cutoff tracing into an isolated source tree only."""
from __future__ import annotations

import argparse
from pathlib import Path

TRACE_STRUCTS = r'''
// Passive D4 search-utility diagnostics. Populated only in an isolated
// diagnostic build when SearchLimits::search_utility_trace is non-null.
struct SearchUtilityCandidateTrace {
    Move move{};
    int legacy_rank{0};
    std::array<double, 24> features{};
};

struct SearchUtilityCutoffTrace {
    Position parent{};
    int search_ply{0};
    int remaining_depth{0};
    int alpha{0};
    int beta{0};
    int parent_piece_count{0};
    int legal_move_count{0};
    bool tt_move_valid{false};
    Move tt_move{};
    Move cutoff_move{};
    int label_index{-1};
    std::vector<SearchUtilityCandidateTrace> candidates;
};

struct SearchUtilityTrace {
    std::vector<SearchUtilityCutoffTrace> cutoffs;
};

'''

SEARCHER_MEMBER_OLD = r'''    // Passive autopsy instrumentation. Both pointers are null in production.
    DepthOneSearchTrace*                  depth_one_trace{nullptr};
    DepthOneMoveTrace*                    active_depth_one_move{nullptr};
'''
SEARCHER_MEMBER_NEW = SEARCHER_MEMBER_OLD + r'''    SearchUtilityTrace*                   search_utility_trace{nullptr};
'''

ORDER_OLD = r'''    const Move prev_move = move_played[static_cast<std::size_t>(ply)];
    order_moves(moves, *this, ply, tt_move, tt_move_valid, prev_move);

    // 4. Search.
'''
ORDER_NEW = r'''    const Move prev_move = move_played[static_cast<std::size_t>(ply)];
    order_moves(moves, *this, ply, tt_move, tt_move_valid, prev_move);

    // D4 diagnostic capture: freeze the first up-to-four LEGACY non-TT
    // candidates and their cheap pre-search features before any child is
    // searched. This block is passive and exists only in the rendered teacher.
    std::array<Move, 4> d4_trace_moves{};
    std::array<std::array<double, 24>, 4> d4_trace_features{};
    int d4_trace_count = 0;
    int d4_trace_alpha = alpha;
    int d4_trace_beta = beta;
    const int d4_piece_count = popcount(pos.occupied());
    const bool d4_trace_base_eligible =
        search_utility_trace != nullptr
        && ply >= 1
        && d4_piece_count >= 9 && d4_piece_count <= 40
        && depth >= 3
        && moves.size() >= 2 && moves.size() <= 16;
    if (d4_trace_base_eligible) {
        auto d4_squash = [](int value) noexcept -> double {
            const double v = static_cast<double>(value);
            return v / (std::abs(v) + 16384.0);
        };
        auto d4_canonical_square = [&pos](Square square) noexcept -> Square {
            return pos.side_to_move() == Color::White
                ? static_cast<Square>(51 - static_cast<int>(square))
                : square;
        };
        for (const Move& candidate : moves) {
            if (tt_move_valid && candidate == tt_move) continue;
            if (d4_trace_count >= 4) break;
            const int rank = d4_trace_count + 1;
            auto& f = d4_trace_features[static_cast<std::size_t>(d4_trace_count)];
            f.fill(0.0);
            f[0] = static_cast<double>(rank - 1) / 3.0;
            f[1] = static_cast<double>(std::min(depth, 16)) / 16.0;
            f[2] = static_cast<double>(std::min(ply, 64)) / 64.0;
            f[3] = static_cast<double>(std::min<int>(static_cast<int>(moves.size()), 16)) / 16.0;
            f[4] = static_cast<double>(d4_piece_count) / 40.0;
            f[5] = moves[0].is_capture() ? 1.0 : 0.0;
            f[6] = (beta - alpha <= 1) ? 1.0 : 0.0;
            f[7] = candidate.is_capture() ? 1.0 : 0.0;
            f[8] = static_cast<double>(std::min<int>(candidate.num_captures, 10)) / 10.0;
            f[9] = candidate.promotes ? 1.0 : 0.0;
            f[10] = is_king(pos.piece_at(candidate.from)) ? 1.0 : 0.0;
            if (ply <= MAX_PLY) {
                f[11] = candidate == killers[static_cast<std::size_t>(ply)][0] ? 1.0 : 0.0;
                f[12] = candidate == killers[static_cast<std::size_t>(ply)][1] ? 1.0 : 0.0;
            }
            bool cmatch = false;
            if (prev_move.from != 0) {
                const Move& cm = countermove
                    [static_cast<std::size_t>(prev_move.from)]
                    [static_cast<std::size_t>(prev_move.to)];
                cmatch = cm.from != 0 && candidate == cm;
            }
            f[13] = cmatch ? 1.0 : 0.0;
            f[14] = d4_squash(history[candidate.from][candidate.to]);
            int cv = 0;
            if (params.use_conthist && prev_move.from != 0)
                cv = ch(prev_move.to, candidate.from, candidate.to);
            f[15] = d4_squash(cv);
            const Square cf = d4_canonical_square(candidate.from);
            const Square ct = d4_canonical_square(candidate.to);
            const int fr = row_of(cf), fc = col_of(cf);
            const int tr = row_of(ct), tc = col_of(ct);
            f[16] = static_cast<double>(fr) / 9.0;
            f[17] = static_cast<double>(fc) / 9.0;
            f[18] = static_cast<double>(tr) / 9.0;
            f[19] = static_cast<double>(tc) / 9.0;
            f[20] = static_cast<double>(std::abs(tr - fr)) / 9.0;
            f[21] = static_cast<double>(std::abs(tc - fc)) / 9.0;
            f[22] = (tr == 0 || tr == 9 || tc == 0 || tc == 9) ? 1.0 : 0.0;
            f[23] = 1.0 - std::min(
                1.0,
                (std::abs(static_cast<double>(tr) - 4.5)
                 + std::abs(static_cast<double>(tc) - 4.5)) / 9.0);
            d4_trace_moves[static_cast<std::size_t>(d4_trace_count)] = candidate;
            ++d4_trace_count;
        }
    }
    const bool d4_trace_eligible = d4_trace_base_eligible && d4_trace_count >= 2;

    // 4. Search.
'''

CUTOFF_OLD = r'''        if (alpha >= beta) {
            ++cutoffs; if (move_idx == 0) ++first_move_cutoffs;   // DIAG #1
'''
CUTOFF_NEW = r'''        if (alpha >= beta) {
            if (!stopped && d4_trace_eligible) {
                int d4_label = -1;
                for (int i = 0; i < d4_trace_count; ++i) {
                    if (m == d4_trace_moves[static_cast<std::size_t>(i)]) {
                        d4_label = i;
                        break;
                    }
                }
                if (d4_label >= 0) {
                    SearchUtilityCutoffTrace event;
                    event.parent = pos;
                    event.search_ply = ply;
                    event.remaining_depth = depth;
                    event.alpha = d4_trace_alpha;
                    event.beta = d4_trace_beta;
                    event.parent_piece_count = d4_piece_count;
                    event.legal_move_count = static_cast<int>(moves.size());
                    event.tt_move_valid = tt_move_valid;
                    event.tt_move = tt_move;
                    event.cutoff_move = m;
                    event.label_index = d4_label;
                    event.candidates.reserve(static_cast<std::size_t>(d4_trace_count));
                    for (int i = 0; i < d4_trace_count; ++i) {
                        SearchUtilityCandidateTrace candidate;
                        candidate.move = d4_trace_moves[static_cast<std::size_t>(i)];
                        candidate.legacy_rank = i + 1;
                        candidate.features = d4_trace_features[static_cast<std::size_t>(i)];
                        event.candidates.push_back(candidate);
                    }
                    search_utility_trace->cutoffs.push_back(std::move(event));
                }
            }
            ++cutoffs; if (move_idx == 0) ++first_move_cutoffs;   // DIAG #1
'''

CMAKE_APPEND = r'''
# D4 diagnostic-only beta-cutoff teacher exporter. Added only to an isolated
# rendered source tree by jobs/tools/d4_search_utility_trace_render.py.
if(NOT EMSCRIPTEN)
    add_executable(d4_search_utility_trace_export
        jobs/tools/d4_search_utility_trace_export.cpp
        $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(d4_search_utility_trace_export PRIVATE jass_lib jass_warnings)
endif()
'''

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)

def render(root: Path) -> None:
    hpp = root / "src/search.hpp"
    cpp = root / "src/search.cpp"
    cmake = root / "CMakeLists.txt"
    h = hpp.read_text(encoding="utf-8")
    c = cpp.read_text(encoding="utf-8")
    m = cmake.read_text(encoding="utf-8")
    if "SearchUtilityTrace" in h or "d4_trace_moves" in c or "d4_search_utility_trace_export" in m:
        raise RuntimeError("D4 trace rendering already present")
    h = replace_once(h, "#include <atomic>\n", "#include <array>\n#include <atomic>\n", "search.hpp array include")
    h = replace_once(h, "struct SearchLimits {\n", TRACE_STRUCTS + "struct SearchLimits {\n", "search.hpp trace structs")
    h = replace_once(h, "    SearchDecisionTrace* search_decision_trace = nullptr;\n", "    SearchDecisionTrace* search_decision_trace = nullptr;\n    SearchUtilityTrace* search_utility_trace = nullptr;\n", "search.hpp SearchLimits pointer")
    c = replace_once(c, SEARCHER_MEMBER_OLD, SEARCHER_MEMBER_NEW, "search.cpp Searcher member")
    c = replace_once(c, "    if (limits.search_decision_trace) {\n        *limits.search_decision_trace = SearchDecisionTrace{};\n    }\n", "    if (limits.search_decision_trace) {\n        *limits.search_decision_trace = SearchDecisionTrace{};\n    }\n    if (limits.search_utility_trace) {\n        *limits.search_utility_trace = SearchUtilityTrace{};\n    }\n", "search.cpp trace reset")
    c = replace_once(c, "    s.depth_one_trace = limits.depth_one_trace;\n", "    s.depth_one_trace = limits.depth_one_trace;\n    s.search_utility_trace = limits.search_utility_trace;\n", "search.cpp trace pointer assignment")
    c = replace_once(c, ORDER_OLD, ORDER_NEW, "search.cpp legacy-order capture")
    c = replace_once(c, CUTOFF_OLD, CUTOFF_NEW, "search.cpp beta cutoff capture")
    if not m.endswith("\n"):
        m += "\n"
    m += CMAKE_APPEND
    hpp.write_text(h, encoding="utf-8")
    cpp.write_text(c, encoding="utf-8")
    cmake.write_text(m, encoding="utf-8")

def self_test() -> None:
    assert "SearchUtilityCandidateTrace" in TRACE_STRUCTS
    assert "first up-to-four" in ORDER_NEW
    assert "d4_label >= 0" in CUTOFF_NEW
    assert "d4_search_utility_trace_export" in CMAKE_APPEND
    print("D4_SEARCH_UTILITY_TRACE_RENDER_SELFTEST_OK")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.root is None:
        ap.error("--root is required unless --self-test")
    render(args.root)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
