// SPDX-License-Identifier: AGPL-3.0-or-later
// E1-only diagnostic cost attribution for the frozen T3-A/F6 evaluator.
//
// This header is included only by t3_f6_runtime_probe. It adds no production
// activation surface and changes no model, feature, normalization, rounding,
// POV, move generation, search, cache, fit, game, bake, or promotion behavior.
#pragma once

#include "residual_features.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "search_params.hpp"
#include "t3_f6.hpp"
#include "tt.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_set>
#include <utility>
#include <vector>

namespace jass_e1_profile {

using Clock = std::chrono::steady_clock;

inline constexpr std::string_view R0_CORPUS_SHA256 =
    "e22b5d8c8a89ff8491ca096a10219f8936f046a9b22977fcf2cfe48f96b309c5";
inline constexpr std::string_view Q00_SHA256 =
    "61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1";
inline constexpr std::uint64_t ORDER_SEED = 2026092505ULL;

struct FenRow {
    std::string fen;
    jass::Position position;
};

inline std::vector<FenRow> read_fens(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open FEN file: " + path);
    std::vector<FenRow> out;
    std::string line;
    while (std::getline(in, line)) {
        const auto comment = line.find('#');
        if (comment != std::string::npos) line.resize(comment);
        const auto first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) continue;
        const auto last = line.find_last_not_of(" \t\r\n");
        line = line.substr(first, last - first + 1U);
        auto position = jass::Position::from_fen(line);
        if (!position) throw std::runtime_error("invalid FEN: " + line);
        out.push_back({line, *position});
    }
    if (out.empty()) throw std::runtime_error("empty FEN file: " + path);
    return out;
}

inline std::string read_text_exact(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open text file: " + path);
    return std::string(std::istreambuf_iterator<char>(in),
                       std::istreambuf_iterator<char>());
}

inline std::size_t phase_index(const jass::Position& position) {
    const int pieces = std::popcount(position.occupied());
    if (pieces >= 30 && pieces <= 40) return 0U;
    if (pieces >= 20 && pieces <= 29) return 1U;
    if (pieces >= 12 && pieces <= 19) return 2U;
    if (pieces >= 9 && pieces <= 11) return 3U;
    throw std::runtime_error("E1 root outside frozen R0 phase support");
}

inline const char* phase_name(std::size_t index) {
    static constexpr std::array<const char*, 4> names = {"P0", "P1", "P2", "P3"};
    return names.at(index);
}

inline std::unique_ptr<jass::INetwork> load_base(const std::string& curriculum) {
    std::string error;
    if (jass::t3_f6::sha256_file(curriculum, &error)
        != jass::t3_f6::FROZEN_CURRICULUM_SHA256) {
        throw std::runtime_error("CURRICULUM SHA mismatch");
    }
    auto base = jass::load_eval_network(curriculum, &error);
    if (!base) throw std::runtime_error("CURRICULUM load failed: " + error);
    return base;
}

inline jass::t3_f6::Model load_t3(const std::string& model_path) {
    std::string error;
    auto model = jass::t3_f6::load_model(
        model_path, jass::t3_f6::LoadPolicy::FrozenOnly, &error);
    if (!model) throw std::runtime_error("T3-A load failed: " + error);
    return *model;
}

inline int exact_round_score(double score) {
    if (!std::isfinite(score)) throw std::runtime_error("non-finite E1 score");
    return static_cast<int>(std::clamp(std::llround(score), -20000LL, 20000LL));
}

struct LeafProfile {
    jass::residual_features::Profile family{};
    std::uint64_t extract_total_ns{0};
    std::uint64_t base_ns{0};
    std::uint64_t mlp_ns{0};
    std::uint64_t feature_mismatches{0};
    std::uint64_t score_mismatches{0};
};

inline LeafProfile profile_leaves(const std::vector<FenRow>& corpus,
                                  jass::t3_f6::Network& t3) {
    LeafProfile total;
    for (const FenRow& row : corpus) {
        const auto off = jass::residual_features::extract_f6(row.position).all_new();

        jass::residual_features::Profile one;
        const auto extract_start = Clock::now();
        const auto on = jass::residual_features::extract_f6(row.position, &one).all_new();
        total.extract_total_ns += static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                Clock::now() - extract_start).count());
        for (std::size_t i = 0; i < total.family.family_ns.size(); ++i)
            total.family.family_ns[i] += one.family_ns[i];
        total.family.movegen_calls += one.movegen_calls;
        total.family.response_enumerations += one.response_enumerations;

        for (std::size_t i = 0; i < on.size(); ++i) {
            if (std::bit_cast<std::uint32_t>(off[i])
                != std::bit_cast<std::uint32_t>(on[i])) {
                ++total.feature_mismatches;
            }
        }

        const auto base_start = Clock::now();
        const int base_score = t3.base_network()->evaluate(row.position);
        total.base_ns += static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                Clock::now() - base_start).count());

        const auto mlp_start = Clock::now();
        const double residual = t3.model().residual_parent(on);
        total.mlp_ns += static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                Clock::now() - mlp_start).count());

        const int instrumented_score =
            exact_round_score(static_cast<double>(base_score) - residual);
        const int reference_score = t3.evaluate(row.position);
        if (instrumented_score != reference_score) ++total.score_mismatches;
    }

    const std::uint64_t expected_movegen =
        static_cast<std::uint64_t>(corpus.size()) * 2ULL
        + total.family.response_enumerations;
    if (total.family.movegen_calls != expected_movegen) {
        throw std::runtime_error("E1 movegen decomposition drift");
    }
    std::uint64_t family_sum = 0;
    for (const std::uint64_t value : total.family.family_ns) family_sum += value;
    if (family_sum > total.extract_total_ns) {
        throw std::runtime_error("E1 exclusive family timing exceeds extract total");
    }
    return total;
}

