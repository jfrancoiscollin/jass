// SPDX-License-Identifier: AGPL-3.0-or-later
// Benchmark-only sibling exporter for the preregistered Scan ceiling study.
// It enumerates target-blind parent moves and emits child states plus the
// frozen CURRICULUM scalar. It performs no search, fit, selection, or game.

#include "scan_eval.hpp"

#define load_pattern_jass_network load_eval_network
#define main deep_sibling_teacher_main_disabled
#include "deep_sibling_teacher.cpp"
#undef main
#undef load_pattern_jass_network

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct ExportCounters {
    std::uint64_t source_rows{0};
    std::uint64_t processed_parent_rows{0};
    std::uint64_t invalid_rows{0};
    std::uint64_t duplicate_move_entries{0};
    std::uint64_t emitted_siblings{0};
    std::uint64_t rule_terminal_children{0};
    std::uint64_t exact_tb_children{0};
};

std::string position_fingerprint(const jass::Position& pos) {
    std::ostringstream out;
    out << std::hex << std::setfill('0')
        << std::setw(13) << pos.white_men() << ':'
        << std::setw(13) << pos.white_kings() << ':'
        << std::setw(13) << pos.black_men() << ':'
        << std::setw(13) << pos.black_kings() << ':'
        << std::dec << (pos.side_to_move() == jass::Color::White ? 0 : 1);
    return out.str();
}

std::string bitboard_hex(jass::Bitboard value) {
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(13)
        << static_cast<std::uint64_t>(value);
    return out.str();
}

