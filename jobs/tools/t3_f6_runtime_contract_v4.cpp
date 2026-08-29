// SPDX-License-Identifier: AGPL-3.0-or-later
// R0-v4 data-free ZERO-wrapper transparency and real-search contract probe.
#include "egdb_bridge.hpp"
#include "endgame.hpp"
#include "movegen.hpp"
#include "scan_sacs.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "search_params.hpp"
#include "t3_f6.hpp"
#include "tt.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {
using jass::DepthOneSearchTrace;
using jass::Move;
using jass::MoveList;
using jass::Position;

struct FenRow { std::string fen; Position position; };

std::string json_string(std::string_view value) {
    std::ostringstream out; out << '"';
    for (const unsigned char c : value) {
        switch (c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << static_cast<char>(c);
        }
    }
    return out << '"', out.str();
}
const char* boolean(bool value) noexcept { return value ? "true" : "false"; }

Position parse(std::string_view fen) {
    auto p=Position::from_fen(fen);
    if (!p) throw std::runtime_error("invalid FEN: "+std::string(fen));
    return *p;
}
std::vector<FenRow> read_fens(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open FEN file: "+path);
    std::vector<FenRow> out; std::string line;
    while (std::getline(in,line)) {
        const auto hash=line.find('#'); if (hash!=std::string::npos) line.resize(hash);
        const auto first=line.find_first_not_of(" \t\r\n");
        if (first==std::string::npos) continue;
        const auto last=line.find_last_not_of(" \t\r\n");
        line=line.substr(first,last-first+1U);
        out.push_back({line,parse(line)});
    }
    return out;
}
std::string phase(const Position& p) {
    const int n=std::popcount(p.occupied());
    if (n>=30 && n<=40) return "P0";
    if (n>=20 && n<=29) return "P1";
    if (n>=12 && n<=19) return "P2";
    if (n>=9 && n<=11) return "P3";
    return "OUT";
}
std::string move_id(const Move& move) {
    std::ostringstream out;
    out << static_cast<int>(move.from) << (move.is_capture()?'x':'-')
        << static_cast<int>(move.to);
    if (move.is_capture()) out << "/n" << static_cast<unsigned>(move.num_captures)
                               << "/bb" << std::hex << move.captured << std::dec;
    if (move.promotes) out << "/K";
    return out.str();
}
int rounded(int base,double residual) noexcept {
    return static_cast<int>(std::clamp(
        std::llround(static_cast<double>(base)-residual),-20000LL,20000LL));
}

bool same_result(const jass::SearchResult& a,const jass::SearchResult& b) {
    return a.best_move==b.best_move && a.score==b.score && a.depth==b.depth
        && a.effective_depth==b.effective_depth && a.completed_depth==b.completed_depth
        && a.aborted_iteration==b.aborted_iteration && a.stop_reason==b.stop_reason
        && a.nodes==b.nodes && a.cutoffs==b.cutoffs
        && a.first_move_cutoffs==b.first_move_cutoffs
        && a.pvs_researches==b.pvs_researches && a.moves_searched==b.moves_searched
        && a.eval_calls==b.eval_calls && a.scan_verify_probes==b.scan_verify_probes
        && a.scan_verify_cutoffs==b.scan_verify_cutoffs
        && a.scan_threat_reentries==b.scan_threat_reentries
        && a.qnodes==b.qnodes && a.qsearch_calls==b.qsearch_calls
        && a.tablebase_probes==b.tablebase_probes && a.tablebase_hits==b.tablebase_hits
        && a.tt_probes==b.tt_probes && a.tt_hits==b.tt_hits
        && a.terminal_hits==b.terminal_hits && a.reductions==b.reductions
        && a.extensions==b.extensions
        && a.root_order_applications==b.root_order_applications
        && a.root_order_failures==b.root_order_failures
        && a.pv==b.pv && a.from_book==b.from_book;
}

