// SPDX-License-Identifier: AGPL-3.0-or-later
// Preregistered E2 equal-nodes harness for frozen T3-A/F6 vs CURRICULUM.
//
// This tool is deliberately isolated under jobs/tools.  It does not alter the
// production HUB/tournament/search path.  It implements only the E2 mechanics
// frozen in docs/experiments/L3_F6_TRANSFER_PROGRAM_E1_E3_20260830.md:
//   * threads=1, book OFF, exact node budgets, movetime disabled;
//   * fresh game state and TT per game;
//   * exact O1 residual cache ON only for T3-A, cold at every move/root;
//   * C1 20k/20k, C2 20k/10k, C3 byte-identical 20k/20k;
//   * colour-paired games from caller-supplied frozen openings;
//   * no fit/tuning/refit/calibration/D1/ablation/bake/promotion.

#include "egdb_bridge.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "residual_features.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "search_params.hpp"
#include "t3_f6.hpp"
#include "tt.hpp"
#include "types.hpp"
#include "zobrist.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {
using namespace jass;
using Clock = std::chrono::steady_clock;

constexpr std::uint64_t NODES_20K = 20'000ULL;
constexpr std::uint64_t NODES_10K = 10'000ULL;
constexpr std::size_t TT_MB = 16U;
// E2 did not introduce a new ply-cap parameter; preserve the existing native
// tournament harness default instead of adding a tunable degree of freedom.
constexpr int MAX_GAME_PLIES = 300;

struct CacheKey {
    std::uint64_t white_men{0};
    std::uint64_t white_kings{0};
    std::uint64_t black_men{0};
    std::uint64_t black_kings{0};
    std::uint8_t side_to_move{0};

    friend bool operator==(const CacheKey& a, const CacheKey& b) noexcept {
        return a.white_men == b.white_men
            && a.white_kings == b.white_kings
            && a.black_men == b.black_men
            && a.black_kings == b.black_kings
            && a.side_to_move == b.side_to_move;
    }
};

struct CacheEntry {
    CacheKey key{};
    double residual{0.0};
    bool valid{false};
};

CacheKey cache_key(const Position& pos) noexcept {
    return {
        static_cast<std::uint64_t>(pos.white_men()),
        static_cast<std::uint64_t>(pos.white_kings()),
        static_cast<std::uint64_t>(pos.black_men()),
        static_cast<std::uint64_t>(pos.black_kings()),
        static_cast<std::uint8_t>(pos.side_to_move() == Color::White ? 0U : 1U),
    };
}

int exact_round_score(double score) noexcept {
    if (!std::isfinite(score)) return 0;
    const long long rounded = std::llround(score);
    return static_cast<int>(std::clamp(rounded, -20000LL, 20000LL));
}

// E2-local realization of the terminal O1 cache contract.  The index is not
// reimplemented: it calls the frozen public O1 index function.  Full-key
// equality, explicit valid bits, direct replacement, raw-double residuals and
// cold-per-root lifecycle are reproduced literally.  --selftest compares its
// fixed-node search result against the canonical O1SearchSession before E2 can
// be sized or run.
class ExactO1Network final : public INetwork {
public:
    ExactO1Network(std::unique_ptr<INetwork> base, t3_f6::Model model)
        : base_(std::move(base)), model_(std::move(model)),
          cache_(t3_f6::CACHE_CAPACITY) {
        if (!base_) throw std::runtime_error("E2 O1 base network is null");
    }

    int evaluate(const Position& pos) const noexcept override {
        const int base_score = base_->evaluate(pos);
        const double residual = residual_parent(pos);
        return exact_round_score(static_cast<double>(base_score) - residual);
    }

    void clear_for_root() const noexcept {
        for (auto& entry : cache_) entry.valid = false;
        stats_ = {};
    }

