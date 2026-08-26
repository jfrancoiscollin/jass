// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-Francois Collin
//
// Offline teacher for the preregistered Deep Search Sibling Distillation v1.
//
// Reads the already target-blind selected parent JNNW corpus. For every unique
// semantic legal sibling it evaluates the child with byte-pinned CURRICULUM and
// reruns three independent searches from a clean Engine/TT state: 5k nodes
// (diagnostic), 50k nodes (stability screen), and 200k nodes (teacher target).
// No labels are selected here and no model is fit here.

#include "bitboard.hpp"
#include "egdb_bridge.hpp"
#include "endgame.hpp"
#include "engine.hpp"
#include "movegen.hpp"
#include "pattern_jass_bridge.hpp"
#include "position.hpp"
#include "search.hpp"
#include "types.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>

namespace {

using namespace jass;

constexpr std::size_t JNNW_RECORD_SIZE = 38;
constexpr std::uint64_t CHEAP_BUDGET = 5'000;
constexpr std::uint64_t SCREEN_BUDGET = 50'000;
constexpr std::uint64_t TEACHER_BUDGET = 200'000;
constexpr std::size_t DEFAULT_TT_MB = 16;

struct DiskRow {
    std::uint64_t wm{0};
    std::uint64_t wk{0};
    std::uint64_t bm{0};
    std::uint64_t bk{0};
    std::uint8_t stm{0};
    std::int32_t score{0};
    std::int8_t wdl{0};
};

struct SearchObs {
    int parent_score{0};
    std::uint64_t nodes{0};
    int completed_depth{0};
    int effective_depth{0};
    bool aborted_iteration{false};
    SearchStopReason stop_reason{SearchStopReason::None};
    std::uint64_t elapsed_us{0};
    bool pv_enters_egdb{false};
};

struct Counters {
    std::uint64_t source_rows{0};
    std::uint64_t processed_parent_rows{0};
    std::uint64_t invalid_rows{0};
    std::uint64_t duplicate_move_entries{0};
    std::uint64_t emitted_siblings{0};
    std::uint64_t rule_terminal_children{0};
    std::uint64_t exact_tb_children{0};
    std::uint64_t cheap_searches{0};
    std::uint64_t screen_searches{0};
    std::uint64_t teacher_searches{0};
    std::uint64_t cheap_nodes{0};
    std::uint64_t screen_nodes{0};
    std::uint64_t teacher_nodes{0};
};

template <typename T>
T load_le(const char* p) noexcept {
    T out{};
    std::memcpy(&out, p, sizeof(T));
    return out;
}

template <typename T>
void store_le(char* p, T value) noexcept {
    std::memcpy(p, &value, sizeof(T));
}

bool read_row(std::istream& in, DiskRow& row) {
    std::array<char, JNNW_RECORD_SIZE> raw{};
    if (!in.read(raw.data(), static_cast<std::streamsize>(raw.size()))) return false;
    row.wm = load_le<std::uint64_t>(raw.data() + 0);
    row.wk = load_le<std::uint64_t>(raw.data() + 8);
    row.bm = load_le<std::uint64_t>(raw.data() + 16);
    row.bk = load_le<std::uint64_t>(raw.data() + 24);
    row.stm = load_le<std::uint8_t>(raw.data() + 32);
    row.score = load_le<std::int32_t>(raw.data() + 33);
    row.wdl = load_le<std::int8_t>(raw.data() + 37);
    return true;
}

void write_zero_target_row(std::ostream& out, const Position& pos) {
    std::array<char, JNNW_RECORD_SIZE> raw{};
    store_le<std::uint64_t>(raw.data() + 0, pos.white_men());
    store_le<std::uint64_t>(raw.data() + 8, pos.white_kings());
    store_le<std::uint64_t>(raw.data() + 16, pos.black_men());
    store_le<std::uint64_t>(raw.data() + 24, pos.black_kings());
    store_le<std::uint8_t>(raw.data() + 32,
        pos.side_to_move() == Color::White ? std::uint8_t{0} : std::uint8_t{1});
    store_le<std::int32_t>(raw.data() + 33, 0);
    store_le<std::int8_t>(raw.data() + 37, 0);
    out.write(raw.data(), static_cast<std::streamsize>(raw.size()));
}

void add_bits(Position& pos, Bitboard bb, Piece piece) {
    while (bb) {
        const Square sq = pop_lsb(bb);
        pos.add_piece(sq, piece);
    }
}

bool valid_row(const DiskRow& r) noexcept {
    if (r.stm > 1) return false;
    const Bitboard all = r.wm | r.wk | r.bm | r.bk;
    if ((all & ~PLAYABLE_BB) != 0) return false;
    return ((r.wm & r.wk) | (r.wm & r.bm) | (r.wm & r.bk)
          | (r.wk & r.bm) | (r.wk & r.bk) | (r.bm & r.bk)) == 0;
}

Position position_from_row(const DiskRow& r) {
    Position pos;
    pos.clear();
    add_bits(pos, r.wm, Piece::WhiteMan);
    add_bits(pos, r.wk, Piece::WhiteKing);
    add_bits(pos, r.bm, Piece::BlackMan);
    add_bits(pos, r.bk, Piece::BlackKing);
    pos.set_side_to_move(r.stm == 0 ? Color::White : Color::Black);
    pos.set_halfmove_clock(0);
    return pos;
}

std::string parent_fingerprint(const DiskRow& r) {
    std::ostringstream out;
    out << std::hex << std::setfill('0')
        << std::setw(13) << r.wm << ':'
        << std::setw(13) << r.wk << ':'
        << std::setw(13) << r.bm << ':'
        << std::setw(13) << r.bk << ':'
        << std::dec << static_cast<int>(r.stm);
    return out.str();
}

bool same_semantic_move(const Move& a, const Move& b) noexcept {
    return a.from == b.from && a.to == b.to && a.captured == b.captured
        && a.promotes == b.promotes;
}

bool semantic_less(const Move& a, const Move& b) noexcept {
    return std::tuple{
        static_cast<int>(a.from), static_cast<int>(a.to),
        static_cast<std::uint64_t>(a.captured), a.promotes
    } < std::tuple{
        static_cast<int>(b.from), static_cast<int>(b.to),
        static_cast<std::uint64_t>(b.captured), b.promotes
    };
}

int absolute_white_utility(EndgameResult r) noexcept {
    if (r == EndgameResult::WhiteWin) return 1;
    if (r == EndgameResult::BlackWin) return -1;
    return 0;
}

std::optional<int> exact_parent_utility(const Position& parent,
                                        const Position& child,
                                        int tb_cap,
                                        bool& rule_terminal,
                                        bool& tb_exact) {
    MoveList child_legal;
    generate_legal_moves(child, child_legal);
    if (child_legal.empty()) {
        rule_terminal = true;
        return 1;  // child side to move has lost, therefore parent mover wins.
    }
    if (popcount(child.occupied()) <= tb_cap) {
        const EndgameResult result = egdb::probe(child);
        if (result != EndgameResult::Unknown) {
            tb_exact = true;
            const int white_u = absolute_white_utility(result);
            return parent.side_to_move() == Color::White ? white_u : -white_u;
        }
    }
    return std::nullopt;
}

bool position_is_exact_egdb(const Position& pos, int tb_cap) {
    if (popcount(pos.occupied()) > tb_cap) return false;
    return egdb::probe(pos) != EndgameResult::Unknown;
}

bool pv_enters_egdb(Position pos, const SearchResult& result, int tb_cap) {
    if (position_is_exact_egdb(pos, tb_cap)) return true;
    for (const Move& move : result.pv) {
        pos = pos.after(move);
        if (position_is_exact_egdb(pos, tb_cap)) return true;
    }
    return false;
}

SearchObs run_fresh_search(Engine& engine,
                           const Position& child,
                           const INetwork* net,
                           std::uint64_t budget,
                           int tb_cap) {
    engine.clear_tt();
    engine.set_position(child);
    SearchLimits limits;
    limits.max_depth = MAX_PLY;
    limits.max_nodes = budget;
    limits.node_limit_mode = NodeLimitMode::Exact;
    limits.threads = 1;
    limits.nnue = net;
    const auto t0 = std::chrono::steady_clock::now();
    const SearchResult result = engine.search(limits);
    const auto t1 = std::chrono::steady_clock::now();
    if (result.from_book) throw std::runtime_error("teacher search unexpectedly used opening book");
    SearchObs out;
    out.parent_score = -result.score;
    out.nodes = result.nodes;
    out.completed_depth = result.completed_depth;
    out.effective_depth = result.effective_depth;
    out.aborted_iteration = result.aborted_iteration;
    out.stop_reason = result.stop_reason;
    out.elapsed_us = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count());
    out.pv_enters_egdb = pv_enters_egdb(child, result, tb_cap);
    return out;
}

