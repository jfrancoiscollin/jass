// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-Francois Collin
//
// Offline exact sibling-ranking corpus extractor.
//
// Reads counted JNNW positions, keeps only parents immediately outside the
// loaded EGDB coverage whose legal moves are captures and whose ALL unique
// children are covered exactly by EGDB, then emits one JNNW child row per
// legal semantic move plus a TSV group map carrying the exact parent-POV WLD
// utility.  No search score or game-result label participates in selection.

#include "bitboard.hpp"
#include "egdb_bridge.hpp"
#include "endgame.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "types.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_set>
#include <vector>

namespace {

using namespace jass;

constexpr std::size_t JNNW_RECORD_SIZE = 38;

struct DiskRow {
    std::uint64_t wm{0};
    std::uint64_t wk{0};
    std::uint64_t bm{0};
    std::uint64_t bk{0};
    std::uint8_t stm{0};
    std::int32_t score{0};
    std::int8_t wdl{0};
};

struct Counters {
    std::uint64_t source_rows{0};
    std::uint64_t invalid_rows{0};
    std::uint64_t parent_piece_rows{0};
    std::uint64_t duplicate_parent_states{0};
    std::uint64_t multi_capture_parents{0};
    std::uint64_t duplicate_move_entries{0};
    std::uint64_t child_above_tb_cap{0};
    std::uint64_t child_unknown_probes{0};
    std::uint64_t all_children_exact_parents{0};
    std::uint64_t homogeneous_wld_parents{0};
    std::uint64_t informative_parents{0};
    std::uint64_t child_rows{0};
};

struct ChildLabel {
    Move move{};
    Position child{};
    int parent_utility{0};
    int child_wdl_stm{0};
    bool moving_king{false};
    int captured_kings{0};
};

template <typename T>
T load_le(const char* p) noexcept {
    T out{};
    std::memcpy(&out, p, sizeof(T));
    return out;
}

template <typename T>
void store_le(char* p, T value) noexcept {
    std::memcpy(p, &value, sizeof(T));
}

bool read_row(std::istream& in, DiskRow& row) {
    std::array<char, JNNW_RECORD_SIZE> raw{};
    if (!in.read(raw.data(), static_cast<std::streamsize>(raw.size()))) return false;
    row.wm = load_le<std::uint64_t>(raw.data() + 0);
    row.wk = load_le<std::uint64_t>(raw.data() + 8);
    row.bm = load_le<std::uint64_t>(raw.data() + 16);
    row.bk = load_le<std::uint64_t>(raw.data() + 24);
    row.stm = load_le<std::uint8_t>(raw.data() + 32);
    row.score = load_le<std::int32_t>(raw.data() + 33);
    row.wdl = load_le<std::int8_t>(raw.data() + 37);
    return true;
}

void write_row(std::ostream& out, const Position& pos, std::int8_t wdl) {
    std::array<char, JNNW_RECORD_SIZE> raw{};
    store_le<std::uint64_t>(raw.data() + 0, pos.white_men());
    store_le<std::uint64_t>(raw.data() + 8, pos.white_kings());
    store_le<std::uint64_t>(raw.data() + 16, pos.black_men());
    store_le<std::uint64_t>(raw.data() + 24, pos.black_kings());
    store_le<std::uint8_t>(raw.data() + 32,
        pos.side_to_move() == Color::White ? std::uint8_t{0} : std::uint8_t{1});
    store_le<std::int32_t>(raw.data() + 33, 0);
    store_le<std::int8_t>(raw.data() + 37, wdl);
    out.write(raw.data(), static_cast<std::streamsize>(raw.size()));
}

void add_bits(Position& pos, Bitboard bb, Piece piece) {
    while (bb) {
        const Square sq = pop_lsb(bb);
        pos.add_piece(sq, piece);
    }
}

bool valid_row(const DiskRow& r) noexcept {
    if (r.stm > 1) return false;
    const Bitboard all = r.wm | r.wk | r.bm | r.bk;
    if ((all & ~PLAYABLE_BB) != 0) return false;
    return ((r.wm & r.wk) | (r.wm & r.bm) | (r.wm & r.bk)
          | (r.wk & r.bm) | (r.wk & r.bk) | (r.bm & r.bk)) == 0;
}

Position position_from_row(const DiskRow& r) {
    Position pos;
    pos.clear();
    add_bits(pos, r.wm, Piece::WhiteMan);
    add_bits(pos, r.wk, Piece::WhiteKing);
    add_bits(pos, r.bm, Piece::BlackMan);
    add_bits(pos, r.bk, Piece::BlackKing);
    pos.set_side_to_move(r.stm == 0 ? Color::White : Color::Black);
    pos.set_halfmove_clock(0);
    return pos;
}

int absolute_white_utility(EndgameResult r) noexcept {
    if (r == EndgameResult::WhiteWin) return 1;
    if (r == EndgameResult::BlackWin) return -1;
    return 0;
}

std::string parent_fingerprint(const DiskRow& r) {
    std::ostringstream out;
    out << std::hex << std::setfill('0')
        << std::setw(13) << r.wm << ':'
        << std::setw(13) << r.wk << ':'
        << std::setw(13) << r.bm << ':'
        << std::setw(13) << r.bk << ':'
        << std::dec << static_cast<int>(r.stm);
    return out.str();
}

bool same_semantic_move(const Move& a, const Move& b) noexcept {
    return a.from == b.from && a.to == b.to && a.captured == b.captured
        && a.promotes == b.promotes;
}

void write_report(const std::string& path, const std::string& input,
                  int tb_cap, int parent_pieces, const Counters& c) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open report output");
    out << "{\n"
        << "  \"schema\": \"jass.tb_frontier_extract.v1\",\n"
        << "  \"input\": \"" << input << "\",\n"
        << "  \"egdb_max_pieces\": " << tb_cap << ",\n"
        << "  \"parent_pieces\": " << parent_pieces << ",\n"
        << "  \"source_rows\": " << c.source_rows << ",\n"
        << "  \"invalid_rows\": " << c.invalid_rows << ",\n"
        << "  \"parent_piece_rows\": " << c.parent_piece_rows << ",\n"
        << "  \"duplicate_parent_states\": " << c.duplicate_parent_states << ",\n"
        << "  \"multi_capture_parents\": " << c.multi_capture_parents << ",\n"
        << "  \"duplicate_move_entries\": " << c.duplicate_move_entries << ",\n"
        << "  \"child_above_tb_cap\": " << c.child_above_tb_cap << ",\n"
        << "  \"child_unknown_probes\": " << c.child_unknown_probes << ",\n"
        << "  \"all_children_exact_parents\": " << c.all_children_exact_parents << ",\n"
        << "  \"homogeneous_wld_parents\": " << c.homogeneous_wld_parents << ",\n"
        << "  \"informative_parents\": " << c.informative_parents << ",\n"
        << "  \"child_rows\": " << c.child_rows << "\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "JNNW tool currently requires a little-endian host");
    if (argc < 6 || argc > 8) {
        std::cerr << "usage: jass_tb_frontier <input.jnnw> <children.jnnw> "
                     "<groups.tsv> <report.json> <egdb_dir> [cache_mb=2048] "
                     "[parent_pieces=egdb_max+1]\n";
        return 2;
    }

