// SPDX-License-Identifier: AGPL-3.0-or-later
#include "bitboard.hpp"
#include "position.hpp"
#include "residual_features.hpp"

#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

std::uint32_t read_u32(std::istream& in) {
    std::array<unsigned char, 4> b{};
    in.read(reinterpret_cast<char*>(b.data()), 4);
    if (!in) throw std::runtime_error("truncated u32");
    return static_cast<std::uint32_t>(b[0])
         | (static_cast<std::uint32_t>(b[1]) << 8U)
         | (static_cast<std::uint32_t>(b[2]) << 16U)
         | (static_cast<std::uint32_t>(b[3]) << 24U);
}

std::uint64_t read_u64(std::istream& in) {
    std::array<unsigned char, 8> b{};
    in.read(reinterpret_cast<char*>(b.data()), 8);
    if (!in) throw std::runtime_error("truncated u64");
    std::uint64_t v = 0;
    for (unsigned i = 0; i < 8U; ++i) v |= static_cast<std::uint64_t>(b[i]) << (8U * i);
    return v;
}

void write_u32(std::ostream& out, std::uint32_t v) {
    const std::array<unsigned char, 4> b = {
        static_cast<unsigned char>(v & 0xffU),
        static_cast<unsigned char>((v >> 8U) & 0xffU),
        static_cast<unsigned char>((v >> 16U) & 0xffU),
        static_cast<unsigned char>((v >> 24U) & 0xffU),
    };
    out.write(reinterpret_cast<const char*>(b.data()), 4);
}

void add_bits(jass::Position& p, jass::Bitboard bb, jass::Piece piece) {
    while (bb) p.add_piece(jass::pop_lsb(bb), piece);
}

jass::Position read_record(std::istream& in) {
    const std::uint64_t wm = read_u64(in);
    const std::uint64_t wk = read_u64(in);
    const std::uint64_t bm = read_u64(in);
    const std::uint64_t bk = read_u64(in);
    unsigned char stm = 0;
    in.read(reinterpret_cast<char*>(&stm), 1);
    if (!in) throw std::runtime_error("truncated stm");
    // score (i32) and WDL (i8) are deliberately consumed but NEVER interpreted.
    std::array<unsigned char, 5> forbidden_labels{};
    in.read(reinterpret_cast<char*>(forbidden_labels.data()), 5);
    if (!in) throw std::runtime_error("truncated forbidden label bytes");

    jass::Position p;
    p.clear();
    add_bits(p, wm, jass::Piece::WhiteMan);
    add_bits(p, wk, jass::Piece::WhiteKing);
    add_bits(p, bm, jass::Piece::BlackMan);
    add_bits(p, bk, jass::Piece::BlackKing);
    if (stm > 1U) throw std::runtime_error("invalid JNNW stm");
    p.set_side_to_move(stm == 0U ? jass::Color::White : jass::Color::Black);
    return p;
}

void write_float_le(std::ostream& out, float value) {
    static_assert(sizeof(float) == 4U);
    std::uint32_t raw = 0;
    std::memcpy(&raw, &value, 4);
#if __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
    raw = __builtin_bswap32(raw);
#endif
    write_u32(out, raw);
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 3) {
            std::cerr << "usage: residual_feature_dump <children.jnnw> <features.rffd>\n";
            return 2;
        }
        std::ifstream in(argv[1], std::ios::binary);
        if (!in) throw std::runtime_error("cannot open JNNW input");
        std::array<char, 4> magic{};
        in.read(magic.data(), 4);
        if (!in || std::string(magic.data(), magic.size()) != "JNNW") throw std::runtime_error("bad JNNW magic");
        const std::uint32_t n = read_u32(in);

        std::ofstream out(argv[2], std::ios::binary | std::ios::trunc);
        if (!out) throw std::runtime_error("cannot open RFFD output");
        out.write("RFFD", 4);
        write_u32(out, n);
        write_u32(out, static_cast<std::uint32_t>(jass::residual_features::TOTAL_WIDTH));

        bool ctx2_verified = false;
        for (std::uint32_t i = 0; i < n; ++i) {
            const jass::Position p = read_record(in);
            const auto f = jass::residual_features::extract(p);
            if (!f.ctx2_available) {
                throw std::runtime_error(
                    "CTX2_REF unavailable: build with JASS_ENDGAME_FEATURES=ON, "
                    "JASS_KING_MOBILITY=ON, JASS_SCAN_PARITY=ON, JASS_TEMPO_STAGE=ON");
            }
            ctx2_verified = true;
            for (float value : f.packed()) write_float_le(out, value);
        }
        char extra = 0;
        if (in.read(&extra, 1)) throw std::runtime_error("JNNW trailing bytes/count drift");
        if (!out) throw std::runtime_error("RFFD write failed");
        std::cout << "RFFD rows=" << n
                  << " width=" << jass::residual_features::TOTAL_WIDTH
                  << " ctx2=" << (ctx2_verified || n == 0U ? "verified" : "missing")
                  << "\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "residual_feature_dump: " << e.what() << "\n";
        return 1;
    }
}
