// SPDX-License-Identifier: AGPL-3.0-or-later
// CLS-D diagnostic-only exact-node root profiler for the preregistered
// Jass-vs-Scan depth/growth campaign. No training, tuning, games or promotion.

#include "pattern_jass_bridge.hpp"
#include "scan_eval.hpp"

#define load_pattern_jass_network load_eval_network
#define main deep_sibling_teacher_main_disabled
#include "../../src/deep_sibling_teacher.cpp"
#undef main
#undef load_pattern_jass_network

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

namespace {

constexpr std::array<std::uint64_t, 3> ALLOWED_BUDGETS{5'000, 50'000, 200'000};
constexpr std::size_t TT_MB = 16;
constexpr int EGDB_CACHE_MB = 256;

std::vector<std::uint64_t> parse_budgets(const std::string& text) {
    std::vector<std::uint64_t> out;
    std::set<std::uint64_t> seen;
    std::stringstream stream(text);
    std::string token;
    while (std::getline(stream, token, ',')) {
        if (token.empty()) throw std::runtime_error("empty budget token");
        const auto value = static_cast<std::uint64_t>(std::stoull(token));
        if (std::find(ALLOWED_BUDGETS.begin(), ALLOWED_BUDGETS.end(), value)
                == ALLOWED_BUDGETS.end()) {
            throw std::runtime_error("budget outside frozen CLS-D ladder");
        }
        if (!seen.insert(value).second) throw std::runtime_error("duplicate budget");
        out.push_back(value);
    }
    if (out.empty()) throw std::runtime_error("empty budget ladder");
    return out;
}

std::unordered_set<std::uint32_t> load_ids(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open root id file");
    std::unordered_set<std::uint32_t> out;
    std::uint64_t value = 0;
    while (in >> value) {
        if (value > std::numeric_limits<std::uint32_t>::max())
            throw std::runtime_error("root id overflow");
        if (!out.insert(static_cast<std::uint32_t>(value)).second)
            throw std::runtime_error("duplicate root id");
    }
    if (!in.eof() || out.empty()) throw std::runtime_error("invalid/empty root id file");
    return out;
}

std::string canonical_move(const jass::Move& move) {
    if (move.from == jass::NO_SQUARE || move.to == jass::NO_SQUARE) return "";
    std::ostringstream out;
    out << static_cast<int>(move.from) << (move.is_capture() ? 'x' : '-')
        << static_cast<int>(move.to);
    if (move.is_capture()) {
        out << "|caps=";
        bool first = true;
        std::uint64_t captured = move.captured;
        while (captured) {
            const int bit = std::countr_zero(captured);
            captured &= captured - 1;
            if (!first) out << ',';
            first = false;
            out << static_cast<int>(jass::bit_to_square(bit));
        }
    }
    return out.str();
}

struct RootShape {
    std::size_t branching{0};
    bool forced_capture{false};
    int max_capture_len{0};
};

RootShape root_shape(const jass::Position& pos) {
    jass::MoveList moves;
    jass::generate_legal_moves(pos, moves);
    RootShape shape;
    shape.branching = moves.size();
    for (const auto& move : moves) {
        shape.forced_capture = shape.forced_capture || move.is_capture();
        shape.max_capture_len = std::max(shape.max_capture_len,
                                         static_cast<int>(move.num_captures));
    }
    return shape;
}

bool exact_budget_ok(const jass::SearchResult& r, std::uint64_t budget) {
    if (r.nodes == budget && r.stop_reason == jass::SearchStopReason::Nodes
            && r.aborted_iteration) return true;
    return r.nodes > 0 && r.nodes < budget
        && r.stop_reason == jass::SearchStopReason::None
        && r.completed_depth == jass::MAX_PLY
        && r.effective_depth == jass::MAX_PLY
        && !r.aborted_iteration;
}

struct TimedSearch {
    jass::SearchResult result{};
    jass::BreakdownStats breakdown{};
    std::uint64_t elapsed_us{0};
};

TimedSearch run_one(const jass::Position& root, const jass::INetwork* network,
                    std::uint64_t budget) {
    jass::Engine engine(TT_MB);
    engine.use_book(false);
    engine.clear_tt();
    engine.set_position(root);
    jass::SearchLimits limits;
    limits.max_depth = jass::MAX_PLY;
    limits.max_nodes = budget;
    limits.node_limit_mode = jass::NodeLimitMode::Exact;
    limits.threads = 1;
    limits.nnue = network;
    jass::breakdown_reset();
    const auto t0 = std::chrono::steady_clock::now();
    const auto result = engine.search(limits);
    const auto t1 = std::chrono::steady_clock::now();
    const auto breakdown = jass::breakdown_snapshot();
    if (result.from_book) throw std::runtime_error("CLS-D search unexpectedly used book");
    if (!exact_budget_ok(result, budget))
        throw std::runtime_error("CLS-D exact node contract mismatch");
    return {result, breakdown, static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count())};
}

}  // namespace

