// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once
#include "bitboard.hpp"
#include "position.hpp"
#include <array>
#include <cstdint>
#include <cstring>
#include <istream>
#include <stdexcept>

namespace pl8_tooling {
using namespace jass;
inline constexpr std::size_t REC=38;
struct DiskRow { std::uint64_t wm{},wk{},bm{},bk{}; std::uint8_t stm{}; };
template<class T> T load_le(const char* p) noexcept { T v{}; std::memcpy(&v,p,sizeof(T)); return v; }
inline std::uint32_t read_counted_header(std::istream& in) {
    std::array<char,8> h{};
    if(!in.read(h.data(),8) || std::memcmp(h.data(),"JNNW",4)!=0) throw std::runtime_error("bad JNNW header");
    return load_le<std::uint32_t>(h.data()+4);
}
inline bool read_zero_target(std::istream& in,DiskRow& r) {
    std::array<char,REC> raw{}; if(!in.read(raw.data(),REC)) return false;
    r.wm=load_le<std::uint64_t>(raw.data()+0);r.wk=load_le<std::uint64_t>(raw.data()+8);
    r.bm=load_le<std::uint64_t>(raw.data()+16);r.bk=load_le<std::uint64_t>(raw.data()+24);r.stm=load_le<std::uint8_t>(raw.data()+32);
    if(load_le<std::int32_t>(raw.data()+33)!=0 || load_le<std::int8_t>(raw.data()+37)!=0) throw std::runtime_error("JNNW target bytes nonzero");
    const Bitboard all=r.wm|r.wk|r.bm|r.bk;
    if(r.stm>1 || (all&~PLAYABLE_BB)!=0 || ((r.wm&r.wk)|(r.wm&r.bm)|(r.wm&r.bk)|(r.wk&r.bm)|(r.wk&r.bk)|(r.bm&r.bk))!=0) throw std::runtime_error("invalid JNNW board");
    return true;
}
inline void add(Position& p,Bitboard b,Piece pc){while(b)p.add_piece(pop_lsb(b),pc);}
inline Position position(const DiskRow& r){Position p;p.clear();add(p,r.wm,Piece::WhiteMan);add(p,r.wk,Piece::WhiteKing);add(p,r.bm,Piece::BlackMan);add(p,r.bk,Piece::BlackKing);p.set_side_to_move(r.stm?Color::Black:Color::White);p.set_halfmove_clock(0);return p;}
inline void require_eof(std::istream& in){char c;if(in.read(&c,1))throw std::runtime_error("JNNW trailing bytes");}
} // namespace pl8_tooling
