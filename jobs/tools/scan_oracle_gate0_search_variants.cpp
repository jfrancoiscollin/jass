// SPDX-License-Identifier: AGPL-3.0-or-later
// Cheap benchmark-only parent decision scorer for frozen Search-semantics arms.

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
#include <cstdlib>
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

constexpr std::array<const char*, 6> ARMS{
    "J1_SCAN_VERIFY", "J2_SCAN_THREAT_REENTRY", "J3_SCAN_SINGLE_REPLY",
    "J4_SCAN_LMR", "J5_SCAN_ORDERING", "J6_NO_NULL_MOVE",
};

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

SearchParams params_for_arm(const std::string& arm) {
    if (std::find(ARMS.begin(), ARMS.end(), arm) == ARMS.end())
        throw std::runtime_error("arm outside frozen search-variant screen");
    SearchParams p{};
    if (arm == "J1_SCAN_VERIFY") p.scan_verify_pruning = true;
    else if (arm == "J2_SCAN_THREAT_REENTRY") {
        p.qs_threat_ext = false;
        p.scan_threat_reentry = true;
    } else if (arm == "J3_SCAN_SINGLE_REPLY") p.ext_single_reply = true;
    else if (arm == "J4_SCAN_LMR") p.scan_lmr_semantics = true;
    else if (arm == "J5_SCAN_ORDERING") p.scan_probabilistic_ordering = true;
    else if (arm == "J6_NO_NULL_MOVE") p.disable_null_move = true;
    return p;
}

std::string bitboard_hex(Bitboard value) {
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(13)
        << static_cast<std::uint64_t>(value);
    return out.str();
}

bool exact_budget_ok(const SearchResult& r, std::uint64_t budget) {
    if (r.nodes == budget && r.stop_reason == SearchStopReason::Nodes
        && r.aborted_iteration) return true;
    return r.nodes > 0 && r.nodes < budget
        && r.stop_reason == SearchStopReason::None
        && r.completed_depth == MAX_PLY && r.effective_depth == MAX_PLY
        && !r.aborted_iteration;
}

struct Counters {
    std::uint64_t source_rows{0}, selected_rows{0}, processed_rows{0};
    std::uint64_t nodes{0}, eval_calls{0}, wall_us{0};
    std::uint64_t scan_verify_probes{0}, scan_verify_cutoffs{0};
    std::uint64_t scan_threat_reentries{0}, single_reply_extensions{0};
    std::uint64_t reductions{0}, reduced_plies{0};
    std::uint64_t ordering_good_updates{0}, ordering_bad_updates{0};
    std::uint64_t null_probes{0}, null_cutoffs{0};
};

void write_report(const std::string& path, const std::string& arm,
                  std::uint64_t budget, const Counters& c) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot write Gate-0 variant report");
    out << "{\n"
        << "  \"schema\": \"jass.scan_oracle_gate0_search_variant.v1\",\n"
        << "  \"benchmark_only\": true,\n"
        << "  \"exploratory_screen_only\": true,\n"
        << "  \"arm\": \"" << arm << "\",\n"
        << "  \"budget_nodes\": " << budget << ",\n"
        << "  \"threads\": 1,\n"
        << "  \"book\": false,\n"
        << "  \"external_egdb_enabled\": false,\n"
        << "  \"fresh_engine_each_parent\": true,\n"
        << "  \"source_rows\": " << c.source_rows << ",\n"
        << "  \"selected_rows\": " << c.selected_rows << ",\n"
        << "  \"processed_rows\": " << c.processed_rows << ",\n"
        << "  \"nodes\": " << c.nodes << ",\n"
        << "  \"eval_calls\": " << c.eval_calls << ",\n"
        << "  \"wall_us\": " << c.wall_us << ",\n"
        << "  \"scan_verify_probes\": " << c.scan_verify_probes << ",\n"
        << "  \"scan_verify_cutoffs\": " << c.scan_verify_cutoffs << ",\n"
        << "  \"scan_threat_reentries\": " << c.scan_threat_reentries << ",\n"
        << "  \"single_reply_extensions\": " << c.single_reply_extensions << ",\n"
        << "  \"reductions\": " << c.reductions << ",\n"
        << "  \"reduced_plies\": " << c.reduced_plies << ",\n"
        << "  \"ordering_good_updates\": " << c.ordering_good_updates << ",\n"
        << "  \"ordering_bad_updates\": " << c.ordering_bad_updates << ",\n"
        << "  \"null_probes\": " << c.null_probes << ",\n"
        << "  \"null_cutoffs\": " << c.null_cutoffs << ",\n"
        << "  \"scan_searches\": 0,\n"
        << "  \"fits\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"promotion_authorized\": false\n"
        << "}\n";
}

