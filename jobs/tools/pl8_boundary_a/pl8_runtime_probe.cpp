// SPDX-License-Identifier: AGPL-3.0-or-later
#include "pl8.hpp"
#include "egdb_bridge.hpp"
#include "position.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "search_params.hpp"
#include "tt.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

using namespace jass;
namespace {
using Clock=std::chrono::steady_clock;

std::string slurp(const std::string& p) {
    std::ifstream in(p,std::ios::binary); if(!in) throw std::runtime_error("cannot read text input");
    return std::string(std::istreambuf_iterator<char>(in),{});
}
std::vector<Position> read_fens(const std::string& p) {
    std::ifstream in(p); if(!in) throw std::runtime_error("cannot read roots");
    std::vector<Position> out; std::string line;
    while(std::getline(in,line)) {
        auto hash=line.find('#'); if(hash!=std::string::npos) line.resize(hash);
        const auto a=line.find_first_not_of(" \t\r\n"); if(a==std::string::npos) continue;
        const auto b=line.find_last_not_of(" \t\r\n"); line=line.substr(a,b-a+1);
        auto pos=Position::from_fen(line); if(!pos) throw std::runtime_error("bad root FEN"); out.push_back(*pos);
    }
    if(out.empty()) throw std::runtime_error("empty roots"); return out;
}
pl8::Model zero_model() {
    pl8::Model m; m.sigma.fill(1.0); m.shrink=1.0; return m;
}
struct Obs { SearchResult r{}; std::uint64_t wall_ns=0; };
Obs run_one(const Position& p,const INetwork* net,const SearchParams& params) {
    SearchLimits lim; lim.max_depth=9; lim.max_nodes=0; lim.threads=1; lim.movetime_ms=0; lim.tt_mb=16; lim.params=params; lim.nnue=net;
    TranspositionTable tt; tt.resize_mb(16);
    const auto t0=Clock::now(); auto r=search(p,lim,tt,{}); const auto t1=Clock::now();
    return {std::move(r),static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(t1-t0).count())};
}
bool same_result(const SearchResult& a,const SearchResult& b) {
    return a.best_move.from==b.best_move.from && a.best_move.to==b.best_move.to
        && a.best_move.captured==b.best_move.captured && a.best_move.promotes==b.best_move.promotes
        && a.score==b.score && a.depth==b.depth && a.completed_depth==b.completed_depth
        && a.effective_depth==b.effective_depth && a.nodes==b.nodes && a.eval_calls==b.eval_calls
        && a.qnodes==b.qnodes && a.tablebase_probes==b.tablebase_probes && a.tablebase_hits==b.tablebase_hits
        && a.pv==b.pv && a.stop_reason==b.stop_reason;
}
}

