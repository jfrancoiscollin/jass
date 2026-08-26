// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Frozen Deep Search Sibling Distillation (DSSD) move-ordering head.
//
// Scientific contract:
//   * never contributes to leaf evaluation, alpha/beta values, TT values or
//     bounds, pruning thresholds, legal move generation, or adjudication;
//   * scores only already-legal capture siblings;
//   * runtime support is parent piece count 9..40 inclusive;
//   * unset JASS_DSSD_MOVE_ORDER_POLICY is a strict dormant path;
//   * a requested malformed/mismatched policy fails closed.
//
// Inputs reproduce the frozen Phase-A learner exactly:
//   120 production scan_eval::compute_extras(child) values
//   + [num_captures, captured_kings, promotes, moving_king,
//      from/50, to/50].
#pragma once

#include "bitboard.hpp"
#include "position.hpp"
#include "scan_eval.hpp"
#include "types.hpp"

#include <array>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <optional>
#include <string>

namespace jass::dssd_policy {

inline constexpr int MOVE_FEATURES = 6;
inline constexpr int TOTAL_FEATURES = scan_eval::NUM_EXTRAS + MOVE_FEATURES;
inline constexpr int MIN_PARENT_PIECES = 9;
inline constexpr int MAX_PARENT_PIECES = 40;
inline constexpr const char* FILE_MAGIC = "JASS_DSSD_MOVE_ORDER_POLICY_V1";
inline constexpr const char* ENV_VAR = "JASS_DSSD_MOVE_ORDER_POLICY";

inline bool supports_parent(const Position& parent) noexcept {
    const int pieces = popcount(parent.occupied());
    return pieces >= MIN_PARENT_PIECES && pieces <= MAX_PARENT_PIECES;
}

struct Policy {
    std::array<std::array<double, TOTAL_FEATURES>, 2> weights{};

    double score(const Position& parent, const Move& move) const noexcept {
        const Color us = parent.side_to_move();
        const Position child = parent.after(move);
        std::array<float, scan_eval::NUM_EXTRAS> extras{};
        scan_eval::compute_extras(child, extras);

        const auto& w = weights[static_cast<std::size_t>(color_index(us))];
        double value = 0.0;
        for (int i = 0; i < scan_eval::NUM_EXTRAS; ++i) {
            value += w[static_cast<std::size_t>(i)]
                   * static_cast<double>(extras[static_cast<std::size_t>(i)]);
        }

        const Bitboard own_kings = parent.kings_of(us);
        const Bitboard enemy_kings = parent.kings_of(opposite(us));
        const std::array<double, MOVE_FEATURES> move_features = {
            static_cast<double>(move.num_captures),
            static_cast<double>(popcount(move.captured & enemy_kings)),
            move.promotes ? 1.0 : 0.0,
            test(own_kings, move.from) ? 1.0 : 0.0,
            static_cast<double>(move.from) / 50.0,
            static_cast<double>(move.to) / 50.0,
        };
        for (int i = 0; i < MOVE_FEATURES; ++i) {
            value += w[static_cast<std::size_t>(scan_eval::NUM_EXTRAS + i)]
                   * move_features[static_cast<std::size_t>(i)];
        }
        return value;
    }
};

inline std::optional<Policy> load(const std::string& path, std::string* error = nullptr) {
    auto fail = [&](const std::string& message) -> std::optional<Policy> {
        if (error) *error = message;
        return std::nullopt;
    };

    std::ifstream in(path);
    if (!in) return fail("cannot open policy file");

    std::string magic;
    int eval_width = 0;
    int move_width = 0;
    if (!(in >> magic) || magic != FILE_MAGIC) return fail("bad policy magic");
    if (!(in >> eval_width >> move_width)) return fail("missing policy dimensions");
    if (eval_width != scan_eval::NUM_EXTRAS) {
        return fail("eval feature width mismatch: file=" + std::to_string(eval_width)
                    + " binary=" + std::to_string(scan_eval::NUM_EXTRAS));
    }
    if (move_width != MOVE_FEATURES) return fail("move feature width mismatch");

    Policy policy;
    for (auto& bank : policy.weights) {
        for (double& value : bank) {
            if (!(in >> value) || !std::isfinite(value)) {
                return fail("missing or non-finite policy weight");
            }
        }
    }
    std::string trailing;
    if (in >> trailing) return fail("trailing token after policy weights");
    return policy;
}

// One immutable policy per process. The causal harness activates the candidate
// by launching the same executable through a wrapper that sets ENV_VAR; the
// baseline launches that executable with the variable absent.
inline const Policy* active() {
    static const std::optional<Policy> policy = []() -> std::optional<Policy> {
        const char* path = std::getenv(ENV_VAR);
        if (path == nullptr || *path == '\0') return std::nullopt;
        std::string error;
        auto loaded = load(path, &error);
        if (!loaded) {
            std::cerr << "DSSD_MOVE_ORDER_POLICY_ERROR path=" << path
                      << " reason=" << error << '\n';
            std::cerr.flush();
            std::exit(2);
        }
        return loaded;
    }();
    return policy ? &*policy : nullptr;
}

}  // namespace jass::dssd_policy
