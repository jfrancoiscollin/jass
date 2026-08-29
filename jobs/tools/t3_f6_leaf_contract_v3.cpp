// SPDX-License-Identifier: AGPL-3.0-or-later
// R0-v3 mechanical isolation and corrected leaf/search contract probe.
#include "egdb_bridge.hpp"
#include "endgame.hpp"
#include "movegen.hpp"
#include "scan_sacs.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "search_params.hpp"
#include "t3_f6.hpp"
#include "tt.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {

using jass::DepthOneSearchTrace;
using jass::Move;
using jass::MoveList;
using jass::Position;

struct FenPosition {
    std::string fen;
    Position position;
};

std::string json_string(std::string_view value) {
    std::ostringstream out;
    out << '"';
    for (const unsigned char c : value) {
        switch (c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 0x20U) {
                    out << "\\u" << std::hex << std::setw(4)
                        << std::setfill('0') << static_cast<unsigned>(c) << std::dec;
                } else {
                    out << static_cast<char>(c);
                }
        }
    }
    return out << '"', out.str();
}

const char* boolean(bool value) noexcept { return value ? "true" : "false"; }

std::string move_id(const Move& move) {
    std::ostringstream out;
    out << static_cast<int>(move.from)
        << (move.is_capture() ? 'x' : '-')
        << static_cast<int>(move.to);
    if (move.is_capture())
        out << "/n" << static_cast<unsigned>(move.num_captures)
            << "/bb" << std::hex << move.captured << std::dec;
    if (move.promotes) out << "/K";
    return out.str();
}

Position parse(std::string_view fen) {
    auto position = Position::from_fen(fen);
    if (!position) throw std::runtime_error("invalid FEN: " + std::string(fen));
    return *position;
}

std::vector<FenPosition> read_positions(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open FEN file: " + path);
    std::vector<FenPosition> rows;
    std::string line;
    while (std::getline(input, line)) {
        const auto comment = line.find('#');
        if (comment != std::string::npos) line.resize(comment);
        const auto first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) continue;
        const auto last = line.find_last_not_of(" \t\r\n");
        line = line.substr(first, last - first + 1U);
        rows.push_back(FenPosition{line, parse(line)});
    }
    return rows;
}

std::string phase(const Position& position) {
    const int pieces = std::popcount(position.occupied());
    if (pieces >= 30 && pieces <= 40) return "P0";
    if (pieces >= 20 && pieces <= 29) return "P1";
    if (pieces >= 12 && pieces <= 19) return "P2";
    if (pieces >= 9 && pieces <= 11) return "P3";
    return "OUT";
}

struct Mechanics {
    bool isolated{true};
    std::size_t root_moves{0};
    std::size_t child_terminal{0};
    std::size_t child_tablebase{0};
    std::size_t child_reply_capture{0};
    std::size_t child_opponent_threat{0};
    std::size_t child_selective_sac{0};
    std::size_t child_forcing_reply{0};
    std::size_t child_promotion_reply{0};
    std::size_t child_draw_special{0};
};

Mechanics mechanics(const Position& root) {
    Mechanics out;
    MoveList legal;
    jass::generate_legal_moves(root, legal);
    out.root_moves = legal.size();
    if (legal.empty() || root.halfmove_clock() >= jass::FIFTY_MOVE_PLIES)
        out.isolated = false;
    for (const Move& move : legal) {
        const Position child = root.after(move);
        MoveList replies;
        jass::generate_legal_moves(child, replies);
        if (replies.empty()) ++out.child_terminal;
        if (jass::probe_endgame(child) != jass::EndgameResult::Unknown)
            ++out.child_tablebase;
        if (std::any_of(replies.begin(), replies.end(),
                        [](const Move& reply) { return reply.is_capture(); }))
            ++out.child_reply_capture;
        bool has_forcing_reply = false;
        bool has_promotion_reply = false;
        for (const Move& reply : replies) {
            has_promotion_reply = has_promotion_reply || reply.promotes;
            if (!reply.is_capture())
                has_forcing_reply = has_forcing_reply
                    || jass::has_any_capture(child.after(reply));
        }
        out.child_forcing_reply += has_forcing_reply;
        out.child_promotion_reply += has_promotion_reply;
        if (jass::has_any_capture(child, jass::opposite(child.side_to_move())))
            ++out.child_opponent_threat;
        MoveList sacs;
        jass::scan_add_sacs(child, sacs);
        if (!sacs.empty()) ++out.child_selective_sac;
        if (child.halfmove_clock() >= jass::FIFTY_MOVE_PLIES || child.hash() == root.hash())
            ++out.child_draw_special;
    }
    out.isolated = out.isolated
        && out.child_terminal == 0
        && out.child_tablebase == 0
        && out.child_reply_capture == 0
        && out.child_opponent_threat == 0
        && out.child_selective_sac == 0
        && out.child_forcing_reply == 0
        && out.child_promotion_reply == 0
        && out.child_draw_special == 0;
    return out;
}