int main(int argc,char** argv) {
    if(argc!=6) {
        std::cerr<<"usage: pl8_runtime_probe <roots.fen> <curriculum.pjtw> <q00.txt> <egdb_dir> <report.json>\n";
        return 2;
    }
    try {
        const auto roots=read_fens(argv[1]); const std::string curriculum_path=argv[2];
        const auto params=parse_search_params(slurp(argv[3]));
        if(!egdb::init(argv[4],128) || !egdb::available()) throw std::runtime_error("EGDB unavailable");
        std::string err;
        auto base_weights=scan_eval::load_scan_weights(curriculum_path,&err);
        auto pl8_weights=scan_eval::load_scan_weights(curriculum_path,&err);
        if(!base_weights||!pl8_weights) throw std::runtime_error("CURRICULUM load failed: "+err);
        if(base_weights->fm_rank!=0||pl8_weights->fm_rank!=0) throw std::runtime_error("nonlinear CURRICULUM drift");
        scan_eval::ScanEvalNetwork base(std::move(*base_weights));
        pl8::Network latent(std::move(*pl8_weights),zero_model());

        std::uint64_t base_eval_ns=0,pl8_eval_ns=0,base_wall=0,pl8_wall=0,base_nodes=0,pl8_nodes=0;
        std::uint64_t base_evals=0,pl8_evals=0; std::uint64_t mismatches=0; long long checksum=0;
        constexpr int eval_reps=2000;
        for(std::size_t i=0;i<roots.size();++i) {
            const auto& p=roots[i];
            const int bs=base.evaluate(p), ps=latent.evaluate(p); if(bs!=ps) ++mismatches;
            auto eval_arm=[&](const INetwork& n,std::uint64_t& ns) {
                const auto a=Clock::now(); for(int r=0;r<eval_reps;++r) checksum += n.evaluate(p); const auto b=Clock::now();
                ns += static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(b-a).count());
            };
            if((i&1U)==0U) { eval_arm(base,base_eval_ns); eval_arm(latent,pl8_eval_ns); }
            else { eval_arm(latent,pl8_eval_ns); eval_arm(base,base_eval_ns); }

            Obs bo,po;
            if((i&1U)==0U) { bo=run_one(p,&base,params); po=run_one(p,&latent,params); }
            else { po=run_one(p,&latent,params); bo=run_one(p,&base,params); }
            if(!same_result(bo.r,po.r)) ++mismatches;
            base_wall+=bo.wall_ns; pl8_wall+=po.wall_ns; base_nodes+=bo.r.nodes; pl8_nodes+=po.r.nodes;
            base_evals+=bo.r.eval_calls; pl8_evals+=po.r.eval_calls;
        }
        if(mismatches) throw std::runtime_error("zero-residual PL8 changed score/search result");
        const double base_nps=base_wall?static_cast<double>(base_nodes)*1e9/base_wall:0.0;
        const double pl8_nps=pl8_wall?static_cast<double>(pl8_nodes)*1e9/pl8_wall:0.0;
        std::ofstream out(argv[5]); if(!out) throw std::runtime_error("cannot create report");
        out<<std::setprecision(17)
           <<"{\n  \"schema\": \"jass.pl8_boundary_a_runtime_probe.v1\",\n"
           <<"  \"technical_only\": true,\n  \"roots\": "<<roots.size()<<",\n  \"depth\": 9,\n"
           <<"  \"threads\": 1,\n  \"tt_mb\": 16,\n  \"book\": \"OFF\",\n"
           <<"  \"probe_model\": \"ZERO_RESIDUAL_T0_IDENTICAL\",\n"
           <<"  \"score_search_mismatches\": 0,\n"
           <<"  \"base_eval_ns_total\": "<<base_eval_ns<<",\n  \"pl8_eval_ns_total\": "<<pl8_eval_ns<<",\n"
           <<"  \"eval_calls_benchmark_per_arm\": "<<(roots.size()*eval_reps)<<",\n"
           <<"  \"base_search_wall_ns\": "<<base_wall<<",\n  \"pl8_search_wall_ns\": "<<pl8_wall<<",\n"
           <<"  \"base_nodes\": "<<base_nodes<<",\n  \"pl8_nodes\": "<<pl8_nodes<<",\n"
           <<"  \"base_eval_calls\": "<<base_evals<<",\n  \"pl8_eval_calls\": "<<pl8_evals<<",\n"
           <<"  \"base_nps\": "<<base_nps<<",\n  \"pl8_nps\": "<<pl8_nps<<",\n"
           <<"  \"search_wall_ratio_pl8_over_t0\": "<<(base_wall?static_cast<double>(pl8_wall)/base_wall:0.0)<<",\n"
           <<"  \"eval_wall_ratio_pl8_over_t0\": "<<(base_eval_ns?static_cast<double>(pl8_eval_ns)/base_eval_ns:0.0)<<",\n"
           <<"  \"checksum\": "<<checksum<<",\n  \"fit_runs\": 0,\n  \"fresh_labels\": 0,\n"
           <<"  \"strength_games\": 0,\n  \"promotion_authorized\": false\n}\n";
        std::cout<<"PL8 runtime technical probe PASS roots="<<roots.size()<<"\n"; return 0;
    } catch(const std::exception& e) {
        std::cerr<<"pl8_runtime_probe: "<<e.what()<<"\n"; return 1;
    }
}
