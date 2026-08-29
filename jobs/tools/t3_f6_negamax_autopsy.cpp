// SPDX-License-Identifier: AGPL-3.0-or-later
// Post-terminal, read-only autopsy of the R0-v2 depth-1 negamax witness.
#include "egdb_bridge.hpp"
#include "endgame.hpp"
#include "movegen.hpp"
#include "scan_sacs.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "t3_f6.hpp"
#include "tt.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {

using jass::DepthOneMoveTrace;
using jass::DepthOneSearchTrace;
using jass::Move;
using jass::MoveList;
using jass::Position;

constexpr std::string_view SOURCE_JOB =
    "cpx62-1648-l3-t3-f6-runtime-r0-v2";
constexpr std::string_view SOURCE_ATTEMPT =
    "20260829T132226Z-f559baed";
constexpr std::string_view SOURCE_TERMINAL_JOB =
    "cpx62-1649-l3-t3-f6-runtime-r0-v2-terminal-readout";
constexpr std::string_view SOURCE_TERMINAL_ATTEMPT =
    "20260829T133232Z-f559baed";
constexpr int R0_V2_OBSERVED_T3_SCORE = -51;

std::string json_string(std::string_view value) {
    std::ostringstream out;
    out << '"';
    for (const char raw : value) {
        const unsigned char c = static_cast<unsigned char>(raw);
        switch (c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 0x20U) {
                    out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                        << static_cast<unsigned>(c) << std::dec;
                } else {
                    out << static_cast<char>(c);
                }
        }
    }
    out << '"';
    return out.str();
}

const char* boolean(bool value) noexcept { return value ? "true" : "false"; }

std::string move_id(const Move& move) {
    std::ostringstream out;
    out << static_cast<int>(move.from)
        << (move.is_capture() ? 'x' : '-')
        << static_cast<int>(move.to);
    if (move.is_capture()) {
        out << "/n" << static_cast<unsigned>(move.num_captures)
            << "/bb" << std::hex << move.captured << std::dec;
    }
    if (move.promotes) out << "/K";
    return out.str();
}

const char* colour_name(jass::Color colour) noexcept {
    return colour == jass::Color::White ? "white" : "black";
}

const char* tablebase_name(jass::EndgameResult result) noexcept {
    switch (result) {
        case jass::EndgameResult::Unknown: return "unknown";
        case jass::EndgameResult::Draw: return "draw";
        case jass::EndgameResult::WhiteWin: return "white_win";
        case jass::EndgameResult::BlackWin: return "black_win";
    }
    return "unknown";
}

int rounded_t3(int t0, double residual) noexcept {
    return static_cast<int>(std::clamp(
        std::llround(static_cast<double>(t0) - residual), -20000LL, 20000LL));
}

struct ChildRow {
    Move move{};
    Position child{};
    int t0{0};
    int t3{0};
    double residual{0.0};
    bool formula_exact{false};
    bool root_capture{false};
    std::size_t replies{0};
    bool any_reply_capture{false};
    bool first_reply_capture{false};
    bool opponent_threat{false};
    std::size_t selective_sacs{0};
    jass::EndgameResult tablebase{jass::EndgameResult::Unknown};
    bool terminal{false};
};

struct ArmRun {
    std::string name;
    const jass::INetwork* network{nullptr};
    int expected_direct{0};
    jass::SearchResult result{};
    DepthOneSearchTrace trace{};
    bool direct_pass{false};
    std::size_t child_mismatches{0};
    std::string first_divergence_stage;
    std::string first_divergence_move;
};

