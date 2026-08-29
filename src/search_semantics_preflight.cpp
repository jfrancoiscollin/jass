// SPDX-License-Identifier: AGPL-3.0-or-later
// Technical-only preflight for L3_JASS_SCAN_SEARCH_SEMANTICS_ATTRIBUTION_V1.
// It uses deterministic synthetic/random-play legal positions only and emits
// mechanics/contract sentinels, never scientific labels or accuracy metrics.

#include "egdb_bridge.hpp"
#include "engine.hpp"
#include "movegen.hpp"
#include "scan_eval.hpp"
#include "search_semantics_alt.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using jass::MoveList;
using jass::Position;
using jass::SearchLimits;
using jass::SearchParams;
using jass::SearchResult;

constexpr std::uint64_t CORE_BUDGET = 4'000;
constexpr std::uint64_t ACT_BUDGET = 20'000;
constexpr std::uint64_t RNG_SEED = 2026091400ULL;  // technical-only, not a cohort seed

bool same_core(const SearchResult& a, const SearchResult& b) {
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
        && a.qsearch_calls == b.qsearch_calls
        && a.qnodes == b.qnodes
        && a.tt_probes == b.tt_probes
        && a.tt_hits == b.tt_hits
        && a.scan_verify_probes == b.scan_verify_probes
        && a.scan_verify_cutoffs == b.scan_verify_cutoffs
        && a.scan_threat_reentries == b.scan_threat_reentries
        && a.pv == b.pv
        && a.from_book == b.from_book;
}

SearchResult production_run(const Position& pos, const jass::INetwork* net,
                            std::uint64_t budget, const SearchParams& params) {
    jass::Engine engine(16);
    engine.use_book(false);
    engine.clear_tt();
    engine.set_position(pos);
    SearchLimits limits;
    limits.max_depth = jass::MAX_PLY;
    limits.max_nodes = budget;
    limits.node_limit_mode = jass::NodeLimitMode::Exact;
    limits.threads = 1;
    limits.nnue = net;
    limits.params = params;
    return engine.search(limits);
}

SearchResult attribution_run(const Position& pos, const jass::INetwork* net,
                             std::uint64_t budget, const SearchParams& params) {
    jass::AttributionEngine engine(16);
    engine.use_book(false);
    engine.clear_tt();
    engine.set_position(pos);
    SearchLimits limits;
    limits.max_depth = jass::MAX_PLY;
    limits.max_nodes = budget;
    limits.node_limit_mode = jass::NodeLimitMode::Exact;
    limits.threads = 1;
    limits.nnue = net;
    limits.params = params;
    return engine.search(limits);
}

bool exact_budget_ok(const SearchResult& r, std::uint64_t budget) {
    if (r.nodes == budget
        && r.stop_reason == jass::SearchStopReason::Nodes
        && r.aborted_iteration) return true;
    return r.nodes > 0 && r.nodes < budget
        && r.stop_reason == jass::SearchStopReason::None
        && r.completed_depth == jass::MAX_PLY
        && r.effective_depth == jass::MAX_PLY
        && !r.aborted_iteration;
}

SearchParams arm_params(int arm) {
    SearchParams p{};
    switch (arm) {
        case 0: break;
        case 1: p.scan_verify_pruning = true; break;
        case 2: p.qs_threat_ext = false; p.scan_threat_reentry = true; break;
        case 3: p.ext_single_reply = true; break;
        case 4: p.scan_lmr_semantics = true; break;
        case 5: p.scan_probabilistic_ordering = true; break;
        case 6: p.disable_null_move = true; break;
        default: throw std::runtime_error("invalid arm");
    }
    return p;
}

