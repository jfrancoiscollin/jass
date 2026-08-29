// SPDX-License-Identifier: AGPL-3.0-or-later
// R0-v2 relative colour-drift, position, transposition and negamax contract.
#include "egdb_bridge.hpp"
#include "endgame.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "residual_features.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "t3_f6.hpp"
#include "tt.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using Features = std::array<float, jass::t3_f6::INPUT_WIDTH>;

jass::Position parse(const std::string& fen) {
    auto p = jass::Position::from_fen(fen);
    if (!p) throw std::runtime_error("bad relative-probe FEN");
    return *p;
}

std::vector<jass::Position> read_positions(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open R0-v2 corpus");
    std::vector<jass::Position> out;
    std::string line;
    while (std::getline(in, line)) {
        const auto hash = line.find('#');
        if (hash != std::string::npos) line.resize(hash);
        if (!line.empty()) out.push_back(parse(line));
    }
    if (out.size() != 4096U) throw std::runtime_error("R0-v2 corpus cardinality drift");
    return out;
}

const char* phase(const jass::Position& p) noexcept {
    const int n = jass::popcount(p.occupied());
    if (n >= 30) return "P0";
    if (n >= 20) return "P1";
    if (n >= 12) return "P2";
    return "P3";
}

jass::Square rotated(jass::Square s) noexcept {
    return static_cast<jass::Square>(51 - static_cast<int>(s));
}

void add_rotated(jass::Position& out, jass::Bitboard pieces, jass::Piece piece) {
    while (pieces) out.add_piece(rotated(jass::pop_lsb(pieces)), piece);
}

jass::Position colour_image(const jass::Position& p) {
    jass::Position out;
    out.clear();
    add_rotated(out, p.black_men(), jass::Piece::WhiteMan);
    add_rotated(out, p.black_kings(), jass::Piece::WhiteKing);
    add_rotated(out, p.white_men(), jass::Piece::BlackMan);
    add_rotated(out, p.white_kings(), jass::Piece::BlackKing);
    out.set_side_to_move(jass::opposite(p.side_to_move()));
    out.set_halfmove_clock(p.halfmove_clock());
    return out;
}

bool exact_features(const Features& a, const Features& b) noexcept {
    for (std::size_t i = 0; i < a.size(); ++i)
        if (std::bit_cast<std::uint32_t>(a[i]) != std::bit_cast<std::uint32_t>(b[i]))
            return false;
    return true;
}

struct State {
    jass::Position pos;
    std::vector<jass::Move> path;
    std::string parent;
};

std::pair<State, State> find_transposition() {
    std::vector<State> frontier{{jass::Position::start_position(), {}, ""}};
    for (int depth = 1; depth <= 6; ++depth) {
        std::map<std::string, State> seen;
        for (const State& state : frontier) {
            jass::MoveList legal;
            jass::generate_legal_moves(state.pos, legal);
            for (const auto& move : legal) {
                State child{state.pos.after(move), state.path, state.pos.to_fen()};
                child.path.push_back(move);
                const std::string key = child.pos.to_fen();
                auto [it, inserted] = seen.emplace(key, child);
                if (!inserted && it->second.parent != child.parent)
                    return {it->second, child};
            }
        }
        frontier.clear();
        frontier.reserve(seen.size());
        for (auto& [key, state] : seen) {
            (void)key;
            frontier.push_back(std::move(state));
        }
        if (frontier.size() > 250000U)
            throw std::runtime_error("transposition search bound exceeded");
    }
    throw std::runtime_error("no explicit legal-path transposition found");
}

double percentile_type7(std::vector<double> values, double p) {
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    const double index = (static_cast<double>(values.size()) - 1.0) * p;
    const auto lo = static_cast<std::size_t>(std::floor(index));
    const auto hi = std::min(lo + 1U, values.size() - 1U);
    return values[lo] + (index - static_cast<double>(lo)) * (values[hi] - values[lo]);
}