    const std::string input_path = argv[1];
    const std::string child_path = argv[2];
    const std::string groups_path = argv[3];
    const std::string report_path = argv[4];
    const std::string egdb_dir = argv[5];
    const int cache_mb = argc >= 7 ? std::max(64, std::stoi(argv[6])) : 2048;

    if (!egdb::init(egdb_dir, cache_mb) || !egdb::available()) {
        std::cerr << "error: EGDB unavailable at " << egdb_dir << '\n';
        return 3;
    }
    const int tb_cap = egdb::max_pieces();
    if (tb_cap <= 0) {
        std::cerr << "error: EGDB reports invalid piece cap " << tb_cap << '\n';
        return 3;
    }
    const int parent_pieces = argc >= 8 ? std::stoi(argv[7]) : tb_cap + 1;
    if (parent_pieces <= tb_cap) {
        std::cerr << "error: parent_pieces must be strictly outside EGDB coverage\n";
        return 2;
    }

    std::ifstream in(input_path, std::ios::binary);
    if (!in) {
        std::cerr << "error: cannot open " << input_path << '\n';
        return 4;
    }
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size()))
        || std::memcmp(header.data(), "JNNW", 4) != 0) {
        std::cerr << "error: input is not counted JNNW\n";
        return 4;
    }
    const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);

    std::ofstream children(child_path, std::ios::binary);
    std::ofstream groups(groups_path);
    if (!children || !groups) {
        std::cerr << "error: cannot open output files\n";
        return 5;
    }
    children.write("JNNW", 4);
    const std::uint32_t zero = 0;
    children.write(reinterpret_cast<const char*>(&zero), 4);
    groups << "row_index\tparent_id\tparent_fingerprint\tparent_stm\tfrom\tto\t"
              "num_captures\tpromotes\tmoving_king\tcaptured_kings\t"
              "parent_utility\tchild_tb_wdl_stm\n";

    Counters c{};
    std::unordered_set<std::string> seen_parents;
    seen_parents.reserve(static_cast<std::size_t>(declared / 20U + 1024U));
    std::uint64_t next_parent_id = 0;
    std::uint32_t output_count = 0;

    DiskRow row{};
    for (std::uint32_t idx = 0; idx < declared; ++idx) {
        if (!read_row(in, row)) {
            std::cerr << "error: truncated JNNW at row " << idx << '\n';
            return 4;
        }
        ++c.source_rows;
        if (!valid_row(row)) { ++c.invalid_rows; continue; }
        if (popcount(row.wm | row.wk | row.bm | row.bk) != parent_pieces) continue;
        ++c.parent_piece_rows;

        const std::string fingerprint = parent_fingerprint(row);
        if (!seen_parents.insert(fingerprint).second) {
            ++c.duplicate_parent_states;
            continue;
        }

        const Position parent = position_from_row(row);
        MoveList legal;
        generate_legal_moves(parent, legal);
        if (legal.size() < 2 || !legal[0].is_capture()) continue;

        std::vector<Move> unique_moves;
        unique_moves.reserve(legal.size());
        for (const Move& m : legal) {
            const auto it = std::find_if(unique_moves.begin(), unique_moves.end(),
                [&](const Move& x) { return same_semantic_move(x, m); });
            if (it == unique_moves.end()) unique_moves.push_back(m);
            else ++c.duplicate_move_entries;
        }
        if (unique_moves.size() < 2) continue;
        ++c.multi_capture_parents;

        std::vector<ChildLabel> labelled;
        labelled.reserve(unique_moves.size());
        bool exact = true;
        for (const Move& move : unique_moves) {
            Position child = parent.after(move);
            if (popcount(child.occupied()) > tb_cap) {
                ++c.child_above_tb_cap;
                exact = false;
                break;
            }
            const EndgameResult result = egdb::probe(child);
            if (result == EndgameResult::Unknown) {
                ++c.child_unknown_probes;
                exact = false;
                break;
            }
            const int white_u = absolute_white_utility(result);
            const int parent_u = parent.side_to_move() == Color::White ? white_u : -white_u;
            const int child_u = child.side_to_move() == Color::White ? white_u : -white_u;
            labelled.push_back(ChildLabel{
                move,
                std::move(child),
                parent_u,
                child_u,
                test(parent.kings_of(parent.side_to_move()), move.from),
                popcount(move.captured & parent.kings_of(opposite(parent.side_to_move())))
            });
        }
        if (!exact || labelled.size() != unique_moves.size()) continue;
        ++c.all_children_exact_parents;

        const auto [umin_it, umax_it] = std::minmax_element(
            labelled.begin(), labelled.end(),
            [](const ChildLabel& a, const ChildLabel& b) {
                return a.parent_utility < b.parent_utility;
            });
        if (umin_it->parent_utility == umax_it->parent_utility) {
            ++c.homogeneous_wld_parents;
            continue;
        }

        const std::uint64_t parent_id = next_parent_id++;
        ++c.informative_parents;
        for (const ChildLabel& item : labelled) {
            write_row(children, item.child, static_cast<std::int8_t>(item.child_wdl_stm));
            groups << output_count << '\t' << parent_id << '\t' << fingerprint << '\t'
                   << static_cast<int>(row.stm) << '\t'
                   << static_cast<int>(item.move.from) << '\t'
                   << static_cast<int>(item.move.to) << '\t'
                   << static_cast<int>(item.move.num_captures) << '\t'
                   << (item.move.promotes ? 1 : 0) << '\t'
                   << (item.moving_king ? 1 : 0) << '\t'
                   << item.captured_kings << '\t'
                   << item.parent_utility << '\t'
                   << item.child_wdl_stm << '\n';
            ++output_count;
            ++c.child_rows;
        }
    }

    char trailing = 0;
    if (in.read(&trailing, 1)) {
        std::cerr << "error: trailing bytes after declared JNNW rows\n";
        return 4;
    }

    children.seekp(4, std::ios::beg);
    children.write(reinterpret_cast<const char*>(&output_count), 4);
    children.flush();
    groups.flush();
    if (!children || !groups) {
        std::cerr << "error: output write failed\n";
        return 5;
    }

    try {
        write_report(report_path, input_path, tb_cap, parent_pieces, c);
    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << '\n';
        return 5;
    }

    std::cout << "TBFRONTIER"
              << " source_rows=" << c.source_rows
              << " parent_piece_rows=" << c.parent_piece_rows
              << " multi_capture_parents=" << c.multi_capture_parents
              << " all_children_exact=" << c.all_children_exact_parents
              << " informative_parents=" << c.informative_parents
              << " child_rows=" << c.child_rows
              << " egdb_max_pieces=" << tb_cap
              << " parent_pieces=" << parent_pieces << '\n';
    egdb::shutdown();
    return 0;
}
