// SPDX-License-Identifier: AGPL-3.0-or-later
// Exact 1000-node diagnostic scorer for preregistered Joint T+D Q1.
// Read-only: no selection, fit, calibration, self-play, strength, or promotion.

#include "pattern_jass_bridge.hpp"
#include "scan_eval.hpp"

// Reuse the audited JNNW parsing, Position conversion and exact-node search
// helper from the DSSD teacher. Disable its entry point and route PJTW v3
// loading through the unified evaluator loader.
#define load_pattern_jass_network load_eval_network
#define main deep_sibling_teacher_main_disabled
#include "deep_sibling_teacher.cpp"
#undef main
#undef load_pattern_jass_network

#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>

namespace {
constexpr std::uint64_t Q1000_BUDGET = 1'000;
}

int main(int argc, char** argv) {
    if (argc < 6 || argc > 10) {
        std::cerr << "usage: joint_td_q1_q1000_score <children.jnnw> <scores.tsv> <report.json> "
                     "<curriculum.pjtw> <egdb_dir> [shard=0] [nshards=1] [tt_mb=16] [egdb_cache_mb=256]\n";
        return 2;
    }
    if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr ||
        std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") != nullptr) {
        std::cerr << "error: move-order policies must be absent for Q1 q1000\n";
        return 2;
    }

    const std::string input_path = argv[1];
    const std::string scores_path = argv[2];
    const std::string report_path = argv[3];
    const std::string curriculum_path = argv[4];
    const std::string egdb_dir = argv[5];
    const int shard = argc >= 7 ? std::stoi(argv[6]) : 0;
    const int nshards = argc >= 8 ? std::stoi(argv[7]) : 1;
    const std::size_t tt_mb = argc >= 9 ? static_cast<std::size_t>(std::max(1, std::stoi(argv[8]))) : 16;
    const std::size_t egdb_cache_mb = argc >= 10 ? static_cast<std::size_t>(std::max(1, std::stoi(argv[9]))) : 256;
    if (shard < 0 || nshards <= 0 || shard >= nshards) {
        std::cerr << "error: invalid shard geometry\n";
        return 2;
    }

    std::string network_error;
    auto curriculum = load_eval_network(curriculum_path, &network_error);
    if (!curriculum) {
        std::cerr << "error: cannot load CURRICULUM: " << network_error << '\n';
        return 3;
    }
    if (!egdb::init(egdb_dir, egdb_cache_mb) || !egdb::available()) {
        std::cerr << "error: real EGDB unavailable at " << egdb_dir << '\n';
        return 3;
    }
    const int tb_cap = egdb::max_pieces();

    std::ifstream in(input_path, std::ios::binary);
    if (!in) {
        std::cerr << "error: cannot open children JNNW\n";
        return 4;
    }
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size())) ||
        std::memcmp(header.data(), "JNNW", 4) != 0) {
        std::cerr << "error: children input is not counted JNNW\n";
        return 4;
    }
    const std::uint32_t n = load_le<std::uint32_t>(header.data() + 4);
    if (n == 0) {
        std::cerr << "error: empty Q1 children corpus\n";
        return 4;
    }

    std::ofstream scores(scores_path);
    if (!scores) {
        std::cerr << "error: cannot create q1000 score TSV\n";
        return 5;
    }
    scores << "row_index\tq1000_parent\tnodes1000\tcompleted_depth1000\teffective_depth1000\t"
              "aborted1000\tstop1000\telapsed_us1000\tpv1000_enters_egdb\n";

    std::uint64_t searched = 0;
    std::uint64_t nodes = 0;
    DiskRow row{};
    for (std::uint32_t i = 0; i < n; ++i) {
        if (!read_row(in, row)) {
            std::cerr << "error: truncated children JNNW at row " << i << '\n';
            return 4;
        }
        if (!valid_row(row)) {
            std::cerr << "error: invalid Q1 child row " << i << '\n';
            return 4;
        }
        if (row.score != 0 || row.wdl != 0) {
            std::cerr << "error: Q1 child target bytes must remain zero at row " << i << '\n';
            return 4;
        }
        if (static_cast<int>(i % static_cast<std::uint32_t>(nshards)) != shard) continue;

        const Position child = position_from_row(row);
        // A new Engine object per sibling makes engine/search state fresh; the
        // helper additionally clears TT immediately before the exact-node search.
        Engine engine(tt_mb);
        engine.use_book(false);
        const SearchObs obs = run_fresh_search(engine, child, curriculum.get(), Q1000_BUDGET, tb_cap);
        scores << i << '\t' << obs.parent_score << '\t' << obs.nodes << '\t'
               << obs.completed_depth << '\t' << obs.effective_depth << '\t'
               << (obs.aborted_iteration ? 1 : 0) << '\t' << static_cast<int>(obs.stop_reason) << '\t'
               << obs.elapsed_us << '\t' << (obs.pv_enters_egdb ? 1 : 0) << '\n';
        ++searched;
        nodes += obs.nodes;
    }
    char trailing = 0;
    if (in.read(&trailing, 1)) {
        std::cerr << "error: children JNNW has trailing bytes\n";
        return 4;
    }
    scores.close();

    std::ofstream report(report_path);
    if (!report) {
        std::cerr << "error: cannot create q1000 report\n";
        return 5;
    }
    report << "{\n"
           << "  \"schema\": \"jass.joint_td_q1_q1000_score.v1\",\n"
           << "  \"input_rows\": " << n << ",\n"
           << "  \"searched_rows\": " << searched << ",\n"
           << "  \"shard\": " << shard << ",\n"
           << "  \"nshards\": " << nshards << ",\n"
           << "  \"budget_nodes\": 1000,\n"
           << "  \"actual_nodes\": " << nodes << ",\n"
           << "  \"book_enabled\": false,\n"
           << "  \"threads_per_search\": 1,\n"
           << "  \"fresh_engine_each_sibling\": true,\n"
           << "  \"fresh_tt_each_search\": true,\n"
           << "  \"node_limit_mode\": \"exact\",\n"
           << "  \"score_convention\": \"higher_is_better_for_parent\",\n"
           << "  \"egdb_max_pieces\": " << tb_cap << ",\n"
           << "  \"fits\": 0,\n"
           << "  \"refits\": 0,\n"
           << "  \"selfplay\": 0,\n"
           << "  \"strength_games\": 0,\n"
           << "  \"promotion_authorized\": false\n"
           << "}\n";
    return 0;
}
