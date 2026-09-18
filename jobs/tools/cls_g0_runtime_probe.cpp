// SPDX-License-Identifier: AGPL-3.0-or-later
// CLS-G0 candidate/parent runtime catastrophe probe.
// Same executable/search configuration for both arms; evaluator bytes only.

#include "pattern_jass_bridge.hpp"
#include "scan_eval.hpp"

#define load_pattern_jass_network load_eval_network
#define main deep_sibling_teacher_main_disabled
#include "../../src/deep_sibling_teacher.cpp"
#undef main
#undef load_pattern_jass_network

#include <array>
#include <bit>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

namespace {

constexpr std::uint64_t PRIMARY_BUDGET = 200'000;
constexpr std::size_t TT_MB = 16;
constexpr int EGDB_CACHE_MB = 256;

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

bool exact_budget_ok(const jass::SearchResult& r, std::uint64_t budget) {
    if (r.nodes == budget && r.stop_reason == jass::SearchStopReason::Nodes
            && r.aborted_iteration) return true;
    return r.nodes > 0 && r.nodes < budget
        && r.stop_reason == jass::SearchStopReason::None
        && r.completed_depth == jass::MAX_PLY
        && r.effective_depth == jass::MAX_PLY
        && !r.aborted_iteration;
}

bool same_public_result(const jass::SearchResult& a, const jass::SearchResult& b) {
    return a.best_move == b.best_move
        && a.score == b.score
        && a.depth == b.depth
        && a.completed_depth == b.completed_depth
        && a.effective_depth == b.effective_depth
        && a.aborted_iteration == b.aborted_iteration
        && a.stop_reason == b.stop_reason
        && a.nodes == b.nodes
        && a.eval_calls == b.eval_calls
        && a.pv == b.pv;
}

struct Observation {
    jass::SearchResult result{};
    jass::SearchDecisionTrace trace{};
    std::uint64_t elapsed_us{0};
};

Observation run_one(const jass::Position& root, const jass::INetwork* network,
                    bool traced) {
    jass::Engine engine(TT_MB);
    engine.use_book(false);
    engine.clear_tt();
    engine.set_position(root);
    jass::SearchLimits limits;
    limits.max_depth = jass::MAX_PLY;
    limits.max_nodes = PRIMARY_BUDGET;
    limits.node_limit_mode = jass::NodeLimitMode::Exact;
    limits.threads = 1;
    limits.nnue = network;
    Observation obs;
    if (traced) limits.search_decision_trace = &obs.trace;
    const auto t0 = std::chrono::steady_clock::now();
    obs.result = engine.search(limits);
    const auto t1 = std::chrono::steady_clock::now();
    obs.elapsed_us = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count());
    if (obs.result.from_book) throw std::runtime_error("CLS-G0 unexpectedly used book");
    if (!exact_budget_ok(obs.result, PRIMARY_BUDGET))
        throw std::runtime_error("CLS-G0 exact node contract mismatch");
    return obs;
}

std::optional<std::uint64_t> exact_nodes_to_depth(
        const jass::SearchDecisionTrace& trace, int target_depth) {
    std::optional<std::uint64_t> value;
    for (const auto& attempt : trace.attempts) {
        if (attempt.depth != target_depth) continue;
        if (!attempt.completed || !attempt.all_actions_searched) continue;
        if (attempt.bound != jass::SearchDecisionBound::Exact) continue;
        value = attempt.nodes_after;  // last exact, full-root receipt wins.
    }
    return value;
}

struct RootRecord {
    std::uint32_t id{0};
    jass::Position position{};
};

