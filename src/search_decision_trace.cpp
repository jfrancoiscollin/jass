// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "search.hpp"

#include <locale>
#include <sstream>

namespace jass {

const char* search_decision_bound_name(SearchDecisionBound bound) noexcept {
    switch (bound) {
        case SearchDecisionBound::Exact: return "Exact";
        case SearchDecisionBound::Lower: return "Lower";
        case SearchDecisionBound::Upper: return "Upper";
        case SearchDecisionBound::None:  return "None";
    }
    return "None";
}

SearchDecisionBound classify_search_decision_bound(
    int score, int alpha, int beta, bool completed) noexcept {
    if (!completed) return SearchDecisionBound::None;
    if (score <= alpha) return SearchDecisionBound::Upper;
    if (score >= beta) return SearchDecisionBound::Lower;
    return SearchDecisionBound::Exact;
}

namespace {

void hash_byte(std::uint64_t& hash, std::uint8_t value) noexcept {
    hash ^= value;
    hash *= 1099511628211ULL;
}

void hash_move(std::uint64_t& hash, const Move& move) noexcept {
    hash_byte(hash, move.from);
    hash_byte(hash, move.to);
    hash_byte(hash, move.num_captures);
    hash_byte(hash, static_cast<std::uint8_t>(move.promotes ? 1 : 0));
    for (unsigned shift = 0; shift < 64; shift += 8) {
        hash_byte(hash, static_cast<std::uint8_t>(move.captured >> shift));
    }
}

void write_bool(std::ostringstream& out, bool value) {
    out << (value ? "true" : "false");
}

void write_move(std::ostringstream& out, const Move& move) {
    out << "{\"from\":" << static_cast<unsigned>(move.from)
        << ",\"to\":" << static_cast<unsigned>(move.to)
        << ",\"num_captures\":" << static_cast<unsigned>(move.num_captures)
        << ",\"promotes\":";
    write_bool(out, move.promotes);
    out << ",\"captured\":" << move.captured << '}';
}

}  // namespace

std::uint64_t search_decision_pv_hash_v1(
    const std::vector<Move>& pv) noexcept {
    std::uint64_t hash = 14695981039346656037ULL;
    for (const Move& move : pv) hash_move(hash, move);
    return hash;
}

std::string serialize_search_decision_trace_v1(
    const SearchDecisionTrace& trace) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << "{\"schema\":\"jass.search-decision-trace\""
        << ",\"version\":" << trace.schema_version
        << ",\"root_rule_draw\":";
    write_bool(out, trace.root_rule_draw);
    out << ",\"no_legal_moves\":";
    write_bool(out, trace.no_legal_moves);
    out << ",\"semantic_root_actions\":" << trace.root_actions.size()
        << ",\"root_actions\":[";
    for (std::size_t i = 0; i < trace.root_actions.size(); ++i) {
        if (i != 0) out << ',';
        write_move(out, trace.root_actions[i]);
    }
    out << "],\"attempts\":[";
    for (std::size_t i = 0; i < trace.attempts.size(); ++i) {
        if (i != 0) out << ',';
        const SearchDecisionAttemptTrace& attempt = trace.attempts[i];
        out << "{\"depth\":" << attempt.depth
            << ",\"attempt\":" << attempt.attempt
            << ",\"alpha\":" << attempt.alpha
            << ",\"beta\":" << attempt.beta
            << ",\"score\":" << attempt.score
            << ",\"bound\":\"" << search_decision_bound_name(attempt.bound)
            << "\",\"best_move\":";
        write_move(out, attempt.best_move);
        out << ",\"nodes_before\":" << attempt.nodes_before
            << ",\"nodes_after\":" << attempt.nodes_after
            << ",\"eval_calls_before\":" << attempt.eval_calls_before
            << ",\"eval_calls_after\":" << attempt.eval_calls_after
            << ",\"pvs_researches_before\":" << attempt.pvs_researches_before
            << ",\"pvs_researches_after\":" << attempt.pvs_researches_after
            << ",\"cutoff\":";
        write_bool(out, attempt.cutoff);
        out << ",\"completed\":";
        write_bool(out, attempt.completed);
        out << ",\"all_actions_searched\":";
        write_bool(out, attempt.all_actions_searched);
        out << ",\"actions\":[";
        for (std::size_t j = 0; j < attempt.actions.size(); ++j) {
            if (j != 0) out << ',';
            const SearchDecisionActionTrace& action = attempt.actions[j];
            out << "{\"move\":";
            write_move(out, action.move);
            out << ",\"score\":" << action.score
                << ",\"bound\":\"" << search_decision_bound_name(action.bound)
                << "\",\"alpha\":" << action.alpha
                << ",\"beta\":" << action.beta
                << ",\"nodes\":" << action.nodes
                << ",\"eval_calls\":" << action.eval_calls
                << ",\"pvs_researches\":" << action.pvs_researches
                << ",\"cutoff\":";
            write_bool(out, action.cutoff);
            out << ",\"completed\":";
            write_bool(out, action.completed);
            out << ",\"pv_hash\":" << action.pv_hash
                << ",\"pv_length\":" << action.pv_length << '}';
        }
        out << "]}";
    }
    out << "],\"result\":{\"best_move\":";
    write_move(out, trace.best_move);
    out << ",\"score\":" << trace.score
        << ",\"completed_depth\":" << trace.completed_depth
        << ",\"effective_depth\":" << trace.effective_depth
        << ",\"aborted_iteration\":";
    write_bool(out, trace.aborted_iteration);
    out << ",\"stop_reason\":\""
        << search_stop_reason_name(trace.stop_reason) << '"'
        << ",\"nodes\":" << trace.nodes
        << ",\"eval_calls\":" << trace.eval_calls
        << ",\"pvs_researches\":" << trace.pvs_researches
        << ",\"pv_hash\":" << trace.pv_hash
        << ",\"pv_length\":" << trace.pv_length << "}}";
    return out.str();
}

}  // namespace jass
