// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#ifndef JASS_P4_SYNTHETIC_FIXTURES
#error "P4 helpers are restricted to explicitly enabled synthetic fixtures"
#endif

#include "search.hpp"

#include <algorithm>
#include <cstdint>
#include <limits>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>
#include <vector>

namespace jass::p4 {

// These helpers compare synthetic observations with an independently supplied
// expected anchor. They do NOT authenticate a database, model or receipt, open
// a live backend, or establish the existence of any future scientific artifact.
inline bool hex_digest(std::string_view value, std::size_t length) noexcept {
    return value.size() == length && std::all_of(
        value.begin(), value.end(), [](char c) {
            return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
        });
}

struct DomainIdentity {
    std::uint32_t schema_version{1};
    std::string code_commit;
    std::string build_sha256;
    std::string driver_sha256;
    std::string database_manifest_sha256;
    std::string config_sha256;
    std::string database_type;

    bool valid() const noexcept {
        return schema_version == 1 && hex_digest(code_commit, 40)
            && hex_digest(build_sha256, 64)
            && hex_digest(driver_sha256, 64)
            && hex_digest(database_manifest_sha256, 64)
            && hex_digest(config_sha256, 64) && !database_type.empty();
    }
    bool operator==(const DomainIdentity&) const = default;
};

enum class BackendState {
    Ready, Disabled, Missing, IdentifyFailure, OpenFailure, IoFailure,
    DriverFailure, Unknown
};

struct DomainObservation {
    DomainIdentity identity;
    BackendState state{BackendState::Disabled};
    int identified_cap{0};
    int handle_cap{0};
    int effective_cap{0};
    std::uint64_t epoch{0};
    bool operator==(const DomainObservation&) const = default;
};

enum class DomainClass { Outside, Covered, Invalid };

class DomainVerifier {
public:
    explicit DomainVerifier(DomainIdentity expected)
        : expected_(std::move(expected)) {}

    std::uint64_t epoch() const {
        std::lock_guard lock(mutex_);
        return epoch_;
    }

    // Serial synthetic lifecycle. A future live adapter must obtain these
    // observations from the actual opened handle under the same lifecycle lock.
    bool publish(const DomainObservation& observed) {
        std::lock_guard lock(mutex_);
        // Replacing an observation revokes all previously issued snapshots,
        // including replacement with an identical identity.
        if (current_) {
            current_.reset();
            advance_epoch();
            return false;
        }
        if (exhausted_ || !expected_.valid()
            || observed.identity != expected_
            || observed.state != BackendState::Ready
            || observed.epoch != epoch_ || observed.epoch == 0
            || observed.identified_cap <= 0 || observed.identified_cap > 50
            || observed.handle_cap <= 0 || observed.handle_cap > 50
            || observed.handle_cap > observed.identified_cap
            || observed.effective_cap
                != std::min(observed.identified_cap, observed.handle_cap)) {
            return false;
        }
        current_ = observed;
        return true;
    }

    std::optional<DomainObservation> snapshot() const {
        std::lock_guard lock(mutex_);
        return current_;
    }

    void invalidate() {
        std::lock_guard lock(mutex_);
        current_.reset();  // revoke Ready before advancing lifecycle
        advance_epoch();
    }

    DomainClass assess(const DomainObservation& captured, int pieces) const {
        std::lock_guard lock(mutex_);
        if (!current_ || exhausted_ || pieces <= 0 || pieces > 50
            || captured.epoch != epoch_ || captured != *current_) {
            return DomainClass::Invalid;
        }
        return pieces > captured.effective_cap
            ? DomainClass::Outside : DomainClass::Covered;
    }

private:
    void advance_epoch() noexcept {
        if (epoch_ == std::numeric_limits<std::uint64_t>::max()) {
            exhausted_ = true;
        } else {
            ++epoch_;
        }
    }

    const DomainIdentity expected_;
    mutable std::mutex mutex_;
    std::uint64_t epoch_{1};
    bool exhausted_{false};
    std::optional<DomainObservation> current_;
};

// A range proof is represented by the digest of the independently reviewed
// proof, not by a caller-controlled "range_proved" flag. Matching that digest
// tests binding only; fixtures never attest the contents of a real proof.
enum class ScorePerspective { SideToMove, WhiteAbsolute, BlackAbsolute };

struct ScoreContract {
    std::uint32_t schema_version{1};
    std::string artifact_sha256;
    std::string implementation_commit;
    std::string build_sha256;
    std::string config_sha256;
    std::string range_proof_sha256;
    std::string terminal_order_sha256;
    ScorePerspective perspective{ScorePerspective::SideToMove};
    int static_min{0};
    int static_max{0};
    int terminal_loss_highest{0};
    int terminal_win_lowest{0};
    std::uint64_t epoch{0};

