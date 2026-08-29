// SPDX-License-Identifier: AGPL-3.0-or-later
// HOME-only target-blind source generator for Search-Semantics Attribution V1.
// Randomness is read exclusively as little-endian uint64 values from stdin; the
// job feeds this stream from numpy.random.Generator(numpy.random.PCG64(seed)).

#include "bitboard.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "types.hpp"

#include <array>
#include <bit>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>

namespace {
constexpr std::size_t RECORD_SIZE = 38;

template <typename T> void store_le(char* p, T value) noexcept { std::memcpy(p, &value, sizeof(T)); }

std::uint64_t next_random() {
    std::uint64_t value = 0;
    if (!std::cin.read(reinterpret_cast<char*>(&value), sizeof(value)))
        throw std::runtime_error("PCG64 raw stream exhausted");
    return value;
}

std::string fingerprint(const jass::Position& p) {
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(13) << p.white_men() << ':'
        << std::setw(13) << p.white_kings() << ':' << std::setw(13) << p.black_men() << ':'
        << std::setw(13) << p.black_kings() << ':' << std::dec
        << (p.side_to_move() == jass::Color::White ? 0 : 1);
    return out.str();
}

void write_zero_target(std::ostream& out, const jass::Position& p) {
    std::array<char, RECORD_SIZE> r{};
    store_le<std::uint64_t>(r.data()+0,p.white_men()); store_le<std::uint64_t>(r.data()+8,p.white_kings());
    store_le<std::uint64_t>(r.data()+16,p.black_men()); store_le<std::uint64_t>(r.data()+24,p.black_kings());
    store_le<std::uint8_t>(r.data()+32,p.side_to_move()==jass::Color::White?0U:1U);
    store_le<std::int32_t>(r.data()+33,0); store_le<std::int8_t>(r.data()+37,0);
    out.write(r.data(), static_cast<std::streamsize>(r.size()));
}

const char* phase_for(int pieces) {
    if (pieces >= 30) return "P0"; if (pieces >= 20) return "P1";
    if (pieces >= 12) return "P2"; return "P3";
}
}

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little, "JNNW requires little endian");
    if (argc < 6 || argc > 8) {
        std::cerr << "usage: jass_search_semantics_source_generator <count> <out.jnnw> <report.json> <seed> <min_ply> [max_ply=160] [min_pieces=9]\n";
        return 2;
    }
    try {
        const std::uint32_t count=static_cast<std::uint32_t>(std::stoul(argv[1]));
        const std::string out_path=argv[2], report_path=argv[3];
        const std::uint64_t seed=std::stoull(argv[4]);
        const int min_ply=std::stoi(argv[5]); const int max_ply=argc>=7?std::stoi(argv[6]):160;
        const int min_pieces=argc>=8?std::stoi(argv[7]):9;
        if (!count || !seed || min_ply<0 || max_ply<min_ply || min_pieces<2 || min_pieces>40)
            throw std::runtime_error("invalid frozen source arguments");
        std::ofstream out(out_path,std::ios::binary|std::ios::trunc); if(!out) throw std::runtime_error("cannot open output");
        out.write("JNNW",4); out.write(reinterpret_cast<const char*>(&count),4);
        std::unordered_set<std::string> seen; seen.reserve(static_cast<std::size_t>(count)*2U);
        std::array<std::uint64_t,4> phases{}; std::uint64_t attempts=0,terminal=0,material=0,dups=0,captures=0,random_words=0;
        const std::uint64_t max_attempts=static_cast<std::uint64_t>(count)*500U+10000U;
        auto rnd=[&](){ ++random_words; return next_random(); };
        std::uint32_t written=0;
        while(written<count && attempts<max_attempts) {
            ++attempts; jass::Position p=jass::Position::start_position();
            const int target=min_ply+static_cast<int>(rnd()%static_cast<std::uint64_t>(max_ply-min_ply+1));
            bool ended=false;
            for(int ply=0;ply<target;++ply){ jass::MoveList legal; jass::generate_legal_moves(p,legal); if(legal.empty()){ended=true;break;} p=p.after(legal[static_cast<std::size_t>(rnd()%legal.size())]); }
            if(ended){++terminal;continue;}
            const int pieces=jass::popcount(p.occupied()); if(pieces<min_pieces){++material;continue;}
            jass::MoveList legal; jass::generate_legal_moves(p,legal); if(legal.empty()){++terminal;continue;}
            const std::string id=fingerprint(p); if(!seen.insert(id).second){++dups;continue;}
            captures+=static_cast<std::uint64_t>(legal[0].is_capture()); phases[phase_for(pieces)[1]-'0']++;
            write_zero_target(out,p); ++written;
        }
        out.close(); if(written!=count) throw std::runtime_error("fixed source support exhausted");
        std::ofstream report(report_path); if(!report) throw std::runtime_error("cannot open report");
        report << "{\n  \"schema\": \"jass.search_semantics_score_free_source.v1\",\n"
               << "  \"protocol\": \"L3_JASS_SCAN_SEARCH_SEMANTICS_ATTRIBUTION_V1_20260829\",\n"
               << "  \"benchmark_only\": true,\n  \"target_blind\": true,\n"
               << "  \"rng\": \"numpy.random.Generator(numpy.random.PCG64(seed)) raw uint64 little-endian stdin\",\n"
               << "  \"seed\": "<<seed<<",\n  \"records\": "<<written<<",\n  \"min_ply\": "<<min_ply<<",\n  \"max_ply\": "<<max_ply<<",\n  \"min_pieces\": "<<min_pieces<<",\n"
               << "  \"attempts\": "<<attempts<<",\n  \"random_words_consumed\": "<<random_words<<",\n"
               << "  \"terminal_rejected\": "<<terminal<<",\n  \"material_rejected\": "<<material<<",\n  \"exact_duplicates_rejected\": "<<dups<<",\n  \"capture_parents\": "<<captures<<",\n"
               << "  \"records_by_phase\": {\"P0\": "<<phases[0]<<", \"P1\": "<<phases[1]<<", \"P2\": "<<phases[2]<<", \"P3\": "<<phases[3]<<"},\n"
               << "  \"evaluations\": 0,\n  \"searches\": 0,\n  \"scores_generated\": 0,\n  \"wdl_generated\": 0,\n"
               << "  \"fits\": 0,\n  \"strength_games\": 0,\n  \"training_allowed\": false,\n  \"tuning_allowed\": false,\n  \"calibration_allowed\": false,\n  \"model_selection_allowed\": false,\n  \"promotion_authorized\": false\n}\n";
        std::cout << "score-free PCG64 source rows="<<written<<" seed="<<seed<<" random_words="<<random_words<<'\n';
        return 0;
    } catch(const std::exception& e) { std::cerr<<"search-semantics source error: "<<e.what()<<'\n'; return 3; }
}