int classify(const std::string& input_path, const std::string& output_path) {
    jass::egdb::ensure_initialised();
    if (!jass::egdb::available())
        throw std::runtime_error("EGDB unavailable for mechanical classification");
    const auto rows = read_positions(input_path);
    std::ofstream out(output_path);
    if (!out) throw std::runtime_error("cannot create mechanics TSV");
    out << "fen\tphase\tisolated\troot_moves\tchild_terminal\tchild_tablebase"
           "\tchild_reply_capture\tchild_opponent_threat\tchild_selective_sac"
           "\tchild_forcing_reply\tchild_promotion_reply\tchild_draw_special\n";
    std::size_t isolated = 0;
    for (const auto& row : rows) {
        const Mechanics m = mechanics(row.position);
        isolated += m.isolated;
        out << row.fen << '\t' << phase(row.position) << '\t' << (m.isolated ? 1 : 0)
            << '\t' << m.root_moves << '\t' << m.child_terminal
            << '\t' << m.child_tablebase << '\t' << m.child_reply_capture
            << '\t' << m.child_opponent_threat << '\t' << m.child_selective_sac
            << '\t' << m.child_forcing_reply << '\t' << m.child_promotion_reply
            << '\t' << m.child_draw_special << '\n';
    }
    std::cout << "R0-v3 mechanics rows=" << rows.size()
              << " isolated=" << isolated << '\n';
    return 0;
}

int rounded_t3(int t0, double residual) noexcept {
    return static_cast<int>(std::clamp(
        std::llround(static_cast<double>(t0) - residual), -20000LL, 20000LL));
}

bool same_result(const jass::SearchResult& a, const jass::SearchResult& b) {
    return a.best_move == b.best_move && a.score == b.score
        && a.depth == b.depth && a.effective_depth == b.effective_depth
        && a.completed_depth == b.completed_depth
        && a.aborted_iteration == b.aborted_iteration
        && a.stop_reason == b.stop_reason && a.nodes == b.nodes
        && a.cutoffs == b.cutoffs && a.first_move_cutoffs == b.first_move_cutoffs
        && a.pvs_researches == b.pvs_researches
        && a.moves_searched == b.moves_searched
        && a.eval_calls == b.eval_calls
        && a.scan_verify_probes == b.scan_verify_probes
        && a.scan_verify_cutoffs == b.scan_verify_cutoffs
        && a.scan_threat_reentries == b.scan_threat_reentries
        && a.root_order_applications == b.root_order_applications
        && a.root_order_failures == b.root_order_failures
        && a.pv == b.pv && a.from_book == b.from_book;
}

struct SearchRun {
    jass::SearchResult result{};
    DepthOneSearchTrace trace{};
};

SearchRun run_search(const Position& root, const jass::INetwork& network,
                     const jass::SearchParams& params, bool traced, int depth = 1) {
    SearchRun out;
    jass::SearchLimits limits;
    limits.max_depth = depth;
    limits.tt_mb = 16;
    limits.threads = 1;
    limits.nnue = &network;
    limits.params = params;
    limits.depth_one_trace = traced ? &out.trace : nullptr;
    jass::TranspositionTable tt;
    tt.resize_mb(16);
    out.result = jass::search(root, limits, tt);
    return out;
}

