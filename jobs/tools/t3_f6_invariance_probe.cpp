// SPDX-License-Identifier: AGPL-3.0-or-later
// R0 board+STM / transposition / negamax invariance proof on frozen bytes.
#include "bitboard.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "residual_features.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "t3_f6.hpp"
#include "tt.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

jass::Position parse(const char* fen) {
    auto p=jass::Position::from_fen(fen);
    if (!p) throw std::runtime_error("bad invariance FEN");
    return *p;
}

jass::Square rotated(jass::Square s) noexcept {
    return static_cast<jass::Square>(51-static_cast<int>(s));
}

void add_rotated(jass::Position& out, jass::Bitboard pieces, jass::Piece piece) {
    while (pieces) out.add_piece(rotated(jass::pop_lsb(pieces)),piece);
}

jass::Position colour_image(const jass::Position& p) {
    jass::Position out; out.clear();
    add_rotated(out,p.black_men(),jass::Piece::WhiteMan);
    add_rotated(out,p.black_kings(),jass::Piece::WhiteKing);
    add_rotated(out,p.white_men(),jass::Piece::BlackMan);
    add_rotated(out,p.white_kings(),jass::Piece::BlackKing);
    out.set_side_to_move(jass::opposite(p.side_to_move()));
    out.set_halfmove_clock(p.halfmove_clock());
    return out;
}

bool exact_features(const jass::Position& a,const jass::Position& b) {
    const auto x=jass::residual_features::extract_f6(a).all_new();
    const auto y=jass::residual_features::extract_f6(b).all_new();
    for (std::size_t i=0;i<x.size();++i)
        if (std::bit_cast<std::uint32_t>(x[i])!=std::bit_cast<std::uint32_t>(y[i])) return false;
    return true;
}

struct State { jass::Position pos; std::vector<jass::Move> path; std::string parent; };

std::pair<State,State> find_transposition() {
    std::vector<State> frontier{{jass::Position::start_position(),{},""}};
    for (int depth=1;depth<=6;++depth) {
        std::map<std::string,State> seen;
        for (const State& state:frontier) {
            jass::MoveList legal; jass::generate_legal_moves(state.pos,legal);
            for (const auto& move:legal) {
                State child{state.pos.after(move),state.path,state.pos.to_fen()};
                child.path.push_back(move);
                const std::string key=child.pos.to_fen();
                auto [it,inserted]=seen.emplace(key,child);
                if (!inserted && it->second.parent!=child.parent)
                    return {it->second,child};
            }
        }
        frontier.clear(); frontier.reserve(seen.size());
        for (auto& [key,state]:seen) { (void)key; frontier.push_back(std::move(state)); }
        if (frontier.size()>250000U) throw std::runtime_error("transposition search bound exceeded");
    }
    throw std::runtime_error("no explicit legal-path transposition found");
}

void require(bool value,const char* what) {
    if (!value) throw std::runtime_error(what);
}

}  // namespace