std::vector<ChildRow> children(const Position& root,
                               const jass::INetwork& t0,
                               const jass::t3_f6::Network& t3) {
    MoveList legal;
    jass::generate_legal_moves(root, legal);
    std::vector<ChildRow> out;
    out.reserve(legal.size());
    for (const Move& move : legal) {
        ChildRow row;
        row.move = move;
        row.child = root.after(move);
        row.t0 = t0.evaluate(row.child);
        row.residual = t3.residual_parent(row.child);
        row.t3 = t3.evaluate(row.child);
        row.formula_exact = row.t3 == rounded_t3(row.t0, row.residual);
        row.root_capture = move.is_capture();
        MoveList replies;
        jass::generate_legal_moves(row.child, replies);
        row.replies = replies.size();
        row.terminal = replies.empty();
        row.first_reply_capture = !replies.empty() && replies[0].is_capture();
        row.any_reply_capture = std::any_of(
            replies.begin(), replies.end(),
            [](const Move& reply) { return reply.is_capture(); });
        row.opponent_threat = jass::has_any_capture(
            row.child, jass::opposite(row.child.side_to_move()));
        MoveList sacs;
        jass::scan_add_sacs(row.child, sacs);
        row.selective_sacs = sacs.size();
        row.tablebase = jass::probe_endgame(row.child);
        out.push_back(row);
    }
    return out;
}

const DepthOneMoveTrace& trace_for(const ArmRun& arm, const Move& move) {
    const auto it = std::find_if(
        arm.trace.moves.begin(), arm.trace.moves.end(),
        [&move](const DepthOneMoveTrace& row) { return row.move == move; });
    if (it == arm.trace.moves.end())
        throw std::runtime_error("missing depth-one trace row");
    return *it;
}

ArmRun run_arm(std::string name, const Position& root,
               const jass::INetwork& network,
               const std::vector<ChildRow>& rows,
               bool t3_arm) {
    ArmRun out;
    out.name = std::move(name);
    out.network = &network;
    out.expected_direct = std::numeric_limits<int>::min();
    for (const auto& row : rows)
        out.expected_direct = std::max(out.expected_direct, -(t3_arm ? row.t3 : row.t0));

    jass::SearchLimits limits;
    limits.max_depth = 1;
    limits.threads = 1;
    limits.nnue = &network;
    limits.depth_one_trace = &out.trace;
    jass::TranspositionTable tt;
    tt.resize_mb(1);
    out.result = jass::search(root, limits, tt);
    out.direct_pass = out.result.score == out.expected_direct;

    for (const auto& row : rows) {
        const auto& trace = trace_for(out, row.move);
        const int direct_child = t3_arm ? row.t3 : row.t0;
        if (trace.child_return != direct_child) {
            ++out.child_mismatches;
            if (out.first_divergence_stage.empty()) {
                out.first_divergence_stage = trace.first_resolution_stage;
                out.first_divergence_move = move_id(row.move);
            }
        }
    }
    if (out.first_divergence_stage.empty())
        out.first_divergence_stage = "none";
    return out;
}

bool stage_is_quiescence(std::string_view stage) noexcept {
    return stage.starts_with("qsearch_");
}

std::string classify(const ArmRun& t0, const ArmRun& t3) {
    const bool t0_child_divergence = t0.child_mismatches != 0;
    const bool t3_child_divergence = t3.child_mismatches != 0;
    if (t0.direct_pass && !t0_child_divergence
        && !t3.direct_pass && t3_child_divergence
        && (!stage_is_quiescence(t3.first_divergence_stage)
            || t3.first_divergence_stage == "qsearch_stand_pat"))
        return "T3_RUNTIME_POV_INTEGRATION_DEFECT";
    if ((t0_child_divergence || t3_child_divergence)
        && ((t0_child_divergence && stage_is_quiescence(t0.first_divergence_stage))
            || (t3_child_divergence && stage_is_quiescence(t3.first_divergence_stage))))
        return "QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH";
    if (!t0.direct_pass && !t3.direct_pass)
        return "NEGAMAX_TEST_WAS_OVERSIMPLIFIED";
    if (!t3.direct_pass)
        return "ROOT_OR_SEARCH_SEMANTICS_EXPLAINS_MISMATCH";
    return "NEGAMAX_MISMATCH_UNRESOLVED";
}