struct SearchRun {
    jass::SearchResult result;
    std::uint64_t wall_ns{0};
};

inline SearchRun run_search(const jass::Position& root,
                            const jass::INetwork& network,
                            const jass::SearchParams& params) {
    jass::SearchLimits limits;
    limits.tt_mb = 16;
    limits.threads = 1;
    limits.max_depth = 9;
    limits.params = params;
    limits.nnue = &network;
    jass::TranspositionTable tt;
    tt.resize_mb(limits.tt_mb);
    const auto start = Clock::now();
    const jass::SearchResult result = jass::search(root, limits, tt, {});
    const auto stop = Clock::now();
    return {result, static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count())};
}

struct RootResult {
    std::size_t index{0};
    std::size_t phase{0};
    SearchRun t3;
    SearchRun curriculum;
};

inline std::vector<RootResult> profile_searches(
    const std::vector<FenRow>& roots,
    jass::t3_f6::Network& t3,
    const jass::INetwork& curriculum,
    const jass::SearchParams& params) {
    std::vector<RootResult> out;
    out.reserve(roots.size());
    for (std::size_t i = 0; i < roots.size(); ++i) {
        RootResult row;
        row.index = i;
        row.phase = phase_index(roots[i].position);
        if ((i & 1U) == 0U) {
            row.t3 = run_search(roots[i].position, t3, params);
            row.curriculum = run_search(roots[i].position, curriculum, params);
        } else {
            row.curriculum = run_search(roots[i].position, curriculum, params);
            row.t3 = run_search(roots[i].position, t3, params);
        }
        out.push_back(std::move(row));
    }
    return out;
}

inline void validate_support(const std::vector<FenRow>& corpus,
                             const std::vector<FenRow>& roots,
                             bool preflight) {
    if (corpus.size() != 4096U)
        throw std::runtime_error("E1 R0 corpus cardinality drift");
    const std::size_t per_phase = preflight ? 1U : 32U;
    if (roots.size() != per_phase * 4U)
        throw std::runtime_error("E1 root cardinality drift");
    std::unordered_set<std::string> support;
    support.reserve(corpus.size());
    for (const FenRow& row : corpus) support.insert(row.fen);
    std::array<std::size_t, 4> phases{};
    for (const FenRow& row : roots) {
        if (!support.contains(row.fen))
            throw std::runtime_error("E1 root not present byte-exact in R0 corpus");
        ++phases[phase_index(row.position)];
    }
    for (const std::size_t count : phases) {
        if (count != per_phase) throw std::runtime_error("E1 phase support drift");
    }
}

