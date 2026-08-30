// SPDX-License-Identifier: AGPL-3.0-or-later
// T3/F6 O1 exact-cache technical equivalence harness.
//
// This executable is deliberately strength-free. The caller must derive
// roots64.fen from the authenticated 4096-row R0-v4 corpus with the frozen
// jobs/tools/t3_f6_search_profile.py::stratified(corpus,16,2026092505)
// rule before invoking this harness. The harness authenticates the frozen
// model/eval bytes, Gate-B leaf equality on all 4096 rows, then Gate-C search
// equality on exactly those 64 roots and the complete R0-v4 same_result set.
#include "egdb_bridge.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "search_params.hpp"
#include "t3_f6.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

using jass::Position;

struct FenRow {
    std::string fen;
    Position position;
};

Position parse(std::string_view fen) {
    auto position = Position::from_fen(fen);
    if (!position) throw std::runtime_error("invalid FEN: " + std::string(fen));
    return *position;
}

std::vector<FenRow> read_fens(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open FEN file: " + path);
    std::vector<FenRow> rows;
    std::string line;
    while (std::getline(input, line)) {
        const auto comment = line.find('#');
        if (comment != std::string::npos) line.resize(comment);
        const auto first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) continue;
        const auto last = line.find_last_not_of(" \t\r\n");
        line = line.substr(first, last - first + 1U);
        rows.push_back({line, parse(line)});
    }
    return rows;
}

std::string phase(const Position& p) {
    const int pieces = std::popcount(p.occupied());
    if (pieces >= 30 && pieces <= 40) return "P0";
    if (pieces >= 20 && pieces <= 29) return "P1";
    if (pieces >= 12 && pieces <= 19) return "P2";
    if (pieces >= 9 && pieces <= 11) return "P3";
    return "OUT";
}

bool same_result(const jass::SearchResult& a, const jass::SearchResult& b) {
    return a.best_move == b.best_move
        && a.score == b.score
        && a.depth == b.depth
        && a.effective_depth == b.effective_depth
        && a.completed_depth == b.completed_depth
        && a.aborted_iteration == b.aborted_iteration
        && a.stop_reason == b.stop_reason
        && a.nodes == b.nodes
        && a.cutoffs == b.cutoffs
        && a.first_move_cutoffs == b.first_move_cutoffs
        && a.pvs_researches == b.pvs_researches
        && a.moves_searched == b.moves_searched
        && a.eval_calls == b.eval_calls
        && a.scan_verify_probes == b.scan_verify_probes
        && a.scan_verify_cutoffs == b.scan_verify_cutoffs
        && a.scan_threat_reentries == b.scan_threat_reentries
        && a.qnodes == b.qnodes
        && a.qsearch_calls == b.qsearch_calls
        && a.tablebase_probes == b.tablebase_probes
        && a.tablebase_hits == b.tablebase_hits
        && a.tt_probes == b.tt_probes
        && a.tt_hits == b.tt_hits
        && a.terminal_hits == b.terminal_hits
        && a.reductions == b.reductions
        && a.extensions == b.extensions
        && a.root_order_applications == b.root_order_applications
        && a.root_order_failures == b.root_order_failures
        && a.pv == b.pv
        && a.from_book == b.from_book;
}

enum class Budget { Depth1, Depth9, Nodes1k, Nodes10k };

const char* budget_name(Budget budget) noexcept {
    switch (budget) {
        case Budget::Depth1: return "depth1";
        case Budget::Depth9: return "depth9";
        case Budget::Nodes1k: return "nodes1000";
        case Budget::Nodes10k: return "nodes10000";
    }
    return "unknown";
}

jass::SearchLimits limits_for(const jass::SearchParams& params, Budget budget) {
    jass::SearchLimits limits;
    limits.tt_mb = 16;
    limits.threads = 1;
    limits.params = params;
    if (budget == Budget::Depth1) {
        limits.max_depth = 1;
    } else if (budget == Budget::Depth9) {
        limits.max_depth = 9;
    } else {
        // Preserve the R0-v4 exact-node contract used by
        // t3_f6_runtime_contract_v4.cpp for node-budget comparisons.
        limits.max_depth = 6;
        limits.max_nodes = budget == Budget::Nodes1k ? 1000U : 10000U;
        limits.node_limit_mode = jass::NodeLimitMode::Exact;
    }
    return limits;
}

std::unique_ptr<jass::INetwork> load_base(const std::string& curriculum) {
    std::string error;
    auto base = jass::load_eval_network(curriculum, &error);
    if (!base) throw std::runtime_error("CURRICULUM load failed: " + error);
    return base;
}

jass::t3_f6::Model load_t3(const std::string& model_path) {
    std::string error;
    auto model = jass::t3_f6::load_model(
        model_path, jass::t3_f6::LoadPolicy::FrozenOnly, &error);
    if (!model) throw std::runtime_error("T3-A load failed: " + error);
    return *model;
}