    t3_f6::CacheStats stats() const noexcept { return stats_; }

private:
    double residual_parent(const Position& pos) const noexcept {
        ++stats_.lookups;
        const std::uint16_t index = t3_f6::Network::cache_index(pos);
        CacheEntry& entry = cache_[index];
        const CacheKey key = cache_key(pos);
        if (entry.valid && entry.key == key) {
            ++stats_.hits;
            return entry.residual;
        }
        ++stats_.misses;
        if (entry.valid) ++stats_.replacements;
        ++stats_.extract_f6_executions;
        const double residual = model_.residual_parent(
            residual_features::extract_f6(pos).all_new());
        entry.key = key;
        entry.residual = residual;
        entry.valid = true;  // valid is committed last, exactly as O1.
        return residual;
    }

    std::unique_ptr<INetwork> base_;
    t3_f6::Model model_;
    mutable std::vector<CacheEntry> cache_;
    mutable t3_f6::CacheStats stats_{};
};

enum class EvalKind { Curriculum, T3O1 };

struct SideSpec {
    EvalKind eval{EvalKind::Curriculum};
    std::uint64_t nodes{NODES_20K};
};

struct SearchTotals {
    std::uint64_t searches{0};
    std::uint64_t nodes{0};
    std::uint64_t eval_calls{0};
    std::uint64_t wall_ns{0};
    std::uint64_t completed_depth_sum{0};
    std::uint64_t effective_depth_sum{0};
    std::uint64_t cache_lookups{0};
    std::uint64_t cache_hits{0};
    std::uint64_t cache_misses{0};
    std::uint64_t cache_replacements{0};
    std::uint64_t extract_f6_executions{0};
};

std::unique_ptr<INetwork> load_curriculum(const std::string& path) {
    std::string error;
    if (t3_f6::sha256_file(path, &error) != t3_f6::FROZEN_CURRICULUM_SHA256)
        throw std::runtime_error("E2 CURRICULUM SHA mismatch");
    auto net = load_eval_network(path, &error);
    if (!net) throw std::runtime_error("E2 CURRICULUM load failed: " + error);
    return net;
}

t3_f6::Model load_t3_model(const std::string& path) {
    std::string error;
    auto model = t3_f6::load_model(path, t3_f6::LoadPolicy::FrozenOnly, &error);
    if (!model) throw std::runtime_error("E2 T3-A load failed: " + error);
    return *model;
}

class GameSide {
public:
    GameSide(const SideSpec& spec,
             const std::string& curriculum_path,
             const t3_f6::Model& model,
             const SearchParams& params)
        : spec_(spec), params_(params) {
        tt_.resize_mb(TT_MB);
        if (spec_.eval == EvalKind::T3O1) {
            t3_ = std::make_unique<ExactO1Network>(
                load_curriculum(curriculum_path), model);
            network_ = t3_.get();
        } else {
            curriculum_ = load_curriculum(curriculum_path);
            network_ = curriculum_.get();
        }
    }

    SearchResult search_root(const Position& pos,
                             const std::vector<ZobristHash>& history) {
        SearchLimits limits;
        limits.max_depth = MAX_PLY;
        limits.max_nodes = spec_.nodes;
        limits.node_limit_mode = NodeLimitMode::Exact;
        limits.threads = 1;
        limits.movetime_ms = 0;
        limits.tt_mb = TT_MB;
        limits.params = params_;
        limits.nnue = network_;
        if (t3_) t3_->clear_for_root();

        const auto begin = Clock::now();
        const SearchResult result = jass::search(pos, limits, tt_, history);
        const auto end = Clock::now();
        const std::uint64_t wall_ns = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count());

        ++totals_.searches;
        totals_.nodes += result.nodes;
        totals_.eval_calls += result.eval_calls;
        totals_.wall_ns += wall_ns;
        totals_.completed_depth_sum += static_cast<std::uint64_t>(
            std::max(0, result.completed_depth));
        totals_.effective_depth_sum += static_cast<std::uint64_t>(
            std::max(0, result.effective_depth));
        if (t3_) {
            const auto c = t3_->stats();
            totals_.cache_lookups += c.lookups;
            totals_.cache_hits += c.hits;
            totals_.cache_misses += c.misses;
            totals_.cache_replacements += c.replacements;
            totals_.extract_f6_executions += c.extract_f6_executions;
        }
        return result;
    }

    const SearchTotals& totals() const noexcept { return totals_; }