std::vector<RootRecord> load_roots(const std::string& parents_path,
                                   const std::unordered_set<std::uint32_t>& ids) {
    std::ifstream in(parents_path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open parents.jnnw");
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size()))
            || std::memcmp(header.data(), "JNNW", 4) != 0)
        throw std::runtime_error("bad parents JNNW header");
    const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);
    for (const auto id : ids) if (id >= declared)
        throw std::runtime_error("root id outside parent corpus");

    std::vector<RootRecord> roots;
    roots.reserve(ids.size());
    DiskRow row{};
    for (std::uint32_t idx = 0; idx < declared; ++idx) {
        if (!read_row(in, row)) throw std::runtime_error("truncated parents JNNW");
        if (!ids.count(idx)) continue;
        if (!valid_row(row) || row.score != 0 || row.wdl != 0)
            throw std::runtime_error("invalid or labelled CLS-G0 parent row");
        jass::MoveList legal;
        const auto position = position_from_row(row);
        jass::generate_legal_moves(position, legal);
        if (legal.size() < 2 || legal.size() > 16)
            throw std::runtime_error("CLS-G0 root branching outside frozen support");
        roots.push_back({idx, position});
    }
    if (in.read(reinterpret_cast<char*>(&row), 1))
        throw std::runtime_error("trailing parent bytes");
    if (roots.size() != ids.size()) throw std::runtime_error("root cardinality drift");
    return roots;
}

void write_row(std::ofstream& out, std::uint32_t root_id, const char* arm,
               const Observation& obs, int target_depth,
               const std::optional<std::uint64_t>& nodes_to_target) {
    const double nps = obs.elapsed_us == 0 ? 0.0
        : static_cast<double>(obs.result.nodes) * 1'000'000.0
            / static_cast<double>(obs.elapsed_us);
    if (!(nps > 0.0)) throw std::runtime_error("nonpositive NPS");
    out << root_id << '\t' << arm << '\t' << obs.result.nodes << '\t'
        << obs.result.completed_depth << '\t' << obs.result.effective_depth << '\t'
        << canonical_move(obs.result.best_move) << '\t' << obs.result.score << '\t'
        << obs.elapsed_us << '\t' << nps << '\t' << target_depth << '\t';
    if (nodes_to_target.has_value()) out << *nodes_to_target;
    out << '\t' << obs.trace.attempts.size() << '\n';
}

void write_id_array(std::ofstream& out, const std::vector<std::uint32_t>& ids) {
    out << '[';
    for (std::size_t i = 0; i < ids.size(); ++i) {
        if (i != 0) out << ',';
        out << ids[i];
    }
    out << ']';
}

}  // namespace

