// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-Francois Collin
//
// Phase M3 extractor for L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.
// Enumerates every unique semantic legal sibling of the already-frozen,
// target-blind 100k-parent M3 selection and scores ONLY the preregistered
// B*=1000 micro-search teacher.  No q5k/q50/q200/WDL/source label is read.
// The production CURRICULUM scalar is emitted solely as a mapping audit value
// for the later exact PatternEval design-equivalence proof; it is not a label.

#include "scan_eval.hpp"

#define load_pattern_jass_network load_eval_network
#define main deep_sibling_teacher_main_disabled
#include "deep_sibling_teacher.cpp"
#undef main
#undef load_pattern_jass_network

#include <array>
#include <bit>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <string>
#include <vector>

namespace {

constexpr std::uint64_t M3_BUDGET = 1'000;

struct M3Counters {
    std::uint64_t source_rows{0};
    std::uint64_t processed_parent_rows{0};
    std::uint64_t invalid_rows{0};
    std::uint64_t duplicate_move_entries{0};
    std::uint64_t emitted_siblings{0};
    std::uint64_t searches{0};
    std::uint64_t nodes{0};
    std::uint64_t elapsed_us{0};
};

void write_m3_report(const std::string& path,
                     std::uint32_t declared,
                     int shard,
                     int nshards,
                     int tb_cap,
                     std::size_t tt_mb,
                     const M3Counters& c) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open M3 report output");
    out << "{\n"
        << "  \"schema\": \"jass.micro_search_m3_teacher_extract.v1\",\n"
        << "  \"input_parents\": " << declared << ",\n"
        << "  \"shard\": " << shard << ",\n"
        << "  \"nshards\": " << nshards << ",\n"
        << "  \"budget_nodes\": " << M3_BUDGET << ",\n"
        << "  \"book_enabled\": false,\n"
        << "  \"threads_per_search\": 1,\n"
        << "  \"fresh_tt_each_search\": true,\n"
        << "  \"node_limit_mode\": \"exact\",\n"
        << "  \"tt_mb\": " << tt_mb << ",\n"
        << "  \"egdb_max_pieces\": " << tb_cap << ",\n"
        << "  \"source_rows\": " << c.source_rows << ",\n"
        << "  \"processed_parent_rows\": " << c.processed_parent_rows << ",\n"
        << "  \"invalid_rows\": " << c.invalid_rows << ",\n"
        << "  \"duplicate_move_entries\": " << c.duplicate_move_entries << ",\n"
        << "  \"emitted_siblings\": " << c.emitted_siblings << ",\n"
        << "  \"searches\": " << c.searches << ",\n"
        << "  \"nodes\": " << c.nodes << ",\n"
        << "  \"elapsed_us\": " << c.elapsed_us << ",\n"
        << "  \"source_labels_read\": false,\n"
        << "  \"teacher_scores_produced\": true,\n"
        << "  \"deep_scores_read\": 0,\n"
        << "  \"fits\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"runtime_micro_search\": false,\n"
        << "  \"promotion_authorized\": false\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "JNNW tool currently requires a little-endian host");
    if (argc < 7 || argc > 11) {
        std::cerr << "usage: jass_micro_search_m3_teacher <parents.jnnw> <children.jnnw> "
                     "<groups.tsv> <report.json> <curriculum.pjtw> <egdb_dir> "
                     "[shard=0] [nshards=1] [tt_mb=16] [egdb_cache_mb=256]\n";
        return 2;
    }
    if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr ||
        std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") != nullptr) {
        std::cerr << "error: runtime move-order policies must be absent for frozen M3 teacher\n";
        return 2;
    }

    const std::string input_path = argv[1];
    const std::string child_path = argv[2];
    const std::string groups_path = argv[3];
    const std::string report_path = argv[4];
    const std::string curriculum_path = argv[5];
    const std::string egdb_dir = argv[6];
    const int shard = argc >= 8 ? std::stoi(argv[7]) : 0;
    const int nshards = argc >= 9 ? std::stoi(argv[8]) : 1;
    const std::size_t tt_mb = argc >= 10
        ? static_cast<std::size_t>(std::max(1, std::stoi(argv[9]))) : DEFAULT_TT_MB;
    const int egdb_cache_mb = argc >= 11 ? std::max(64, std::stoi(argv[10])) : 256;
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
    if (!in) { std::cerr << "error: cannot open input\n"; return 4; }
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size())) ||
        std::memcmp(header.data(), "JNNW", 4) != 0) {
        std::cerr << "error: input is not counted JNNW\n";
        return 4;
    }
    const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);
    if (declared != 100000U) {
        std::cerr << "error: M3 parent count must be exactly 100000\n";
        return 4;
    }

    std::ofstream children(child_path, std::ios::binary);
    std::ofstream groups(groups_path);
    if (!children || !groups) { std::cerr << "error: cannot open outputs\n"; return 5; }
    children.write("JNNW", 4);
    const std::uint32_t zero = 0;
    children.write(reinterpret_cast<const char*>(&zero), 4);
    groups << "row_index\tparent_id\tparent_fingerprint\tparent_stm\tparent_pieces\t"
              "from\tto\tnum_captures\tpromotes\tmoving_king\tcaptured_kings\t"
              "material_count_delta_parent\tchild_pieces\tchild_legal_moves\t"
              "child_forced_capture\tt0_parent\tmicro1000_parent\tnodes1000\t"
              "completed_depth1000\teffective_depth1000\taborted1000\tstop1000\t"
              "elapsed_us1000\tpv1000_enters_egdb\n";

    Engine engine(tt_mb);
    engine.use_book(false);
    M3Counters c{};
    std::uint32_t output_count = 0;
    DiskRow row{};
    for (std::uint32_t idx = 0; idx < declared; ++idx) {
        if (!read_row(in, row)) {
            std::cerr << "error: truncated JNNW at row " << idx << '\n';
            return 4;
        }
        ++c.source_rows;
        if (static_cast<int>(idx % static_cast<std::uint32_t>(nshards)) != shard) continue;
        ++c.processed_parent_rows;
        if (!valid_row(row)) { ++c.invalid_rows; continue; }
        if (row.score != 0 || row.wdl != 0) {
            std::cerr << "error: selected-parent target bytes are not zero at row " << idx << '\n';
            return 4;
        }
        const int parent_pieces = popcount(row.wm | row.wk | row.bm | row.bk);
        if (parent_pieces < 9 || parent_pieces > 40) {
            std::cerr << "error: selected parent outside frozen 9..40 support\n";
            return 4;
        }

        const Position parent = position_from_row(row);
        MoveList legal;
        generate_legal_moves(parent, legal);
        std::vector<Move> unique_moves;
        unique_moves.reserve(legal.size());
        for (const Move& move : legal) {
            const auto it = std::find_if(unique_moves.begin(), unique_moves.end(),
                [&](const Move& existing) { return same_semantic_move(existing, move); });
            if (it == unique_moves.end()) unique_moves.push_back(move);
            else ++c.duplicate_move_entries;
        }
        std::sort(unique_moves.begin(), unique_moves.end(), semantic_less);
        if (unique_moves.size() < 2 || unique_moves.size() > 16) {
            std::cerr << "error: selected parent legal-decision count drift at row " << idx << '\n';
            return 4;
        }

        const std::string fingerprint = parent_fingerprint(row);
        for (const Move& move : unique_moves) {
            const bool moving_king = test(parent.kings_of(parent.side_to_move()), move.from);
            const int captured_kings = popcount(
                move.captured & parent.kings_of(opposite(parent.side_to_move())));
            const Position child = parent.after(move);
            MoveList child_legal;
            generate_legal_moves(child, child_legal);
            const bool child_forced_capture = !child_legal.empty() && child_legal[0].is_capture();

            // Direct CURRICULUM score exists only to prove the exported full
            // PatternEval row reproduces production scoring exactly.  It never
            // determines inclusion, ordering, a teacher target, or a fit row.
            const int t0_parent = -curriculum->evaluate(child);
            const SearchObs s = run_fresh_search(engine, child, curriculum.get(), M3_BUDGET, tb_cap);
            ++c.searches;
            c.nodes += s.nodes;
            c.elapsed_us += s.elapsed_us;

            write_zero_target_row(children, child);
            groups << output_count << '\t' << idx << '\t' << fingerprint << '\t'
                   << static_cast<int>(row.stm) << '\t' << parent_pieces << '\t'
                   << static_cast<int>(move.from) << '\t' << static_cast<int>(move.to) << '\t'
                   << static_cast<int>(move.num_captures) << '\t' << (move.promotes ? 1 : 0) << '\t'
                   << (moving_king ? 1 : 0) << '\t' << captured_kings << '\t'
                   << material_count_delta_parent(parent, child) << '\t'
                   << popcount(child.occupied()) << '\t' << child_legal.size() << '\t'
                   << (child_forced_capture ? 1 : 0) << '\t' << t0_parent << '\t'
                   << s.parent_score << '\t' << s.nodes << '\t' << s.completed_depth << '\t'
                   << s.effective_depth << '\t' << (s.aborted_iteration ? 1 : 0) << '\t'
                   << search_stop_reason_name(s.stop_reason) << '\t' << s.elapsed_us << '\t'
                   << (s.pv_enters_egdb ? 1 : 0) << '\n';
            ++output_count;
            ++c.emitted_siblings;
        }
    }

    char trailing = 0;
    if (in.read(&trailing, 1)) {
        std::cerr << "error: input has trailing bytes\n";
        return 4;
    }
    children.seekp(4, std::ios::beg);
    children.write(reinterpret_cast<const char*>(&output_count), 4);
    children.close();
    groups.close();
    write_m3_report(report_path, declared, shard, nshards, tb_cap, tt_mb, c);
    return 0;
}