private:
    SideSpec spec_{};
    SearchParams params_{};
    TranspositionTable tt_{};
    std::unique_ptr<INetwork> curriculum_{};
    std::unique_ptr<ExactO1Network> t3_{};
    const INetwork* network_{nullptr};
    SearchTotals totals_{};
};

std::vector<Position> read_fens(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open E2 opening FEN file");
    std::vector<Position> rows;
    std::string line;
    while (std::getline(in, line)) {
        const auto comment = line.find('#');
        if (comment != std::string::npos) line.resize(comment);
        const auto first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) continue;
        const auto last = line.find_last_not_of(" \t\r\n");
        line = line.substr(first, last - first + 1U);
        auto pos = Position::from_fen(line);
        if (!pos) throw std::runtime_error("bad E2 opening FEN");
        MoveList legal;
        generate_legal_moves(*pos, legal);
        if (legal.empty()) throw std::runtime_error("terminal E2 opening FEN");
        rows.push_back(*pos);
    }
    if (rows.empty()) throw std::runtime_error("empty E2 opening FEN file");
    return rows;
}

std::string read_text(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open E2 text input");
    return std::string(std::istreambuf_iterator<char>(in),
                       std::istreambuf_iterator<char>());
}

int repetition_count(const std::vector<ZobristHash>& history,
                     ZobristHash current) noexcept {
    int n = 0;
    for (const auto h : history) if (h == current) ++n;
    return n;
}

bool legal_contains(const MoveList& legal, const Move& target) noexcept {
    for (const auto& move : legal) {
        if (move.from == target.from && move.to == target.to
            && move.captured == target.captured && move.promotes == target.promotes)
            return true;
    }
    return false;
}

enum class Outcome { WhiteWin, BlackWin, Draw };

struct GameResult {
    Outcome outcome{Outcome::Draw};
    int plies{0};
    std::string reason;
    SearchTotals white{};
    SearchTotals black{};
    std::uint64_t wall_ns{0};
};

struct GameTimeout final : std::runtime_error {
    using std::runtime_error::runtime_error;
};

GameResult play_game(const Position& opening,
                     const SideSpec& white_spec,
                     const SideSpec& black_spec,
                     const std::string& curriculum_path,
                     const t3_f6::Model& model,
                     const SearchParams& params,
                     std::uint64_t game_timeout_ms) {
    GameSide white(white_spec, curriculum_path, model, params);
    GameSide black(black_spec, curriculum_path, model, params);
    Position pos = opening;
    std::vector<ZobristHash> history;
    history.reserve(static_cast<std::size_t>(MAX_GAME_PLIES));
    const auto game_begin = Clock::now();

    auto elapsed_ms = [&]() -> std::uint64_t {
        return static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                Clock::now() - game_begin).count());
    };
    auto finish = [&](Outcome outcome, int plies, std::string reason) {
        GameResult out;
        out.outcome = outcome;
        out.plies = plies;
        out.reason = std::move(reason);
        out.white = white.totals();
        out.black = black.totals();
        out.wall_ns = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                Clock::now() - game_begin).count());
        return out;
    };

    for (int ply = 0; ply < MAX_GAME_PLIES; ++ply) {
        if (game_timeout_ms > 0 && elapsed_ms() > game_timeout_ms)
            throw GameTimeout("E2 game exceeded calibrated game timeout");

        MoveList legal;
        generate_legal_moves(pos, legal);
        if (legal.empty()) {
            return finish(pos.side_to_move() == Color::White
                              ? Outcome::BlackWin : Outcome::WhiteWin,
                          ply, "no legal moves");
        }
        if (pos.halfmove_clock() >= FIFTY_MOVE_PLIES)
            return finish(Outcome::Draw, ply, "25-move rule");
        const ZobristHash current_hash = zobrist_hash(pos);
        if (repetition_count(history, current_hash) >= 2)
            return finish(Outcome::Draw, ply, "3-fold repetition");

        GameSide& side = pos.side_to_move() == Color::White ? white : black;
        const SearchResult result = side.search_root(pos, history);
        if (result.from_book)
            throw std::runtime_error("E2 search unexpectedly used opening book");
        if (!legal_contains(legal, result.best_move))
            throw std::runtime_error("E2 engine returned illegal/no best move");
        history.push_back(current_hash);
        pos = pos.after(result.best_move);
    }
    return finish(Outcome::Draw, MAX_GAME_PLIES, "ply cap");
}

