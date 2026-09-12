// SPDX-License-Identifier: AGPL-3.0-or-later
// ED4-FRESH score-free source. One endpoint per independently restarted trajectory.
#include "bitboard.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "types.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
namespace {
using Pos=jass::Position;
std::uint64_t rotate(std::uint64_t b){std::uint64_t r=0;for(unsigned i=0;i<50;++i)if(b&(1ULL<<i))r|=1ULL<<(49-i);return r;}
std::string fp(std::uint64_t wm,std::uint64_t wk,std::uint64_t bm,std::uint64_t bk,int stm){std::ostringstream o;o<<std::hex<<std::setfill('0')<<std::setw(13)<<wm<<':'<<std::setw(13)<<wk<<':'<<std::setw(13)<<bm<<':'<<std::setw(13)<<bk<<':'<<std::dec<<stm;return o.str();}
std::string exact(const Pos&p){return fp(p.white_men(),p.white_kings(),p.black_men(),p.black_kings(),p.side_to_move()==jass::Color::White?0:1);}
std::string canon(const Pos&p){int stm=p.side_to_move()==jass::Color::White?0:1;return std::min(exact(p),fp(rotate(p.black_men()),rotate(p.black_kings()),rotate(p.white_men()),rotate(p.white_kings()),1-stm));}
int phase(const Pos&p){int n=jass::popcount(p.occupied());return n>=30?0:n>=20?1:n>=12?2:3;}
std::array<char,38> record(const Pos&p){std::array<char,38>r{};std::array<std::uint64_t,4>b={p.white_men(),p.white_kings(),p.black_men(),p.black_kings()};for(std::size_t i=0;i<4;++i)std::memcpy(r.data()+8*i,&b[i],8);r[32]=p.side_to_move()==jass::Color::White?0:1;return r;}
void binary(const std::filesystem::path&path,const std::vector<std::array<char,38>>&rows){if(std::filesystem::exists(path))throw std::runtime_error("existing output");std::ofstream f(path,std::ios::binary);auto n=static_cast<std::uint32_t>(rows.size());f.write("JNNW",4);f.write(reinterpret_cast<const char*>(&n),4);for(auto&r:rows)f.write(r.data(),38);f.close();if(!f)throw std::runtime_error("binary output failure");}
}
int main(int argc,char**argv){
 static_assert(std::endian::native==std::endian::little);
 try{
  if(argc!=5)throw std::runtime_error("usage: ed4_fresh_source exclusions.txt out-dir production|smoke master-seed");
  std::string mode=argv[3];if(mode!="production"&&mode!="smoke")throw std::runtime_error("invalid mode");
  std::uint64_t master=std::stoull(argv[4]);
  std::ifstream in(argv[1]);if(!in)throw std::runtime_error("missing exclusions");
  std::set<std::string>used;std::string line;while(std::getline(in,line))if(!line.empty())used.insert(line);std::size_t exclusions=used.size();
  std::filesystem::path out=argv[2];if(std::filesystem::exists(out))throw std::runtime_error("output directory already exists");std::filesystem::create_directories(out);
  std::ofstream groups(out/"groups.tsv"),parents(out/"parents.tsv");
  groups<<"row_index\tsibling_identity\tchild_fingerprint\tchild_rule_terminal\tchild_legal_moves\tparent_id\tparent_phase\tparent_stm\tsplit\n";
  parents<<"parent_id\tparent_fingerprint\tcanonical_fingerprint\tparent_phase\tparent_stm\tsplit\ttrajectory_index\tseed\n";
  std::array<std::string,3>splits={"calibration","decision","reserved"};
  std::array<int,3>quotas=mode=="production"?std::array<int,3>{2,64,32}:std::array<int,3>{1,2,1};
  std::array<std::uint64_t,3>seeds={master,master+1,master+2};
  std::vector<std::array<char,38>>pr,cr;std::array<std::uint64_t,3>attempts{};
  for(std::size_t split=0;split<3;++split){
   std::mt19937_64 rng(seeds[split]);std::array<int,8>cells{};int kept=0;
   for(std::uint64_t attempt=0;kept<quotas[split]*8&&attempt<2000000ULL;++attempt){
    ++attempts[split];Pos p=Pos::start_position();int target=8+static_cast<int>(rng()%153ULL);bool dead=false;
    for(int ply=0;ply<target;++ply){jass::MoveList legal;jass::generate_legal_moves(p,legal);if(legal.empty()){dead=true;break;}p=p.after(legal[static_cast<std::size_t>(rng()%legal.size())]);}
    if(dead||jass::popcount(p.occupied())<9)continue;int ph=phase(p),stm=p.side_to_move()==jass::Color::White?0:1;auto cell=static_cast<std::size_t>(2*ph+stm);if(cells[cell]>=quotas[split])continue;
    jass::MoveList legal;jass::generate_legal_moves(p,legal);if(legal.size()<2||legal.size()>16)continue;
    std::vector<Pos>children;std::set<std::string>footprint{canon(p)};for(auto&move:legal){children.push_back(p.after(move));footprint.insert(canon(children.back()));}
    if(std::any_of(footprint.begin(),footprint.end(),[&](auto&x){return used.count(x)!=0;}))continue;
    auto pid=pr.size();pr.push_back(record(p));parents<<pid<<'\t'<<exact(p)<<'\t'<<canon(p)<<"\tP"<<ph<<'\t'<<stm<<'\t'<<splits[split]<<'\t'<<attempt<<'\t'<<seeds[split]<<'\n';
    for(std::size_t a=0;a<children.size();++a){auto&c=children[a];jass::MoveList reply;jass::generate_legal_moves(c,reply);groups<<cr.size()<<'\t'<<pid<<':'<<a<<'\t'<<exact(c)<<'\t'<<(reply.empty()?1:0)<<'\t'<<reply.size()<<'\t'<<pid<<"\tP"<<ph<<'\t'<<stm<<'\t'<<splits[split]<<'\n';cr.push_back(record(c));}
    used.insert(footprint.begin(),footprint.end());++cells[cell];++kept;
   }
   if(kept!=quotas[split]*8)throw std::runtime_error("fixed source support exhausted");
  }
  groups.close();parents.close();if(!groups||!parents)throw std::runtime_error("metadata output failure");binary(out/"parents.jnnw",pr);binary(out/"children.jnnw",cr);
  std::ofstream report(out/"source.json");report<<"{\"schema\":\"jass.ed4.fresh_scorefree_source.v1\",\"mode\":\""<<mode<<"\",\"master_seed\":"<<master<<",\"split_seeds\":["<<seeds[0]<<','<<seeds[1]<<','<<seeds[2]<<"],\"parents\":"<<pr.size()<<",\"children\":"<<cr.size()<<",\"excluded_identities\":"<<exclusions<<",\"attempts\":["<<attempts[0]<<','<<attempts[1]<<','<<attempts[2]<<"],\"evaluations\":0,\"searches\":0,\"fits\":0,\"scores_generated\":0,\"target_reads\":0,\"one_endpoint_per_trajectory\":true}\n";report.close();if(!report)throw std::runtime_error("report output failure");return 0;
 }catch(const std::exception&e){std::cerr<<"ED4_FRESH_SOURCE_TECHNICAL_FAILURE: "<<e.what()<<'\n';return 2;}
}