void write_pv(std::ostream& out, const std::vector<Move>& pv) {
    out << '[';
    for (std::size_t i = 0; i < pv.size(); ++i) {
        if (i != 0) out << ',';
        out << json_string(move_id(pv[i]));
    }
    out << ']';
}

void write_trace(std::ostream& out, const DepthOneMoveTrace& row) {
    out << "{\"actual_search_child_return\":" << row.child_return
        << ",\"root_negated_return\":" << row.root_negated_return
        << ",\"alpha_before\":" << row.alpha_before
        << ",\"beta\":" << row.beta
        << ",\"child_depth\":" << row.child_depth
        << ",\"nodes_delta\":" << (row.nodes_after - row.nodes_before)
        << ",\"eval_calls_delta\":" << (row.eval_calls_after - row.eval_calls_before)
        << ",\"entered_quiescence\":" << boolean(row.entered_quiescence)
        << ",\"qsearch_alpha\":" << row.qsearch_alpha
        << ",\"qsearch_beta\":" << row.qsearch_beta
        << ",\"qsearch_legal_moves\":" << row.qsearch_legal_moves
        << ",\"qsearch_forced_capture\":" << boolean(row.qsearch_forced_capture)
        << ",\"qsearch_opponent_threat\":" << boolean(row.qsearch_opponent_threat)
        << ",\"qsearch_stand_pat_valid\":" << boolean(row.qsearch_stand_pat_valid)
        << ",\"qsearch_stand_pat\":" << row.qsearch_stand_pat
        << ",\"qsearch_selective_sacs\":" << row.qsearch_selective_sacs
        << ",\"qsearch_moves_searched\":" << row.qsearch_moves_searched
        << ",\"qsearch_return\":" << row.qsearch_return
        << ",\"path_draw\":" << boolean(row.path_draw)
        << ",\"fifty_move_draw\":" << boolean(row.fifty_move_draw)
        << ",\"tablebase_hit\":" << boolean(row.tablebase_hit)
        << ",\"tt_cutoff\":" << boolean(row.tt_cutoff)
        << ",\"terminal_hit\":" << boolean(row.terminal_hit)
        << ",\"first_resolution_stage\":" << json_string(row.first_resolution_stage)
        << '}';
}

void write_arm_summary(std::ostream& out, const ArmRun& arm) {
    out << "{\"expected_direct_score\":" << arm.expected_direct
        << ",\"actual_depth1_score\":" << arm.result.score
        << ",\"direct_negamax_pass\":" << boolean(arm.direct_pass)
        << ",\"classification_token\":"
        << json_string(arm.direct_pass ? arm.name + "_DIRECT_NEGAMAX_PASS"
                                       : arm.name + "_DIRECT_NEGAMAX_FAIL")
        << ",\"best_move\":" << json_string(move_id(arm.result.best_move))
        << ",\"depth\":" << arm.result.depth
        << ",\"nodes\":" << arm.result.nodes
        << ",\"qnodes\":" << arm.trace.qnodes
        << ",\"eval_calls\":" << arm.result.eval_calls
        << ",\"tablebase_probes\":" << arm.trace.tablebase_probes
        << ",\"tablebase_hits\":" << arm.trace.tablebase_hits
        << ",\"terminal_hits\":" << arm.trace.terminal_hits
        << ",\"tt_probes\":" << arm.trace.tt_probes
        << ",\"tt_hits\":" << arm.trace.tt_hits
        << ",\"child_mismatch_count\":" << arm.child_mismatches
        << ",\"first_divergence_move\":" << json_string(arm.first_divergence_move)
        << ",\"first_divergence_stage\":" << json_string(arm.first_divergence_stage)
        << ",\"pv\":";
    write_pv(out, arm.result.pv);
    out << '}';
}