struct CellSpec {
    std::string name;
    SideSpec a;
    SideSpec b;
};

CellSpec cell_spec(std::string_view cell) {
    if (cell == "C1")
        return {"C1", {EvalKind::T3O1, NODES_20K},
                      {EvalKind::Curriculum, NODES_20K}};
    if (cell == "C2")
        return {"C2", {EvalKind::Curriculum, NODES_20K},
                      {EvalKind::Curriculum, NODES_10K}};
    if (cell == "C3")
        return {"C3", {EvalKind::Curriculum, NODES_20K},
                      {EvalKind::Curriculum, NODES_20K}};
    throw std::runtime_error("E2 cell must be C1, C2 or C3");
}

double a_score(const GameResult& game, bool a_is_white) noexcept {
    if (game.outcome == Outcome::Draw) return 0.5;
    const bool white_won = game.outcome == Outcome::WhiteWin;
    return (white_won == a_is_white) ? 1.0 : 0.0;
}

const char* outcome_name(Outcome outcome) noexcept {
    if (outcome == Outcome::WhiteWin) return "white_win";
    if (outcome == Outcome::BlackWin) return "black_win";
    return "draw";
}

struct RunSummary {
    std::uint64_t openings{0};
    std::uint64_t games{0};
    std::uint64_t a_wins{0};
    std::uint64_t b_wins{0};
    std::uint64_t draws{0};
    std::uint64_t skipped{0};
    std::uint64_t wall_ns{0};
    std::uint64_t max_game_wall_ns{0};
    SearchTotals a{};
    SearchTotals b{};
    std::uint64_t paired_complementarity_failures{0};
};

void add_totals(SearchTotals& dst, const SearchTotals& src) {
    dst.searches += src.searches;
    dst.nodes += src.nodes;
    dst.eval_calls += src.eval_calls;
    dst.wall_ns += src.wall_ns;
    dst.completed_depth_sum += src.completed_depth_sum;
    dst.effective_depth_sum += src.effective_depth_sum;
    dst.cache_lookups += src.cache_lookups;
    dst.cache_hits += src.cache_hits;
    dst.cache_misses += src.cache_misses;
    dst.cache_replacements += src.cache_replacements;
    dst.extract_f6_executions += src.extract_f6_executions;
}

void account_game(RunSummary& sum, const GameResult& game,
                  bool a_is_white) {
    ++sum.games;
    const double score = a_score(game, a_is_white);
    if (score == 1.0) ++sum.a_wins;
    else if (score == 0.0) ++sum.b_wins;
    else ++sum.draws;
    sum.wall_ns += game.wall_ns;
    sum.max_game_wall_ns = std::max(sum.max_game_wall_ns, game.wall_ns);
    if (a_is_white) {
        add_totals(sum.a, game.white);
        add_totals(sum.b, game.black);
    } else {
        add_totals(sum.a, game.black);
        add_totals(sum.b, game.white);
    }
}

