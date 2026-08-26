// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-Francois Collin
//
// Target-blind parent filter for Deep Search Sibling Distillation.
// Reads counted JNNW and consumes ONLY board state + side-to-move. Historical
// score/WDL bytes are deliberately ignored and zeroed in the output.

#include "bitboard.hpp"
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
    std::uint64_t wm{0}, wk{0}, bm{0}, bk{0};
    std::uint8_t stm{0};
};

struct Counters {
    std::uint64_t source_rows{0};
    std::uint64_t invalid_rows{0};
    std::uint64_t piece_eligible_rows{0};
    std::uint64_t exact_duplicates{0};
    std::uint64_t below_min_moves{0};
    std::uint64_t above_max_moves{0};
    std::uint64_t duplicate_move_entries{0};
    std::uint64_t selected_parents{0};
};

template <typename T>
T load_le(const char* p) noexcept { T out{}; std::memcpy(&out, p, sizeof(T)); return out; }

template <typename T>
void store_le(char* p, T value) noexcept { std::memcpy(p, &value, sizeof(T)); }

bool read_row(std::istream& in, DiskRow& row) {
    std::array<char, JNNW_RECORD_SIZE> raw{};
    if (!in.read(raw.data(), static_cast<std::streamsize>(raw.size()))) return false;
    row.wm = load_le<std::uint64_t>(raw.data() + 0);
    row.wk = load_le<std::uint64_t>(raw.data() + 8);
    row.bm = load_le<std::uint64_t>(raw.data() + 16);
    row.bk = load_le<std::uint64_t>(raw.data() + 24);
    row.stm = load_le<std::uint8_t>(raw.data() + 32);
    return true; // score + WDL bytes 33..37 are intentionally never read.
}

bool valid_row(const DiskRow& r) noexcept {
    if (r.stm > 1) return false;
    const Bitboard all = r.wm | r.wk | r.bm | r.bk;
    if ((all & ~PLAYABLE_BB) != 0) return false;
    return ((r.wm & r.wk) | (r.wm & r.bm) | (r.wm & r.bk)
          | (r.wk & r.bm) | (r.wk & r.bk) | (r.bm & r.bk)) == 0;
}

