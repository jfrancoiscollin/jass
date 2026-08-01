// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Helpers shared by the WDL self-play generator and its regression tests.
// They keep the Top-K exploration contract explicit:
//   * child searches use d-1 so their root horizon matches a play search at d;
//   * the child receives the real game predecessors, including the current root;
//   * semantically identical moves are ranked only once;
//   * optional split RNG streams keep future openings independent from policy
//     divergence in a causal UNIFORM-vs-TOPK experiment.

#pragma once

#include "engine.hpp"
#include "movegen.hpp"
#include "search.hpp"
#include "tt.hpp"
#include "zobrist.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <random>
#include <utility>
#include <vector>

namespace jass::selfplay {

inline std::uint64_t derive_stream_seed(std::uint64_t seed,
                                        std::uint64_t stream) noexcept {
    // SplitMix64 finalizer.  The stream index is mixed before mt19937_64 sees
    // it, so adjacent streams do not inherit nearby linear seeds.
    std::uint64_t z = seed
        + std::uint64_t{0x9E3779B97F4A7C15} * (stream + std::uint64_t{1});
    z = (z ^ (z >> 30)) * std::uint64_t{0xBF58476D1CE4E5B9};
    z = (z ^ (z >> 27)) * std::uint64_t{0x94D049BB133111EB};
    return z ^ (z >> 31);
}

class SelfplayRngStreams {
public:
    explicit SelfplayRngStreams(std::uint64_t seed, bool split) noexcept
        : split_(split),
          legacy_(seed),
          opening_(derive_stream_seed(seed, 0)),
          sampling_(derive_stream_seed(seed, 1)),
          exploration_(derive_stream_seed(seed, 2)),
          role_(derive_stream_seed(seed, 3)) {}

    std::mt19937_64& opening() noexcept {
        return split_ ? opening_ : legacy_;
    }
    std::mt19937_64& sampling() noexcept {
        return split_ ? sampling_ : legacy_;
    }
    std::mt19937_64& exploration() noexcept {
        return split_ ? exploration_ : legacy_;
    }
    std::mt19937_64& role() noexcept {
        return split_ ? role_ : legacy_;
    }

