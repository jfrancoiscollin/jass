// SPDX-License-Identifier: AGPL-3.0-or-later
// HOME-only score-free sibling enumeration for Search-Semantics Attribution V1.
// This freezes legal child identities and exact terminal/TB metadata only. It
// deliberately does not load CURRICULUM and does not evaluate or search a child.

#define main deep_sibling_teacher_main_disabled
#include "deep_sibling_teacher.cpp"
#undef main

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
    std::uint64_t source_rows{0}, processed_parent_rows{0}, invalid_rows{0};
    std::uint64_t duplicate_move_entries{0}, emitted_siblings{0};
    std::uint64_t rule_terminal_children{0}, exact_tb_children{0};
};

std::string child_fingerprint(const jass::Position& p) {
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(13) << p.white_men() << ':'
        << std::setw(13) << p.white_kings() << ':' << std::setw(13) << p.black_men() << ':'
        << std::setw(13) << p.black_kings() << ':' << std::dec
        << (p.side_to_move()==jass::Color::White?0:1);
    return out.str();
}
std::string bbhex(jass::Bitboard v) {
    std::ostringstream out; out << std::hex << std::setfill('0') << std::setw(13)
        << static_cast<std::uint64_t>(v); return out.str();
}
void report(const std::string& path, std::uint32_t declared, int shard, int nshards,
            int tb_cap, const ExportCounters& c) {
    std::ofstream out(path); if(!out) throw std::runtime_error("cannot open sibling report");
    out << "{\n  \"schema\": \"jass.search_semantics_sibling_export.v1\",\n"
        << "  \"protocol\": \"L3_JASS_SCAN_SEARCH_SEMANTICS_ATTRIBUTION_V1_20260829\",\n"
        << "  \"benchmark_only\": true,\n  \"target_blind\": true,\n  \"score_free\": true,\n"
        << "  \"input_parents\": "<<declared<<",\n  \"shard\": "<<shard<<",\n  \"nshards\": "<<nshards<<",\n"
        << "  \"semantic_move_order\": \"from,to,captured_bitboard,promotes\",\n"
        << "  \"egdb_max_pieces\": "<<tb_cap<<",\n  \"source_rows\": "<<c.source_rows<<",\n"
        << "  \"processed_parent_rows\": "<<c.processed_parent_rows<<",\n  \"invalid_rows\": "<<c.invalid_rows<<",\n"
        << "  \"duplicate_move_entries\": "<<c.duplicate_move_entries<<",\n  \"emitted_siblings\": "<<c.emitted_siblings<<",\n"
        << "  \"rule_terminal_children\": "<<c.rule_terminal_children<<",\n  \"exact_tb_children\": "<<c.exact_tb_children<<",\n"
        << "  \"source_labels_read\": false,\n  \"source_score_bytes_read\": false,\n  \"source_wdl_bytes_read\": false,\n"
        << "  \"curriculum_loaded\": false,\n  \"evaluations\": 0,\n  \"searches\": 0,\n  \"scores_generated\": 0,\n"
        << "  \"fits\": 0,\n  \"calibrations\": 0,\n  \"strength_games\": 0,\n  \"training_allowed\": false,\n"
        << "  \"tuning_allowed\": false,\n  \"model_selection_allowed\": false,\n  \"promotion_authorized\": false\n}\n";
}
}