struct ArmAudit {
    int expected_direct{0};
    SearchRun control{};
    SearchRun traced{};
    std::size_t neutral_mismatches{0};
    std::size_t direct_root_mismatches{0};
    std::size_t child_return_mismatches{0};
    std::size_t root_negation_mismatches{0};
    std::size_t leaf_eval_mismatches{0};
    std::size_t formula_mismatches{0};
    std::size_t saturation_count{0};
    std::size_t unexpected_qsearch_continuations{0};
};

const jass::DepthOneMoveTrace* find_move_trace(
    const DepthOneSearchTrace& trace, const Move& move) {
    const auto it = std::find_if(trace.moves.begin(), trace.moves.end(),
        [&move](const jass::DepthOneMoveTrace& row) { return row.move == move; });
    return it == trace.moves.end() ? nullptr : &*it;
}

void write_move_trace(std::ostream& out, const jass::DepthOneMoveTrace& row) {
    out << "{\"move\":" << json_string(move_id(row.move))
        << ",\"alpha_before\":" << row.alpha_before
        << ",\"beta\":" << row.beta
        << ",\"child_depth\":" << row.child_depth
        << ",\"actual_search_child_return\":" << row.child_return
        << ",\"root_negated_return\":" << row.root_negated_return
        << ",\"nodes_delta\":" << (row.nodes_after - row.nodes_before)
        << ",\"eval_calls_delta\":"
        << (row.eval_calls_after - row.eval_calls_before)
        << ",\"entered_quiescence\":" << boolean(row.entered_quiescence)
        << ",\"qsearch_alpha\":" << row.qsearch_alpha
        << ",\"qsearch_beta\":" << row.qsearch_beta
        << ",\"qsearch_legal_moves\":" << row.qsearch_legal_moves
        << ",\"qsearch_forced_capture\":"
        << boolean(row.qsearch_forced_capture)
        << ",\"qsearch_opponent_threat\":"
        << boolean(row.qsearch_opponent_threat)
        << ",\"qsearch_stand_pat_valid\":"
        << boolean(row.qsearch_stand_pat_valid)
        << ",\"qsearch_stand_pat\":" << row.qsearch_stand_pat
        << ",\"qsearch_selective_sacs\":" << row.qsearch_selective_sacs
        << ",\"qsearch_moves_searched\":" << row.qsearch_moves_searched
        << ",\"qsearch_return\":" << row.qsearch_return
        << ",\"path_draw\":" << boolean(row.path_draw)
        << ",\"fifty_move_draw\":" << boolean(row.fifty_move_draw)
        << ",\"tablebase_hit\":" << boolean(row.tablebase_hit)
        << ",\"tt_cutoff\":" << boolean(row.tt_cutoff)
        << ",\"terminal_hit\":" << boolean(row.terminal_hit)
        << ",\"first_resolution_stage\":"
        << json_string(row.first_resolution_stage) << '}';
}