void write_search_totals(std::ostream& out, const char* name,
                         const SearchTotals& t) {
    const double nps = t.wall_ns == 0 ? 0.0
        : static_cast<double>(t.nodes) * 1.0e9 / static_cast<double>(t.wall_ns);
    const double cache_hit_rate = t.cache_lookups == 0 ? 0.0
        : static_cast<double>(t.cache_hits) / static_cast<double>(t.cache_lookups);
    out << "  \"" << name << "\": {"
        << "\"searches\": " << t.searches
        << ", \"nodes\": " << t.nodes
        << ", \"eval_calls\": " << t.eval_calls
        << ", \"wall_ns\": " << t.wall_ns
        << ", \"nps\": " << nps
        << ", \"completed_depth_sum\": " << t.completed_depth_sum
        << ", \"effective_depth_sum\": " << t.effective_depth_sum
        << ", \"cache_lookups\": " << t.cache_lookups
        << ", \"cache_hits\": " << t.cache_hits
        << ", \"cache_misses\": " << t.cache_misses
        << ", \"cache_replacements\": " << t.cache_replacements
        << ", \"extract_f6_executions\": " << t.extract_f6_executions
        << ", \"cache_hit_rate\": " << cache_hit_rate << "}";
}

void write_summary(const std::string& path, const CellSpec& cell,
                   const RunSummary& s, bool sizer,
                   std::uint64_t game_timeout_ms) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create E2 report");
    const double score = s.games == 0 ? 0.0
        : (static_cast<double>(s.a_wins) + 0.5 * static_cast<double>(s.draws))
          / static_cast<double>(s.games);
    out << std::setprecision(17)
        << "{\n"
        << "  \"schema\": \"jass.t3_f6_e2_equal_nodes.v1\",\n"
        << "  \"mode\": \"" << (sizer ? "preflight_sizer" : "cell_run") << "\",\n"
        << "  \"cell\": \"" << cell.name << "\",\n"
        << "  \"technical_only\": " << (sizer ? "true" : "false") << ",\n"
        << "  \"strength_games\": " << (sizer ? 0 : s.games) << ",\n"
        << "  \"technical_games\": " << (sizer ? s.games : 0) << ",\n"
        << "  \"fit_runs\": 0,\n"
        << "  \"threads\": 1,\n"
        << "  \"book\": \"OFF\",\n"
        << "  \"movetime_ms\": 0,\n"
        << "  \"node_limit_mode\": \"exact\",\n"
        << "  \"tt_mb\": 16,\n"
        << "  \"max_game_plies\": " << MAX_GAME_PLIES << ",\n"
        << "  \"cache_o1_t3\": \"ON_COLD_PER_ROOT\",\n"
        << "  \"game_timeout_ms\": " << game_timeout_ms << ",\n"
        << "  \"openings\": " << s.openings << ",\n"
        << "  \"games\": " << s.games << ",\n"
        << "  \"game_skipped\": " << s.skipped << ",\n"
        << "  \"wall_ns_total\": " << s.wall_ns << ",\n"
        << "  \"max_game_wall_ns\": " << s.max_game_wall_ns << ",\n"
        << "  \"a_wins\": " << (sizer ? 0 : s.a_wins) << ",\n"
        << "  \"b_wins\": " << (sizer ? 0 : s.b_wins) << ",\n"
        << "  \"draws\": " << (sizer ? 0 : s.draws) << ",\n"
        << "  \"a_score\": " << (sizer ? 0.0 : score) << ",\n"
        << "  \"paired_complementarity_failures\": "
        << s.paired_complementarity_failures << ",\n";
    write_search_totals(out, "a_search", s.a); out << ",\n";
    write_search_totals(out, "b_search", s.b); out << "\n}\n";
}

bool same_search_result(const SearchResult& a, const SearchResult& b) {
    return a.best_move.from == b.best_move.from
        && a.best_move.to == b.best_move.to
        && a.best_move.captured == b.best_move.captured
        && a.best_move.promotes == b.best_move.promotes
        && a.score == b.score
        && a.depth == b.depth
        && a.effective_depth == b.effective_depth
        && a.completed_depth == b.completed_depth
        && a.aborted_iteration == b.aborted_iteration
        && a.stop_reason == b.stop_reason
        && a.nodes == b.nodes
        && a.cutoffs == b.cutoffs
        && a.first_move_cutoffs == b.first_move_cutoffs
        && a.pvs_researches == b.pvs_researches
        && a.moves_searched == b.moves_searched
        && a.eval_calls == b.eval_calls
        && a.scan_verify_probes == b.scan_verify_probes
        && a.scan_verify_cutoffs == b.scan_verify_cutoffs
        && a.scan_threat_reentries == b.scan_threat_reentries
        && a.qnodes == b.qnodes
        && a.qsearch_calls == b.qsearch_calls
        && a.tablebase_probes == b.tablebase_probes
        && a.tablebase_hits == b.tablebase_hits
        && a.tt_probes == b.tt_probes
        && a.tt_hits == b.tt_hits
        && a.terminal_hits == b.terminal_hits
        && a.reductions == b.reductions
        && a.extensions == b.extensions
        && a.root_order_applications == b.root_order_applications
        && a.root_order_failures == b.root_order_failures
        && a.pv == b.pv
        && a.from_book == b.from_book;
}