std::vector<Position> technical_positions() {
    // Legal states reached only by playing legal moves from the start position.
    // Fixed RNG and no evaluator/search information enter selection.
    std::mt19937_64 rng(RNG_SEED);
    std::vector<Position> out;
    out.reserve(64);
    for (int game = 0; game < 16 && out.size() < 64U; ++game) {
        Position p = Position::start_position();
        for (int ply = 0; ply < 140 && out.size() < 64U; ++ply) {
            MoveList moves;
            jass::generate_legal_moves(p, moves);
            if (moves.empty()) break;
            const std::size_t pick = static_cast<std::size_t>(rng() % moves.size());
            p = p.after(moves[pick]);
            MoveList next;
            jass::generate_legal_moves(p, next);
            if (next.empty()) break;
            const int pieces = std::popcount(p.occupied());
            if (pieces >= 9 && (ply % 7 == 3)) out.push_back(p);
        }
    }
    if (out.size() < 32U) throw std::runtime_error("technical position generation too sparse");
    return out;
}

struct Activation {
    std::uint64_t j0_null{0};
    std::uint64_t verify{0};
    std::uint64_t threat{0};
    std::uint64_t single_reply{0};
    std::uint64_t lmr_reductions{0};
    std::uint64_t lmr_reduced_plies{0};
    std::uint64_t order_good{0};
    std::uint64_t order_bad{0};
    std::uint64_t j6_null{0};
    std::uint64_t exact_budget_failures{0};
};

void add_activation(Activation& a, int arm, const SearchResult& r) {
    if (arm == 0) a.j0_null += r.null_probes;
    if (arm == 1) a.verify += r.scan_verify_probes;
    if (arm == 2) a.threat += r.scan_threat_reentries;
    if (arm == 3) a.single_reply += r.single_reply_extensions;
    if (arm == 4) {
        a.lmr_reductions += r.reductions;
        a.lmr_reduced_plies += r.reduced_plies;
    }
    if (arm == 5) {
        a.order_good += r.ordering_good_updates;
        a.order_bad += r.ordering_bad_updates;
    }
    if (arm == 6) a.j6_null += r.null_probes;
}