jass::SearchResult run_off(const Position& root,
                           const std::string& curriculum,
                           const jass::t3_f6::Model& model,
                           const jass::SearchParams& params,
                           Budget budget) {
    jass::t3_f6::Network network(load_base(curriculum), model);
    auto limits = limits_for(params, budget);
    limits.nnue = &network;
    return jass::search(root, limits);
}

std::pair<jass::SearchResult, jass::t3_f6::CacheStats> run_on(
    const Position& root,
    const std::string& curriculum,
    const jass::t3_f6::Model& model,
    const jass::SearchParams& params,
    Budget budget) {
    std::string error;
    auto session = jass::t3_f6::O1SearchSession::create(
        load_base(curriculum), model, 1, &error);
    if (!session) throw std::runtime_error("O1 session creation failed: " + error);
    auto limits = limits_for(params, budget);
    const auto result = session->run_search(root, limits, &error);
    if (!result) throw std::runtime_error("O1 search rejected: " + error);
    return {*result, session->cache_stats()};
}

const char* boolean(bool value) noexcept { return value ? "true" : "false"; }

int run_contract(int argc, char** argv) {
    if (argc != 7) {
        throw std::runtime_error(
            "usage: t3_f6_exact_cache_o1_contract <r0-corpus.fen> <roots64.fen> "
            "<curriculum.pjtw> <t3.json> <q00-search-params> <report.json>");
    }
    const std::string corpus_path = argv[1];
    const std::string roots_path = argv[2];
    const std::string curriculum_path = argv[3];
    const std::string model_path = argv[4];
    const std::string params_spec = argv[5];
    const std::string report_path = argv[6];

    std::string error;
    if (jass::t3_f6::sha256_file(curriculum_path, &error)
        != jass::t3_f6::FROZEN_CURRICULUM_SHA256) {
        throw std::runtime_error("CURRICULUM SHA256 mismatch");
    }
    if (jass::t3_f6::sha256_file(model_path, &error)
        != jass::t3_f6::FROZEN_MODEL_SHA256) {
        throw std::runtime_error("T3-A SHA256 mismatch");
    }

    const auto corpus = read_fens(corpus_path);
    const auto roots = read_fens(roots_path);
    if (corpus.size() != 4096U)
        throw std::runtime_error("O1 Gate B requires exactly 4096 corpus rows");
    if (roots.size() != 64U)
        throw std::runtime_error("O1 Gate C requires exactly 64 roots");

    std::set<std::string> corpus_fens;
    for (const auto& row : corpus) corpus_fens.insert(row.fen);
    std::set<std::string> root_fens;
    std::map<std::string, std::size_t> phases;
    for (const auto& row : roots) {
        if (!root_fens.insert(row.fen).second)
            throw std::runtime_error("duplicate O1 Gate C root");
        if (!corpus_fens.count(row.fen))
            throw std::runtime_error("O1 Gate C root not present in authenticated corpus");
        ++phases[phase(row.position)];
    }
    const std::map<std::string, std::size_t> expected_phases = {
        {"P0", 16U}, {"P1", 16U}, {"P2", 16U}, {"P3", 16U}};
    if (phases != expected_phases)
        throw std::runtime_error("O1 Gate C phase support drift");

    const auto model = load_t3(model_path);
    const auto params = jass::parse_search_params(params_spec);
    jass::egdb::ensure_initialised();
    if (!jass::egdb::available())
        throw std::runtime_error("EGDB unavailable for O1 Gate C");

    // Gate B: exact leaf equality on all 4096 authenticated R0-v4 positions.
    jass::t3_f6::Network off_leaf(load_base(curriculum_path), model);
    auto on_leaf = jass::t3_f6::O1SearchSession::create(
        load_base(curriculum_path), model, 1, &error);
    if (!on_leaf) throw std::runtime_error("O1 Gate B session creation failed: " + error);

    std::size_t residual_mismatches = 0;
    std::size_t score_mismatches = 0;
    std::size_t nonfinite = 0;
    for (const auto& row : corpus) {
        const double off_residual = off_leaf.residual_parent(row.position);
        const double on_residual = on_leaf->residual_parent(row.position);
        residual_mismatches +=
            std::bit_cast<std::uint64_t>(off_residual)
            != std::bit_cast<std::uint64_t>(on_residual);
        score_mismatches += off_leaf.evaluate(row.position) != on_leaf->evaluate(row.position);
        nonfinite += !std::isfinite(off_residual) || !std::isfinite(on_residual);
    }

    // Replay in reverse order to force real cache hits despite direct-mapped
    // replacement collisions. Then prove an explicit flush returns counters
    // and validity state to the cold-cache contract.
    for (auto it = corpus.rbegin(); it != corpus.rend(); ++it)
        (void)on_leaf->residual_parent(it->position);
    const auto replay_stats = on_leaf->cache_stats();
    const bool real_hit_observed = replay_stats.hits > 0U;
    on_leaf->clear_cache();
    const bool flush_zero = on_leaf->cache_stats().lookups == 0U;
    (void)on_leaf->residual_parent(corpus.front().position);
    const auto cold_after_flush = on_leaf->cache_stats();
    const bool flush_miss = cold_after_flush.hits == 0U
                         && cold_after_flush.misses == 1U
                         && cold_after_flush.extract_f6_executions == 1U;
    const bool gate_b = residual_mismatches == 0U
                     && score_mismatches == 0U
                     && nonfinite == 0U
                     && real_hit_observed
                     && flush_zero
                     && flush_miss;

    constexpr std::array<Budget, 4> budgets = {
        Budget::Depth1, Budget::Depth9, Budget::Nodes1k, Budget::Nodes10k};
    std::size_t search_mismatches = 0;
    std::size_t search_pairs = 0;
    std::uint64_t gate_c_lookups = 0;
    std::uint64_t gate_c_hits = 0;
    std::uint64_t gate_c_misses = 0;
    for (const auto& row : roots) {
        for (const auto budget : budgets) {
            const auto off = run_off(row.position, curriculum_path, model, params, budget);
            const auto [on, stats] = run_on(
                row.position, curriculum_path, model, params, budget);
            ++search_pairs;
            search_mismatches += !same_result(off, on);
            gate_c_lookups += stats.lookups;
            gate_c_hits += stats.hits;
            gate_c_misses += stats.misses;
        }
    }
    const bool gate_c = search_pairs == 64U * budgets.size()
                     && search_mismatches == 0U;

    const char* verdict = !gate_b
        ? "O1_EXACT_CACHE_EQUIVALENCE_FAILED"
        : !gate_c
            ? "O1_EXACT_CACHE_SEARCH_EQUIVALENCE_FAILED"
            : "O1_EXACT_CACHE_ABC_PASS";

    std::ofstream report(report_path);
    if (!report) throw std::runtime_error("cannot create O1 Gate B/C report");
    report << "{\n"
           << "  \"schema\": \"jass.t3_f6_exact_cache_o1_contract.v1\",\n"
           << "  \"verdict\": \"" << verdict << "\",\n"
           << "  \"gate_b_pass\": " << boolean(gate_b) << ",\n"
           << "  \"gate_c_pass\": " << boolean(gate_c) << ",\n"
           << "  \"corpus_rows\": " << corpus.size() << ",\n"
           << "  \"roots\": " << roots.size() << ",\n"
           << "  \"roots_sha256\": \""
           << jass::t3_f6::sha256_file(roots_path, &error) << "\",\n"
           << "  \"order_seed\": 2026092505,\n"
           << "  \"root_selection_external_contract\": \"t3_f6_search_profile.py::stratified(corpus,16,2026092505)\",\n"
           << "  \"residual_mismatches\": " << residual_mismatches << ",\n"
           << "  \"score_mismatches\": " << score_mismatches << ",\n"
           << "  \"nonfinite\": " << nonfinite << ",\n"
           << "  \"gate_b_hits\": " << replay_stats.hits << ",\n"
           << "  \"search_pairs\": " << search_pairs << ",\n"
           << "  \"search_mismatches\": " << search_mismatches << ",\n"
           << "  \"gate_c_cache_lookups\": " << gate_c_lookups << ",\n"
           << "  \"gate_c_cache_hits\": " << gate_c_hits << ",\n"
           << "  \"gate_c_cache_misses\": " << gate_c_misses << ",\n"
           << "  \"strength_games\": 0,\n"
           << "  \"scientific_decision\": false\n"
           << "}\n";
    std::cout << verdict << " search_pairs=" << search_pairs
              << " mismatches=" << search_mismatches << '\n';
    return gate_b && gate_c ? 0 : 2;
}

int selftest() {
    class Square final : public jass::INetwork {
    public:
        int evaluate(const Position& p) const noexcept override {
            return static_cast<int>((p.white_men() ^ p.black_men()) % 401U) - 200;
        }
    };
    std::string error;
    auto session = jass::t3_f6::O1SearchSession::create(
        std::make_unique<Square>(), jass::t3_f6::Model{}, 2, &error);
    if (session || error.empty())
        throw std::runtime_error("O1 threads>1 selftest failed");
    std::cout << "T3/F6 O1 contract selftest PASS\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string_view(argv[1]) == "--selftest")
            return selftest();
        return run_contract(argc, argv);
    } catch (const std::exception& error) {
        std::cerr << "t3_f6_exact_cache_o1_contract: " << error.what() << '\n';
        return 1;
    }
}