    bool split() const noexcept { return split_; }

private:
    bool            split_{false};
    std::mt19937_64 legacy_;
    std::mt19937_64 opening_;
    std::mt19937_64 sampling_;
    std::mt19937_64 exploration_;
    std::mt19937_64 role_;
};

inline int topk_child_search_depth(int play_depth) noexcept {
    // A root search at depth d calls negamax(child, d-1).  Because the Top-K
    // pass starts a new root search from that child, d-1 is the matching
    // horizon.  d=1 is clamped because search() iterates from depth one.
    return std::max(1, play_depth - 1);
}

inline std::vector<Move> unique_semantic_moves(const MoveList& legal) {
    std::vector<Move> unique;
    unique.reserve(legal.size());
    for (const auto& move : legal) {
        if (std::find(unique.begin(), unique.end(), move) == unique.end()) {
            unique.push_back(move);
        }
    }
    return unique;
}

inline std::vector<ZobristHash> topk_child_history(const Engine& engine) {
    // search() expects predecessors only.  For a candidate child, the current
    // engine position is its immediate predecessor and must be appended to the
    // predecessors already stored by Engine.
    std::vector<ZobristHash> history = engine.hash_history();
    history.push_back(zobrist_hash(engine.position()));
    return history;
}

struct TopKChoice {
    Move        move{};
    std::size_t legal_candidates{0};
    std::size_t unique_candidates{0};
    std::size_t eligible_candidates{0};
    std::size_t duplicate_candidates{0};
    int         child_search_depth{0};
    std::size_t selected_rank{0};
    bool        ranked{false};
    bool        margin_singleton{false};
    bool        softmax_sampled{false};
};

template <class URBG>
std::size_t sample_ranked_index(const std::vector<int>& scores,
                                double temperature_cp,
                                URBG& rng) {
    if (scores.empty()) return 0;
    if (!(temperature_cp > 0.0) || !std::isfinite(temperature_cp)) {
        // Preserve the historical Top-K stream exactly, including the draw
        // consumed by `rng() % 1` when the margin collapses to one move.
        return static_cast<std::size_t>(rng() % scores.size());
    }
    if (scores.size() == 1) return 0;

    // Scores are sorted best-first. Subtracting the best makes every exponent
    // non-positive, avoiding overflow even when an unbounded Top-K includes a
    // catastrophically bad move.
    const double best = static_cast<double>(scores.front());
    std::vector<double> weights;
    weights.reserve(scores.size());
    double total = 0.0;
    for (const int score : scores) {
        const double weight =
            std::exp((static_cast<double>(score) - best) / temperature_cp);
        weights.push_back(weight);
        total += weight;
    }

    // Construct a deterministic [0,1) variate directly from the top 53 bits.
    // This avoids implementation-defined details of standard distributions and
    // makes smoke-test sequences portable across libstdc++/libc++.
    constexpr double INV_2_POW_53 = 1.0 / 9007199254740992.0;
    const double target =
        static_cast<double>(static_cast<std::uint64_t>(rng()) >> 11)
        * INV_2_POW_53 * total;
    double cumulative = 0.0;
    for (std::size_t i = 0; i < weights.size(); ++i) {
        cumulative += weights[i];
        if (target < cumulative) return i;
    }
    return weights.size() - 1;
}

template <class URBG, class SearchFn>
TopKChoice select_topk_exploration_move_with(
    const Engine&             engine,
    const MoveList&           legal,
    const SearchLimits&       play_limits,
    int                       topk,
    int                       margin,
    TranspositionTable&       rank_tt,
    URBG&                     rng,
    SearchFn&&                search_fn,
    double                    softmax_temperature_cp = 0.0
) {
    TopKChoice choice;
    choice.legal_candidates = legal.size();

    const std::vector<Move> unique = unique_semantic_moves(legal);
    choice.unique_candidates = unique.size();
    choice.duplicate_candidates = legal.size() - unique.size();
    choice.child_search_depth = topk_child_search_depth(play_limits.max_depth);

    if (unique.empty()) return choice;
    if (topk <= 0 || unique.size() == 1) {
        choice.move = unique.front();
        choice.eligible_candidates = 1;
        return choice;
    }

    SearchLimits ranking_limits = play_limits;
    ranking_limits.max_depth = choice.child_search_depth;
    ranking_limits.movetime_ms = 0;  // deterministic ranking; depth is the contract
    ranking_limits.threads = 1;      // never nest lazy-SMP inside every candidate
    ranking_limits.root_order_schedule.clear();
    if (ranking_limits.nnue == nullptr) ranking_limits.nnue = engine.nnue();

    const std::vector<ZobristHash> history = topk_child_history(engine);
    std::vector<std::pair<int, Move>> ranked;
    ranked.reserve(unique.size());
    for (const auto& candidate : unique) {
        const SearchResult child = search_fn(
            engine.position().after(candidate), ranking_limits, rank_tt, history);
        // Negamax: child.score is from the opponent's point of view.
        ranked.emplace_back(-child.score, candidate);
    }

    std::stable_sort(ranked.begin(), ranked.end(),
                     [](const auto& lhs, const auto& rhs) {
                         return lhs.first > rhs.first;
                     });

    std::size_t eligible = std::min<std::size_t>(
        static_cast<std::size_t>(topk), ranked.size());
    if (margin > 0) {
        const int best_score = ranked.front().first;
        std::size_t within = 1;
        while (within < eligible
               && ranked[within].first >= best_score - margin) {
            ++within;
        }
        eligible = within;
        choice.margin_singleton = (eligible == 1);
    }

    std::vector<int> eligible_scores;
    eligible_scores.reserve(eligible);
    for (std::size_t i = 0; i < eligible; ++i) {
        eligible_scores.push_back(ranked[i].first);
    }
    choice.selected_rank =
        sample_ranked_index(eligible_scores, softmax_temperature_cp, rng);
    choice.move = ranked[choice.selected_rank].second;
    choice.eligible_candidates = eligible;
    choice.ranked = true;
    choice.softmax_sampled = softmax_temperature_cp > 0.0 && eligible > 1;
    return choice;
}

template <class URBG>
TopKChoice select_topk_exploration_move(
    const Engine&       engine,
    const MoveList&     legal,
    const SearchLimits& play_limits,
    int                 topk,
    int                 margin,
    TranspositionTable& rank_tt,
    URBG&               rng,
    double              softmax_temperature_cp = 0.0
) {
    auto run_search = [](
        const Position&                  position,
        const SearchLimits&              limits,
        TranspositionTable&              tt,
        const std::vector<ZobristHash>&  history
    ) {
        return search(position, limits, tt, history);
    };
    return select_topk_exploration_move_with(
        engine, legal, play_limits, topk, margin, rank_tt, rng, run_search,
        softmax_temperature_cp);
}

}  // namespace jass::selfplay