int main(int argc, char** argv) {
    try {
        static_assert(std::endian::native == std::endian::little);
        if (argc != 8) {
            std::cerr << "usage: cls_g0_runtime_probe <parents.jnnw> <root_ids.txt> "
                         "<output.tsv> <report.json> <parent.pjtw> <candidate.pjtw> <egdb_dir>\n";
            return 2;
        }
        if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr
            || std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") != nullptr
            || std::getenv("JASS_T3_F6_MODEL") != nullptr
            || std::getenv("JASS_SEARCH_PARAMS") != nullptr) {
            throw std::runtime_error("forbidden runtime policy/model override");
        }

        const auto ids = load_ids(argv[2]);
        const auto roots = load_roots(argv[1], ids);
        std::string error;
        auto parent = load_eval_network(argv[5], &error);
        if (!parent) throw std::runtime_error("cannot load parent evaluator: " + error);
        error.clear();
        auto candidate = load_eval_network(argv[6], &error);
        if (!candidate) throw std::runtime_error("cannot load candidate evaluator: " + error);
        if (!jass::egdb::init(argv[7], EGDB_CACHE_MB) || !jass::egdb::available())
            throw std::runtime_error("required real EGDB unavailable");

        // Phase 1: prove SearchDecisionTrace is passive on every parent root
        // before any candidate root is measured.
        std::vector<Observation> parent_obs;
        std::vector<int> target_depths;
        std::vector<std::optional<std::uint64_t>> parent_nodes_to_target;
        std::vector<std::uint32_t> parent_missing_roots;
        parent_obs.reserve(roots.size());
        target_depths.reserve(roots.size());
        parent_nodes_to_target.reserve(roots.size());
        for (const auto& root : roots) {
            const auto off = run_one(root.position, parent.get(), false);
            auto on = run_one(root.position, parent.get(), true);
            if (!same_public_result(off.result, on.result))
                throw std::runtime_error("trace-on/off public search mismatch");
            const int target = std::max(1, on.result.completed_depth - 1);
            const auto nodes = exact_nodes_to_depth(on.trace, target);
            if (nodes.has_value() && (*nodes == 0 || *nodes > on.result.nodes))
                throw std::runtime_error("invalid parent same-search nodes-to-depth");
            if (!nodes.has_value()) parent_missing_roots.push_back(root.id);
            parent_obs.push_back(std::move(on));
            target_depths.push_back(target);
            parent_nodes_to_target.push_back(nodes);
        }

        // Phase 2: only after all trace passivity checks succeed, measure candidate.
        // A missing exact/full-root d* receipt is a preregistered hard G0-C FAIL,
        // not a technical exception. Preserve it as missing; never fabricate a surrogate.
        std::vector<Observation> candidate_obs;
        std::vector<std::optional<std::uint64_t>> candidate_nodes_to_target;
        std::vector<std::uint32_t> candidate_missing_roots;
        candidate_obs.reserve(roots.size());
        candidate_nodes_to_target.reserve(roots.size());
        for (std::size_t i = 0; i < roots.size(); ++i) {
            auto obs = run_one(roots[i].position, candidate.get(), true);
            const auto nodes = exact_nodes_to_depth(obs.trace, target_depths[i]);
            if (nodes.has_value() && (*nodes == 0 || *nodes > obs.result.nodes))
                throw std::runtime_error("invalid candidate same-search nodes-to-depth");
            if (!nodes.has_value()) candidate_missing_roots.push_back(roots[i].id);
            candidate_obs.push_back(std::move(obs));
            candidate_nodes_to_target.push_back(nodes);
        }

        std::unordered_set<std::uint32_t> hard_missing_set;
        for (const auto id : parent_missing_roots) hard_missing_set.insert(id);
        for (const auto id : candidate_missing_roots) hard_missing_set.insert(id);
        std::vector<std::uint32_t> hard_missing_roots;
        for (const auto& root : roots) {
            if (hard_missing_set.count(root.id)) hard_missing_roots.push_back(root.id);
        }

        std::ofstream out(argv[3]);
        if (!out) throw std::runtime_error("cannot write output TSV");
        out << "root_id\tarm\tnodes_observed\tcompleted_nominal_depth\teffective_depth\t"
               "bestmove_canonical\tscore_cp\twall_us\tnps\ttarget_depth\tnodes_to_target\t"
               "trace_attempts\n";
        for (std::size_t i = 0; i < roots.size(); ++i) {
            write_row(out, roots[i].id, "parent", parent_obs[i], target_depths[i],
                      parent_nodes_to_target[i]);
            write_row(out, roots[i].id, "candidate", candidate_obs[i], target_depths[i],
                      candidate_nodes_to_target[i]);
        }
        out.close();

        std::ofstream report(argv[4]);
        if (!report) throw std::runtime_error("cannot write report JSON");
        report << "{\n"
               << "  \"schema\": \"jass.cls_g0_runtime_probe.v1\",\n"
               << "  \"roots\": " << roots.size() << ",\n"
               << "  \"budget_nodes\": " << PRIMARY_BUDGET << ",\n"
               << "  \"threads\": 1,\n"
               << "  \"tt_mb\": " << TT_MB << ",\n"
               << "  \"book_enabled\": false,\n"
               << "  \"trace_parity_roots\": " << roots.size() << ",\n"
               << "  \"trace_parity_mismatches\": 0,\n"
               << "  \"nodes_to_depth_rule\": \"LAST_COMPLETED_EXACT_ALL_ACTIONS_SEARCHED_AT_TARGET_DEPTH\",\n"
               << "  \"parent_searches\": " << roots.size() * 2 << ",\n"
               << "  \"candidate_searches\": " << roots.size() << ",\n"
               << "  \"parent_nodes_to_depth_missing_roots\": ";
        write_id_array(report, parent_missing_roots);
        report << ",\n  \"candidate_nodes_to_depth_missing_roots\": ";
        write_id_array(report, candidate_missing_roots);
        report << ",\n  \"hard_nodes_to_depth_failure_count\": " << hard_missing_roots.size()
               << ",\n  \"hard_nodes_to_depth_failure_roots\": ";
        write_id_array(report, hard_missing_roots);
        report << ",\n  \"nodes_to_depth_surrogate_used\": false,\n"
               << "  \"alpha_spent\": 0,\n"
               << "  \"promotion_authorized\": false\n"
               << "}\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "CLS-G0 runtime probe error: " << exc.what() << '\n';
        return 3;
    }
}