void write_export_report(const std::string& path,
                         std::uint32_t declared,
                         int shard,
                         int nshards,
                         int tb_cap,
                         const ExportCounters& c) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open Scan-ceiling export report");
    out << "{\n"
        << "  \"schema\": \"jass.scan_ceiling_sibling_export.v1\",\n"
        << "  \"input_parents\": " << declared << ",\n"
        << "  \"shard\": " << shard << ",\n"
        << "  \"nshards\": " << nshards << ",\n"
        << "  \"semantic_move_order\": \"from,to,captured_bitboard,promotes\",\n"
        << "  \"score_convention\": \"higher_is_better_for_parent\",\n"
        << "  \"egdb_max_pieces\": " << tb_cap << ",\n"
        << "  \"source_rows\": " << c.source_rows << ",\n"
        << "  \"processed_parent_rows\": " << c.processed_parent_rows << ",\n"
        << "  \"invalid_rows\": " << c.invalid_rows << ",\n"
        << "  \"duplicate_move_entries\": " << c.duplicate_move_entries << ",\n"
        << "  \"emitted_siblings\": " << c.emitted_siblings << ",\n"
        << "  \"rule_terminal_children\": " << c.rule_terminal_children << ",\n"
        << "  \"exact_tb_children\": " << c.exact_tb_children << ",\n"
        << "  \"source_labels_read\": false,\n"
        << "  \"source_score_bytes_read\": false,\n"
        << "  \"source_wdl_bytes_read\": false,\n"
        << "  \"searches\": 0,\n"
        << "  \"fits\": 0,\n"
        << "  \"calibrations\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"training_allowed\": false,\n"
        << "  \"tuning_allowed\": false,\n"
        << "  \"calibration_allowed\": false,\n"
        << "  \"model_selection_allowed\": false,\n"
        << "  \"runtime_scale_selection_allowed\": false,\n"
        << "  \"promotion_authorized\": false\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "JNNW tool requires a little-endian host");
    if (argc < 7 || argc > 10) {
        std::cerr << "usage: jass_scan_ceiling_sibling_export <parents.jnnw> "
                     "<children.jnnw> <groups.tsv> <report.json> "
                     "<curriculum.pjtw> <egdb_dir> [shard=0] [nshards=1] "
                     "[egdb_cache_mb=256]\n";
        return 2;
    }
    if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr ||
        std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") != nullptr ||
        std::getenv("JASS_T3_F6_MODEL") != nullptr) {
        std::cerr << "error: runtime policy/model variables must be absent\n";
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
    if (!jass::egdb::init(egdb_dir, egdb_cache_mb) || !jass::egdb::available()) {
        std::cerr << "error: real EGDB unavailable at " << egdb_dir << '\n';
        return 3;
    }
    const int tb_cap = jass::egdb::max_pieces();
    if (tb_cap <= 0) {
        std::cerr << "error: invalid EGDB max pieces\n";
        return 3;
    }

    std::ifstream in(input_path, std::ios::binary);
    if (!in) {
        std::cerr << "error: cannot open parents input\n";
        return 4;
    }
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size())) ||
        std::memcmp(header.data(), "JNNW", 4) != 0) {
        std::cerr << "error: parents input is not counted JNNW\n";
        return 4;
    }
    const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);

    std::ofstream children(child_path, std::ios::binary);
    std::ofstream groups(groups_path);
    if (!children || !groups) {
        std::cerr << "error: cannot open export outputs\n";
        return 5;
    }
    children.write("JNNW", 4);
    const std::uint32_t zero = 0;
    children.write(reinterpret_cast<const char*>(&zero), 4);
    groups << "local_row_index\tparent_id\tparent_fingerprint\tparent_stm\tparent_pieces\t"
              "from\tto\tcaptured_hex\tnum_captures\tpromotes\tmoving_king\t"
              "captured_kings\tmaterial_count_delta_parent\tchild_fingerprint\t"
              "child_pieces\tchild_legal_moves\tchild_forced_capture\t"
              "child_rule_terminal\tchild_tb_exact\texact_parent_utility\tt0_parent\n";

    ExportCounters counters{};
    std::uint32_t output_count = 0;
    DiskRow row{};
    for (std::uint32_t idx = 0; idx < declared; ++idx) {
        if (!read_row(in, row)) {
            std::cerr << "error: truncated parent JNNW at row " << idx << '\n';
            return 4;
        }
        ++counters.source_rows;
        if (static_cast<int>(idx % static_cast<std::uint32_t>(nshards)) != shard) continue;
        ++counters.processed_parent_rows;
        if (!valid_row(row)) {
            ++counters.invalid_rows;
            continue;
        }
        if (row.score != 0 || row.wdl != 0) {
            std::cerr << "error: parent target bytes are not zero at row " << idx << '\n';
            return 4;
        }
        const int parent_pieces = jass::popcount(row.wm | row.wk | row.bm | row.bk);
        if (parent_pieces < 9 || parent_pieces > 40) {
            std::cerr << "error: parent outside preregistered 9..40 pieces\n";
            return 4;
        }

        const jass::Position parent = position_from_row(row);
        jass::MoveList legal;
        jass::generate_legal_moves(parent, legal);
        std::vector<jass::Move> unique_moves;
        unique_moves.reserve(legal.size());
        for (const jass::Move& move : legal) {
            const auto it = std::find_if(unique_moves.begin(), unique_moves.end(),
                [&](const jass::Move& old) { return same_semantic_move(old, move); });
            if (it == unique_moves.end()) unique_moves.push_back(move);
            else ++counters.duplicate_move_entries;
        }
        std::sort(unique_moves.begin(), unique_moves.end(), semantic_less);
        if (unique_moves.size() < 2 || unique_moves.size() > 16) {
            std::cerr << "error: parent legal-move support drift at row " << idx << '\n';
            return 4;
        }

        const std::string fingerprint = parent_fingerprint(row);
        for (const jass::Move& move : unique_moves) {
            const bool moving_king = jass::test(
                parent.kings_of(parent.side_to_move()), move.from);
            const int captured_kings = jass::popcount(
                move.captured & parent.kings_of(jass::opposite(parent.side_to_move())));
            const jass::Position child = parent.after(move);
            jass::MoveList child_legal;
            jass::generate_legal_moves(child, child_legal);
            const bool child_forced_capture =
                !child_legal.empty() && child_legal[0].is_capture();
            bool rule_terminal = false;
            bool tb_exact = false;
            const std::optional<int> exact_u = exact_parent_utility(
                parent, child, tb_cap, rule_terminal, tb_exact);
            counters.rule_terminal_children += static_cast<std::uint64_t>(rule_terminal);
            counters.exact_tb_children += static_cast<std::uint64_t>(tb_exact);

            const int t0_parent = -curriculum->evaluate(child);
            write_zero_target_row(children, child);
            groups << output_count << '\t' << idx << '\t' << fingerprint << '\t'
                   << static_cast<int>(row.stm) << '\t' << parent_pieces << '\t'
                   << static_cast<int>(move.from) << '\t' << static_cast<int>(move.to) << '\t'
                   << bitboard_hex(move.captured) << '\t'
                   << static_cast<int>(move.num_captures) << '\t'
                   << (move.promotes ? 1 : 0) << '\t' << (moving_king ? 1 : 0) << '\t'
                   << captured_kings << '\t'
                   << material_count_delta_parent(parent, child) << '\t'
                   << position_fingerprint(child) << '\t'
                   << jass::popcount(child.occupied()) << '\t' << child_legal.size() << '\t'
                   << (child_forced_capture ? 1 : 0) << '\t'
                   << (rule_terminal ? 1 : 0) << '\t' << (tb_exact ? 1 : 0) << '\t'
                   << (exact_u ? *exact_u : 2) << '\t' << t0_parent << '\n';
            ++output_count;
            ++counters.emitted_siblings;
        }
    }

    char trailing = 0;
    if (in.read(&trailing, 1)) {
        std::cerr << "error: parents input has trailing bytes\n";
        return 4;
    }
    children.seekp(4, std::ios::beg);
    children.write(reinterpret_cast<const char*>(&output_count), 4);
    children.close();
    groups.close();
    write_export_report(report_path, declared, shard, nshards, tb_cap, counters);
    return 0;
}