ArmAudit audit_arm(const Position& root, const jass::INetwork& network,
                   const jass::INetwork& t0,
                   const jass::t3_f6::Network& t3,
                   const jass::SearchParams& params,
                   bool t3_arm, bool require_isolated) {
    ArmAudit out;
    MoveList legal;
    jass::generate_legal_moves(root, legal);
    out.expected_direct = std::numeric_limits<int>::min();
    std::map<std::string, int> direct_by_move;
    for (const Move& move : legal) {
        const Position child = root.after(move);
        const int direct = network.evaluate(child);
        direct_by_move.emplace(move_id(move), direct);
        out.expected_direct = std::max(out.expected_direct, -direct);
        out.saturation_count += std::abs(direct) == 20000;
        if (t3_arm) {
            const int base = t0.evaluate(child);
            if (direct != rounded_t3(base, t3.residual_parent(child)))
                ++out.formula_mismatches;
        }
    }
    out.control = run_search(root, network, params, false);
    out.traced = run_search(root, network, params, true);
    out.neutral_mismatches += !same_result(out.control.result, out.traced.result);
    out.neutral_mismatches += out.traced.trace.leaf_eval_overflow;
    if (require_isolated && out.traced.result.score != out.expected_direct)
        ++out.direct_root_mismatches;
    if (out.traced.trace.moves.size() != legal.size())
        ++out.child_return_mismatches;
    for (const Move& move : legal) {
        const auto* trace = find_move_trace(out.traced.trace, move);
        if (!trace) {
            ++out.child_return_mismatches;
            continue;
        }
        const int direct = direct_by_move.at(move_id(move));
        if (require_isolated && trace->child_return != direct)
            ++out.child_return_mismatches;
        if (trace->root_negated_return != -trace->child_return)
            ++out.root_negation_mismatches;
        if (require_isolated) {
            const bool quiet_stand = trace->entered_quiescence
                && trace->qsearch_stand_pat_valid
                && !trace->qsearch_forced_capture
                && !trace->qsearch_opponent_threat
                && trace->qsearch_selective_sacs == 0
                && trace->qsearch_moves_searched == 0
                && !trace->path_draw && !trace->fifty_move_draw
                && !trace->tablebase_hit && !trace->tt_cutoff
                && !trace->terminal_hit;
            if (!quiet_stand) ++out.unexpected_qsearch_continuations;
        }
    }
    for (const auto& leaf : out.traced.trace.leaf_evals) {
        const int direct = network.evaluate(leaf.position);
        if (direct != leaf.score) ++out.leaf_eval_mismatches;
        out.saturation_count += std::abs(leaf.score) == 20000;
        if (t3_arm) {
            const int base = t0.evaluate(leaf.position);
            if (leaf.score != rounded_t3(base, t3.residual_parent(leaf.position)))
                ++out.formula_mismatches;
        }
    }
    return out;
}

std::size_t total_mismatches(const ArmAudit& arm, bool isolated) {
    return arm.neutral_mismatches
        + (isolated ? arm.direct_root_mismatches : 0U)
        + arm.child_return_mismatches + arm.root_negation_mismatches
        + arm.leaf_eval_mismatches + arm.formula_mismatches
        + arm.saturation_count
        + (isolated ? arm.unexpected_qsearch_continuations : 0U);
}

void write_arm(std::ostream& out, const ArmAudit& arm,
               std::string_view evaluator_source) {
    out << "{\"expected_direct\":" << arm.expected_direct
        << ",\"actual_depth1\":" << arm.traced.result.score
        << ",\"best_move\":" << json_string(move_id(arm.traced.result.best_move))
        << ",\"nodes\":" << arm.traced.result.nodes
        << ",\"qnodes\":" << arm.traced.trace.qnodes
        << ",\"eval_calls\":" << arm.traced.result.eval_calls
        << ",\"leaf_trace_calls\":" << arm.traced.trace.leaf_evals.size()
        << ",\"neutral_mismatches\":" << arm.neutral_mismatches
        << ",\"direct_root_mismatches\":" << arm.direct_root_mismatches
        << ",\"child_return_mismatches\":" << arm.child_return_mismatches
        << ",\"root_negation_mismatches\":" << arm.root_negation_mismatches
        << ",\"leaf_eval_mismatches\":" << arm.leaf_eval_mismatches
        << ",\"formula_mismatches\":" << arm.formula_mismatches
        << ",\"saturations\":" << arm.saturation_count
        << ",\"unexpected_qsearch_continuations\":"
        << arm.unexpected_qsearch_continuations
        << ",\"move_traces\":[";
    for (std::size_t i = 0; i < arm.traced.trace.moves.size(); ++i) {
        if (i != 0) out << ',';
        write_move_trace(out, arm.traced.trace.moves[i]);
    }
    out << "],\"leaf_evals\":[";
    for (std::size_t i = 0; i < arm.traced.trace.leaf_evals.size(); ++i) {
        if (i != 0) out << ',';
        const auto& leaf = arm.traced.trace.leaf_evals[i];
        const auto* root_trace = find_move_trace(arm.traced.trace, leaf.root_move);
        out << "{\"fen\":" << json_string(leaf.position.to_fen())
            << ",\"stm\":"
            << json_string(leaf.position.side_to_move() == jass::Color::White
                               ? "white" : "black")
            << ",\"root_move\":" << json_string(move_id(leaf.root_move))
            << ",\"stage\":\"static_eval\""
            << ",\"root_resolution_stage\":"
            << json_string(root_trace ? root_trace->first_resolution_stage : "")
            << ",\"ply\":" << leaf.ply
            << ",\"score_stm\":" << leaf.score
            << ",\"evaluator_source\":" << json_string(evaluator_source)
            << '}';
    }
    out << "]}";
}