struct DriftStats {
    double minimum{0};
    double mean{0};
    double p50{0};
    double p95{0};
    double p99{0};
    double maximum{0};
    std::size_t nonzero{0};
};

DriftStats summarize(const std::vector<int>& signed_values) {
    std::vector<double> values;
    values.reserve(signed_values.size());
    for (int value : signed_values) values.push_back(std::abs(static_cast<double>(value)));
    DriftStats out;
    out.minimum = *std::min_element(values.begin(), values.end());
    out.maximum = *std::max_element(values.begin(), values.end());
    out.mean = std::accumulate(values.begin(), values.end(), 0.0)
             / static_cast<double>(values.size());
    out.p50 = percentile_type7(values, 0.50);
    out.p95 = percentile_type7(values, 0.95);
    out.p99 = percentile_type7(values, 0.99);
    out.nonzero = static_cast<std::size_t>(std::count_if(
        signed_values.begin(), signed_values.end(), [](int v) { return v != 0; }));
    return out;
}

void write_stats(std::ostream& out, const DriftStats& s) {
    out << "{\"min\":" << s.minimum << ",\"mean\":" << s.mean
        << ",\"p50\":" << s.p50 << ",\"p95\":" << s.p95
        << ",\"p99\":" << s.p99 << ",\"max\":" << s.maximum
        << ",\"nonzero_count\":" << s.nonzero << '}';
}

struct EvalRow {
    Features features{};
    double residual{0};
    int t0{0};
    double t3_float{0};
    int t3_engine{0};
};

EvalRow evaluate_row(const jass::Position& p, const jass::t3_f6::Network& t3,
                     const jass::INetwork& t0) {
    EvalRow row;
    row.features = jass::residual_features::extract_f6(p).all_new();
    row.residual = t3.model().residual_parent(row.features);
    row.t0 = t0.evaluate(p);
    row.t3_float = static_cast<double>(row.t0) - row.residual;
    row.t3_engine = t3.evaluate_from_base(p, row.t0);
    return row;
}

