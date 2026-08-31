// SPDX-License-Identifier: AGPL-3.0-or-later
#include "pl8.hpp"
#include "pl8_jnnw.hpp"
#include "scan_eval.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <vector>

using namespace jass;
int main(int argc,char** argv){
 if(argc!=5){std::cerr<<"usage: pl8_anchor <states.jnnw> <curriculum.pjtw> <model.pl8p> <report.json>\n";return 2;}
 try{
  std::string err;auto w=scan_eval::load_scan_weights(argv[2],&err);if(!w)throw std::runtime_error("T0 load: "+err);
  scan_eval::ScanEvalNetwork t0(std::move(*w));auto net=pl8::load_network(argv[2],argv[3],&err);if(!net)throw std::runtime_error("PL8 reload: "+err);
  std::ifstream in(argv[1],std::ios::binary);if(!in)throw std::runtime_error("anchor open");const auto n=pl8_tooling::read_counted_header(in);if(n!=500000U)throw std::runtime_error("anchor states !=500000");
  long double ss=0;int mx=0;std::vector<int>d;d.reserve(n);pl8_tooling::DiskRow r;
  for(std::uint32_t i=0;i<n;++i){if(!pl8_tooling::read_zero_target(in,r))throw std::runtime_error("anchor truncated");auto p=pl8_tooling::position(r);int x=std::abs(net->evaluate(p)-t0.evaluate(p));d.push_back(x);ss+=(long double)x*x;mx=std::max(mx,x);}pl8_tooling::require_eof(in);
  std::sort(d.begin(),d.end());std::size_t rank=(std::size_t(n)*99U+99U)/100U;int p99=d.at(std::max<std::size_t>(1,rank)-1);double rms=std::sqrt(double(ss/(long double)n));
  std::ofstream out(argv[4]);if(!out)throw std::runtime_error("report create");out<<std::setprecision(17)
   <<"{\n  \"schema\": \"jass.pl8_anchor_eval.v1\",\n  \"states\": "<<n<<",\n  \"rms_abs_cp\": "<<rms<<",\n  \"p99_abs_cp\": "<<p99<<",\n  \"max_abs_cp\": "<<mx<<",\n  \"serialize_reload\": true,\n  \"source_labels_read\": false,\n  \"deep_scores_read\": 0,\n  \"runtime_micro_search\": false,\n  \"f6_present_at_inference\": false,\n  \"d_present_at_inference\": false,\n  \"d1_present_at_inference\": false,\n  \"rich_d_present_at_inference\": false,\n  \"strength_games\": 0\n}\n";return 0;
 }catch(const std::exception&e){std::cerr<<"pl8_anchor: "<<e.what()<<"\n";return 1;}
}