bool isolated_leaf_root(const Position& root) {
    MoveList legal;
    jass::generate_legal_moves(root, legal);
    if (legal.size() < 2U || legal[0].is_capture()) return false;
    for (const Move& move : legal) {
        const Position child = root.after(move);
        if (jass::probe_endgame(child) != jass::EndgameResult::Unknown) return false;
        MoveList replies;
        jass::generate_legal_moves(child, replies);
        if (replies.empty()) return false;
        if (std::any_of(replies.begin(), replies.end(),
                        [](const Move& reply) { return reply.is_capture(); })) return false;
        if (jass::has_any_capture(child, jass::opposite(child.side_to_move()))) return false;
        MoveList sacs;
        jass::scan_add_sacs(child, sacs);
        if (!sacs.empty()) return false;
    }
    return true;
}

Position random_synthetic(std::mt19937_64& rng) {
    std::array<int, 50> squares{};
    std::iota(squares.begin(), squares.end(), 1);
    std::shuffle(squares.begin(), squares.end(), rng);
    Position p;
    p.clear();
    // Ten pieces keep the synthetic mechanics outside the six-piece EGDB.
    for (int i = 0; i < 5; ++i) {
        p.add_piece(static_cast<jass::Square>(squares[static_cast<std::size_t>(i)]),
                    i == 0 ? jass::Piece::WhiteKing : jass::Piece::WhiteMan);
    }
    for (int i = 5; i < 10; ++i) {
        p.add_piece(static_cast<jass::Square>(squares[static_cast<std::size_t>(i)]),
                    i == 5 ? jass::Piece::BlackKing : jass::Piece::BlackMan);
    }
    p.set_side_to_move((rng() & 1U) != 0U ? jass::Color::White : jass::Color::Black);
    return p;
}

struct SyntheticCase {
    std::string name;
    Position position;
    ArmRun t0;
    ArmRun t3;
    std::size_t legal_moves{0};
    bool isolated{false};
};

SyntheticCase analyse_synthetic(std::string name, const Position& p,
                                const jass::INetwork& t0,
                                const jass::t3_f6::Network& t3) {
    const auto rows = children(p, t0, t3);
    SyntheticCase out;
    out.name = std::move(name);
    out.position = p;
    out.legal_moves = rows.size();
    out.isolated = isolated_leaf_root(p);
    out.t0 = run_arm("T0", p, t0, rows, false);
    out.t3 = run_arm("T3", p, t3, rows, true);
    return out;
}

std::vector<SyntheticCase> synthetic_cases(const jass::INetwork& t0,
                                           const jass::t3_f6::Network& t3) {
    std::mt19937_64 rng(2026082901ULL);
    std::vector<Position> isolated;
    Position single;
    bool have_single = false;
    for (int attempt = 0; attempt < 100000 && (isolated.size() < 2U || !have_single); ++attempt) {
        Position p = random_synthetic(rng);
        MoveList legal;
        jass::generate_legal_moves(p, legal);
        if (!have_single && legal.size() == 1U) {
            single = p;
            have_single = true;
        }
        if (isolated.size() < 2U && isolated_leaf_root(p)) isolated.push_back(p);
    }
    if (!have_single || isolated.size() < 2U)
        throw std::runtime_error("synthetic position search exhausted");

    std::vector<SyntheticCase> out;
    out.push_back(analyse_synthetic("A_multi_move_isolated_leaf", isolated[0], t0, t3));
    out.push_back(analyse_synthetic("B_exactly_one_legal_move", single, t0, t3));
    out.push_back(analyse_synthetic("C_D_nonterminal_non_tb_no_capture_direct_control",
                                    isolated[1], t0, t3));
    if (!out[0].t0.direct_pass || !out[0].t3.direct_pass
        || !out[2].t0.direct_pass || !out[2].t3.direct_pass)
        throw std::runtime_error("isolated synthetic direct-eval control failed");
    return out;
}

