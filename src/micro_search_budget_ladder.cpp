// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-Francois Collin
//
// Exploratory M1 budget ladder for L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.
//
// This translation unit deliberately reuses the frozen DSSD teacher's exact
// production-search implementation and unified ScanEval/PJTW loader.  It reads
// the already-emitted Phase-C child JNNW rows and reruns each child from a
// freshly cleared TT at the preregistered node budgets only.  No label is read
// or selected here and no model is fit here.

#include "pattern_jass_bridge.hpp"
#include "scan_eval.hpp"

#define load_pattern_jass_network load_eval_network
#define main deep_sibling_teacher_main_disabled
#include "deep_sibling_teacher.cpp"
#undef main
#undef load_pattern_jass_network

#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>

namespace {

constexpr std::array<std::uint64_t, 6> MICRO_BUDGETS{
    125, 250, 500, 1000, 2000, 5000
};

struct LadderCounters {
    std::uint64_t source_rows{0};
    std::uint64_t processed_rows{0};
    std::uint64_t invalid_rows{0};
    std::array<std::uint64_t, MICRO_BUDGETS.size()> searches{};
    std::array<std::uint64_t, MICRO_BUDGETS.size()> nodes{};
    std::array<std::uint64_t, MICRO_BUDGETS.size()> elapsed_us{};
};

void write_ladder_report(const std::string& path,
                         std::uint32_t declared,
                         int shard,
                         int nshards,
                         int tb_cap,
                         std::size_t tt_mb,
                         const LadderCounters& c) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open ladder report output");
    out << "{\n"
        << "  \"schema\": \"jass.micro_search_budget_ladder_extract.v1\",\n"
        << "  \"input_children\": " << declared << ",\n"
        << "  \"shard\": " << shard << ",\n"
        << "  \"nshards\": " << nshards << ",\n"
        << "  \"budgets_nodes\": [125, 250, 500, 1000, 2000, 5000],\n"
        << "  \"book_enabled\": false,\n"
        << "  \"threads_per_search\": 1,\n"
        << "  \"fresh_tt_each_search\": true,\n"
        << "  \"node_limit_mode\": \"exact\",\n"
        << "  \"tt_mb\": " << tt_mb << ",\n"
        << "  \"egdb_max_pieces\": " << tb_cap << ",\n"
        << "  \"source_rows\": " << c.source_rows << ",\n"
        << "  \"processed_rows\": " << c.processed_rows << ",\n"
        << "  \"invalid_rows\": " << c.invalid_rows << ",\n"
        << "  \"searches_by_budget\": {\n";
    for (std::size_t i = 0; i < MICRO_BUDGETS.size(); ++i) {
        out << "    \"" << MICRO_BUDGETS[i] << "\": " << c.searches[i]
            << (i + 1 == MICRO_BUDGETS.size() ? "\n" : ",\n");
    }
    out << "  },\n  \"nodes_by_budget\": {\n";
    for (std::size_t i = 0; i < MICRO_BUDGETS.size(); ++i) {
        out << "    \"" << MICRO_BUDGETS[i] << "\": " << c.nodes[i]
            << (i + 1 == MICRO_BUDGETS.size() ? "\n" : ",\n");
    }
    out << "  },\n  \"elapsed_us_by_budget\": {\n";
    for (std::size_t i = 0; i < MICRO_BUDGETS.size(); ++i) {
        out << "    \"" << MICRO_BUDGETS[i] << "\": " << c.elapsed_us[i]
            << (i + 1 == MICRO_BUDGETS.size() ? "\n" : ",\n");
    }
    out << "  },\n"
        << "  \"labels_read\": 0,\n"
        << "  \"fits\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"promotion_authorized\": false\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "JNNW tool currently requires a little-endian host");
    if (argc < 6 || argc > 10) {
        std::cerr << "usage: jass_micro_search_budget_ladder <children.jnnw> "
                     "<ladder.tsv> <report.json> <curriculum.pjtw> <egdb_dir> "
                     "[shard=0] [nshards=1] [tt_mb=16] [egdb_cache_mb=256]\n";
        return 2;
    }
    if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr) {
        std::cerr << "error: JASS_TB_MOVE_ORDER_POLICY must be absent for micro-search teacher\n";
        return 2;
    }

    const std::string input_path = argv[1];
    const std::string ladder_path = argv[2];
    const std::string report_path = argv[3];
    const std::string curriculum_path = argv[4];
    const std::string egdb_dir = argv[5];
    const int shard = argc >= 7 ? std::stoi(argv[6]) : 0;
    const int nshards = argc >= 8 ? std::stoi(argv[7]) : 1;
    const std::size_t tt_mb = argc >= 9
        ? static_cast<std::size_t>(std::max(1, std::stoi(argv[8]))) : DEFAULT_TT_MB;
    const int egdb_cache_mb = argc >= 10 ? std::max(64, std::stoi(argv[9])) : 256;
    if (nshards <= 0 || shard < 0 || shard >= nshards) {
        std::cerr << "error: invalid shard/nshards\n";
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
    if (tb_cap <= 0) {
        std::cerr << "error: invalid EGDB max pieces\n";
        return 3;
    }

    std::ifstream in(input_path, std::ios::binary);
    if (!in) {
        std::cerr << "error: cannot open input\n";
        return 4;
    }
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size()))
        || std::memcmp(header.data(), "JNNW", 4) != 0) {
        std::cerr << "error: input is not counted JNNW\n";
        return 4;
    }
    const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);

    std::ofstream out(ladder_path);
    if (!out) {
        std::cerr << "error: cannot open ladder output\n";
        return 5;
    }
    out << "row_index";
    for (const auto budget : MICRO_BUDGETS) out << "\tq" << budget << "_parent";
    for (const auto budget : MICRO_BUDGETS) out << "\tnodes" << budget;
    for (const auto budget : MICRO_BUDGETS) out << "\tcompleted_depth" << budget;
    for (const auto budget : MICRO_BUDGETS) out << "\teffective_depth" << budget;
    for (const auto budget : MICRO_BUDGETS) out << "\telapsed_us" << budget;
    for (const auto budget : MICRO_BUDGETS) out << "\tpv" << budget << "_enters_egdb";
    out << '\n';

    Engine engine(tt_mb);
    engine.use_book(false);
    LadderCounters counters{};
    DiskRow row{};
    for (std::uint32_t idx = 0; idx < declared; ++idx) {
        if (!read_row(in, row)) {
            std::cerr << "error: truncated JNNW at row " << idx << '\n';
            return 4;
        }
        ++counters.source_rows;
        if (static_cast<int>(idx % static_cast<std::uint32_t>(nshards)) != shard) continue;
        ++counters.processed_rows;
        if (!valid_row(row)) {
            ++counters.invalid_rows;
            continue;
        }
        if (row.score != 0 || row.wdl != 0) {
            std::cerr << "error: child target bytes are not zero at row " << idx << '\n';
            return 4;
        }
        const Position child = position_from_row(row);
        std::array<SearchObs, MICRO_BUDGETS.size()> obs{};
        for (std::size_t b = 0; b < MICRO_BUDGETS.size(); ++b) {
            obs[b] = run_fresh_search(engine, child, curriculum.get(), MICRO_BUDGETS[b], tb_cap);
            ++counters.searches[b];
            counters.nodes[b] += obs[b].nodes;
            counters.elapsed_us[b] += obs[b].elapsed_us;
        }

        out << idx;
        for (const auto& s : obs) out << '\t' << s.parent_score;
        for (const auto& s : obs) out << '\t' << s.nodes;
        for (const auto& s : obs) out << '\t' << s.completed_depth;
        for (const auto& s : obs) out << '\t' << s.effective_depth;
        for (const auto& s : obs) out << '\t' << s.elapsed_us;
        for (const auto& s : obs) out << '\t' << (s.pv_enters_egdb ? 1 : 0);
        out << '\n';
    }

    char trailing = 0;
    if (in.read(&trailing, 1)) {
        std::cerr << "error: input has trailing bytes\n";
        return 4;
    }
    out.close();
    write_ladder_report(report_path, declared, shard, nshards, tb_cap, tt_mb, counters);
    return 0;
}