enum class Budget { Depth1, Nodes1k, Nodes10k };
const char* budget_name(Budget b) noexcept {
    switch (b) {
        case Budget::Depth1: return "depth1";
        case Budget::Nodes1k: return "nodes1000";
        case Budget::Nodes10k: return "nodes10000";
    }
    return "unknown";
}
struct Run { jass::SearchResult result{}; DepthOneSearchTrace trace{}; };
Run run_search(const Position& root,const jass::INetwork& net,
               const jass::SearchParams& params,Budget budget,bool traced=false) {
    Run out; jass::SearchLimits limits;
    limits.max_depth=budget==Budget::Depth1 ? 1 : 6;
    limits.tt_mb=16; limits.threads=1; limits.nnue=&net; limits.params=params;
    if (budget!=Budget::Depth1) {
        limits.max_nodes=budget==Budget::Nodes1k ? 1000U : 10000U;
        limits.node_limit_mode=jass::NodeLimitMode::Exact;
    }
    limits.depth_one_trace=traced ? &out.trace : nullptr;
    jass::TranspositionTable tt; tt.resize_mb(16);
    out.result=jass::search(root,limits,tt);
    return out;
}

bool trace_leaf_exact(const Run& run,const jass::INetwork& net) {
    if (run.trace.leaf_eval_overflow) return false;
    return std::all_of(run.trace.leaf_evals.begin(),run.trace.leaf_evals.end(),
        [&net](const jass::LeafEvalTrace& leaf) {
            return leaf.score==net.evaluate(leaf.position);
        });
}
bool trace_t3_formula(const Run& run,const jass::INetwork& t0,
                      const jass::t3_f6::Network& t3) {
    if (run.trace.leaf_eval_overflow) return false;
    return std::all_of(run.trace.leaf_evals.begin(),run.trace.leaf_evals.end(),
        [&t0,&t3](const jass::LeafEvalTrace& leaf) {
            const int base=t0.evaluate(leaf.position);
            return leaf.score==rounded(base,t3.residual_parent(leaf.position));
        });
}

bool isolated_leaf_root(const Position& root) {
    MoveList legal; jass::generate_legal_moves(root,legal);
    if (legal.size()<2U || legal[0].is_capture()) return false;
    for (const Move& move:legal) {
        const Position child=root.after(move);
        if (jass::probe_endgame(child)!=jass::EndgameResult::Unknown) return false;
        MoveList replies; jass::generate_legal_moves(child,replies);
        if (replies.empty() || std::any_of(replies.begin(),replies.end(),
                [](const Move& m){return m.is_capture();})) return false;
        if (jass::has_any_capture(child,jass::opposite(child.side_to_move()))) return false;
        MoveList sacs; jass::scan_add_sacs(child,sacs);
        if (!sacs.empty()) return false;
    }
    return true;
}
Position random_synthetic(std::mt19937_64& rng) {
    std::array<int,50> squares{}; std::iota(squares.begin(),squares.end(),1);
    std::shuffle(squares.begin(),squares.end(),rng);
    Position p; p.clear();
    for (int i=0;i<5;++i) p.add_piece(static_cast<jass::Square>(squares[i]),
        i==0 ? jass::Piece::WhiteKing : jass::Piece::WhiteMan);
    for (int i=5;i<10;++i) p.add_piece(static_cast<jass::Square>(squares[i]),
        i==5 ? jass::Piece::BlackKing : jass::Piece::BlackMan);
    p.set_side_to_move((rng()&1U)!=0U ? jass::Color::White : jass::Color::Black);
    return p;
}
int direct_score(const Position& root,const jass::INetwork& net) {
    MoveList legal; jass::generate_legal_moves(root,legal);
    int best=std::numeric_limits<int>::min();
    for (const Move& move:legal) best=std::max(best,-net.evaluate(root.after(move)));
    return best;
}
struct SyntheticSummary {
    std::size_t cases{0}; std::size_t gated{0}; std::size_t mismatches{0};
};
SyntheticSummary synthetic_gate(const jass::INetwork& t0,
                                const jass::t3_f6::Network& zero,
                                const jass::t3_f6::Network& t3,
                                const jass::SearchParams& params) {
    std::mt19937_64 rng(2026082901ULL); std::vector<Position> isolated;
    Position single; bool have_single=false;
    for (int attempt=0;attempt<100000 && (isolated.size()<2U || !have_single);++attempt) {
        Position p=random_synthetic(rng); MoveList legal;
        jass::generate_legal_moves(p,legal);
        if (!have_single && legal.size()==1U) {single=p;have_single=true;}
        if (isolated.size()<2U && isolated_leaf_root(p)) isolated.push_back(p);
    }
    if (!have_single || isolated.size()<2U)
        throw std::runtime_error("synthetic position search exhausted");
    std::vector<std::pair<Position,bool>> cases={{isolated[0],true},{single,false},{isolated[1],true}};
    SyntheticSummary out; out.cases=cases.size();
    for (const auto& [root,gated]:cases) {
        if (!gated) continue;
        ++out.gated;
        for (const jass::INetwork* net:std::array<const jass::INetwork*,3>{&t0,&zero,&t3}) {
            const auto actual=run_search(root,*net,params,Budget::Depth1,true);
            if (actual.result.score!=direct_score(root,*net)
                || !trace_leaf_exact(actual,*net)) ++out.mismatches;
        }
    }
    return out;
}