void write_report(const std::string& path, std::string_view code_sha,
                  const Position& root, const std::vector<ChildRow>& rows,
                  const ArmRun& t0, const ArmRun& t3,
                  const std::vector<SyntheticCase>& synthetic,
                  const std::string& classification) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open autopsy output");
    out << std::setprecision(17);
    out << "{\n  \"schema\":\"jass.t3_f6_negamax_autopsy.v1\","
        << "\n  \"diagnostic_only\":true,"
        << "\n  \"strength_games\":0,"
        << "\n  \"source_r0_v2\":{\"job_id\":" << json_string(SOURCE_JOB)
        << ",\"attempt_id\":" << json_string(SOURCE_ATTEMPT)
        << ",\"terminal_job_id\":" << json_string(SOURCE_TERMINAL_JOB)
        << ",\"terminal_attempt_id\":" << json_string(SOURCE_TERMINAL_ATTEMPT)
        << ",\"immutable_terminal_verdict\":\"R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED\"},"
        << "\n  \"code_sha\":" << json_string(code_sha) << ','
        << "\n  \"t0_sha256\":" << json_string(jass::t3_f6::FROZEN_CURRICULUM_SHA256) << ','
        << "\n  \"t3_sha256\":" << json_string(jass::t3_f6::FROZEN_MODEL_SHA256) << ','
        << "\n  \"f6_order_sha256\":" << json_string(jass::t3_f6::FROZEN_FEATURE_ORDER_SHA256) << ','
        << "\n  \"root_fen\":" << json_string(root.to_fen()) << ','
        << "\n  \"root_stm\":" << json_string(colour_name(root.side_to_move())) << ','
        << "\n  \"legal_move_count\":" << rows.size() << ','
        << "\n  \"r0_v2_observed_t3_depth1_score\":" << R0_V2_OBSERVED_T3_SCORE << ','
        << "\n  \"t0\":";
    write_arm_summary(out, t0);
    out << ",\n  \"t3\":";
    write_arm_summary(out, t3);
    out << ",\n  \"children\":[\n";
    for (std::size_t i = 0; i < rows.size(); ++i) {
        const auto& row = rows[i];
        const auto& t0_trace = trace_for(t0, row.move);
        const auto& t3_trace = trace_for(t3, row.move);
        out << "    {\"move_id\":" << json_string(move_id(row.move))
            << ",\"child_fen\":" << json_string(row.child.to_fen())
            << ",\"child_stm\":" << json_string(colour_name(row.child.side_to_move()))
            << ",\"root_move_capture\":" << boolean(row.root_capture)
            << ",\"reply_count\":" << row.replies
            << ",\"first_reply_capture\":" << boolean(row.first_reply_capture)
            << ",\"any_reply_capture\":" << boolean(row.any_reply_capture)
            << ",\"terminal\":" << boolean(row.terminal)
            << ",\"tablebase_class\":" << json_string(tablebase_name(row.tablebase))
            << ",\"opponent_threat_at_child\":" << boolean(row.opponent_threat)
            << ",\"selective_sac_count_at_child\":" << row.selective_sacs
            << ",\"t0_child\":" << row.t0
            << ",\"minus_t0_child\":" << -row.t0
            << ",\"residual_parent\":" << row.residual
            << ",\"t3_child\":" << row.t3
            << ",\"minus_t3_child\":" << -row.t3
            << ",\"native_formula_exact\":" << boolean(row.formula_exact)
            << ",\"t0_search_trace\":";
        write_trace(out, t0_trace);
        out << ",\"t3_search_trace\":";
        write_trace(out, t3_trace);
        out << '}' << (i + 1U == rows.size() ? "\n" : ",\n");
    }
    out << "  ],\n  \"capture_audit\":{\"all_replies_scanned\":true,"
        << "\"children_with_any_capture\":"
        << std::count_if(rows.begin(), rows.end(),
                         [](const ChildRow& row) { return row.any_reply_capture; })
        << ",\"children_where_first_vs_any_disagree\":"
        << std::count_if(rows.begin(), rows.end(), [](const ChildRow& row) {
               return row.first_reply_capture != row.any_reply_capture;
           }) << "},"
        << "\n  \"pov_contract\":{"
        << "\"training\":\"S(parent,child)=-T0_child+r_parent(child); T3_child=T0_child-r_parent(child)\","
        << "\"artifact_score_convention\":\"higher_is_better_for_parent\","
        << "\"artifact_base_contract\":\"byte-identical T0 parent score, coefficient 1\","
        << "\"native\":\"evaluate_from_base(child,T0_child)=round_clamp(T0_child-residual_parent(F6(child)))\","
        << "\"search\":\"leaf evaluator returns child STM POV; root applies exactly one negation to the actual child-search return\","
        << "\"formula_mismatch_count\":"
        << std::count_if(rows.begin(), rows.end(),
                         [](const ChildRow& row) { return !row.formula_exact; })
        << ",\"missing_transformation\":"
        << (classification == "T3_RUNTIME_POV_INTEGRATION_DEFECT"
                ? json_string("see first_divergence_stage") : "null")
        << ",\"specific_t3_pov_defect_observed\":"
        << boolean(classification == "T3_RUNTIME_POV_INTEGRATION_DEFECT") << "},"
        << "\n  \"real_depth1_path\":["
        << "\"search(root,depth=1)\",\"for each root move: negamax(child,depth=0,ply=1)\","
        << "\"draw -> tablebase -> TT -> legal-move/terminal checks\","
        << "\"depth<=0: quiescence(child)\","
        << "\"forced captures OR threat extension OR stand-pat plus selective sacrifices\","
        << "\"return child score; root negates once\"],"
        << "\n  \"synthetic_seed\":2026082901,"
        << "\n  \"synthetic_cases\":[";
    for (std::size_t i = 0; i < synthetic.size(); ++i) {
        const auto& row = synthetic[i];
        if (i != 0) out << ',';
        out << "{\"name\":" << json_string(row.name)
            << ",\"fen\":" << json_string(row.position.to_fen())
            << ",\"stm\":" << json_string(colour_name(row.position.side_to_move()))
            << ",\"legal_moves\":" << row.legal_moves
            << ",\"isolated_leaf_contract\":" << boolean(row.isolated)
            << ",\"t0_expected\":" << row.t0.expected_direct
            << ",\"t0_actual\":" << row.t0.result.score
            << ",\"t0_pass\":" << boolean(row.t0.direct_pass)
            << ",\"t3_expected\":" << row.t3.expected_direct
            << ",\"t3_actual\":" << row.t3.result.score
            << ",\"t3_pass\":" << boolean(row.t3.direct_pass) << '}';
    }
    out << "],"
        << "\n  \"first_divergence_stage\":"
        << json_string(!t3.direct_pass ? t3.first_divergence_stage
                                      : t0.first_divergence_stage) << ','
        << "\n  \"final_classification\":" << json_string(classification) << ','
        << "\n  \"force_authorized\":false,"
        << "\n  \"v3_executed\":false"
        << "\n}\n";
}