int selftest(const std::string& curriculum_path,
             const std::string& model_path,
             const std::string& q00_path) {
    const auto params = parse_search_params(read_text(q00_path));
    const auto model = load_t3_model(model_path);
    const Position pos = Position::start_position();

    ExactO1Network local(load_curriculum(curriculum_path), model);
    local.clear_for_root();
    SearchLimits local_limits;
    local_limits.max_depth = MAX_PLY;
    local_limits.max_nodes = 1000;
    local_limits.node_limit_mode = NodeLimitMode::Exact;
    local_limits.threads = 1;
    local_limits.movetime_ms = 0;
    local_limits.tt_mb = TT_MB;
    local_limits.params = params;
    local_limits.nnue = &local;
    TranspositionTable local_tt;
    local_tt.resize_mb(TT_MB);
    const SearchResult a = jass::search(pos, local_limits, local_tt, {});
    const auto local_stats = local.stats();
    if (local_stats.hits == 0 || local_stats.extract_f6_executions == 0)
        throw std::runtime_error("E2 local O1 selftest did not exercise real hits/misses");

    std::string error;
    auto official = t3_f6::O1SearchSession::create(
        load_curriculum(curriculum_path), model, 1, &error);
    if (!official) throw std::runtime_error("official O1 selftest create failed: " + error);
    SearchLimits official_limits = local_limits;
    official_limits.nnue = nullptr;
    TranspositionTable official_tt;
    official_tt.resize_mb(TT_MB);
    const auto b_opt = official->run_search(pos, official_limits, official_tt, &error);
    if (!b_opt) throw std::runtime_error("official O1 selftest search failed: " + error);
    if (!same_search_result(a, *b_opt))
        throw std::runtime_error("E2 local O1 search differs from terminal O1 session");
    if (official->cache_stats().hits == 0)
        throw std::runtime_error("official O1 selftest produced no cache hit");

    std::cout << "T3/F6 E2 equal-nodes selftest PASS\n";
    return 0;
}