bool same_row(const EvalRow& a, const EvalRow& b) noexcept {
    return exact_features(a.features, b.features)
        && std::bit_cast<std::uint64_t>(a.residual) == std::bit_cast<std::uint64_t>(b.residual)
        && a.t0 == b.t0
        && std::bit_cast<std::uint64_t>(a.t3_float) == std::bit_cast<std::uint64_t>(b.t3_float)
        && a.t3_engine == b.t3_engine;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--transposition-selftest") {
            const auto [a, b] = find_transposition();
            if (!(a.pos == b.pos) || a.parent == b.parent)
                throw std::runtime_error("relative transposition selftest failed");
            std::cout << "T3/F6 v2 transposition witness PASS depth=" << a.path.size() << '\n';
            return 0;
        }
        if (argc != 6) {
            std::cerr << "usage: t3_f6_relative_probe <corpus.fen> <curriculum.pjtw> "
                         "<t3.json> <report.json> <permutation-seed>\n";
            return 2;
        }
        const std::uint64_t seed = std::stoull(argv[5]);
        if (seed != 2026091703ULL)
            throw std::runtime_error("R0-v2 permutation seed drift");
        const auto positions = read_positions(argv[1]);
        std::map<std::string, std::size_t> phase_counts;
        for (const auto& p : positions) ++phase_counts[phase(p)];
        const bool phase_balance = phase_counts == std::map<std::string, std::size_t>{
            {"P0", 1024U}, {"P1", 1024U}, {"P2", 1024U}, {"P3", 1024U}};

        std::string err;
        if (jass::t3_f6::sha256_file(argv[2], &err)
            != jass::t3_f6::FROZEN_CURRICULUM_SHA256)
            throw std::runtime_error("CURRICULUM SHA mismatch");
        auto base = jass::load_eval_network(argv[2], &err);
        if (!base) throw std::runtime_error("base load: " + err);
        auto model = jass::t3_f6::load_model(
            argv[3], jass::t3_f6::LoadPolicy::FrozenOnly, &err);
        if (!model) throw std::runtime_error("T3 load: " + err);
        jass::t3_f6::Network t3(std::move(base), std::move(*model));
        const jass::INetwork* t0 = t3.base_network();

        std::vector<EvalRow> expected;
        expected.reserve(positions.size());
        for (const auto& p : positions) expected.push_back(evaluate_row(p, t3, *t0));

        bool gate1 = phase_balance;
        std::size_t replay_mismatches = 0;
        std::vector<std::size_t> order(positions.size());
        std::iota(order.begin(), order.end(), 0U);
        std::mt19937_64 rng(seed);
        std::shuffle(order.begin(), order.end(), rng);
        for (int pass = 0; pass < 3; ++pass) {
            if (pass == 1) std::reverse(order.begin(), order.end());
            if (pass == 2) std::sort(order.begin(), order.end());
            for (std::size_t index : order) {
                const auto reparsed = parse(positions[index].to_fen());
                if (!same_row(expected[index], evaluate_row(reparsed, t3, *t0)))
                    ++replay_mismatches;
            }
        }
        gate1 = gate1 && replay_mismatches == 0;

        std::size_t q_wdl_mismatches = 0;
        struct Labelled {
            jass::Position pos;
            std::array<unsigned char, 17> bytes{};
        };
        for (std::size_t i = 0; i < positions.size(); ++i) {
            Labelled labelled{positions[i], {}};
            labelled.bytes.fill(static_cast<unsigned char>((i * 131U) & 0xffU));
            if (t3.evaluate(labelled.pos) != expected[i].t3_engine) ++q_wdl_mismatches;
        }
        gate1 = gate1 && q_wdl_mismatches == 0;

        bool explicit_transposition = false;
        std::size_t transposition_depth = 0;
        try {
            const auto [a, b] = find_transposition();
            explicit_transposition = a.pos == b.pos && a.parent != b.parent
                && same_row(evaluate_row(a.pos, t3, *t0), evaluate_row(b.pos, t3, *t0));
            transposition_depth = a.path.size();
        } catch (...) {
            explicit_transposition = false;
        }
        gate1 = gate1 && explicit_transposition;

        std::size_t tt_mismatches = 0;
        std::map<std::string, int> phase_taken;
        for (std::size_t i = 0; i < positions.size(); ++i) {
            const std::string name = phase(positions[i]);
            if (phase_taken[name] >= 16) continue;
            ++phase_taken[name];
            jass::SearchLimits limits;
            limits.max_depth = 3;
            limits.nnue = &t3;
            jass::TranspositionTable warm;
            warm.resize_mb(1);
            (void)jass::search(positions[i], limits, warm);
            (void)jass::search(positions[i], limits, warm);
            jass::TranspositionTable cold;
            cold.resize_mb(1);
            (void)jass::search(positions[i], limits, cold);
            if (t3.evaluate(positions[i]) != expected[i].t3_engine) ++tt_mismatches;
        }
        gate1 = gate1 && tt_mismatches == 0
            && phase_taken == std::map<std::string, int>{{"P0",16},{"P1",16},{"P2",16},{"P3",16}};

        std::size_t feature_colour_mismatches = 0;
        std::size_t residual_colour_mismatches = 0;
        std::size_t engine_extra_mismatches = 0;
        std::size_t saturations = 0;
        double max_abs_extra_float = 0.0;
        int max_abs_extra_engine = 0;
        std::vector<int> d0_values, d3_values;
        d0_values.reserve(positions.size());
        d3_values.reserve(positions.size());
        for (std::size_t i = 0; i < positions.size(); ++i) {
            const jass::Position image = colour_image(positions[i]);
            const EvalRow other = evaluate_row(image, t3, *t0);
            if (!exact_features(expected[i].features, other.features)) ++feature_colour_mismatches;
            if (std::bit_cast<std::uint64_t>(expected[i].residual)
                != std::bit_cast<std::uint64_t>(other.residual))
                ++residual_colour_mismatches;
            const int d0 = expected[i].t0 - other.t0;
            const int d3 = expected[i].t3_engine - other.t3_engine;
            const int extra_engine = d3 - d0;
            const double d0_float = static_cast<double>(expected[i].t0)
                                  - static_cast<double>(other.t0);
            const double d3_float = expected[i].t3_float - other.t3_float;
            const double extra_float = d3_float - d0_float;
            d0_values.push_back(d0);
            d3_values.push_back(d3);
            engine_extra_mismatches += extra_engine != 0;
            max_abs_extra_engine = std::max(max_abs_extra_engine, std::abs(extra_engine));
            max_abs_extra_float = std::max(max_abs_extra_float, std::abs(extra_float));
            saturations += std::abs(expected[i].t3_engine) == 20000;
            saturations += std::abs(other.t3_engine) == 20000;
        }
        const bool gate2 = feature_colour_mismatches == 0 && residual_colour_mismatches == 0;
        const bool gate3 = gate2 && engine_extra_mismatches == 0
            && max_abs_extra_float <= 1e-10 && saturations == 0;

        bool negamax_ok = false;
        bool terminal_precedence = false;
        bool tablebase_precedence = false;
        bool egdb_available = false;
        int negamax_depth1_score = 0;
        if (gate1 && gate2 && gate3) {
            const jass::Position root = jass::Position::start_position();
            jass::MoveList moves;
            jass::generate_legal_moves(root, moves);
            int expected_root = std::numeric_limits<int>::min();
            bool quiet = true;
            for (const auto& move : moves) {
                const jass::Position child = root.after(move);
                jass::MoveList replies;
                jass::generate_legal_moves(child, replies);
                quiet = quiet && (replies.empty() || !replies[0].is_capture());
                expected_root = std::max(expected_root, -t3.evaluate(child));
            }
            jass::SearchLimits one;
            one.max_depth = 1;
            one.nnue = &t3;
            jass::TranspositionTable tt;
            tt.resize_mb(1);
            const auto result = jass::search(root, one, tt);
            negamax_depth1_score = result.score;
            negamax_ok = quiet && result.score == expected_root;

            jass::Position terminal;
            terminal.clear();
            terminal.add_piece(static_cast<jass::Square>(1), jass::Piece::BlackMan);
            terminal.set_side_to_move(jass::Color::White);
            jass::SearchLimits off_terminal, on_terminal;
            off_terminal.max_depth = on_terminal.max_depth = 2;
            off_terminal.nnue = t0;
            on_terminal.nnue = &t3;
            jass::TranspositionTable off_tt, on_tt;
            off_tt.resize_mb(1);
            on_tt.resize_mb(1);
            const auto terminal_off = jass::search(terminal, off_terminal, off_tt);
            const auto terminal_on = jass::search(terminal, on_terminal, on_tt);
            terminal_precedence = terminal_off.score == terminal_on.score
                && terminal_off.eval_calls == 0 && terminal_on.eval_calls == 0;

            const jass::Position tb = parse("W:WK12,K28:BK7");
            jass::egdb::ensure_initialised();
            egdb_available = jass::egdb::available();
            const auto tb_class = jass::probe_endgame(tb);
            jass::SearchLimits off_tb, on_tb;
            off_tb.max_depth = on_tb.max_depth = 2;
            off_tb.nnue = t0;
            on_tb.nnue = &t3;
            jass::TranspositionTable off_tb_tt, on_tb_tt;
            off_tb_tt.resize_mb(1);
            on_tb_tt.resize_mb(1);
            const auto tb_off = jass::search(tb, off_tb, off_tb_tt);
            const auto tb_on = jass::search(tb, on_tb, on_tb_tt);
            tablebase_precedence = egdb_available
                && tb_class != jass::EndgameResult::Unknown
                && tb_off.score == tb_on.score
                && tb_off.eval_calls == 0 && tb_on.eval_calls == 0;
        }
        const bool gate4 = negamax_ok && terminal_precedence && tablebase_precedence;
        const bool passed = gate1 && gate2 && gate3 && gate4;
        const char* verdict = passed ? "R0_V2_RELATIVE_PROBE_PASS"
            : !gate1 ? "R0_V2_POSITION_TRANSPOSITION_CONTRACT_FAILED"
            : !gate2 ? "R0_V2_F6_RESIDUAL_INVARIANCE_FAILED"
            : !gate3 ? "R0_V2_ADDITIONAL_SYMMETRY_DRIFT_DETECTED"
            : "R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED";

        const DriftStats t0_stats = summarize(d0_values);
        const DriftStats t3_stats = summarize(d3_values);
        std::ofstream out(argv[4]);
        if (!out) throw std::runtime_error("cannot create R0-v2 relative report");
        out << std::setprecision(17)
            << "{\n  \"schema\": \"jass.t3_f6_relative_contract.v2\",\n"
            << "  \"passed\": " << (passed ? "true" : "false") << ",\n"
            << "  \"verdict\": \"" << verdict << "\",\n"
            << "  \"positions\": " << positions.size() << ",\n"
            << "  \"permutation_seed\": " << seed << ",\n"
            << "  \"model_sha256\": \"" << jass::t3_f6::FROZEN_MODEL_SHA256 << "\",\n"
            << "  \"curriculum_sha256\": \"" << jass::t3_f6::FROZEN_CURRICULUM_SHA256 << "\",\n"
            << "  \"feature_order_sha256\": \"" << jass::t3_f6::FROZEN_FEATURE_ORDER_SHA256 << "\",\n"
            << "  \"gate1_position_transposition\": " << (gate1 ? "true" : "false") << ",\n"
            << "  \"position_replay_mismatches\": " << replay_mismatches << ",\n"
            << "  \"q_wdl_container_mismatches\": " << q_wdl_mismatches << ",\n"
            << "  \"tt_search_state_mismatches\": " << tt_mismatches << ",\n"
            << "  \"explicit_distinct_parent_transposition\": " << (explicit_transposition ? "true" : "false") << ",\n"
            << "  \"explicit_transposition_depth\": " << transposition_depth << ",\n"
            << "  \"gate2_f6_residual_invariance\": " << (gate2 ? "true" : "false") << ",\n"
            << "  \"f6_colour_mismatch_rows\": " << feature_colour_mismatches << ",\n"
            << "  \"residual_colour_mismatch_rows\": " << residual_colour_mismatches << ",\n"
            << "  \"gate3_relative_drift\": " << (gate3 ? "true" : "false") << ",\n"
            << "  \"engine_extra_drift_mismatch_count\": " << engine_extra_mismatches << ",\n"
            << "  \"max_abs_extra_drift_engine_cp\": " << max_abs_extra_engine << ",\n"
            << "  \"max_abs_extra_drift_float_cp\": " << max_abs_extra_float << ",\n"
            << "  \"extra_float_tolerance_cp\": 1e-10,\n"
            << "  \"t0_abs_drift_cp\": ";
        write_stats(out, t0_stats);
        out << ",\n  \"t3_abs_drift_cp\": ";
        write_stats(out, t3_stats);
        out << ",\n  \"saturations\": " << saturations << ",\n"
            << "  \"gate4_negamax_terminal_tb\": " << (gate4 ? "true" : "false") << ",\n"
            << "  \"negamax_single_inversion\": " << (negamax_ok ? "true" : "false") << ",\n"
            << "  \"negamax_depth1_score\": " << negamax_depth1_score << ",\n"
            << "  \"terminal_precedence\": " << (terminal_precedence ? "true" : "false") << ",\n"
            << "  \"egdb_available\": " << (egdb_available ? "true" : "false") << ",\n"
            << "  \"tablebase_precedence\": " << (tablebase_precedence ? "true" : "false") << "\n}\n";
        std::cout << verdict << " positions=" << positions.size()
                  << " extra_mismatches=" << engine_extra_mismatches << '\n';
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "t3_f6_relative_probe: " << e.what() << '\n';
        return 1;
    }
}