class SquareNetwork final : public jass::INetwork {
public:
    int evaluate(const Position& p) const noexcept override {
        const std::uint64_t mix = p.white_men() ^ (p.black_men() << 1U)
                                ^ (p.white_kings() << 2U) ^ (p.black_kings() << 3U);
        const int raw = static_cast<int>(mix % 401U) - 200;
        return p.side_to_move() == jass::Color::White ? raw : -raw;
    }
};

int selftest() {
    const Position root = Position::start_position();
    SquareNetwork network;
    MoveList legal;
    jass::generate_legal_moves(root, legal);
    std::vector<ChildRow> rows;
    rows.reserve(legal.size());
    for (const Move& move : legal) {
        ChildRow row;
        row.move = move;
        row.child = root.after(move);
        row.t0 = network.evaluate(row.child);
        rows.push_back(row);
    }
    const ArmRun traced = run_arm("T0", root, network, rows, false);
    jass::SearchLimits limits;
    limits.max_depth = 1;
    limits.nnue = &network;
    jass::TranspositionTable tt;
    tt.resize_mb(1);
    const auto control = jass::search(root, limits, tt);
    if (control.score != traced.result.score
        || control.best_move != traced.result.best_move
        || control.nodes != traced.result.nodes
        || control.eval_calls != traced.result.eval_calls
        || traced.trace.moves.size() != legal.size())
        throw std::runtime_error("passive trace changed search semantics");
    jass::t3_f6::Model zero;
    zero.stddev.fill(1.0);
    zero.w0.assign(jass::t3_f6::INPUT_WIDTH * jass::t3_f6::H0, 0.0);
    zero.w1.assign(jass::t3_f6::H0 * jass::t3_f6::H1, 0.0);
    zero.w2.assign(jass::t3_f6::H1 * jass::t3_f6::H2, 0.0);
    jass::t3_f6::Network t3(std::make_unique<SquareNetwork>(), std::move(zero));
    const auto synthetic = synthetic_cases(network, t3);
    if (synthetic.size() != 3U || synthetic[0].legal_moves < 2U
        || synthetic[1].legal_moves != 1U || !synthetic[2].isolated
        || !synthetic[0].t0.direct_pass || !synthetic[0].t3.direct_pass
        || !synthetic[2].t0.direct_pass || !synthetic[2].t3.direct_pass)
        throw std::runtime_error("synthetic mechanical controls failed");
    std::cout << "T3/F6 negamax autopsy passive-trace selftest PASS\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string_view(argv[1]) == "--selftest") return selftest();
        if (argc != 5) {
            std::cerr << "usage: t3_f6_negamax_autopsy <curriculum.pjtw> <t3.json> "
                         "<code-sha> <negamax-autopsy.json>\n";
            return 2;
        }
        const std::string_view code_sha = argv[3];
        if (code_sha.size() != 40U)
            throw std::runtime_error("code SHA must be full 40-hex");
        std::string err;
        if (jass::t3_f6::sha256_file(argv[1], &err)
            != jass::t3_f6::FROZEN_CURRICULUM_SHA256)
            throw std::runtime_error("CURRICULUM SHA mismatch");
        if (jass::t3_f6::sha256_file(argv[2], &err)
            != jass::t3_f6::FROZEN_MODEL_SHA256)
            throw std::runtime_error("T3 SHA mismatch");
        auto base = jass::load_eval_network(argv[1], &err);
        if (!base) throw std::runtime_error("CURRICULUM load: " + err);
        auto model = jass::t3_f6::load_model(
            argv[2], jass::t3_f6::LoadPolicy::FrozenOnly, &err);
        if (!model) throw std::runtime_error("T3 load: " + err);
        jass::t3_f6::Network t3(std::move(base), std::move(*model));
        const jass::INetwork& t0 = *t3.base_network();

        jass::egdb::ensure_initialised();
        const Position root = Position::start_position();
        const auto rows = children(root, t0, t3);
        const ArmRun t0_run = run_arm("T0", root, t0, rows, false);
        const ArmRun t3_run = run_arm("T3", root, t3, rows, true);
        if (t3_run.result.score != R0_V2_OBSERVED_T3_SCORE)
            throw std::runtime_error("R0-v2 witness score was not reproduced");
        if (std::any_of(rows.begin(), rows.end(),
                        [](const ChildRow& row) { return !row.formula_exact; }))
            throw std::runtime_error("native T3 formula mismatch");
        const auto synthetic = synthetic_cases(t0, t3);
        const std::string classification = classify(t0_run, t3_run);
        write_report(argv[4], code_sha, root, rows, t0_run, t3_run,
                     synthetic, classification);
        std::cout << classification
                  << " T0=" << t0_run.expected_direct << '/' << t0_run.result.score
                  << " T3=" << t3_run.expected_direct << '/' << t3_run.result.score
                  << " strength_games=0\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "t3_f6_negamax_autopsy: " << error.what() << '\n';
        return 1;
    }
}