struct Aggregate {
    std::size_t roots{0};
    std::map<std::string, std::size_t> phases;
    std::size_t mechanical_mismatches{0};
    std::size_t t0_mismatches{0};
    std::size_t t3_mismatches{0};
    std::uint64_t t0_nodes{0};
    std::uint64_t t3_nodes{0};
    std::uint64_t t0_evals{0};
    std::uint64_t t3_evals{0};
    std::uint64_t t0_qnodes{0};
    std::uint64_t t3_qnodes{0};
};

void write_aggregate(std::ostream& out, const Aggregate& a) {
    out << "{\"roots\":" << a.roots << ",\"by_phase\":{";
    bool first = true;
    for (const auto& [name, count] : a.phases) {
        if (!first) out << ',';
        first = false;
        out << json_string(name) << ':' << count;
    }
    out << "},\"mechanical_mismatches\":" << a.mechanical_mismatches
        << ",\"t0_mismatches\":" << a.t0_mismatches
        << ",\"t3_mismatches\":" << a.t3_mismatches
        << ",\"t0_nodes\":" << a.t0_nodes << ",\"t3_nodes\":" << a.t3_nodes
        << ",\"t0_eval_calls\":" << a.t0_evals
        << ",\"t3_eval_calls\":" << a.t3_evals
        << ",\"t0_qnodes\":" << a.t0_qnodes
        << ",\"t3_qnodes\":" << a.t3_qnodes << '}';
}

Aggregate audit_set(const std::vector<FenPosition>& rows,
                    const jass::INetwork& t0,
                    const jass::t3_f6::Network& t3,
                    const jass::SearchParams& params,
                    bool isolated, std::ostream& details, bool& first_detail) {
    Aggregate out;
    for (const auto& row : rows) {
        ++out.roots;
        ++out.phases[phase(row.position)];
        const Mechanics m = mechanics(row.position);
        if (isolated && !m.isolated) ++out.mechanical_mismatches;
        const ArmAudit a0 = audit_arm(row.position, t0, t0, t3, params, false, isolated);
        const ArmAudit a3 = audit_arm(row.position, t3, t0, t3, params, true, isolated);
        out.t0_mismatches += total_mismatches(a0, isolated);
        out.t3_mismatches += total_mismatches(a3, isolated);
        out.t0_nodes += a0.traced.result.nodes;
        out.t3_nodes += a3.traced.result.nodes;
        out.t0_evals += a0.traced.result.eval_calls;
        out.t3_evals += a3.traced.result.eval_calls;
        out.t0_qnodes += a0.traced.trace.qnodes;
        out.t3_qnodes += a3.traced.trace.qnodes;
        if (!first_detail) details << ",\n";
        first_detail = false;
        details << "    {\"fen\":" << json_string(row.fen)
                << ",\"phase\":" << json_string(phase(row.position))
                << ",\"isolated_required\":" << boolean(isolated)
                << ",\"mechanically_isolated\":" << boolean(m.isolated)
                << ",\"t0\":";
        write_arm(details, a0, "CURRICULUM_T0");
        details << ",\"t3\":";
        write_arm(details, a3, "T3_A_F6");
        details << '}';
    }
    return out;
}

bool exact_phase_quota(const Aggregate& aggregate, std::size_t total,
                       std::size_t per_phase) {
    return aggregate.roots == total
        && aggregate.phases == std::map<std::string, std::size_t>{
            {"P0", per_phase}, {"P1", per_phase},
            {"P2", per_phase}, {"P3", per_phase}};
}