int material_count_delta_parent(const Position& parent, const Position& child) noexcept {
    const bool white = parent.side_to_move() == Color::White;
    const int own_before = popcount(white
        ? (parent.white_men() | parent.white_kings())
        : (parent.black_men() | parent.black_kings()));
    const int opp_before = popcount(white
        ? (parent.black_men() | parent.black_kings())
        : (parent.white_men() | parent.white_kings()));
    const int own_after = popcount(white
        ? (child.white_men() | child.white_kings())
        : (child.black_men() | child.black_kings()));
    const int opp_after = popcount(white
        ? (child.black_men() | child.black_kings())
        : (child.white_men() | child.white_kings()));
    return (own_after - opp_after) - (own_before - opp_before);
}

void write_report(const std::string& path,
                  std::uint32_t declared,
                  int shard,
                  int nshards,
                  int tb_cap,
                  std::size_t tt_mb,
                  const Counters& c) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open report output");
    out << "{\n"
        << "  \"schema\": \"jass.deep_sibling_teacher_extract.v1\",\n"
        << "  \"input_parents\": " << declared << ",\n"
        << "  \"shard\": " << shard << ",\n"
        << "  \"nshards\": " << nshards << ",\n"
        << "  \"book_enabled\": false,\n"
        << "  \"threads_per_search\": 1,\n"
        << "  \"fresh_tt_each_search\": true,\n"
        << "  \"node_limit_mode\": \"exact\",\n"
        << "  \"cheap_budget_nodes\": " << CHEAP_BUDGET << ",\n"
        << "  \"screen_budget_nodes\": " << SCREEN_BUDGET << ",\n"
        << "  \"teacher_budget_nodes\": " << TEACHER_BUDGET << ",\n"
        << "  \"tt_mb\": " << tt_mb << ",\n"
        << "  \"egdb_max_pieces\": " << tb_cap << ",\n"
        << "  \"source_rows\": " << c.source_rows << ",\n"
        << "  \"processed_parent_rows\": " << c.processed_parent_rows << ",\n"
        << "  \"invalid_rows\": " << c.invalid_rows << ",\n"
        << "  \"duplicate_move_entries\": " << c.duplicate_move_entries << ",\n"
        << "  \"emitted_siblings\": " << c.emitted_siblings << ",\n"
        << "  \"rule_terminal_children\": " << c.rule_terminal_children << ",\n"
        << "  \"exact_tb_children\": " << c.exact_tb_children << ",\n"
        << "  \"cheap_searches\": " << c.cheap_searches << ",\n"
        << "  \"screen_searches\": " << c.screen_searches << ",\n"
        << "  \"teacher_searches\": " << c.teacher_searches << ",\n"
        << "  \"cheap_nodes\": " << c.cheap_nodes << ",\n"
        << "  \"screen_nodes\": " << c.screen_nodes << ",\n"
        << "  \"teacher_nodes\": " << c.teacher_nodes << ",\n"
        << "  \"teacher_scores_produced\": true,\n"
        << "  \"stable_pairs_selected\": false,\n"
        << "  \"fits\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"promotion_authorized\": false\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "JNNW tool currently requires a little-endian host");
    if (argc < 7 || argc > 11) {
        std::cerr << "usage: jass_deep_sibling_teacher <parents.jnnw> <children.jnnw> "
                     "<groups.tsv> <report.json> <curriculum.pjtw> <egdb_dir> "
                     "[shard=0] [nshards=1] [tt_mb=16] [egdb_cache_mb=2048]\n";
        return 2;
    }
    if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr) {
        std::cerr << "error: JASS_TB_MOVE_ORDER_POLICY must be absent for the frozen teacher\n";
        return 2;
    }

    const std::string input_path = argv[1];
    const std::string child_path = argv[2];
    const std::string groups_path = argv[3];
    const std::string report_path = argv[4];
    const std::string curriculum_path = argv[5];
    const std::string egdb_dir = argv[6];
    const int shard = argc >= 8 ? std::stoi(argv[7]) : 0;
    const int nshards = argc >= 9 ? std::stoi(argv[8]) : 1;
    const std::size_t tt_mb = argc >= 10
        ? static_cast<std::size_t>(std::max(1, std::stoi(argv[9]))) : DEFAULT_TT_MB;
    const int egdb_cache_mb = argc >= 11 ? std::max(64, std::stoi(argv[10])) : 2048;
    if (nshards <= 0 || shard < 0 || shard >= nshards) {
        std::cerr << "error: invalid shard/nshards\n";
        return 2;
    }

    std::string network_error;
    auto curriculum = load_pattern_jass_network(curriculum_path, &network_error);
    if (!curriculum) {
        std::cerr << "error: cannot load CURRICULUM: " << network_error << '\n';
        return 3;
    }
    if (!egdb::init(egdb_dir, egdb_cache_mb) || !egdb::available()) {
        std::cerr << "error: real EGDB unavailable at " << egdb_dir << '\n';
        return 3;
    }
    const int tb_cap = egdb::max_pieces();
    if (tb_cap <= 0) {
        std::cerr << "error: invalid EGDB max pieces\n";
        return 3;
    }

    std::ifstream in(input_path, std::ios::binary);
    if (!in) {
        std::cerr << "error: cannot open input\n";
        return 4;
    }
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size()))
        || std::memcmp(header.data(), "JNNW", 4) != 0) {
        std::cerr << "error: input is not counted JNNW\n";
        return 4;
    }
    const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);

    std::ofstream children(child_path, std::ios::binary);
    std::ofstream groups(groups_path);
    if (!children || !groups) {
        std::cerr << "error: cannot open outputs\n";
        return 5;
    }
    children.write("JNNW", 4);
    const std::uint32_t zero = 0;
    children.write(reinterpret_cast<const char*>(&zero), 4);
    groups << "row_index\tparent_id\tparent_fingerprint\tparent_stm\tparent_pieces\t"
              "from\tto\tnum_captures\tpromotes\tmoving_king\tcaptured_kings\t"
              "material_count_delta_parent\tchild_pieces\tchild_legal_moves\t"
              "child_forced_capture\tchild_rule_terminal\tchild_tb_exact\t"
              "exact_parent_utility\tt_baseline_parent\tq5k_parent\tq50_parent\tq200_parent\t"
              "nodes5k\tnodes50k\tnodes200k\tcompleted_depth5k\tcompleted_depth50k\t"
              "completed_depth200k\teffective_depth5k\teffective_depth50k\teffective_depth200k\t"
              "aborted5k\taborted50k\taborted200k\tstop5k\tstop50k\tstop200k\t"
              "elapsed_us5k\telapsed_us50k\telapsed_us200k\tpv5k_enters_egdb\t"
              "pv50k_enters_egdb\tpv200k_enters_egdb\n";

    Engine engine(tt_mb);
    engine.use_book(false);
    Counters c{};
    std::uint32_t output_count = 0;

    DiskRow row{};
    for (std::uint32_t idx = 0; idx < declared; ++idx) {
        if (!read_row(in, row)) {
            std::cerr << "error: truncated JNNW at row " << idx << '\n';
            return 4;
        }
        ++c.source_rows;
        if (static_cast<int>(idx % static_cast<std::uint32_t>(nshards)) != shard) continue;
        ++c.processed_parent_rows;
        if (!valid_row(row)) { ++c.invalid_rows; continue; }
        if (row.score != 0 || row.wdl != 0) {
            std::cerr << "error: selected-parent target bytes are not zero at row " << idx << '\n';
            return 4;
        }
        const int parent_pieces = popcount(row.wm | row.wk | row.bm | row.bk);
        if (parent_pieces < 9 || parent_pieces > 40) {
            std::cerr << "error: selected parent outside frozen 9..40 support\n";
            return 4;
        }

        const Position parent = position_from_row(row);
        MoveList legal;
        generate_legal_moves(parent, legal);
        std::vector<Move> unique_moves;
        unique_moves.reserve(legal.size());
        for (const Move& move : legal) {
            const auto it = std::find_if(unique_moves.begin(), unique_moves.end(),
                [&](const Move& existing) { return same_semantic_move(existing, move); });
            if (it == unique_moves.end()) unique_moves.push_back(move);
            else ++c.duplicate_move_entries;
        }
        std::sort(unique_moves.begin(), unique_moves.end(), semantic_less);
        if (unique_moves.size() < 2 || unique_moves.size() > 16) {
            std::cerr << "error: selected parent legal-decision count drift at row " << idx << '\n';
            return 4;
        }

        const std::string fingerprint = parent_fingerprint(row);
        for (const Move& move : unique_moves) {
            const bool moving_king = test(parent.kings_of(parent.side_to_move()), move.from);
            const int captured_kings = popcount(
                move.captured & parent.kings_of(opposite(parent.side_to_move())));
            const Position child = parent.after(move);
            MoveList child_legal;
            generate_legal_moves(child, child_legal);
            const bool child_forced_capture = !child_legal.empty() && child_legal[0].is_capture();
            bool rule_terminal = false;
            bool tb_exact = false;
            const std::optional<int> exact_u = exact_parent_utility(
                parent, child, tb_cap, rule_terminal, tb_exact);
            c.rule_terminal_children += static_cast<std::uint64_t>(rule_terminal);
            c.exact_tb_children += static_cast<std::uint64_t>(tb_exact);

            // T baseline is the direct CURRICULUM scalar leaf score. Child STM
            // is the opponent, hence negate into the parent's point of view.
            const int t_baseline_parent = -curriculum->evaluate(child);

            const SearchObs s5 = run_fresh_search(engine, child, curriculum.get(), CHEAP_BUDGET, tb_cap);
            const SearchObs s50 = run_fresh_search(engine, child, curriculum.get(), SCREEN_BUDGET, tb_cap);
            const SearchObs s200 = run_fresh_search(engine, child, curriculum.get(), TEACHER_BUDGET, tb_cap);
            ++c.cheap_searches; ++c.screen_searches; ++c.teacher_searches;
            c.cheap_nodes += s5.nodes; c.screen_nodes += s50.nodes; c.teacher_nodes += s200.nodes;

            write_zero_target_row(children, child);
            groups << output_count << '\t' << idx << '\t' << fingerprint << '\t'
                   << static_cast<int>(row.stm) << '\t' << parent_pieces << '\t'
                   << static_cast<int>(move.from) << '\t' << static_cast<int>(move.to) << '\t'
                   << static_cast<int>(move.num_captures) << '\t' << (move.promotes ? 1 : 0) << '\t'
                   << (moving_king ? 1 : 0) << '\t' << captured_kings << '\t'
                   << material_count_delta_parent(parent, child) << '\t'
                   << popcount(child.occupied()) << '\t' << child_legal.size() << '\t'
                   << (child_forced_capture ? 1 : 0) << '\t' << (rule_terminal ? 1 : 0) << '\t'
                   << (tb_exact ? 1 : 0) << '\t' << (exact_u ? *exact_u : 2) << '\t'
                   << t_baseline_parent << '\t' << s5.parent_score << '\t'
                   << s50.parent_score << '\t' << s200.parent_score << '\t'
                   << s5.nodes << '\t' << s50.nodes << '\t' << s200.nodes << '\t'
                   << s5.completed_depth << '\t' << s50.completed_depth << '\t' << s200.completed_depth << '\t'
                   << s5.effective_depth << '\t' << s50.effective_depth << '\t' << s200.effective_depth << '\t'
                   << (s5.aborted_iteration ? 1 : 0) << '\t'
                   << (s50.aborted_iteration ? 1 : 0) << '\t'
                   << (s200.aborted_iteration ? 1 : 0) << '\t'
                   << search_stop_reason_name(s5.stop_reason) << '\t'
                   << search_stop_reason_name(s50.stop_reason) << '\t'
                   << search_stop_reason_name(s200.stop_reason) << '\t'
                   << s5.elapsed_us << '\t' << s50.elapsed_us << '\t' << s200.elapsed_us << '\t'
                   << (s5.pv_enters_egdb ? 1 : 0) << '\t'
                   << (s50.pv_enters_egdb ? 1 : 0) << '\t'
                   << (s200.pv_enters_egdb ? 1 : 0) << '\n';
            ++output_count;
            ++c.emitted_siblings;
        }
    }

    char trailing = 0;
    if (in.read(&trailing, 1)) {
        std::cerr << "error: input has trailing bytes\n";
        return 4;
    }
    children.seekp(4, std::ios::beg);
    children.write(reinterpret_cast<const char*>(&output_count), 4);
    children.close();
    groups.close();
    write_report(report_path, declared, shard, nshards, tb_cap, tt_mb, c);
    return 0;
}