int main(int argc, char** argv) {
    try {
        static_assert(std::endian::native == std::endian::little);
        if (argc != 8) {
            std::cerr << "usage: cls_depth_growth_jass <parents.jnnw> <root_ids.txt> "
                         "<output.tsv> <report.json> <curriculum.pjtw> <egdb_dir> "
                         "<budgets_csv>\n";
            return 2;
        }
        if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr
            || std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") != nullptr
            || std::getenv("JASS_T3_F6_MODEL") != nullptr
            || std::getenv("JASS_SEARCH_PARAMS") != nullptr) {
            throw std::runtime_error("forbidden runtime policy/model override");
        }
        const std::string parents_path = argv[1];
        const auto ids = load_ids(argv[2]);
        const std::string output_path = argv[3];
        const std::string report_path = argv[4];
        const std::string curriculum_path = argv[5];
        const std::string egdb_dir = argv[6];
        const auto budgets = parse_budgets(argv[7]);

        std::string error;
        auto curriculum = load_eval_network(curriculum_path, &error);
        if (!curriculum) throw std::runtime_error("cannot load CURRICULUM: " + error);
        if (!jass::egdb::init(egdb_dir, EGDB_CACHE_MB) || !jass::egdb::available())
            throw std::runtime_error("required real EGDB unavailable");

        std::ifstream in(parents_path, std::ios::binary);
        if (!in) throw std::runtime_error("cannot open parents.jnnw");
        std::array<char, 8> header{};
        if (!in.read(header.data(), static_cast<std::streamsize>(header.size()))
            || std::memcmp(header.data(), "JNNW", 4) != 0)
            throw std::runtime_error("bad parents JNNW header");
        const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);
        for (const auto id : ids) if (id >= declared) throw std::runtime_error("root id outside parent corpus");

        std::ofstream out(output_path);
        if (!out) throw std::runtime_error("cannot open CLS-D Jass output");
        out << "root_id\tbudget\tnodes_observed\tcompleted_nominal_depth\teffective_depth\t"
               "bestmove_canonical\tscore_cp\twall_us\tnps\tbranching\tforced_capture_at_root\t"
               "max_capture_len\tpieces\tstm\tqnodes\teval_calls\ttt_probes\ttt_hits\tcutoffs\t"
               "first_move_cutoffs\tpvs_researches\tmoves_searched\tbreakdown_total_ns\t"
               "breakdown_eval_ns\tbreakdown_movegen_ns\tbreakdown_apply_ns\n";

        std::uint64_t searches = 0, nodes = 0, elapsed_us = 0;
        DiskRow row{};
        for (std::uint32_t idx = 0; idx < declared; ++idx) {
            if (!read_row(in, row)) throw std::runtime_error("truncated parents JNNW");
            if (!ids.count(idx)) continue;
            if (!valid_row(row) || row.score != 0 || row.wdl != 0)
                throw std::runtime_error("invalid or labelled CLS-D parent row");
            const auto root = position_from_row(row);
            const auto shape = root_shape(root);
            if (shape.branching < 2 || shape.branching > 16)
                throw std::runtime_error("CLS-D root branching outside frozen support");
            const int pieces = std::popcount(row.wm | row.wk | row.bm | row.bk);
            for (const auto budget : budgets) {
                const auto obs = run_one(root, curriculum.get(), budget);
                const auto& r = obs.result;
                const double nps = obs.elapsed_us == 0 ? 0.0
                    : static_cast<double>(r.nodes) * 1'000'000.0 / static_cast<double>(obs.elapsed_us);
                out << idx << '\t' << budget << '\t' << r.nodes << '\t' << r.completed_depth
                    << '\t' << r.effective_depth << '\t' << canonical_move(r.best_move)
                    << '\t' << r.score << '\t' << obs.elapsed_us << '\t' << nps
                    << '\t' << shape.branching << '\t' << (shape.forced_capture ? 1 : 0)
                    << '\t' << shape.max_capture_len << '\t' << pieces << '\t'
                    << static_cast<int>(row.stm) << '\t' << r.qnodes << '\t' << r.eval_calls
                    << '\t' << r.tt_probes << '\t' << r.tt_hits << '\t' << r.cutoffs
                    << '\t' << r.first_move_cutoffs << '\t' << r.pvs_researches
                    << '\t' << r.moves_searched << '\t' << obs.breakdown.total_ns
                    << '\t' << obs.breakdown.eval_ns << '\t' << obs.breakdown.movegen_ns
                    << '\t' << obs.breakdown.apply_ns << '\n';
                ++searches; nodes += r.nodes; elapsed_us += obs.elapsed_us;
            }
        }
        if (in.read(reinterpret_cast<char*>(&row), 1)) throw std::runtime_error("trailing parent bytes");
        if (searches != ids.size() * budgets.size()) throw std::runtime_error("CLS-D search cardinality drift");
        out.close();

        std::ofstream report(report_path);
        if (!report) throw std::runtime_error("cannot write CLS-D Jass report");
        report << "{\n"
               << "  \"schema\": \"jass.cls_depth_growth_jass.v1\",\n"
               << "  \"diagnostic_only\": true,\n"
               << "  \"roots\": " << ids.size() << ",\n"
               << "  \"searches\": " << searches << ",\n"
               << "  \"nodes\": " << nodes << ",\n"
               << "  \"elapsed_us\": " << elapsed_us << ",\n"
               << "  \"tt_mb\": " << TT_MB << ",\n"
               << "  \"threads\": 1,\n"
               << "  \"book_enabled\": false,\n"
               << "  \"node_limit_mode\": \"exact\",\n"
               << "  \"fresh_engine_per_root_budget\": true,\n"
               << "  \"cross_engine_depth_curve_available\": false,\n"
               << "  \"labels_read\": 0,\n"
               << "  \"fits\": 0,\n"
               << "  \"strength_games\": 0,\n"
               << "  \"promotion_authorized\": false\n"
               << "}\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "CLS-D Jass profiler error: " << exc.what() << '\n';
        return 3;
    }
}