inline void write_report(const std::string& path,
                         const std::vector<RootResult>& roots,
                         const LeafProfile* leaves,
                         bool preflight) {
    std::uint64_t t3_nodes = 0, curriculum_nodes = 0;
    std::uint64_t t3_evals = 0, curriculum_evals = 0;
    std::uint64_t t3_wall = 0, curriculum_wall = 0;
    for (const RootResult& row : roots) {
        t3_nodes += row.t3.result.nodes;
        curriculum_nodes += row.curriculum.result.nodes;
        t3_evals += row.t3.result.eval_calls;
        curriculum_evals += row.curriculum.result.eval_calls;
        t3_wall += row.t3.wall_ns;
        curriculum_wall += row.curriculum.wall_ns;
    }
    const double nodes_ratio = curriculum_nodes == 0 ? 0.0
        : static_cast<double>(t3_nodes) / static_cast<double>(curriculum_nodes);
    const double t3_nps = t3_wall == 0 ? 0.0
        : static_cast<double>(t3_nodes) * 1.0e9 / static_cast<double>(t3_wall);
    const double curriculum_nps = curriculum_wall == 0 ? 0.0
        : static_cast<double>(curriculum_nodes) * 1.0e9
          / static_cast<double>(curriculum_wall);

    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create E1 report");
    out << std::setprecision(17)
        << "{\n"
        << "  \"schema\": \"jass.t3_f6_e1_cost_profile.v1\",\n"
        << "  \"status\": \""
        << (preflight ? "E1_PREFLIGHT_SIZER_COMPLETE"
                      : "E1_PROFILE_COMPLETE_NONTERMINAL") << "\",\n"
        << "  \"preflight\": " << (preflight ? "true" : "false") << ",\n"
        << "  \"technical_only\": true,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"fit_runs\": 0,\n"
        << "  \"scientific_decision\": false,\n"
        << "  \"model_sha256\": \"" << jass::t3_f6::FROZEN_MODEL_SHA256 << "\",\n"
        << "  \"curriculum_sha256\": \"" << jass::t3_f6::FROZEN_CURRICULUM_SHA256 << "\",\n"
        << "  \"feature_order_sha256\": \"" << jass::t3_f6::FROZEN_FEATURE_ORDER_SHA256 << "\",\n"
        << "  \"feature_count\": " << jass::t3_f6::INPUT_WIDTH << ",\n"
        << "  \"cache_o1\": \"OFF\",\n"
        << "  \"threads\": 1,\n"
        << "  \"tt_mb\": 16,\n"
        << "  \"depth\": 9,\n"
        << "  \"order_seed\": " << ORDER_SEED << ",\n"
        << "  \"primary_wall_window\": \"search_only\",\n"
        << "  \"setup_teardown_in_primary_wall\": false,\n"
        << "  \"root_count\": " << roots.size() << ",\n"
        << "  \"t3_nodes_total\": " << t3_nodes << ",\n"
        << "  \"curriculum_nodes_total\": " << curriculum_nodes << ",\n"
        << "  \"nodes_ratio_t3_over_curriculum\": " << nodes_ratio << ",\n"
        << "  \"t3_eval_calls_total\": " << t3_evals << ",\n"
        << "  \"curriculum_eval_calls_total\": " << curriculum_evals << ",\n"
        << "  \"t3_wall_ns_total\": " << t3_wall << ",\n"
        << "  \"curriculum_wall_ns_total\": " << curriculum_wall << ",\n"
        << "  \"t3_nps\": " << t3_nps << ",\n"
        << "  \"curriculum_nps\": " << curriculum_nps << ",\n"
        << "  \"root_rows\": [\n";
    for (std::size_t i = 0; i < roots.size(); ++i) {
        const RootResult& row = roots[i];
        out << "    {\"index\": " << row.index
            << ", \"phase\": \"" << phase_name(row.phase) << "\""
            << ", \"t3_nodes\": " << row.t3.result.nodes
            << ", \"curriculum_nodes\": " << row.curriculum.result.nodes
            << ", \"t3_eval_calls\": " << row.t3.result.eval_calls
            << ", \"curriculum_eval_calls\": " << row.curriculum.result.eval_calls
            << ", \"t3_wall_ns\": " << row.t3.wall_ns
            << ", \"curriculum_wall_ns\": " << row.curriculum.wall_ns
            << "}" << (i + 1U == roots.size() ? "" : ",") << "\n";
    }
    out << "  ]";

    if (leaves != nullptr) {
        std::uint64_t family_sum = 0;
        for (const std::uint64_t value : leaves->family.family_ns) family_sum += value;
        const std::uint64_t gap = leaves->extract_total_ns - family_sum;
        const double evals = 4096.0;
        out << ",\n"
            << "  \"leaf_positions\": 4096,\n"
            << "  \"instrumentation_feature_mismatches\": "
            << leaves->feature_mismatches << ",\n"
            << "  \"instrumentation_score_mismatches\": "
            << leaves->score_mismatches << ",\n"
            << "  \"extract_instrumented_total_ns\": " << leaves->extract_total_ns << ",\n"
            << "  \"family_sum_ns\": " << family_sum << ",\n"
            << "  \"family_gap_ns\": " << gap << ",\n"
            << "  \"base_ns_total\": " << leaves->base_ns << ",\n"
            << "  \"base_ns_per_eval\": " << static_cast<double>(leaves->base_ns) / evals << ",\n"
            << "  \"mlp_ns_total\": " << leaves->mlp_ns << ",\n"
            << "  \"mlp_ns_per_eval\": " << static_cast<double>(leaves->mlp_ns) / evals << ",\n"
            << "  \"movegen_calls_total\": " << leaves->family.movegen_calls << ",\n"
            << "  \"response_enumerations_f2\": "
            << leaves->family.response_enumerations << ",\n"
            << "  \"families\": {\n";
        for (std::size_t i = 0; i < 5U; ++i) {
            std::uint64_t movegen = 0;
            std::uint64_t child_builds = 0;
            if (i == 0U) movegen = 8192ULL;
            if (i == 1U) {
                movegen = leaves->family.response_enumerations;
                child_builds = leaves->family.response_enumerations;
            }
            const double share_total = leaves->extract_total_ns == 0 ? 0.0
                : static_cast<double>(leaves->family.family_ns[i])
                  / static_cast<double>(leaves->extract_total_ns);
            const double share_family = family_sum == 0 ? 0.0
                : static_cast<double>(leaves->family.family_ns[i])
                  / static_cast<double>(family_sum);
            out << "    \"F" << (i + 1U) << "\": {"
                << "\"ns_total\": " << leaves->family.family_ns[i]
                << ", \"ns_per_eval\": "
                << static_cast<double>(leaves->family.family_ns[i]) / evals
                << ", \"share_of_extract_total\": " << share_total
                << ", \"share_of_family_sum\": " << share_family
                << ", \"movegen_calls_total\": " << movegen
                << ", \"movegen_calls_per_eval\": "
                << static_cast<double>(movegen) / evals
                << ", \"child_builds_total\": " << child_builds
                << ", \"child_builds_per_eval\": "
                << static_cast<double>(child_builds) / evals
                << "}" << (i == 4U ? "" : ",") << "\n";
        }
        out << "  }";
    }
    out << "\n}\n";
}

