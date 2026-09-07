// SPDX-License-Identifier: AGPL-3.0-or-later
// Cheap benchmark-only parent decision scorer for the frozen Scan Gate 0.

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
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {

using namespace jass;

std::set<std::uint32_t> load_ids(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open parent ids");
    std::set<std::uint32_t> ids;
    std::uint64_t value = 0;
    while (in >> value) {
        if (value > 1999 || !ids.insert(static_cast<std::uint32_t>(value)).second)
            throw std::runtime_error("invalid/duplicate parent id");
    }
    if (!in.eof() || ids.size() != 512)
        throw std::runtime_error("Gate-0 parent ids must contain exactly 512 rows");
    return ids;
}

std::string bitboard_hex(Bitboard value) {
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(13)
        << static_cast<std::uint64_t>(value);
    return out.str();
}

bool exact_budget_ok(const SearchResult& r, std::uint64_t budget) {
    if (r.nodes == budget
        && r.stop_reason == SearchStopReason::Nodes
        && r.aborted_iteration) return true;
    return r.nodes > 0 && r.nodes < budget
        && r.stop_reason == SearchStopReason::None
        && r.completed_depth == MAX_PLY
        && r.effective_depth == MAX_PLY
        && !r.aborted_iteration;
}

struct Gate0Counters {
    std::uint64_t source_rows{0};
    std::uint64_t selected_rows{0};
    std::uint64_t processed_rows{0};
    std::uint64_t invalid_rows{0};
    std::uint64_t exact_budget_failures{0};
    std::uint64_t nodes{0};
    std::uint64_t eval_calls{0};
    std::uint64_t wall_us{0};
};

void write_report(const std::string& path, const std::string& arm,
                  std::uint64_t budget, int shard, int nshards,
                  std::size_t tt_mb, int tb_cap, const Gate0Counters& c) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot write Gate-0 report");
    out << "{\n"
        << "  \"schema\": \"jass.scan_oracle_gate0_runtime.v1\",\n"
        << "  \"benchmark_only\": true,\n"
        << "  \"arm\": \"" << arm << "\",\n"
        << "  \"budget_nodes\": " << budget << ",\n"
        << "  \"node_limit_mode\": \"exact\",\n"
        << "  \"threads\": 1,\n"
        << "  \"book\": false,\n"
        << "  \"fresh_engine_each_parent\": true,\n"
        << "  \"shard\": " << shard << ",\n"
        << "  \"nshards\": " << nshards << ",\n"
        << "  \"tt_mb\": " << tt_mb << ",\n"
        << "  \"egdb_max_pieces\": " << tb_cap << ",\n"
        << "  \"source_rows\": " << c.source_rows << ",\n"
        << "  \"selected_rows\": " << c.selected_rows << ",\n"
        << "  \"processed_rows\": " << c.processed_rows << ",\n"
        << "  \"invalid_rows\": " << c.invalid_rows << ",\n"
        << "  \"exact_budget_failures\": " << c.exact_budget_failures << ",\n"
        << "  \"nodes\": " << c.nodes << ",\n"
        << "  \"eval_calls\": " << c.eval_calls << ",\n"
        << "  \"wall_us\": " << c.wall_us << ",\n"
        << "  \"scan_searches\": 0,\n"
        << "  \"fits\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"promotion_authorized\": false\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "JNNW tool requires a little-endian host");
    try {
        if (argc < 9 || argc > 13) {
            std::cerr << "usage: jass_scan_oracle_gate0_runtime <parents.jnnw> <parent_ids.txt> "
                         "<scores.tsv> <report.json> <wdl_control.pjtw> <egdb_dir> "
                         "<budget_nodes> <arm> [shard=0] [nshards=1] [tt_mb=16] "
                         "[egdb_cache_mb=256]\n";
            return 2;
        }
        const std::string input_path = argv[1];
        const std::string ids_path = argv[2];
        const std::string scores_path = argv[3];
        const std::string report_path = argv[4];
        const std::string model_path = argv[5];
        const std::string egdb_dir = argv[6];
        const std::uint64_t budget = std::stoull(argv[7]);
        const std::string arm = argv[8];
        const int shard = argc >= 10 ? std::stoi(argv[9]) : 0;
        const int nshards = argc >= 11 ? std::stoi(argv[10]) : 1;
        const std::size_t tt_mb = argc >= 12
            ? static_cast<std::size_t>(std::max(1, std::stoi(argv[11]))) : 16U;
        const int egdb_cache_mb = argc >= 13 ? std::max(64, std::stoi(argv[12])) : 256;
        if (budget != 20'000 || nshards <= 0 || shard < 0 || shard >= nshards)
            throw std::runtime_error("Gate-0 runtime contract drift");
        if (arm != "CONTROL" && arm != "D3")
            throw std::runtime_error("unsupported Gate-0 arm");

        const char* d3a = std::getenv("JASS_D3_RUNTIME_ADAPTER");
        const char* d3b = std::getenv("JASS_D3_RUNTIME_BASE_MODEL");
        if ((arm == "CONTROL" && (d3a || d3b)) ||
            (arm == "D3" && (!d3a || !d3b)))
            throw std::runtime_error("D3 runtime environment/arm mismatch");
        if (std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") != nullptr ||
            std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr ||
            std::getenv("JASS_T3_F6_MODEL") != nullptr)
            throw std::runtime_error("unrelated runtime treatment is active");

        std::string network_error;
        auto network = load_eval_network(model_path, &network_error);
        if (!network) throw std::runtime_error("cannot load WDL_CONTROL: " + network_error);
        if (!egdb::init(egdb_dir, egdb_cache_mb) || !egdb::available())
            throw std::runtime_error("real EGDB unavailable");
        const int tb_cap = egdb::max_pieces();
        if (tb_cap <= 0) throw std::runtime_error("invalid EGDB cap");
        const auto ids = load_ids(ids_path);

        std::ifstream in(input_path, std::ios::binary);
        if (!in) throw std::runtime_error("cannot open parents JNNW");
        std::array<char, 8> header{};
        if (!in.read(header.data(), static_cast<std::streamsize>(header.size())) ||
            std::memcmp(header.data(), "JNNW", 4) != 0)
            throw std::runtime_error("parents input is not counted JNNW");
        const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);
        if (declared != 2000) throw std::runtime_error("frozen parent cardinality drift");

        std::ofstream out(scores_path);
        if (!out) throw std::runtime_error("cannot write Gate-0 scores");
        out << "parent_id\tfrom\tto\tcaptured_hex\tpromotes\tsearch_score\tnodes\t"
               "completed_depth\teffective_depth\teval_calls\tcutoffs\twall_us\n";

        Gate0Counters c{};
        DiskRow row{};
        for (std::uint32_t idx = 0; idx < declared; ++idx) {
            if (!read_row(in, row)) throw std::runtime_error("truncated parents JNNW");
            ++c.source_rows;
            if (!ids.count(idx)) continue;
            ++c.selected_rows;
            if (static_cast<int>(idx % static_cast<std::uint32_t>(nshards)) != shard) continue;
            ++c.processed_rows;
            if (!valid_row(row) || row.score != 0 || row.wdl != 0) {
                ++c.invalid_rows;
                throw std::runtime_error("invalid/target-bearing frozen parent row");
            }
            const Position pos = position_from_row(row);
            Engine engine(tt_mb);
            engine.use_book(false);
            engine.clear_tt();
            engine.set_position(pos);
            SearchLimits limits;
            limits.max_depth = MAX_PLY;
            limits.max_nodes = budget;
            limits.node_limit_mode = NodeLimitMode::Exact;
            limits.threads = 1;
            limits.nnue = network.get();
            limits.params = SearchParams{};
            const auto started = std::chrono::steady_clock::now();
            const SearchResult r = engine.search(limits);
            const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count();
            if (!exact_budget_ok(r, budget)) {
                ++c.exact_budget_failures;
                throw std::runtime_error("exact-node contract failure");
            }
            c.nodes += r.nodes;
            c.eval_calls += r.eval_calls;
            c.wall_us += static_cast<std::uint64_t>(std::max<std::int64_t>(0, elapsed));
            out << idx << '\t' << static_cast<int>(r.best_move.from) << '\t'
                << static_cast<int>(r.best_move.to) << '\t' << bitboard_hex(r.best_move.captured)
                << '\t' << (r.best_move.promotes ? 1 : 0) << '\t' << r.score << '\t'
                << r.nodes << '\t' << r.completed_depth << '\t' << r.effective_depth << '\t'
                << r.eval_calls << '\t' << r.cutoffs << '\t' << elapsed << '\n';
        }
        char trailing = 0;
        if (in.read(&trailing, 1)) throw std::runtime_error("parents JNNW trailing bytes");
        if (c.selected_rows != 512 || c.processed_rows != 512 || c.invalid_rows != 0
            || c.exact_budget_failures != 0)
            throw std::runtime_error("Gate-0 scorer count/integrity drift");
        write_report(report_path, arm, budget, shard, nshards, tt_mb, tb_cap, c);
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "error: " << ex.what() << '\n';
        return 1;
    }
}