void add_bits(Position& pos, Bitboard bb, Piece piece) {
    while (bb) pos.add_piece(pop_lsb(bb), piece);
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

std::string fingerprint(const DiskRow& r) {
    std::ostringstream out;
    out << std::hex << std::setfill('0')
        << std::setw(13) << r.wm << ':' << std::setw(13) << r.wk << ':'
        << std::setw(13) << r.bm << ':' << std::setw(13) << r.bk << ':'
        << std::dec << static_cast<int>(r.stm);
    return out.str();
}

bool same_semantic_move(const Move& a, const Move& b) noexcept {
    return a.from == b.from && a.to == b.to && a.captured == b.captured
        && a.promotes == b.promotes;
}

void write_zero_target_row(std::ostream& out, const DiskRow& r) {
    std::array<char, JNNW_RECORD_SIZE> raw{};
    store_le<std::uint64_t>(raw.data() + 0, r.wm);
    store_le<std::uint64_t>(raw.data() + 8, r.wk);
    store_le<std::uint64_t>(raw.data() + 16, r.bm);
    store_le<std::uint64_t>(raw.data() + 24, r.bk);
    store_le<std::uint8_t>(raw.data() + 32, r.stm);
    store_le<std::int32_t>(raw.data() + 33, 0);
    store_le<std::int8_t>(raw.data() + 37, 0);
    out.write(raw.data(), static_cast<std::streamsize>(raw.size()));
}

void write_report(const std::string& path, const std::string& input,
                  int min_pieces, int max_pieces, int min_moves, int max_moves,
                  const Counters& c) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open report output");
    out << "{\n"
        << "  \"schema\": \"jass.deep_sibling.parent_filter.v1\",\n"
        << "  \"input\": \"" << input << "\",\n"
        << "  \"labels_used_from_sources\": false,\n"
        << "  \"source_score_bytes_read\": false,\n"
        << "  \"source_wdl_bytes_read\": false,\n"
        << "  \"min_pieces\": " << min_pieces << ",\n"
        << "  \"max_pieces\": " << max_pieces << ",\n"
        << "  \"min_semantic_legal_moves\": " << min_moves << ",\n"
        << "  \"max_semantic_legal_moves\": " << max_moves << ",\n"
        << "  \"source_rows\": " << c.source_rows << ",\n"
        << "  \"invalid_rows\": " << c.invalid_rows << ",\n"
        << "  \"piece_eligible_rows\": " << c.piece_eligible_rows << ",\n"
        << "  \"exact_duplicates\": " << c.exact_duplicates << ",\n"
        << "  \"below_min_moves\": " << c.below_min_moves << ",\n"
        << "  \"above_max_moves\": " << c.above_max_moves << ",\n"
        << "  \"duplicate_move_entries\": " << c.duplicate_move_entries << ",\n"
        << "  \"selected_parents\": " << c.selected_parents << "\n"
        << "}\n";
}
} // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "JNNW tools currently require little-endian hosts");
    if (argc < 5 || argc > 9) {
        std::cerr << "usage: jass_deep_sibling_parent_filter <input.jnnw> <parents.jnnw> "
                     "<parents.tsv> <report.json> [min_pieces=9] [max_pieces=40] "
                     "[min_moves=2] [max_moves=16]\n";
        return 2;
    }
    const std::string input_path = argv[1], output_path = argv[2], tsv_path = argv[3], report_path = argv[4];
    const int min_pieces = argc >= 6 ? std::stoi(argv[5]) : 9;
    const int max_pieces = argc >= 7 ? std::stoi(argv[6]) : 40;
    const int min_moves = argc >= 8 ? std::stoi(argv[7]) : 2;
    const int max_moves = argc >= 9 ? std::stoi(argv[8]) : 16;
    if (min_pieces < 1 || max_pieces > 40 || min_pieces > max_pieces
        || min_moves < 2 || max_moves < min_moves) {
        std::cerr << "error: invalid filter bounds\n";
        return 2;
    }

    std::ifstream in(input_path, std::ios::binary);
    if (!in) { std::cerr << "error: cannot open input\n"; return 4; }
    std::array<char,8> header{};
    if (!in.read(header.data(), 8) || std::memcmp(header.data(), "JNNW", 4) != 0) {
        std::cerr << "error: input is not counted JNNW\n"; return 4;
    }
    const std::uint32_t declared = load_le<std::uint32_t>(header.data()+4);

    std::ofstream parents(output_path, std::ios::binary);
    std::ofstream tsv(tsv_path);
    if (!parents || !tsv) { std::cerr << "error: cannot open outputs\n"; return 5; }
    parents.write("JNNW",4);
    const std::uint32_t zero = 0;
    parents.write(reinterpret_cast<const char*>(&zero),4);
    tsv << "row_index\tsource_row_index\tparent_fingerprint\tparent_stm\tpieces\tlegal_moves\n";

    Counters c{};
    std::unordered_set<std::string> seen;
    seen.reserve(static_cast<std::size_t>(declared / 8U + 1024U));
    std::uint32_t out_count = 0;
    DiskRow row{};
    for (std::uint32_t idx=0; idx<declared; ++idx) {
        if (!read_row(in,row)) { std::cerr << "error: truncated JNNW at row " << idx << '\n'; return 4; }
        ++c.source_rows;
        if (!valid_row(row)) { ++c.invalid_rows; continue; }
        const int pieces = popcount(row.wm | row.wk | row.bm | row.bk);
        if (pieces < min_pieces || pieces > max_pieces) continue;
        ++c.piece_eligible_rows;
        const std::string fp = fingerprint(row);
        if (!seen.insert(fp).second) { ++c.exact_duplicates; continue; }

        const Position parent = position_from_row(row);
        MoveList legal;
        generate_legal_moves(parent, legal);
        std::vector<Move> unique;
        unique.reserve(legal.size());
        for (const Move& move : legal) {
            auto it = std::find_if(unique.begin(), unique.end(), [&](const Move& x){ return same_semantic_move(x,move); });
            if (it == unique.end()) unique.push_back(move); else ++c.duplicate_move_entries;
        }
        const int nlegal = static_cast<int>(unique.size());
        if (nlegal < min_moves) { ++c.below_min_moves; continue; }
        if (nlegal > max_moves) { ++c.above_max_moves; continue; }

        write_zero_target_row(parents,row);
        tsv << out_count << '\t' << idx << '\t' << fp << '\t' << static_cast<int>(row.stm)
            << '\t' << pieces << '\t' << nlegal << '\n';
        ++out_count; ++c.selected_parents;
    }
    char trailing=0;
    if (in.read(&trailing,1)) { std::cerr << "error: trailing bytes after declared JNNW rows\n"; return 4; }
    parents.seekp(4);
    parents.write(reinterpret_cast<const char*>(&out_count),4);
    parents.close(); tsv.close();
    try { write_report(report_path,input_path,min_pieces,max_pieces,min_moves,max_moves,c); }
    catch (const std::exception& e) { std::cerr << "error: " << e.what() << '\n'; return 5; }
    return 0;
}
