// SPDX-License-Identifier: AGPL-3.0-or-later
// Read-only ED2 native value/feature bridge; no search or runtime engine change.
#include "scan_eval.hpp"
#include "movegen.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

#if !defined(JASS_TEMPO_STAGE) || !defined(JASS_SCAN_PARITY) || !defined(JASS_KING_MOBILITY) || !defined(JASS_ENDGAME_FEATURES)
#error ED2 requires the frozen 120-extra tempo architecture
#endif
#if defined(JASS_KING_PATTERNS) || defined(JASS_SCAN_EXACT_EVAL) || defined(JASS_DRAWISH_SCALING)
#error ED2 does not change the baseline eval semantics
#endif
namespace {
template<class T> T read_le(const char* p) { T x{}; std::memcpy(&x,p,sizeof x); return x; }
jass::Position position(const std::array<char,38>& r) {
    if (r[32]!=0 && r[32]!=1) throw std::runtime_error("invalid STM");
    for (std::size_t i=33;i<38;++i) if(r[i]!=0) throw std::runtime_error("expected score-free input");
    std::ostringstream f; f<<(r[32]==0?'W':'B');
    for (int side=0;side<2;++side) {
        f<<':'<<(side==0?'W':'B'); bool comma=false;
        for (int kind=0;kind<2;++kind) {
            auto b=read_le<std::uint64_t>(r.data()+8*(2*side+kind));
            if (b>>50) throw std::runtime_error("bitboard overflow");
            for(int i=0;i<50;++i) if (b&(1ULL<<i)) {
                if(comma) f<<','; if(kind) f<<'K'; f<<i+1; comma=true;
            }
        }
    }
    auto p=jass::Position::from_fen(f.str());
    if(!p) throw std::runtime_error("invalid board"); return *p;
}
double phase(const jass::Position& p) {
    long t=9L*jass::popcount(p.black_men());
    for(int r=0;r<10;++r) {
        const auto mask=31ULL<<(5*r);
        t+=r*(jass::popcount(p.white_men()&mask)-jass::popcount(p.black_men()&mask));
    }
    return std::clamp(static_cast<double>(t)/300.0,0.0,1.0);
}
}
int main(int argc,char** argv) {
    static_assert(std::endian::native==std::endian::little);
    static_assert(jass::scan_eval::NUM_EXTRAS==120);
    try {
        if(argc==2 && std::string(argv[1])=="--layout") {
            std::cout<<pattern_jass::TOTAL_BUCKETS<<" 120\n"; return 0;
        }
        if(argc!=4) throw std::runtime_error("usage: ed2_value_probe data.jnnw model.pjtw out.tsv");
        if(std::filesystem::exists(argv[3])) throw std::runtime_error("refusing output overwrite");
        if(std::getenv("JASS_DENSE_REMAP")) throw std::runtime_error("unexpected runtime remap");
        std::string err;
        auto w=jass::scan_eval::load_scan_weights(argv[2],&err);
        if(!w || w->fm_rank || w->scale!=1000 || !w->remap.empty() || !w->remap8.empty())
            throw std::runtime_error("expected ordinary PJTW v3 scale=1000: "+err);
        auto net=jass::scan_eval::load_scan_eval_network(argv[2],&err);
        if(!net) throw std::runtime_error(err);
        std::ifstream in(argv[1],std::ios::binary); std::array<char,8> head{};
        if(!in.read(head.data(),8) || std::memcmp(head.data(),"JNNW",4)) throw std::runtime_error("bad JNNW header");
        const auto n=read_le<std::uint32_t>(head.data()+4);
        if(!n || std::filesystem::file_size(argv[1])!=8ULL+38ULL*n) throw std::runtime_error("bad JNNW size");
        std::ofstream out(argv[3]); out<<std::setprecision(17)<<"row_index\tblack_logit\tscore_stm\twmg";
        for(int e=0;e<120;++e) out<<"\tx"<<e;
        out<<'\n';
        constexpr auto offsets=pattern_jass::pattern_offsets();
        for(std::uint32_t row=0;row<n;++row) {
            std::array<char,38> rec{}; if(!in.read(rec.data(),38)) throw std::runtime_error("truncated input");
            const auto p=position(rec); std::array<std::uint32_t,pattern_jass::NUM_PATTERNS> idx{};
            pattern_jass::extract_all(jass::scan_eval::pat_black(p),jass::scan_eval::pat_white(p),idx);
            std::int64_t mg=0,eg=0;
            for(std::size_t i=0;i<idx.size();++i) {
                const auto col=offsets[i]+idx[i]%pattern_jass::BUCKETS_PER_PATTERN;
                mg+=w->pat[col].mg; eg+=w->pat[col].eg;
            }
            std::array<float,120> x{}; jass::scan_eval::compute_extras(p,x);
            double em=0,ee=0;
            for(std::size_t i=0;i<x.size();++i) { em+=static_cast<double>(w->ext_mg[i])*x[i]; ee+=static_cast<double>(w->ext_eg[i])*x[i]; }
            const double wm=phase(p);
            const double z=(wm*(static_cast<double>(mg)+em)+(1.0-wm)*(static_cast<double>(eg)+ee))/1000.0;
            const double cp=(rec[32]==1?1.0:-1.0)*z*100.0;
            const int expected=static_cast<int>(std::clamp(cp,-20000.0,20000.0));
            const int native=net->evaluate(p);
            if(!std::isfinite(z) || expected!=native) throw std::runtime_error("native linear/rounding parity failure row="+std::to_string(row));
            out<<row<<'\t'<<z<<'\t'<<native<<'\t'<<wm;
            for(float a:x) out<<'\t'<<a;
            out<<'\n';
        }
        out.close(); if(!out) throw std::runtime_error("output failure");
        return 0;
    } catch(const std::exception& e) { std::cerr<<"ED2_VALUE_PROBE_FAILURE: "<<e.what()<<'\n'; return 2; }
}