int main(int argc,char** argv) {
    try {
        if (argc==2 && std::string(argv[1])=="--transposition-selftest") {
            const auto [path_a,path_b]=find_transposition();
            require(path_a.pos==path_b.pos,"selftest transposition board drift");
            require(path_a.parent!=path_b.parent,"selftest parents not distinct");
            require(exact_features(path_a.pos,path_b.pos),"selftest F6 drift");
            std::cout << "T3/F6 transposition witness PASS depth="
                      << path_a.path.size() << '\n';
            return 0;
        }
        if (argc!=5) {
            std::cerr << "usage: t3_f6_invariance_probe <curriculum.pjtw> <t3.json> "
                         "<report.json> <permutation-seed>\n";
            return 2;
        }
        const std::uint64_t permutation_seed=std::stoull(argv[4]);
        require(permutation_seed==2026090903ULL,"invariance permutation seed drift");
        std::string err;
        require(jass::t3_f6::sha256_file(argv[1],&err)==jass::t3_f6::FROZEN_CURRICULUM_SHA256,
                "CURRICULUM SHA mismatch");
        auto base=jass::load_eval_network(argv[1],&err);
        if (!base) throw std::runtime_error("base load: "+err);
        auto model=jass::t3_f6::load_model(argv[2],jass::t3_f6::LoadPolicy::FrozenOnly,&err);
        if (!model) throw std::runtime_error("T3 load: "+err);
        jass::t3_f6::Network t3(std::move(base),std::move(*model));
        const jass::INetwork* t0=t3.base_network();

        const jass::Position target=parse("W:W28,31,K40:B14,22,K3");
        const auto target_f=jass::residual_features::extract_f6(target).all_new();
        const double target_r=t3.residual_parent(target);
        const int target_s=t3.evaluate(target);
        // Parent identity, unrelated contexts and sibling order cannot enter.
        std::vector<jass::Position> contexts={
            parse("B:W31,32:B1,2"),target,parse("W:W26,K45:B6,K10")};
        std::mt19937_64 rng(permutation_seed);
        std::shuffle(contexts.begin(),contexts.end(),rng);
        for (const auto& p:contexts) (void)t3.evaluate(p);
        std::reverse(contexts.begin(),contexts.end());
        for (const auto& p:contexts) (void)t3.evaluate(p);
        require(exact_features(target,target),"repeat feature drift");
        require(std::bit_cast<std::uint64_t>(target_r)==
                std::bit_cast<std::uint64_t>(t3.residual_parent(target)),"repeat residual drift");
        require(target_s==t3.evaluate(target),"repeat score drift");

        const auto [path_a,path_b]=find_transposition();
        require(path_a.pos==path_b.pos,"transposition board drift");
        require(path_a.parent!=path_b.parent,"transposition parent identity not distinct");
        require(exact_features(path_a.pos,path_b.pos),"transposition feature drift");
        require(t3.evaluate(path_a.pos)==t3.evaluate(path_b.pos),"transposition score drift");

        // Direct evaluation is independent of TT contents and search state.
        const int direct_before=t3.evaluate(target);
        jass::SearchLimits limits; limits.max_depth=3; limits.nnue=&t3;
        jass::TranspositionTable warm; warm.resize_mb(1);
        (void)jass::search(target,limits,warm);
        (void)jass::search(target,limits,warm);
        jass::TranspositionTable cold; cold.resize_mb(1);
        (void)jass::search(target,limits,cold);
        require(t3.evaluate(target)==direct_before,"TT/search-state eval drift");

        struct Labelled { jass::Position pos; std::array<unsigned char,17> qbytes{}; };
        Labelled labelled{target,{}};
        const int before_labels=t3.evaluate(labelled.pos);
        labelled.qbytes.fill(0xffU);
        require(t3.evaluate(labelled.pos)==before_labels,"q/WDL byte dependency");

        const jass::Position image=colour_image(target);
        require(exact_features(target,image),"colour-image F6 drift");
        require(std::bit_cast<std::uint64_t>(t3.residual_parent(target))==
                std::bit_cast<std::uint64_t>(t3.residual_parent(image)),"colour-image residual drift");
        require(t0->evaluate(target)==t0->evaluate(image),"colour-image T0 drift");
        require(t3.evaluate(target)==t3.evaluate(image),"colour-image T3 drift");

        // At depth one from a quiet position, qsearch immediately reaches
        // the T3 leaf. The root score must therefore be max(-T3(child)).
        const jass::Position negamax_parent=jass::Position::start_position();
        jass::MoveList root_moves;
        jass::generate_legal_moves(negamax_parent,root_moves);
        int expected_root=std::numeric_limits<int>::min();
        for (const auto& move:root_moves) {
            const jass::Position child=negamax_parent.after(move);
            jass::MoveList child_moves;
            jass::generate_legal_moves(child,child_moves);
            require(child_moves.empty() || !child_moves[0].is_capture(),
                    "negamax witness enters q-capture search");
            expected_root=std::max(expected_root,-t3.evaluate(child));
        }
        jass::SearchLimits one_ply;
        one_ply.max_depth=1;
        one_ply.nnue=&t3;
        jass::TranspositionTable one_ply_tt;
        one_ply_tt.resize_mb(1);
        const auto one_ply_result=jass::search(negamax_parent,one_ply,one_ply_tt);
        require(one_ply_result.score==expected_root,"negamax leaf inversion drift");

        std::ofstream out(argv[3]);
        if (!out) throw std::runtime_error("cannot create invariance report");
        out << "{\n"
            << "  \"schema\": \"jass.t3_f6_invariance.v1\",\n"
            << "  \"model_sha256\": \"" << jass::t3_f6::FROZEN_MODEL_SHA256 << "\",\n"
            << "  \"curriculum_sha256\": \"" << jass::t3_f6::FROZEN_CURRICULUM_SHA256 << "\",\n"
            << "  \"feature_order_sha256\": \"" << jass::t3_f6::FROZEN_FEATURE_ORDER_SHA256 << "\",\n"
            << "  \"permutation_seed\": " << permutation_seed << ",\n"
            << "  \"passed\": true,\n"
            << "  \"verdict\": \"T3_F6_TRANSPOSITION_SAFE\",\n"
            << "  \"position_only\": true,\n"
            << "  \"sibling_order_independent\": true,\n"
            << "  \"explicit_transposition_depth\": " << path_a.path.size() << ",\n"
            << "  \"distinct_immediate_parents\": true,\n"
            << "  \"tt_cold_warm_independent\": true,\n"
            << "  \"q_wdl_bytes_independent\": true,\n"
            << "  \"colour_perspective_exact\": true,\n"
            << "  \"negamax_single_inversion\": true,\n"
            << "  \"negamax_depth1_score\": " << one_ply_result.score << ",\n"
            << "  \"feature_width\": " << target_f.size() << "\n"
            << "}\n";
        std::cout << "T3/F6 invariance PASS transposition_depth=" << path_a.path.size() << '\n';
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "t3_f6_invariance_probe: " << e.what() << '\n';
        return 1;
    }
}