int main(int argc,char** argv) {
    static_assert(std::endian::native==std::endian::little,"JNNW requires little endian");
    if(argc<6||argc>9){std::cerr<<"usage: jass_search_semantics_sibling_export <parents.jnnw> <children.jnnw> <groups.tsv> <report.json> <egdb_dir> [shard=0] [nshards=1] [egdb_cache_mb=256]\n";return 2;}
    if(std::getenv("JASS_TB_MOVE_ORDER_POLICY")||std::getenv("JASS_DSSD_MOVE_ORDER_POLICY")||std::getenv("JASS_T3_F6_MODEL")){std::cerr<<"error: runtime policy/model variables must be absent\n";return 2;}
    const std::string input=argv[1],children_path=argv[2],groups_path=argv[3],report_path=argv[4],egdb_dir=argv[5];
    const int shard=argc>=7?std::stoi(argv[6]):0,nshards=argc>=8?std::stoi(argv[7]):1,cache=argc>=9?std::max(64,std::stoi(argv[8])):256;
    if(nshards<=0||shard<0||shard>=nshards){std::cerr<<"error: invalid shard contract\n";return 2;}
    if(!jass::egdb::init(egdb_dir,cache)||!jass::egdb::available()){std::cerr<<"error: EGDB unavailable\n";return 3;}
    const int tb_cap=jass::egdb::max_pieces(); if(tb_cap<=0){std::cerr<<"error: bad EGDB cap\n";return 3;}
    std::ifstream in(input,std::ios::binary); std::array<char,8> header{};
    if(!in||!in.read(header.data(),8)||std::memcmp(header.data(),"JNNW",4)!=0){std::cerr<<"error: bad parent JNNW\n";return 4;}
    const std::uint32_t declared=load_le<std::uint32_t>(header.data()+4);
    std::ofstream children(children_path,std::ios::binary),groups(groups_path); if(!children||!groups){std::cerr<<"error: cannot open outputs\n";return 5;}
    children.write("JNNW",4); const std::uint32_t zero=0; children.write(reinterpret_cast<const char*>(&zero),4);
    groups << "local_row_index\tparent_id\tparent_fingerprint\tparent_stm\tparent_pieces\tfrom\tto\tcaptured_hex\tnum_captures\tpromotes\tmoving_king\tcaptured_kings\tmaterial_count_delta_parent\tchild_fingerprint\tchild_pieces\tchild_legal_moves\tchild_forced_capture\tchild_rule_terminal\tchild_tb_exact\texact_parent_utility\tt0_parent\n";
    ExportCounters c{}; std::uint32_t output_count=0; DiskRow row{};
    for(std::uint32_t idx=0;idx<declared;++idx){
        if(!read_row(in,row)){std::cerr<<"error: truncated parents\n";return 4;} ++c.source_rows;
        if(static_cast<int>(idx%static_cast<std::uint32_t>(nshards))!=shard) continue; ++c.processed_parent_rows;
        if(!valid_row(row)){++c.invalid_rows;continue;} if(row.score!=0||row.wdl!=0){std::cerr<<"error: parent targets not zero\n";return 4;}
        const int parent_pieces=jass::popcount(row.wm|row.wk|row.bm|row.bk); if(parent_pieces<9||parent_pieces>40){std::cerr<<"error: pieces drift\n";return 4;}
        const jass::Position parent=position_from_row(row); jass::MoveList legal; jass::generate_legal_moves(parent,legal); std::vector<jass::Move> unique; unique.reserve(legal.size());
        for(const auto& m:legal){auto it=std::find_if(unique.begin(),unique.end(),[&](const auto& x){return same_semantic_move(x,m);}); if(it==unique.end()) unique.push_back(m); else ++c.duplicate_move_entries;}
        std::sort(unique.begin(),unique.end(),semantic_less); if(unique.size()<2||unique.size()>16){std::cerr<<"error: legal support drift\n";return 4;}
        const std::string pfp=parent_fingerprint(row);
        for(const auto& move:unique){
            const bool moving_king=jass::test(parent.kings_of(parent.side_to_move()),move.from);
            const int captured_kings=jass::popcount(move.captured & parent.kings_of(jass::opposite(parent.side_to_move())));
            const jass::Position child=parent.after(move); jass::MoveList child_legal; jass::generate_legal_moves(child,child_legal);
            const bool forced=!child_legal.empty()&&child_legal[0].is_capture(); bool rule_terminal=false,tb_exact=false;
            const std::optional<int> exact=exact_parent_utility(parent,child,tb_cap,rule_terminal,tb_exact);
            c.rule_terminal_children+=static_cast<std::uint64_t>(rule_terminal); c.exact_tb_children+=static_cast<std::uint64_t>(tb_exact);
            write_zero_target_row(children,child);
            groups << output_count<<'\t'<<idx<<'\t'<<pfp<<'\t'<<static_cast<int>(row.stm)<<'\t'<<parent_pieces<<'\t'
                   <<static_cast<int>(move.from)<<'\t'<<static_cast<int>(move.to)<<'\t'<<bbhex(move.captured)<<'\t'<<static_cast<int>(move.num_captures)<<'\t'
                   <<(move.promotes?1:0)<<'\t'<<(moving_king?1:0)<<'\t'<<captured_kings<<'\t'<<material_count_delta_parent(parent,child)<<'\t'
                   <<child_fingerprint(child)<<'\t'<<jass::popcount(child.occupied())<<'\t'<<child_legal.size()<<'\t'<<(forced?1:0)<<'\t'
                   <<(rule_terminal?1:0)<<'\t'<<(tb_exact?1:0)<<'\t'<<(exact?*exact:2)<<'\t'<<0<<'\n';
            ++output_count; ++c.emitted_siblings;
        }
    }
    char trailing=0; if(in.read(&trailing,1)){std::cerr<<"error: trailing parent bytes\n";return 4;}
    children.seekp(4,std::ios::beg); children.write(reinterpret_cast<const char*>(&output_count),4); children.close(); groups.close();
    try{report(report_path,declared,shard,nshards,tb_cap,c);}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 5;}
    return 0;
}