int run_contract(const std::string& isolated_path, const std::string& real_path,
                 const std::string& curriculum_path, const std::string& model_path,
                 std::string_view params_spec, std::string_view code_sha,
                 const std::string& output_path) {
    if (code_sha.size() != 40U)
        throw std::runtime_error("code SHA must be full 40-hex");
    if (std::count(params_spec.begin(), params_spec.end(), ',') + 1 != 63)
        throw std::runtime_error("Q00 63-parameter string drift");
    const jass::SearchParams params = jass::parse_search_params(params_spec);
    if (params.qs_forcing_depth != 0 || params.qs_promo_depth != 0
        || params.qs_threat_ext || params.qs_sacs || params.scan_threat_reentry
        || params.drawish_scaling != 0)
        throw std::runtime_error("R0-v3 isolated/Q00 parameter drift");

    std::string error;
    if (jass::t3_f6::sha256_file(curriculum_path, &error)
        != jass::t3_f6::FROZEN_CURRICULUM_SHA256)
        throw std::runtime_error("CURRICULUM SHA mismatch");
    if (jass::t3_f6::sha256_file(model_path, &error)
        != jass::t3_f6::FROZEN_MODEL_SHA256)
        throw std::runtime_error("T3 SHA mismatch");
    auto base = jass::load_eval_network(curriculum_path, &error);
    if (!base) throw std::runtime_error("CURRICULUM load: " + error);
    auto model = jass::t3_f6::load_model(
        model_path, jass::t3_f6::LoadPolicy::FrozenOnly, &error);
    if (!model) throw std::runtime_error("T3 load: " + error);
    jass::t3_f6::Network t3(std::move(base), std::move(*model));
    const jass::INetwork& t0 = *t3.base_network();

    jass::egdb::ensure_initialised();
    const bool egdb_available = jass::egdb::available();
    if (!egdb_available) throw std::runtime_error("EGDB unavailable");
    const auto isolated_rows = read_positions(isolated_path);
    const auto real_rows = read_positions(real_path);

    std::ostringstream details;
    bool first_detail = true;
    const Aggregate a4 = audit_set(
        isolated_rows, t0, t3, params, true, details, first_detail);
    const Aggregate b4 = audit_set(
        real_rows, t0, t3, params, false, details, first_detail);
    const bool gate4a = exact_phase_quota(a4, 128, 32)
        && a4.mechanical_mismatches == 0
        && a4.t0_mismatches == 0 && a4.t3_mismatches == 0;
    const bool gate4b = exact_phase_quota(b4, 256, 64)
        && b4.t0_mismatches == 0 && b4.t3_mismatches == 0;

    const Position terminal = parse("W:W:B1");
    const Position tb = parse("W:WK12,K28:BK7");
    const auto terminal_t0 = run_search(terminal, t0, params, false, 2).result;
    const auto terminal_t3 = run_search(terminal, t3, params, false, 2).result;
    const auto tb_class = jass::probe_endgame(tb);
    const auto tb_t0 = run_search(tb, t0, params, false, 2).result;
    const auto tb_t3 = run_search(tb, t3, params, false, 2).result;
    const bool terminal_precedence = terminal_t0.score == terminal_t3.score
        && terminal_t0.eval_calls == 0 && terminal_t3.eval_calls == 0;
    const bool tablebase_precedence = tb_class != jass::EndgameResult::Unknown
        && tb_t0.score == tb_t3.score
        && tb_t0.eval_calls == 0 && tb_t3.eval_calls == 0;
    const bool gate5 = egdb_available && terminal_precedence && tablebase_precedence;

    const bool passed = gate4a && gate4b && gate5;
    const char* verdict = passed ? "R0_V3_LEAF_SEARCH_CONTRACT_PASS"
        : !gate4a ? "R0_V3_ISOLATED_NEGAMAX_CONTRACT_FAILED"
        : !gate4b ? "R0_V3_REAL_SEARCH_SEMANTICS_FAILED"
        : "R0_V3_TERMINAL_OR_TABLEBASE_PRECEDENCE_FAILED";

    std::ofstream out(output_path);
    if (!out) throw std::runtime_error("cannot create v3 leaf-contract report");
    out << "{\n  \"schema\":\"jass.t3_f6_leaf_search_contract.v3\","
        << "\n  \"passed\":" << boolean(passed) << ','
        << "\n  \"verdict\":" << json_string(verdict) << ','
        << "\n  \"code_sha\":" << json_string(code_sha) << ','
        << "\n  \"model_sha256\":"
        << json_string(jass::t3_f6::FROZEN_MODEL_SHA256) << ','
        << "\n  \"curriculum_sha256\":"
        << json_string(jass::t3_f6::FROZEN_CURRICULUM_SHA256) << ','
        << "\n  \"search_params\":" << json_string(params_spec) << ','
        << "\n  \"same_search_code_and_params\":true,"
        << "\n  \"candidate_only_changes_leaf_source\":true,"
        << "\n  \"dynamic_cutoff_paths_may_differ\":true,"
        << "\n  \"gate4a_isolated_static_leaf\":" << boolean(gate4a) << ','
        << "\n  \"gate4a\":";
    write_aggregate(out, a4);
    out << ",\n  \"gate4b_real_search_semantics\":" << boolean(gate4b) << ','
        << "\n  \"gate4b\":";
    write_aggregate(out, b4);
    out << ",\n  \"gate5_terminal_tablebase\":" << boolean(gate5) << ','
        << "\n  \"egdb_available\":" << boolean(egdb_available) << ','
        << "\n  \"terminal_precedence\":" << boolean(terminal_precedence) << ','
        << "\n  \"terminal_score_t0\":" << terminal_t0.score << ','
        << "\n  \"terminal_score_t3\":" << terminal_t3.score << ','
        << "\n  \"terminal_eval_calls_t0\":" << terminal_t0.eval_calls << ','
        << "\n  \"terminal_eval_calls_t3\":" << terminal_t3.eval_calls << ','
        << "\n  \"tablebase_precedence\":" << boolean(tablebase_precedence) << ','
        << "\n  \"tablebase_score_t0\":" << tb_t0.score << ','
        << "\n  \"tablebase_score_t3\":" << tb_t3.score << ','
        << "\n  \"tablebase_eval_calls_t0\":" << tb_t0.eval_calls << ','
        << "\n  \"tablebase_eval_calls_t3\":" << tb_t3.eval_calls << ','
        << "\n  \"root_details\":[\n" << details.str() << "\n  ]\n}\n";
    std::cout << verdict << " isolated=" << a4.roots
              << " real=" << b4.roots << '\n';
    return 0;
}