void write_json(const std::string& path, std::size_t positions,
                std::size_t core_cases, std::size_t deterministic_cases,
                const Activation& a) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot write preflight report");
    out << "{\n"
        << "  \"schema\": \"jass.search_semantics_technical_preflight.v1\",\n"
        << "  \"protocol\": \"L3_JASS_SCAN_SEARCH_SEMANTICS_ATTRIBUTION_V1_20260829\",\n"
        << "  \"technical_positions\": " << positions << ",\n"
        << "  \"j0_production_equivalence_cases\": " << core_cases << ",\n"
        << "  \"determinism_cases\": " << deterministic_cases << ",\n"
        << "  \"j0_null_probes\": " << a.j0_null << ",\n"
        << "  \"j1_scan_verify_probes\": " << a.verify << ",\n"
        << "  \"j2_scan_threat_reentries\": " << a.threat << ",\n"
        << "  \"j3_single_reply_extensions\": " << a.single_reply << ",\n"
        << "  \"j4_reductions\": " << a.lmr_reductions << ",\n"
        << "  \"j4_reduced_plies\": " << a.lmr_reduced_plies << ",\n"
        << "  \"j5_ordering_good_updates\": " << a.order_good << ",\n"
        << "  \"j5_ordering_bad_updates\": " << a.order_bad << ",\n"
        << "  \"j6_null_probes\": " << a.j6_null << ",\n"
        << "  \"exact_budget_failures\": " << a.exact_budget_failures << ",\n"
        << "  \"scientific_data\": 0,\n"
        << "  \"scores_interpreted\": 0,\n"
        << "  \"fits\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"training\": false,\n"
        << "  \"tuning\": false,\n"
        << "  \"bake\": false,\n"
        << "  \"promotion\": false,\n"
        << "  \"verdict\": \"TECHNICAL_PASS\"\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 4) {
            std::cerr << "usage: jass_search_semantics_preflight <curriculum.pjtw> <egdb_dir> <report.json>\n";
            return 2;
        }
        std::string error;
        auto net = jass::load_eval_network(argv[1], &error);
        if (!net) throw std::runtime_error("cannot load frozen CURRICULUM: " + error);
        if (!jass::egdb::init(argv[2], 256) || !jass::egdb::available())
            throw std::runtime_error("real EGDB unavailable");

        const auto positions = technical_positions();
        std::size_t core_cases = 0;
        std::size_t deterministic_cases = 0;

        // J0 must be behaviorally identical to current production search. Use
        // high-material legal states to avoid a technical comparison being
        // dominated by endgame-tablebase termination.
        for (const Position& p : positions) {
            if (std::popcount(p.occupied()) < 20 || core_cases >= 8U) continue;
            const SearchParams j0 = arm_params(0);
            const SearchResult prod = production_run(p, net.get(), CORE_BUDGET, j0);
            const SearchResult alt = attribution_run(p, net.get(), CORE_BUDGET, j0);
            if (!same_core(prod, alt))
                throw std::runtime_error("J0/current-production search equivalence failed");
            if (!exact_budget_ok(prod, CORE_BUDGET) || !exact_budget_ok(alt, CORE_BUDGET))
                throw std::runtime_error("J0 exact-node budget contract failed");
            ++core_cases;
        }
        if (core_cases < 6U) throw std::runtime_error("insufficient J0 equivalence cases");

        // Determinism is checked independently on an exact-node HOME run.
        for (std::size_t i = 0; i < positions.size() && deterministic_cases < 6U; ++i) {
            const SearchResult a = attribution_run(positions[i], net.get(), CORE_BUDGET, arm_params(0));
            const SearchResult b = attribution_run(positions[i], net.get(), CORE_BUDGET, arm_params(0));
            if (!same_core(a, b)) throw std::runtime_error("Attribution J0 determinism failed");
            ++deterministic_cases;
        }

        Activation activation{};
        std::array<bool, 7> done{};
        for (const Position& p : positions) {
            for (int arm = 0; arm <= 6; ++arm) {
                if (done[static_cast<std::size_t>(arm)] && arm != 0 && arm != 6) continue;
                const SearchResult r = attribution_run(p, net.get(), ACT_BUDGET, arm_params(arm));
                if (!exact_budget_ok(r, ACT_BUDGET)) ++activation.exact_budget_failures;
                add_activation(activation, arm, r);
                if (arm == 1 && activation.verify > 0) done[1] = true;
                if (arm == 2 && activation.threat > 0) done[2] = true;
                if (arm == 3 && activation.single_reply > 0) done[3] = true;
                if (arm == 4 && activation.lmr_reductions > 0 && activation.lmr_reduced_plies > 0) done[4] = true;
                if (arm == 5 && activation.order_good > 0 && activation.order_bad > 0) done[5] = true;
            }
            if (done[1] && done[2] && done[3] && done[4] && done[5]
                && activation.j0_null > 0) break;
        }

        if (activation.exact_budget_failures != 0)
            throw std::runtime_error("exact-node activation budget contract failed");
        if (activation.j0_null == 0) throw std::runtime_error("J0 null-move sentinel inactive");
        if (activation.verify == 0) throw std::runtime_error("J1 Scan verification sentinel inactive");
        if (activation.threat == 0) throw std::runtime_error("J2 Scan threat sentinel inactive");
        if (activation.single_reply == 0) throw std::runtime_error("J3 single-reply sentinel inactive");
        if (activation.lmr_reductions == 0 || activation.lmr_reduced_plies == 0)
            throw std::runtime_error("J4 Scan LMR sentinel inactive");
        if (activation.order_good == 0 || activation.order_bad == 0)
            throw std::runtime_error("J5 Scan ordering sentinel inactive");
        if (activation.j6_null != 0)
            throw std::runtime_error("J6 null-move disabling sentinel failed");

        write_json(argv[3], positions.size(), core_cases, deterministic_cases, activation);
        std::cout << "SEARCH_SEMANTICS_TECHNICAL_PREFLIGHT_PASS\n";
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "error: " << ex.what() << '\n';
        return 1;
    }
}
