// SPDX-License-Identifier: AGPL-3.0-or-later
#include "pl8.hpp"
#include "pl8_jnnw.hpp"
#include "scan_eval.hpp"
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

using namespace jass;
namespace {
std::vector<std::string> split(const std::string&s){std::vector<std::string>v;std::size_t a=0;for(;;){auto b=s.find('\t',a);v.push_back(s.substr(a,b==std::string::npos?b:b-a));if(b==std::string::npos)break;a=b+1;}return v;}
}
int main(int argc,char**argv){
 if(argc!=8){std::cerr<<"usage: pl8_scalar_score <children.jnnw> <groups.tsv> <curriculum.pjtw> <model.pl8p> <old-t1.pjtw> <scores.tsv> <report.json>\n";return 2;}
 try{
  std::string err;auto w0=scan_eval::load_scan_weights(argv[3],&err);if(!w0)throw std::runtime_error("T0 load: "+err);scan_eval::ScanEvalNetwork t0(std::move(*w0));
  auto pl8=pl8::load_network(argv[3],argv[4],&err);if(!pl8)throw std::runtime_error("PL8 reload: "+err);
  auto w1=scan_eval::load_scan_weights(argv[5],&err);if(!w1)throw std::runtime_error("old T1 load: "+err);scan_eval::ScanEvalNetwork t1(std::move(*w1));
  std::ifstream in(argv[1],std::ios::binary),g(argv[2]);if(!in||!g)throw std::runtime_error("input open");auto n=pl8_tooling::read_counted_header(in);if(!n)throw std::runtime_error("empty children");
  std::string header;if(!std::getline(g,header))throw std::runtime_error("groups header");auto hf=split(header);int qi=-1,ri=-1;for(int i=0;i<(int)hf.size();++i){if(hf[i]=="q1k_parent")qi=i;if(hf[i]=="row_index")ri=i;}if(qi<0||ri<0)throw std::runtime_error("groups q1k/row fields missing");
  std::ofstream out(argv[6]);if(!out)throw std::runtime_error("score create");out<<"row_index\tt0_parent\tpl8_parent\tt1_parent\tmicro1000_parent\n";
  pl8_tooling::DiskRow r;std::string line;
  for(std::uint32_t i=0;i<n;++i){if(!pl8_tooling::read_zero_target(in,r))throw std::runtime_error("children truncated");if(!std::getline(g,line))throw std::runtime_error("groups truncated");auto f=split(line);if(qi>=(int)f.size()||ri>=(int)f.size()||std::stoul(f[ri])!=i)throw std::runtime_error("groups ordering drift");auto p=pl8_tooling::position(r);out<<i<<'\t'<<-t0.evaluate(p)<<'\t'<<-pl8->evaluate(p)<<'\t'<<-t1.evaluate(p)<<'\t'<<f[qi]<<'\n';}
  pl8_tooling::require_eof(in);if(std::getline(g,line))throw std::runtime_error("groups trailing rows");
  std::ofstream rep(argv[7]);if(!rep)throw std::runtime_error("report create");rep<<"{\n  \"schema\": \"jass.pl8_scalar_score.v1\",\n  \"rows\": "<<n<<",\n  \"score_convention\": \"higher_is_better_for_parent\",\n  \"curriculum_exact\": true,\n  \"pl8_serialize_reload\": true,\n  \"old_t1_diagnostic_only\": true,\n  \"micro1000_diagnostic_from_deep_receipt\": true,\n  \"runtime_micro_search\": false,\n  \"f6_present_at_inference\": false,\n  \"d_present_at_inference\": false,\n  \"d1_present_at_inference\": false,\n  \"rich_d_present_at_inference\": false,\n  \"fit_runs\": 0,\n  \"strength_games\": 0,\n  \"promotion_authorized\": false\n}\n";return 0;
 }catch(const std::exception&e){std::cerr<<"pl8_scalar_score: "<<e.what()<<"\n";return 1;}
}