void assert_activation(const std::string& arm, const Counters& c) {
    if (arm == "J1_SCAN_VERIFY" && c.scan_verify_probes == 0)
        throw std::runtime_error("J1 activation sentinel absent");
    if (arm == "J2_SCAN_THREAT_REENTRY" && c.scan_threat_reentries == 0)
        throw std::runtime_error("J2 activation sentinel absent");
    if (arm == "J3_SCAN_SINGLE_REPLY" && c.single_reply_extensions == 0)
        throw std::runtime_error("J3 activation sentinel absent");
    if (arm == "J4_SCAN_LMR" && (c.reductions == 0 || c.reduced_plies == 0))
        throw std::runtime_error("J4 activation sentinel absent");
    if (arm == "J5_SCAN_ORDERING" &&
        (c.ordering_good_updates == 0 || c.ordering_bad_updates == 0))
        throw std::runtime_error("J5 activation sentinel absent");
    if (arm == "J6_NO_NULL_MOVE" && c.null_probes != 0)
        throw std::runtime_error("J6 null-move disable sentinel failed");
}
}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little);
    try {
        if (argc != 8) {
            std::cerr << "usage: jass_scan_oracle_gate0_search_variants <parents.jnnw> "
                         "<parent_ids.txt> <scores.tsv> <report.json> "
                         "<wdl_control.pjtw> <arm> <budget_nodes>\n";
            return 2;
        }
        const std::string input_path = argv[1];
        const std::string ids_path = argv[2];
        const std::string scores_path = argv[3];
        const std::string report_path = argv[4];
        const std::string model_path = argv[5];
        const std::string arm = argv[6];
        const std::uint64_t budget = std::stoull(argv[7]);
        if (budget != 20'000) throw std::runtime_error("Gate-0 budget drift");
        if (std::getenv("JASS_D3_RUNTIME_ADAPTER") ||
            std::getenv("JASS_D3_RUNTIME_BASE_MODEL") ||
            std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") ||
            std::getenv("JASS_TB_MOVE_ORDER_POLICY") ||
            std::getenv("JASS_T3_F6_MODEL") || std::getenv("JASS_SEARCH_PARAMS"))
            throw std::runtime_error("unrelated runtime override active");

        const SearchParams params = params_for_arm(arm);
        std::string error;
        auto network = load_eval_network(model_path, &error);
        if (!network) throw std::runtime_error("cannot load WDL_CONTROL: " + error);
        const auto ids = load_ids(ids_path);

        std::ifstream in(input_path, std::ios::binary);
        if (!in) throw std::runtime_error("cannot open parents JNNW");
        std::array<char, 8> header{};
        if (!in.read(header.data(), static_cast<std::streamsize>(header.size()))
            || std::memcmp(header.data(), "JNNW", 4) != 0)
            throw std::runtime_error("parents input is not counted JNNW");
        const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);
        if (declared != 2000) throw std::runtime_error("frozen parent cardinality drift");

        std::ofstream out(scores_path);
        if (!out) throw std::runtime_error("cannot write Gate-0 variant scores");
        out << "parent_id\tfrom\tto\tcaptured_hex\tpromotes\tsearch_score\tnodes\t"
               "completed_depth\teffective_depth\teval_calls\tcutoffs\twall_us\n";

        Counters c{};
        DiskRow row{};
        for (std::uint32_t idx = 0; idx < declared; ++idx) {
            if (!read_row(in, row)) throw std::runtime_error("truncated parents JNNW");
            ++c.source_rows;
            if (!ids.count(idx)) continue;
            ++c.selected_rows;
            ++c.processed_rows;
            if (!valid_row(row) || row.score != 0 || row.wdl != 0)
                throw std::runtime_error("invalid/target-bearing frozen parent row");
            const Position pos = position_from_row(row);
            Engine engine(16);
            engine.use_book(false);
            engine.clear_tt();
            engine.set_position(pos);
            SearchLimits limits;
            limits.max_depth = MAX_PLY;
            limits.max_nodes = budget;
            limits.node_limit_mode = NodeLimitMode::Exact;
            limits.threads = 1;
            limits.nnue = network.get();
            limits.params = params;
            const auto started = std::chrono::steady_clock::now();
            const SearchResult r = engine.search(limits);
            const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count();
            if (!exact_budget_ok(r, budget))
                throw std::runtime_error("exact-node contract failure");
            c.nodes += r.nodes; c.eval_calls += r.eval_calls;
            c.wall_us += static_cast<std::uint64_t>(std::max<std::int64_t>(0, elapsed));
            c.scan_verify_probes += r.scan_verify_probes;
            c.scan_verify_cutoffs += r.scan_verify_cutoffs;
            c.scan_threat_reentries += r.scan_threat_reentries;
            c.single_reply_extensions += r.single_reply_extensions;
            c.reductions += r.reductions; c.reduced_plies += r.reduced_plies;
            c.ordering_good_updates += r.ordering_good_updates;
            c.ordering_bad_updates += r.ordering_bad_updates;
            c.null_probes += r.null_probes; c.null_cutoffs += r.null_cutoffs;
            out << idx << '\t' << static_cast<int>(r.best_move.from) << '\t'
                << static_cast<int>(r.best_move.to) << '\t' << bitboard_hex(r.best_move.captured)
                << '\t' << (r.best_move.promotes ? 1 : 0) << '\t' << r.score << '\t'
                << r.nodes << '\t' << r.completed_depth << '\t' << r.effective_depth << '\t'
                << r.eval_calls << '\t' << r.cutoffs << '\t' << elapsed << '\n';
        }
        char trailing = 0;
        if (in.read(&trailing, 1)) throw std::runtime_error("parents JNNW trailing bytes");
        if (c.selected_rows != 512 || c.processed_rows != 512)
            throw std::runtime_error("Gate-0 variant cardinality drift");
        assert_activation(arm, c);
        write_report(report_path, arm, budget, c);
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "error: " << ex.what() << '\n';
        return 1;
    }
}
