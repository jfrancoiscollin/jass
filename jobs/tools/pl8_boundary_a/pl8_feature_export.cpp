// SPDX-License-Identifier: AGPL-3.0-or-later
#include "pl8.hpp"
#include "bitboard.hpp"
#include "board.hpp"
#include "position.hpp"
#include "scan_eval.hpp"

#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace jass;

namespace {
constexpr std::size_t JNNW_RECORD_SIZE = 38;
constexpr std::uint32_t PL8X_VERSION = 1;

struct Row {
    std::uint64_t wm=0,wk=0,bm=0,bk=0;
    std::uint8_t stm=0;
};

template<class T> T load_le(const char* p) {
    T v{}; std::memcpy(&v,p,sizeof(T)); return v;
}
void write_u32(std::ostream& out, std::uint32_t v) {
    std::array<unsigned char,4> b{};
    for (unsigned i=0;i<4;++i) b[i]=static_cast<unsigned char>((v>>(8U*i))&0xffU);
    out.write(reinterpret_cast<const char*>(b.data()),4);
}
void write_u64(std::ostream& out, std::uint64_t v) {
    std::array<unsigned char,8> b{};
    for (unsigned i=0;i<8;++i) b[i]=static_cast<unsigned char>((v>>(8U*i))&0xffULL);
    out.write(reinterpret_cast<const char*>(b.data()),8);
}
void write_f64(std::ostream& out, double v) {
    write_u64(out,std::bit_cast<std::uint64_t>(v));
}

bool read_row(std::istream& in, Row& r) {
    std::array<char,JNNW_RECORD_SIZE> raw{};
    if(!in.read(raw.data(),static_cast<std::streamsize>(raw.size()))) return false;
    r.wm=load_le<std::uint64_t>(raw.data()+0);
    r.wk=load_le<std::uint64_t>(raw.data()+8);
    r.bm=load_le<std::uint64_t>(raw.data()+16);
    r.bk=load_le<std::uint64_t>(raw.data()+24);
    r.stm=load_le<std::uint8_t>(raw.data()+32);
    return true; // target bytes [33..37] are deliberately never decoded.
}
void add_bits(Position& p, Bitboard b, Piece piece) {
    while(b) p.add_piece(pop_lsb(b),piece);
}
Position position_from(const Row& r) {
    if(r.stm>1) throw std::runtime_error("invalid JNNW stm");
    const Bitboard all=r.wm|r.wk|r.bm|r.bk;
    if((all&~PLAYABLE_BB)!=0 || ((r.wm&r.wk)|(r.wm&r.bm)|(r.wm&r.bk)|(r.wk&r.bm)|(r.wk&r.bk)|(r.bm&r.bk))!=0)
        throw std::runtime_error("invalid JNNW board");
    Position p; p.clear();
    add_bits(p,r.wm,Piece::WhiteMan); add_bits(p,r.wk,Piece::WhiteKing);
    add_bits(p,r.bm,Piece::BlackMan); add_bits(p,r.bk,Piece::BlackKing);
    p.set_side_to_move(r.stm==0?Color::White:Color::Black);
    p.set_halfmove_clock(0);
    return p;
}
}

int main(int argc,char** argv) {
    static_assert(std::endian::native==std::endian::little);
    static_assert(scan_eval::NUM_EXTRAS==120);
    if(argc<5 || argc>7) {
        std::cerr<<"usage: pl8_feature_export <in.jnnw> <curriculum.pjtw> <out.pl8x> <report.json> [start=0] [count=all]\n";
        return 2;
    }
    try {
        const std::string input=argv[1], curriculum=argv[2], output=argv[3], report=argv[4];
        const std::uint64_t start=argc>=6?std::stoull(argv[5]):0ULL;
        std::ifstream in(input,std::ios::binary);
        if(!in) throw std::runtime_error("cannot open JNNW");
        std::array<char,8> header{};
        if(!in.read(header.data(),8) || std::memcmp(header.data(),"JNNW",4)!=0)
            throw std::runtime_error("bad JNNW header");
        const std::uint32_t declared=load_le<std::uint32_t>(header.data()+4);
        if(start>declared) throw std::runtime_error("start outside JNNW");
        const std::uint64_t available=static_cast<std::uint64_t>(declared)-start;
        const std::uint64_t count=argc>=7?std::stoull(argv[6]):available;
        if(count==0 || count>available) throw std::runtime_error("invalid PL8X count");

        std::string err;
        auto weights=scan_eval::load_scan_weights(curriculum,&err);
        if(!weights) throw std::runtime_error("CURRICULUM load failed: "+err);
        if(weights->fm_rank!=0) throw std::runtime_error("PL8 requires linear CURRICULUM v3");
        pl8::FeatureExtractor extractor(std::move(*weights));

        in.seekg(static_cast<std::streamoff>(8ULL+start*JNNW_RECORD_SIZE),std::ios::beg);
        std::ofstream out(output,std::ios::binary);
        if(!out) throw std::runtime_error("cannot create PL8X");
        out.write("PL8X",4); write_u32(out,PL8X_VERSION); write_u64(out,count);
        write_u32(out,static_cast<std::uint32_t>(pl8::INPUT_WIDTH)); write_u64(out,start);

        std::uint64_t white=0,black=0;
        double checksum=0.0;
        for(std::uint64_t i=0;i<count;++i) {
            Row r{}; if(!read_row(in,r)) throw std::runtime_error("truncated JNNW");
            const Position p=position_from(r);
            white += r.stm==0 ? 1ULL : 0ULL; black += r.stm==1 ? 1ULL : 0ULL;
            const auto x=extractor.extract(p);
            if(x[137]!=static_cast<double>(extractor.base_score(p)))
                throw std::runtime_error("PL8 T0 input equivalence mismatch");
            for(double v:x) {
                if(!std::isfinite(v)) throw std::runtime_error("non-finite PL8 input");
                write_f64(out,v); checksum += v*1.0e-12;
            }
        }
        if(!out) throw std::runtime_error("PL8X write failure");
        std::ofstream js(report);
        if(!js) throw std::runtime_error("cannot create report");
        js<<std::setprecision(17)
          <<"{\n  \"schema\": \"jass.pl8_feature_export.v1\",\n"
          <<"  \"rows\": "<<count<<",\n  \"source_start\": "<<start<<",\n"
          <<"  \"input_width\": 138,\n  \"latent_width\": 8,\n  \"learned_params\": 1121,\n"
          <<"  \"white_stm_rows\": "<<white<<",\n  \"black_stm_rows\": "<<black<<",\n"
          <<"  \"canonical_stm\": \"Black\",\n  \"dense_extras\": 120,\n"
          <<"  \"target_bytes_decoded\": false,\n  \"teacher_scores_read\": 0,\n"
          <<"  \"deep_labels_read\": 0,\n  \"fits\": 0,\n  \"strength_games\": 0,\n"
          <<"  \"input_equivalence_mismatches\": 0,\n  \"finite_checksum\": "<<checksum<<"\n}\n";
        std::cout<<"PL8X PASS rows="<<count<<"\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr<<"pl8_feature_export: "<<e.what()<<"\n"; return 1;
    }
}