    bool valid() const noexcept {
        return schema_version == 1
            && perspective == ScorePerspective::SideToMove
            && hex_digest(artifact_sha256, 64)
            && hex_digest(implementation_commit, 40)
            && hex_digest(build_sha256, 64)
            && hex_digest(config_sha256, 64)
            && hex_digest(range_proof_sha256, 64)
            && hex_digest(terminal_order_sha256, 64)
            && epoch != 0 && static_min <= static_max
            && terminal_loss_highest < 0 && terminal_win_lowest > 0
            && terminal_loss_highest < static_min
            && static_max < terminal_win_lowest;
    }
    bool operator==(const ScoreContract&) const = default;
};

inline bool verify_score_contract(const ScoreContract& expected,
                                  const ScoreContract& observed,
                                  std::uint64_t final_epoch) noexcept {
    return expected.valid() && expected == observed
        && observed.epoch == final_epoch;
}

inline std::int64_t root_score(Color root, Color stm, int score) noexcept {
    const auto wide = static_cast<std::int64_t>(score);
    return root == stm ? wide : -wide;
}

struct Mean2 {
    // Keep the exact numerator: rounding 0.5 to 0 would change move selection.
    std::int64_t numerator{0};
    static constexpr int denominator = 2;
};

inline std::optional<Mean2> mean2(std::int64_t a, std::int64_t b) noexcept {
    constexpr auto hi = std::numeric_limits<std::int64_t>::max();
    constexpr auto lo = std::numeric_limits<std::int64_t>::min();
    if ((b > 0 && a > hi - b) || (b < 0 && a < lo - b)) {
        return std::nullopt;
    }
    return Mean2{a + b};
}

inline bool move_less(const Move& a, const Move& b) noexcept {
    return std::tie(a.from, a.to, a.num_captures, a.promotes, a.captured)
        < std::tie(b.from, b.to, b.num_captures, b.promotes, b.captured);
}

struct Pair {
    Move first, second;
    int first_score{0}, second_score{0}, depth{0}, attempt{0};
};

inline std::optional<Pair> top2(const SearchDecisionTrace& trace) {
    if (trace.root_actions.size() < 2 || trace.no_legal_moves
        || trace.root_rule_draw) {
        return std::nullopt;
    }
    for (const auto& move : trace.root_actions) {
        if (std::count(trace.root_actions.begin(), trace.root_actions.end(),
                       move) != 1) {
            return std::nullopt;
        }
    }
    std::vector<std::pair<int, int>> attempt_ids;
    std::optional<Pair> result;
    for (const auto& attempt : trace.attempts) {
        const auto id = std::pair{attempt.depth, attempt.attempt};
        if (std::find(attempt_ids.begin(), attempt_ids.end(), id)
            != attempt_ids.end()) {
            return std::nullopt;
        }
        attempt_ids.push_back(id);
        if (attempt.depth <= 0 || attempt.attempt <= 0
            || !attempt.completed || !attempt.all_actions_searched
            || attempt.cutoff || attempt.bound != SearchDecisionBound::Exact
            || attempt.alpha >= attempt.beta
            || classify_search_decision_bound(attempt.score, attempt.alpha,
                                               attempt.beta, true)
                != SearchDecisionBound::Exact
            || attempt.actions.size() != trace.root_actions.size()) {
            continue;
        }
        bool bad = false;
        for (const auto& move : trace.root_actions) {
            if (std::count_if(attempt.actions.begin(), attempt.actions.end(),
                              [&](const auto& action) {
                                  return action.move == move;
                              }) != 1) {
                bad = true;
                break;
            }
        }
        if (bad) continue;

        std::vector<SearchDecisionActionTrace> exact;
        int current_alpha = attempt.alpha;
        for (const auto& action : attempt.actions) {
            if (!action.completed || action.cutoff
                || action.alpha != current_alpha
                || action.beta != attempt.beta
                || action.alpha >= action.beta
                || (action.bound != SearchDecisionBound::Exact
                    && action.bound != SearchDecisionBound::Upper)
                || classify_search_decision_bound(action.score, action.alpha,
                                                   action.beta, true)
                    != action.bound) {
                bad = true;
                break;
            }
            current_alpha = std::max(current_alpha, action.score);
            if (action.bound == SearchDecisionBound::Exact) {
                exact.push_back(action);
            }
        }
        if (bad || exact.size() < 2) continue;
        std::sort(exact.begin(), exact.end(), [](const auto& a, const auto& b) {
            return a.score != b.score ? a.score > b.score
                                     : move_less(a.move, b.move);
        });
        if (attempt.score != exact.front().score) continue;
        for (const auto& action : attempt.actions) {
            if (action.bound == SearchDecisionBound::Upper
                && action.score >= exact[1].score) {
                bad = true;
                break;
            }
        }
        if (bad) continue;
        Pair pair{exact[0].move, exact[1].move, exact[0].score, exact[1].score,
                  attempt.depth, attempt.attempt};
        if (!result || id > std::pair{result->depth, result->attempt}) {
            result = pair;
        }
    }
    return result;
}

struct Allocation { std::string id; std::uint64_t cap{0}; };
enum class CallDisposition { Searched, Unused };

class Ledger {
public:
    Ledger(std::uint64_t allowance, const std::vector<Allocation>& plan)
        : allowance_(allowance) {
        for (const auto& allocation : plan) {
            if (allocation.id.empty() || allocation.cap == 0
                || std::any_of(entries_.begin(), entries_.end(),
                               [&](const Entry& entry) {
                                   return entry.allocation.id == allocation.id;
                               })
                || allocation.cap > allowance_ - submitted_) {
                throw std::invalid_argument("invalid or over-budget P4 plan");
            }
            submitted_ += allocation.cap;
            entries_.push_back({allocation, 0, false, CallDisposition::Unused});
        }
        if (entries_.empty() || submitted_ != allowance_) {
            throw std::invalid_argument("P4 allocations must sum to allowance");
        }
    }