RunSummary run_cell(const CellSpec& cell,
                    const std::vector<Position>& all_openings,
                    std::size_t start,
                    std::size_t count,
                    const std::string& curriculum_path,
                    const t3_f6::Model& model,
                    const SearchParams& params,
                    std::uint64_t game_timeout_ms,
                    bool sizer,
                    std::ostream* rows) {
    if (start > all_openings.size()) throw std::runtime_error("E2 start outside opening file");
    const std::size_t stop = std::min(all_openings.size(), start + count);
    if (stop <= start) throw std::runtime_error("E2 empty requested opening slice");
    RunSummary summary;
    summary.openings = stop - start;
    for (std::size_t i = start; i < stop; ++i) {
        const auto pair_begin = Clock::now();
        GameResult first;
        GameResult second;
        try {
            first = play_game(all_openings[i], cell.a, cell.b,
                              curriculum_path, model, params, game_timeout_ms);
            second = play_game(all_openings[i], cell.b, cell.a,
                               curriculum_path, model, params, game_timeout_ms);
        } catch (const GameTimeout&) {
            ++summary.skipped;
            throw;
        }
        account_game(summary, first, true);
        account_game(summary, second, false);
        const double pair_score = a_score(first, true) + a_score(second, false);
        if (cell.name == "C3" && pair_score != 1.0)
            ++summary.paired_complementarity_failures;

        if (rows && !sizer) {
            auto emit = [&](const GameResult& g, int leg, bool a_is_white) {
                *rows << std::setprecision(17)
                      << "{\"opening_index\":" << i
                      << ",\"leg\":" << leg
                      << ",\"a_color\":\"" << (a_is_white ? "white" : "black") << "\""
                      << ",\"outcome\":\"" << outcome_name(g.outcome) << "\""
                      << ",\"a_score\":" << a_score(g, a_is_white)
                      << ",\"plies\":" << g.plies
                      << ",\"reason\":\"" << g.reason << "\""
                      << ",\"game_wall_ns\":" << g.wall_ns
                      << "}\n";
            };
            emit(first, 0, true);
            emit(second, 1, false);
        }
        (void)pair_begin;
    }
    return summary;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 5 && std::string_view(argv[1]) == "--selftest")
            return selftest(argv[2], argv[3], argv[4]);

        const bool sizer = argc == 10 && std::string_view(argv[1]) == "--sizer";
        const bool run = argc == 12 && std::string_view(argv[1]) == "--run";
        if (!sizer && !run) {
            std::cerr
                << "usage:\n"
                << "  t3_f6_e2_match --selftest <curriculum> <t3.json> <q00.txt>\n"
                << "  t3_f6_e2_match --sizer <C1|C2|C3> <openings.fen> <curriculum> "
                   "<t3.json> <q00.txt> <start> <count> <report.json>\n"
                << "  t3_f6_e2_match --run <C1|C2|C3> <openings.fen> <curriculum> "
                   "<t3.json> <q00.txt> <start> <count> <game-timeout-ms> "
                   "<games.jsonl> <report.json>\n";
            return 2;
        }

        const CellSpec cell = cell_spec(argv[2]);
        const auto openings = read_fens(argv[3]);
        const std::string curriculum_path = argv[4];
        const std::string model_path = argv[5];
        const std::string q00_path = argv[6];
        const std::size_t start = static_cast<std::size_t>(std::stoull(argv[7]));
        const std::size_t count = static_cast<std::size_t>(std::stoull(argv[8]));
        const auto model = load_t3_model(model_path);
        const auto params = parse_search_params(read_text(q00_path));

        if (sizer) {
            const std::string report_path = argv[9];
            // No timeout in the preflight sizer: it measures the healthy slow
            // arm so the control job can choose the preregistered timeout before
            // any fresh E2 opening or strength result exists.
            const auto summary = run_cell(cell, openings, start, count,
                                          curriculum_path, model, params,
                                          0, true, nullptr);
            write_summary(report_path, cell, summary, true, 0);
            if (summary.skipped != 0)
                throw std::runtime_error("E2 preflight sizer unexpectedly skipped a game");
            std::cout << "T3/F6 E2 preflight sizer PASS openings=" << summary.openings << '\n';
            return 0;
        }

        const std::uint64_t timeout_ms = std::stoull(argv[9]);
        if (timeout_ms == 0) throw std::runtime_error("E2 run requires nonzero game timeout");
        std::ofstream rows(argv[10]);
        if (!rows) throw std::runtime_error("cannot create E2 games JSONL");
        const auto summary = run_cell(cell, openings, start, count,
                                      curriculum_path, model, params,
                                      timeout_ms, false, &rows);
        write_summary(argv[11], cell, summary, false, timeout_ms);
        if (summary.skipped != 0)
            throw std::runtime_error("E2 cell has skipped games");
        if (cell.name == "C3" && summary.paired_complementarity_failures != 0)
            throw std::runtime_error("E2 C3 complementarity failure");
        std::cout << "T3/F6 E2 cell PASS cell=" << cell.name
                  << " openings=" << summary.openings
                  << " games=" << summary.games << '\n';
        return 0;
    } catch (const GameTimeout& error) {
        std::cerr << "t3_f6_e2_match timeout: " << error.what() << '\n';
        return 4;
    } catch (const std::exception& error) {
        std::cerr << "t3_f6_e2_match: " << error.what() << '\n';
        return 1;
    }
}