class SquareNetwork final : public jass::INetwork {
public:
    int evaluate(const Position& p) const noexcept override {
        const std::uint64_t mix = p.white_men() ^ (p.black_men() << 1U)
                                ^ (p.white_kings() << 2U) ^ (p.black_kings() << 3U);
        const int value = static_cast<int>(mix % 401U) - 200;
        return p.side_to_move() == jass::Color::White ? value : -value;
    }
};

int selftest() {
    SquareNetwork network;
    const Position root = Position::start_position();
    jass::SearchParams params;
    params.qs_forcing_depth = 0;
    params.qs_promo_depth = 0;
    params.qs_threat_ext = false;
    params.qs_sacs = false;
    params.scan_threat_reentry = false;
    const SearchRun control = run_search(root, network, params, false);
    const SearchRun traced = run_search(root, network, params, true);
    if (!same_result(control.result, traced.result)
        || traced.trace.leaf_evals.empty() || traced.trace.leaf_eval_overflow)
        throw std::runtime_error("v3 passive leaf trace selftest failed");
    for (const auto& leaf : traced.trace.leaf_evals)
        if (leaf.score != network.evaluate(leaf.position))
            throw std::runtime_error("v3 leaf STM score selftest failed");
    std::cout << "T3/F6 R0-v3 leaf trace selftest PASS\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string_view(argv[1]) == "--selftest")
            return selftest();
        if (argc == 4 && std::string_view(argv[1]) == "--classify")
            return classify(argv[2], argv[3]);
        if (argc == 9 && std::string_view(argv[1]) == "--contract")
            return run_contract(argv[2], argv[3], argv[4], argv[5],
                                argv[6], argv[7], argv[8]);
        std::cerr << "usage:\n"
            "  t3_f6_leaf_contract_v3 --classify <candidates.fen> <mechanics.tsv>\n"
            "  t3_f6_leaf_contract_v3 --contract <isolated.fen> <real.fen> "
            "<curriculum.pjtw> <t3.json> <search-params> <code-sha> <report.json>\n";
        return 2;
    } catch (const std::exception& error) {
        std::cerr << "t3_f6_leaf_contract_v3: " << error.what() << '\n';
        return 1;
    }
}