    bool finish(std::string_view id, std::uint64_t nodes,
                CallDisposition disposition) noexcept {
        auto entry = std::find_if(entries_.begin(), entries_.end(),
                                  [&](const Entry& candidate) {
                                      return candidate.allocation.id == id;
                                  });
        if (entry == entries_.end() || entry->finished
            || (disposition != CallDisposition::Searched
                && disposition != CallDisposition::Unused)
            || nodes > entry->allocation.cap
            || (disposition == CallDisposition::Searched && nodes == 0)
            || (disposition == CallDisposition::Unused && nodes != 0)
            || nodes > std::numeric_limits<std::uint64_t>::max() - actual_) {
            invalid_ = true;
            return false;
        }
        entry->nodes = nodes;
        entry->finished = true;
        entry->disposition = disposition;
        actual_ += nodes;
        return true;
    }

    bool complete() const noexcept {
        return !invalid_ && std::all_of(entries_.begin(), entries_.end(),
                                       [](const Entry& entry) {
                                           return entry.finished;
                                       });
    }
    std::uint64_t submitted() const noexcept { return submitted_; }
    std::uint64_t actual() const noexcept { return actual_; }
    std::uint64_t slack() const noexcept { return submitted_ - actual_; }

private:
    struct Entry {
        Allocation allocation;
        std::uint64_t nodes;
        bool finished;
        CallDisposition disposition;
    };
    std::uint64_t allowance_, submitted_{0}, actual_{0};
    bool invalid_{false};
    std::vector<Entry> entries_;
};

inline std::vector<Allocation> treatment_plan(std::uint64_t allowance) {
    if (allowance == 0 || allowance % 128 != 0) {
        throw std::invalid_argument("P4 fixture allowance must divide by 128");
    }
    std::vector<Allocation> plan{{"base", allowance / 2}};
    for (int candidate = 0; candidate < 2; ++candidate) {
        for (int rollout = 0; rollout < 2; ++rollout) {
            for (int ply = 0; ply < 16; ++ply) {
                plan.push_back({
                    "c" + std::to_string(candidate)
                        + "/r" + std::to_string(rollout)
                        + "/p" + std::to_string(ply),
                    allowance / 128});
            }
        }
    }
    return plan;
}

struct SeedIdentity {
    std::string contract, run, case_id;
    Color color{Color::White};
    Move root_move;
    std::uint32_t rollout{0}, ply{0};
};

inline std::string encode_seed(const SeedIdentity& seed) {
    std::string result = "jass.p4.seed.v1|";
    const auto field = [&](std::string_view value) {
        result += std::to_string(value.size()) + ":";
        result.append(value);
    };
    field(seed.contract);
    field(seed.run);
    field(seed.case_id);
    field(seed.color == Color::White ? "white" : "black");
    // All semantic Move fields, no capture-path alias or formatting locale.
    field(std::to_string(seed.root_move.from));
    field(std::to_string(seed.root_move.to));
    field(std::to_string(seed.root_move.num_captures));
    field(seed.root_move.promotes ? "1" : "0");
    field(std::to_string(seed.root_move.captured));
    field(std::to_string(seed.rollout));
    field(std::to_string(seed.ply));
    return result;
}

inline std::uint64_t seed_v1(const SeedIdentity& seed) {
    // Non-cryptographic RNG seed only. The full tuple must remain in the
    // eventual manifest; this value is never an authentication digest.
    std::uint64_t value = 14695981039346656037ULL;
    for (const unsigned char byte : encode_seed(seed)) {
        value ^= byte;
        value *= 1099511628211ULL;
    }
    return value;
}

}  // namespace jass::p4