inline int selftest() {
    auto position = jass::Position::from_fen("W:W31-50:B1-20");
    if (!position) throw std::runtime_error("E1 selftest FEN parse failed");
    const auto off = jass::residual_features::extract_f6(*position).all_new();
    jass::residual_features::Profile profile;
    const auto on = jass::residual_features::extract_f6(*position, &profile).all_new();
    for (std::size_t i = 0; i < on.size(); ++i) {
        if (std::bit_cast<std::uint32_t>(off[i])
            != std::bit_cast<std::uint32_t>(on[i])) {
            throw std::runtime_error("E1 selftest feature instrumentation drift");
        }
    }
    if (profile.movegen_calls != 2ULL + profile.response_enumerations)
        throw std::runtime_error("E1 selftest movegen decomposition drift");
    std::cout << "T3/F6 E1 profiler selftest PASS\n";
    return 0;
}

inline bool requested(int argc, char** argv) {
    if (argc < 2) return false;
    const std::string_view mode = argv[1];
    return mode == "--e1" || mode == "--e1-selftest";
}

inline int run(int argc, char** argv) {
    try {
        if (argc == 2 && std::string_view(argv[1]) == "--e1-selftest")
            return selftest();
        const bool preflight = argc == 9 && std::string_view(argv[8]) == "--preflight";
        if ((argc != 8 && !preflight) || std::string_view(argv[1]) != "--e1") {
            throw std::runtime_error(
                "usage: t3_f6_runtime_probe --e1 <r0-corpus.fen> <roots.fen> "
                "<curriculum.pjtw> <t3.json> <q00.txt> <report.json> [--preflight]");
        }
        const std::string corpus_path = argv[2];
        const std::string roots_path = argv[3];
        const std::string curriculum_path = argv[4];
        const std::string model_path = argv[5];
        const std::string q00_path = argv[6];
        const std::string report_path = argv[7];

        std::string error;
        if (jass::t3_f6::sha256_file(corpus_path, &error) != R0_CORPUS_SHA256)
            throw std::runtime_error("E1 R0 corpus SHA mismatch");
        if (jass::t3_f6::sha256_file(q00_path, &error) != Q00_SHA256)
            throw std::runtime_error("E1 Q00 SHA mismatch");

        const auto corpus = read_fens(corpus_path);
        const auto roots = read_fens(roots_path);
        validate_support(corpus, roots, preflight);
        const std::string q00 = read_text_exact(q00_path);
        const jass::SearchParams params = jass::parse_search_params(q00);

        const jass::t3_f6::Model model = load_t3(model_path);
        jass::t3_f6::Network t3(load_base(curriculum_path), model);
        auto curriculum = load_base(curriculum_path);

        LeafProfile leaves;
        LeafProfile* leaves_ptr = nullptr;
        if (!preflight) {
            leaves = profile_leaves(corpus, t3);
            leaves_ptr = &leaves;
        }
        const auto search_rows = profile_searches(roots, t3, *curriculum, params);
        write_report(report_path, search_rows, leaves_ptr, preflight);

        if (!preflight
            && (leaves.feature_mismatches != 0 || leaves.score_mismatches != 0)) {
            std::cerr << "T3/F6 E1 exactness mismatch\n";
            return 3;
        }
        std::cout << (preflight ? "T3/F6 E1 preflight PASS roots=4\n"
                                : "T3/F6 E1 profile PASS roots=128 leaves=4096\n");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "t3_f6_runtime_probe E1: " << error.what() << '\n';
        return 1;
    }
}

}  // namespace jass_e1_profile