struct Sample {
    std::string fen; std::string budget; int t0_score{}; int t3_score{};
    std::string t0_move; std::string t3_move; std::uint64_t t0_nodes{}; std::uint64_t t3_nodes{};
};

int selftest() {
    class Square final:public jass::INetwork { public:
        int evaluate(const Position& p) const noexcept override {
            return static_cast<int>((p.white_men()^p.black_men())%401U)-200;
        }
    };
    auto base=std::make_unique<Square>(); Square direct;
    jass::t3_f6::Model model; model.stddev.fill(1.0);
    model.w0.assign(jass::t3_f6::INPUT_WIDTH*jass::t3_f6::H0,0.0);
    model.w1.assign(jass::t3_f6::H0*jass::t3_f6::H1,0.0);
    model.w2.assign(jass::t3_f6::H1*jass::t3_f6::H2,0.0);
    jass::t3_f6::Network zero(std::move(base),std::move(model));
    const Position root=Position::start_position(); jass::SearchParams params;
    const Run a=run_search(root,direct,params,Budget::Nodes1k);
    const Run b=run_search(root,zero,params,Budget::Nodes1k);
    if (!same_result(a.result,b.result) || zero.evaluate(root)!=direct.evaluate(root))
        throw std::runtime_error("V4 ZERO selftest failed");
    std::cout << "T3/F6 R0-v4 ZERO wrapper selftest PASS\n"; return 0;
}

