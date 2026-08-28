// SPDX-License-Identifier: AGPL-3.0-or-later
// Read-only exact 1000-node scorer for already-emitted sibling child JNNW rows.
// Reuses the frozen DSSD production search semantics. No labels, fits or games.

#include "pattern_jass_bridge.hpp"
#include "scan_eval.hpp"

#define load_pattern_jass_network load_eval_network
#define main deep_sibling_teacher_main_disabled
#include "deep_sibling_teacher.cpp"
#undef main
#undef load_pattern_jass_network

#include <array>
#include <bit>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>

namespace {
constexpr std::uint64_t BUDGET = 1000;

// deep_sibling_teacher.cpp is included into this translation unit and already
// owns a private `Counters` type. Keep this scorer's accounting type distinct
// so the standalone q1000 tool can be compiled without an anonymous-namespace
// type redefinition.
struct Q1000Counters {
    std::uint64_t source_rows{0};
    std::uint64_t processed_rows{0};
    std::uint64_t invalid_rows{0};
    std::uint64_t searches{0};
    std::uint64_t nodes{0};
    std::uint64_t elapsed_us{0};
};

void write_report(const std::string& path, std::uint32_t declared, int shard,
                  int nshards, int tb_cap, std::size_t tt_mb, const Q1000Counters& c) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open q1000 report output");
    out << "{\n"
        << "  \"schema\": \"jass.micro_search_q1000_score.v1\",\n"
        << "  \"input_children\": " << declared << ",\n"
        << "  \"shard\": " << shard << ",\n"
        << "  \"nshards\": " << nshards << ",\n"
        << "  \"budget_nodes\": 1000,\n"
        << "  \"book_enabled\": false,\n"
        << "  \"threads_per_search\": 1,\n"
        << "  \"fresh_tt_each_search\": true,\n"
        << "  \"node_limit_mode\": \"exact\",\n"
        << "  \"tt_mb\": " << tt_mb << ",\n"
        << "  \"egdb_max_pieces\": " << tb_cap << ",\n"
        << "  \"source_rows\": " << c.source_rows << ",\n"
        << "  \"processed_rows\": " << c.processed_rows << ",\n"
        << "  \"invalid_rows\": " << c.invalid_rows << ",\n"
        << "  \"searches\": " << c.searches << ",\n"
        << "  \"nodes\": " << c.nodes << ",\n"
        << "  \"elapsed_us\": " << c.elapsed_us << ",\n"
        << "  \"labels_read\": 0,\n"
        << "  \"fits\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"promotion_authorized\": false\n"
        << "}\n";
}
}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "JNNW tool requires a little-endian host");
    if (argc < 6 || argc > 10) {
        std::cerr << "usage: jass_micro_search_q1000_score <children.jnnw> <scores.tsv> "
                     "<report.json> <curriculum.pjtw> <egdb_dir> "
                     "[shard=0] [nshards=1] [tt_mb=16] [egdb_cache_mb=256]\n";
        return 2;
    }
    if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr ||
        std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") != nullptr) {
        std::cerr << "error: runtime move-order policies must be absent\n";
        return 2;
    }

    const std::string input_path = argv[1];
    const std::string score_path = argv[2];
    const std::string report_path = argv[3];
    const std::string curriculum_path = argv[4];
    const std::string egdb_dir = argv[5];
    const int shard = argc >= 7 ? std::stoi(argv[6]) : 0;
    const int nshards = argc >= 8 ? std::stoi(argv[7]) : 1;
    const std::size_t tt_mb = argc >= 9
        ? static_cast<std::size_t>(std::max(1, std::stoi(argv[8]))) : DEFAULT_TT_MB;
    const int egdb_cache_mb = argc >= 10 ? std::max(64, std::stoi(argv[9])) : 256;
    if (nshards <= 0 || shard < 0 || shard >= nshards) return 2;

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
    if (tb_cap <= 0) return 3;

    std::ifstream in(input_path, std::ios::binary);
    if (!in) return 4;
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size())) ||
        std::memcmp(header.data(), "JNNW", 4) != 0) return 4;
    const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);

    std::ofstream out(score_path);
    if (!out) return 5;
    out << "row_index\tq1000_parent\tnodes1000\tcompleted_depth1000\teffective_depth1000\telapsed_us1000\tpv1000_enters_egdb\n";

    Engine engine(tt_mb);
    engine.use_book(false);
    Q1000Counters c{};
    DiskRow row{};
    for (std::uint32_t idx = 0; idx < declared; ++idx) {
        if (!read_row(in, row)) return 4;
        ++c.source_rows;
        if (static_cast<int>(idx % static_cast<std::uint32_t>(nshards)) != shard) continue;
        ++c.processed_rows;
        if (!valid_row(row)) { ++c.invalid_rows; continue; }
        if (row.score != 0 || row.wdl != 0) {
            std::cerr << "error: child target bytes are not zero at row " << idx << '\n';
            return 4;
        }
        const Position child = position_from_row(row);
        const SearchObs s = run_fresh_search(engine, child, curriculum.get(), BUDGET, tb_cap);
        ++c.searches;
        c.nodes += s.nodes;
        c.elapsed_us += s.elapsed_us;
        out << idx << '\t' << s.parent_score << '\t' << s.nodes << '\t'
            << s.completed_depth << '\t' << s.effective_depth << '\t' << s.elapsed_us
            << '\t' << (s.pv_enters_egdb ? 1 : 0) << '\n';
    }
    char trailing = 0;
    if (in.read(&trailing, 1)) return 4;
    out.close();
    write_report(report_path, declared, shard, nshards, tb_cap, tt_mb, c);
    return 0;
}