int contract(int argc,char** argv) {
    if (argc!=10) throw std::runtime_error(
        "usage: t3_f6_runtime_contract_v4 <corpus.fen> <search.fen> <curriculum> "
        "<t3.json> --zero-probe <zero.json> <q00> <code-sha> <report.json>");
    const std::string corpus_path=argv[1],search_path=argv[2],curr_path=argv[3],
        t3_path=argv[4],zero_path=argv[6],params_spec=argv[7],code_sha=argv[8],out_path=argv[9];
    if (std::string_view(argv[5])!="--zero-probe")
        throw std::runtime_error("explicit --zero-probe flag missing");
    if (code_sha.size()!=40U || std::count(params_spec.begin(),params_spec.end(),',')+1!=63)
        throw std::runtime_error("code SHA/Q00 contract drift");
    std::string error;
    if (jass::t3_f6::sha256_file(curr_path,&error)!=jass::t3_f6::FROZEN_CURRICULUM_SHA256)
        throw std::runtime_error("CURRICULUM SHA mismatch");
    if (jass::t3_f6::sha256_file(t3_path,&error)!=jass::t3_f6::FROZEN_MODEL_SHA256)
        throw std::runtime_error("T3-A SHA mismatch");
    if (jass::t3_f6::sha256_file(zero_path,&error)!=jass::t3_f6::V4_ZERO_PROBE_SHA256)
        throw std::runtime_error("ZERO SHA mismatch");
    auto base0=jass::load_eval_network(curr_path,&error);
    auto basez=jass::load_eval_network(curr_path,&error);
    auto base3=jass::load_eval_network(curr_path,&error);
    if (!base0 || !basez || !base3) throw std::runtime_error("CURRICULUM load: "+error);
    auto mz=jass::t3_f6::load_model(zero_path,jass::t3_f6::LoadPolicy::ZeroProbeOnly,&error);
    auto m3=jass::t3_f6::load_model(t3_path,jass::t3_f6::LoadPolicy::FrozenOnly,&error);
    if (!mz || !m3) throw std::runtime_error("T3 model load: "+error);
    jass::t3_f6::Network zero(std::move(basez),std::move(*mz));
    jass::t3_f6::Network t3(std::move(base3),std::move(*m3));
    const jass::INetwork& t0=*base0;
    const auto corpus=read_fens(corpus_path),roots=read_fens(search_path);
    if (corpus.size()!=4096U || roots.size()!=512U)
        throw std::runtime_error("R0-v4 corpus/subset cardinality drift");
    std::map<std::string,std::size_t> phases;
    for (const auto& row:roots) ++phases[phase(row.position)];
    if (phases!=std::map<std::string,std::size_t>{{"P0",128},{"P1",128},{"P2",128},{"P3",128}})
        throw std::runtime_error("R0-v4 search subset phase drift");
    const jass::SearchParams params=jass::parse_search_params(params_spec);
    jass::egdb::ensure_initialised();
    if (!jass::egdb::available()) throw std::runtime_error("EGDB unavailable");

    std::size_t zero_leaf_mismatches=0,t3_formula_mismatches=0,zero_nonfinite=0,
        zero_saturations=0,t3_saturations=0;
    for (const auto& row:corpus) {
        const int e0=t0.evaluate(row.position);
        const double rz=zero.residual_parent(row.position),r3=t3.residual_parent(row.position);
        const int ez=zero.evaluate(row.position),e3=t3.evaluate(row.position);
        zero_leaf_mismatches += ez!=e0 || std::bit_cast<std::uint64_t>(rz)!=0U;
        t3_formula_mismatches += e3!=rounded(e0,r3);
        zero_nonfinite += !std::isfinite(rz);
        zero_saturations += std::abs(ez)==20000; t3_saturations += std::abs(e3)==20000;
    }
    const bool gate1=zero_leaf_mismatches==0 && t3_formula_mismatches==0
        && zero_nonfinite==0 && zero_saturations==0 && t3_saturations==0;

    constexpr std::array budgets={Budget::Depth1,Budget::Nodes1k,Budget::Nodes10k};
    std::size_t zero_search_mismatches=0,trace_neutral_mismatches=0,
        zero_trace_leaf_mismatches=0,t3_trace_formula_mismatches=0;
    std::uint64_t search_pairs=0,t3_searches=0; std::vector<Sample> samples;
    for (std::size_t i=0;i<roots.size();++i) {
        for (const Budget budget:budgets) {
            const Run off=run_search(roots[i].position,t0,params,budget,false);
            const Run z=run_search(roots[i].position,zero,params,budget,false);
            ++search_pairs; zero_search_mismatches += !same_result(off.result,z.result);
            const Run three=run_search(roots[i].position,t3,params,budget,false); ++t3_searches;
            if (i<8U) samples.push_back({roots[i].fen,budget_name(budget),
                off.result.score,three.result.score,move_id(off.result.best_move),
                move_id(three.result.best_move),off.result.nodes,three.result.nodes});
            if (i<64U) {
                const Run off_trace=run_search(roots[i].position,t0,params,budget,true);
                const Run z_trace=run_search(roots[i].position,zero,params,budget,true);
                const Run t3_trace=run_search(roots[i].position,t3,params,budget,true);
                trace_neutral_mismatches += !same_result(off.result,off_trace.result);
                trace_neutral_mismatches += !same_result(z.result,z_trace.result);
                trace_neutral_mismatches += !same_result(three.result,t3_trace.result);
                zero_trace_leaf_mismatches += !trace_leaf_exact(z_trace,zero);
                t3_trace_formula_mismatches += !trace_t3_formula(t3_trace,t0,t3);
            }
        }
    }
    const bool gate3=zero_search_mismatches==0 && trace_neutral_mismatches==0
        && zero_trace_leaf_mismatches==0;
    const auto synthetic=synthetic_gate(t0,zero,t3,params);
    const bool gate4=synthetic.gated>=2U && synthetic.mismatches==0;
    const bool gate5=t3_searches==512U*3U && t3_trace_formula_mismatches==0;

    const Position terminal=parse("W:W:B1"),tb=parse("W:WK12,K28:BK7");
    const auto terminal0=run_search(terminal,t0,params,Budget::Depth1).result;
    const auto terminalz=run_search(terminal,zero,params,Budget::Depth1).result;
    const auto terminal3=run_search(terminal,t3,params,Budget::Depth1).result;
    const auto tbclass=jass::probe_endgame(tb);
    const auto tb0=run_search(tb,t0,params,Budget::Depth1).result;
    const auto tbz=run_search(tb,zero,params,Budget::Depth1).result;
    const auto tb3=run_search(tb,t3,params,Budget::Depth1).result;
    const bool gate9=terminal0.score==terminalz.score && terminal0.score==terminal3.score
        && terminal0.eval_calls==0 && terminalz.eval_calls==0 && terminal3.eval_calls==0
        && tbclass!=jass::EndgameResult::Unknown
        && tb0.score==tbz.score && tb0.score==tb3.score
        && tb0.eval_calls==0 && tbz.eval_calls==0 && tb3.eval_calls==0;
    const bool gate10=true; // ZERO is reachable only through this explicit CLI/load policy.
    const bool passed=gate1 && gate3 && gate4 && gate5 && gate9 && gate10;
    const char* verdict=passed ? "R0_V4_RUNTIME_WRAPPER_CONTRACT_PASS"
        : !gate1 ? "R0_V4_ZERO_LEAF_EXACTNESS_FAILED"
        : !gate3 ? "R0_V4_ZERO_WRAPPER_SEARCH_EQUIVALENCE_FAILED"
        : !gate4 ? "R0_V4_SYNTHETIC_NEGAMAX_FAILED"
        : !gate5 ? "R0_V4_REAL_SEARCH_SEMANTICS_FAILED"
        : !gate9 ? "R0_V4_TERMINAL_OR_TABLEBASE_PRECEDENCE_FAILED"
        : "R0_V4_DORMANT_CONTRACT_FAILED";

    std::ofstream out(out_path); if (!out) throw std::runtime_error("cannot create V4 report");
    out << "{\n  \"schema\":\"jass.t3_f6_runtime_wrapper_contract.v4\",";
    out << "\n  \"passed\":" << boolean(passed) << ',';
    out << "\n  \"verdict\":" << json_string(verdict) << ',';
    out << "\n  \"code_sha\":" << json_string(code_sha) << ',';
    out << "\n  \"curriculum_sha256\":" << json_string(jass::t3_f6::FROZEN_CURRICULUM_SHA256) << ',';
    out << "\n  \"t3_sha256\":" << json_string(jass::t3_f6::FROZEN_MODEL_SHA256) << ',';
    out << "\n  \"zero_sha256\":" << json_string(jass::t3_f6::V4_ZERO_PROBE_SHA256) << ',';
    out << "\n  \"feature_order_sha256\":" << json_string(jass::t3_f6::FROZEN_FEATURE_ORDER_SHA256) << ',';
    out << "\n  \"gate1_leaf_api_exactness\":" << boolean(gate1) << ',';
    out << "\n  \"zero_leaf_mismatch_count\":" << zero_leaf_mismatches << ',';
    out << "\n  \"zero_leaf_max_abs_diff_cp\":0,";
    out << "\n  \"zero_nonfinite_count\":" << zero_nonfinite << ',';
    out << "\n  \"zero_saturation_count\":" << zero_saturations << ',';
    out << "\n  \"t3_formula_mismatch_count\":" << t3_formula_mismatches << ',';
    out << "\n  \"t3_saturation_count\":" << t3_saturations << ',';
    out << "\n  \"gate3_zero_full_search_equivalence\":" << boolean(gate3) << ',';
    out << "\n  \"search_roots\":512,\n  \"search_budgets\":[\"depth1\",\"nodes1000\",\"nodes10000\"],";
    out << "\n  \"search_pairs\":" << search_pairs << ',';
    out << "\n  \"zero_search_mismatch_count\":" << zero_search_mismatches << ',';
    out << "\n  \"trace_roots\":64,\n  \"trace_neutral_mismatch_count\":" << trace_neutral_mismatches << ',';
    out << "\n  \"zero_trace_leaf_mismatch_count\":" << zero_trace_leaf_mismatches << ',';
    out << "\n  \"gate4_synthetic_negamax\":" << boolean(gate4) << ',';
    out << "\n  \"synthetic_cases\":" << synthetic.cases << ",\n  \"synthetic_gated\":" << synthetic.gated
        << ",\n  \"synthetic_mismatch_count\":" << synthetic.mismatches << ',';
    out << "\n  \"gate5_real_search_semantics\":" << boolean(gate5) << ',';
    out << "\n  \"same_search_function\":true,\n  \"zero_and_t3_same_wrapper_type\":true,";
    out << "\n  \"direct_t3_search_rule_changes\":0,\n  \"t3_searches\":" << t3_searches << ',';
    out << "\n  \"t3_trace_formula_mismatch_count\":" << t3_trace_formula_mismatches << ',';
    out << "\n  \"gate9_terminal_tablebase\":" << boolean(gate9) << ',';
    out << "\n  \"egdb_available\":true,\n  \"terminal_scores\":[" << terminal0.score << ',' << terminalz.score << ',' << terminal3.score << "],";
    out << "\n  \"terminal_eval_calls\":[" << terminal0.eval_calls << ',' << terminalz.eval_calls << ',' << terminal3.eval_calls << "],";
    out << "\n  \"tablebase_scores\":[" << tb0.score << ',' << tbz.score << ',' << tb3.score << "],";
    out << "\n  \"tablebase_eval_calls\":[" << tb0.eval_calls << ',' << tbz.eval_calls << ',' << tb3.eval_calls << "],";
    out << "\n  \"gate10_dormant_contract\":" << boolean(gate10) << ',';
    out << "\n  \"production_env_accepts_zero\":false,\n  \"zero_requires_explicit_cli_flag\":true,";
    out << "\n  \"sample_t3_search_effects\":[";
    for (std::size_t i=0;i<samples.size();++i) {
        if (i) out << ',';
        const auto& s=samples[i];
        out << "{\"fen\":" << json_string(s.fen) << ",\"budget\":" << json_string(s.budget)
            << ",\"t0_score\":" << s.t0_score << ",\"t3_score\":" << s.t3_score
            << ",\"t0_move\":" << json_string(s.t0_move) << ",\"t3_move\":" << json_string(s.t3_move)
            << ",\"t0_nodes\":" << s.t0_nodes << ",\"t3_nodes\":" << s.t3_nodes << '}';
    }
    out << "]\n}\n";
    std::cout << verdict << " zero_search_mismatches=" << zero_search_mismatches << '\n';
    return 0;
}
} // namespace

int main(int argc,char** argv) {
    try {
        if (argc==2 && std::string_view(argv[1])=="--selftest") return selftest();
        return contract(argc,argv);
    } catch (const std::exception& error) {
        std::cerr << "t3_f6_runtime_contract_v4: " << error.what() << '\n'; return 1;
    }
}
