// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Native entry point.
//
// Default: reads HUB-style commands from stdin and writes the responses
// to stdout — the form a draughts GUI expects when launching the engine.
// Pass `--smoke` to run the historical demo (start position, FEN
// round-trip, sample neighbours, depth-6 best-move and a 40-ply
// engine-vs-engine game) instead.

#include "board.hpp"
#include "engine.hpp"
#include "hub.hpp"
#include "movegen.hpp"
#include "eval.hpp"
#include "hybrid_network.hpp"
#include "nnue.hpp"
#include "nnue_server_client.hpp"
#include "pattern_jass_bridge.hpp"
#include "position.hpp"
#include "bitbase.hpp"
#include "bitboard.hpp"
#include "egdb_bridge.hpp"
#include "endgame.hpp"
#include "scan_book.hpp"
#include "scan_eval.hpp"
#include "scan_sacs.hpp"
#include "search.hpp"
#include "selfplay_exploration.hpp"
#include "selfplay_node_budget.hpp"
#include "tournament.hpp"

#include <algorithm>
#include <utility>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <random>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <string_view>

using namespace jass;

namespace {

enum class SelfplaySearchLimitType : std::uint8_t {
    Depth,
    Nodes,
};

struct NodeBudgetRunStats {
    std::uint64_t searches{0};
    std::uint64_t aborted_searches{0};
    long double   budget_sum{0};
    long double   nodes_sum{0};
    long double   ratio_sum{0};
    long double   effective_depth_sum{0};
    std::uint64_t elapsed_us_sum{0};
    std::map<std::uint64_t, std::uint64_t> budget_counts;

    void record(std::uint64_t budget, const SearchResult& result,
                std::uint64_t elapsed_us) {
        ++searches;
        if (result.aborted_iteration) ++aborted_searches;
        budget_sum += static_cast<long double>(budget);
        nodes_sum += static_cast<long double>(result.nodes);
        ratio_sum += static_cast<long double>(result.nodes)
                   / static_cast<long double>(budget);
        effective_depth_sum += result.effective_depth;
        elapsed_us_sum += elapsed_us;
        ++budget_counts[budget];
    }

    std::uint64_t quantile(unsigned numerator, unsigned denominator) const {
        if (searches == 0 || denominator == 0) return 0;
        const std::uint64_t rank = std::max<std::uint64_t>(
            1, (searches * numerator + denominator - 1) / denominator);
        std::uint64_t cumulative = 0;
        for (const auto& [budget, count] : budget_counts) {
            cumulative += count;
            if (cumulative >= rank) return budget;
        }
        return budget_counts.empty() ? 0 : budget_counts.rbegin()->first;
    }
};

void write_node_budget_manifest(
    std::ostream& out,
    const jass::selfplay::NodeBudgetPolicy& policy,
    std::uint64_t cli_seed,
    std::uint64_t sampler_seed) {
    out << "{\"event\":\"node_budget_manifest\""
        << ",\"search_limit_type\":\"nodes\""
        << ",\"distribution\":\""
        << jass::selfplay::node_budget_distribution_name(policy.distribution())
        << "\",\"sample_per\":\""
        << jass::selfplay::sampling_granularity_name(policy.granularity())
        << "\",\"min_budget\":" << policy.min_nodes()
        << ",\"max_budget\":" << policy.max_nodes()
        << ",\"sampler_version\":"
        << jass::selfplay::NODE_BUDGET_SAMPLER_VERSION
        << ",\"global_seed\":" << cli_seed
        << ",\"sampler_seed\":" << sampler_seed
        << ",\"values\":[";
    for (std::size_t i = 0; i < policy.choices().size(); ++i) {
        if (i) out << ',';
        const auto& choice = policy.choices()[i];
        out << "{\"nodes\":" << choice.nodes
            << ",\"weight\":" << choice.weight << '}';
    }
    out << "]}\n";
}

void write_node_budget_summary(std::ostream& out,
                               const NodeBudgetRunStats& stats) {
    const long double count = stats.searches > 0
        ? static_cast<long double>(stats.searches) : 1.0L;
    const long double aggregate_ratio = stats.budget_sum > 0
        ? stats.nodes_sum / stats.budget_sum : 0.0L;
    const long double aggregate_nps = stats.elapsed_us_sum > 0
        ? stats.nodes_sum * 1'000'000.0L / stats.elapsed_us_sum : 0.0L;
    out << std::fixed << std::setprecision(3)
        << "{\"event\":\"node_budget_summary\""
        << ",\"searches\":" << stats.searches
        << ",\"budget_mean\":" << static_cast<double>(stats.budget_sum / count)
        << ",\"budget_p10\":" << stats.quantile(1, 10)
        << ",\"budget_p50\":" << stats.quantile(1, 2)
        << ",\"budget_median\":" << stats.quantile(1, 2)
        << ",\"budget_p90\":" << stats.quantile(9, 10)
        << ",\"nodes_used_total\":"
        << static_cast<std::uint64_t>(stats.nodes_sum)
        << ",\"nodes_used_mean\":" << static_cast<double>(stats.nodes_sum / count)
        << ",\"aggregate_nodes_used_over_budget\":"
        << static_cast<double>(aggregate_ratio)
        << ",\"mean_nodes_used_over_budget\":"
        << static_cast<double>(stats.ratio_sum / count)
        << ",\"effective_depth_mean\":"
        << static_cast<double>(stats.effective_depth_sum / count)
        << ",\"search_time_ms_mean\":"
        << static_cast<double>(stats.elapsed_us_sum / count / 1'000.0L)
        << ",\"nps\":" << static_cast<double>(aggregate_nps)
        << ",\"aborted_iterations\":" << stats.aborted_searches
        << ",\"buckets\":{";
    bool first = true;
    for (const auto& [budget, bucket_count] : stats.budget_counts) {
        if (!first) out << ',';
        first = false;
        out << '\"' << budget << "\":" << bucket_count;
    }
    out << "}}\n";
}

const char* dir_name(Dir d) {
    switch (d) {
        case Dir::UpLeft:    return "NW";
        case Dir::UpRight:   return "NE";
        case Dir::DownLeft:  return "SW";
        case Dir::DownRight: return "SE";
    }
    return "??";
}

void show_neighbours(Square s) {
    std::cout << "Square " << static_cast<int>(s) << " neighbours:";
    for (Dir d : ALL_DIRS) {
        const Square n = neighbour(s, d);
        std::cout << ' ' << dir_name(d) << '=';
        if (n == NO_SQUARE) std::cout << '-';
        else                std::cout << static_cast<int>(n);
    }
    std::cout << '\n';
}

int run_smoke() {
    const Position start = Position::start_position();
    std::cout << "=== Jass — international draughts engine ===\n\n";
    std::cout << start.to_ascii() << '\n';
    std::cout << "Hub FEN: " << start.to_fen() << "\n\n";

    const auto round_trip = Position::from_fen(start.to_fen());
    std::cout << "FEN round-trip: "
              << (round_trip && *round_trip == start ? "OK" : "FAILED")
              << "\n\n";

    std::cout << "Sample diagonal neighbours:\n";
    for (Square s : {Square{1}, Square{6}, Square{28}, Square{45}, Square{50}}) {
        show_neighbours(s);
    }
    std::cout << '\n';

    Engine engine;
    const SearchResult sr = engine.search(6);
    std::cout << "Search at depth " << sr.depth
              << ": best move "    << format_move(sr.best_move)
              << " (score="        << sr.score
              << ", nodes="        << sr.nodes << ")\n\n";

    std::cout << "Engine-vs-engine smoke game (depth 4, cap 40 plies):\n";
    Engine game;
    for (int ply = 1; ply <= 40; ++ply) {
        MoveList legal;
        generate_legal_moves(game.position(), legal);
        if (legal.empty()) {
            std::cout << "  ply " << ply << ": "
                      << (game.position().side_to_move() == Color::White ? "White" : "Black")
                      << " has no legal move — game over.\n";
            break;
        }
        const SearchResult r = game.search(4);
        std::cout << "  ply " << ply << " ("
                  << (game.position().side_to_move() == Color::White ? 'W' : 'B') << "): "
                  << format_move(r.best_move)
                  << " score=" << r.score << '\n';
        game.apply_move(r.best_move);
    }
    return 0;
}

}  // namespace

int parse_int_or(std::string_view s, int fallback) {
    int v = fallback;
    auto [ptr, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
    return (ec == std::errc{}) ? v : fallback;
}

// Game phase by piece count, IDENTICAL bounds to pattern_jass/tools/train.py
// (--phase-weight), tools/game_autopsy.py and tools/phase_proxy.py, so the
// labelling, the training reweighting and the autopsies all bucket positions the
// same way. Index 0..4 = opening / midgame / late-mid / endgame / deep-eg.
constexpr int NUM_PHASES = 5;
constexpr const char* PHASE_NAMES[NUM_PHASES] =
    {"opening", "midgame", "late-mid", "endgame", "deep-eg"};
inline int phase_index_of(int pieces) noexcept {
    if (pieces >= 30) return 0;   // opening
    if (pieces >= 22) return 1;   // midgame
    if (pieces >= 15) return 2;   // late-mid
    if (pieces >= 8)  return 3;   // endgame
    return 4;                     // deep-eg
}

// Parse "endgame=16,deep-eg=20" into per-phase ABSOLUTE search depths (0 = no
// override → use the base depth). Shared by --label-depth-by-phase (deeper
// LABELLING search) and --play-depth-by-phase (deeper PLAY search so the WDL
// outcome of endgames is accurate — cf the 0254/0261 finding that the loop
// trains on WDL, so what fixes endgame labels is playing them deeper, not a
// deeper label search or row-weighting). `flag` names the option in warnings.
// Unknown phase names are reported and ignored; whitespace is tolerated.
std::array<int, NUM_PHASES> parse_depth_by_phase(const std::string& spec,
                                                 const char* flag) {
    std::array<int, NUM_PHASES> out{};   // all 0 = "use base depth"
    std::size_t i = 0;
    while (i < spec.size()) {
        const std::size_t comma = spec.find(',', i);
        std::string tok = spec.substr(
            i, comma == std::string::npos ? std::string::npos : comma - i);
        i = (comma == std::string::npos) ? spec.size() : comma + 1;
        const std::size_t eq = tok.find('=');
        if (eq == std::string::npos) continue;
        std::string name = tok.substr(0, eq);
        // trim spaces around the name
        const auto a = name.find_first_not_of(" \t");
        const auto b = name.find_last_not_of(" \t");
        name = (a == std::string::npos) ? "" : name.substr(a, b - a + 1);
        const int d = parse_int_or(tok.substr(eq + 1), 0);
        bool known = false;
        for (int p = 0; p < NUM_PHASES; ++p) {
            if (name == PHASE_NAMES[p]) { out[p] = d; known = true; break; }
        }
        if (!known) {
            std::cerr << "warning: " << flag << ": unknown phase '"
                      << name << "' ignored\n";
        } else if (d <= 0) {
            // A non-positive depth silently means "use base depth" downstream;
            // warn so a sign typo (endgame=-16) doesn't quietly disable the
            // intended deeper search for that phase.
            std::cerr << "warning: " << flag << ": " << name
                      << " depth " << d << " <= 0 → using base depth for it\n";
        }
    }
    return out;
}

// -----------------------------------------------------------------------------
// --gen-data: write a binary dataset of (position, target-score) records for
// offline NNUE training.  See `tools/README.md` for the format.
// -----------------------------------------------------------------------------
int run_gen_data_mode(int argc, char** argv) {
    int          n         = 10000;
    const char*  out_path  = "selfplay.bin";
    int          play_depth = 4;       // depth used to advance games
    int          eval_depth = 8;       // depth used to label sampled positions
    int          random_open_plies = 4;
    // Optional seed (argv[4]) so the generator can be sharded across cores
    // with disjoint streams. Default keeps the historical fixed seed.
    std::uint64_t seed = 0x5eed5eed5eed5eedULL;

    if (argc > 2) {
        int parsed = parse_int_or(argv[2], -1);
        if (parsed > 0) n = parsed;
    }
    if (argc > 3) out_path = argv[3];
    if (argc > 4) {
        const long long s = parse_int_or(argv[4], -1);
        if (s >= 0) seed = static_cast<std::uint64_t>(s);
    }

    std::ofstream f(out_path, std::ios::binary);
    if (!f) {
        std::cerr << "error: cannot open " << out_path << " for writing\n";
        return 1;
    }

    // Header: 4 bytes magic + 4 bytes record-count.  We backpatch the count
    // at the end of the run so the file is self-describing even if the
    // requested count is reduced (e.g. all reachable positions were sampled).
    const char magic[4] = {'J', 'N', 'N', 'T'};
    f.write(magic, 4);
    std::uint32_t count_placeholder = 0;
    f.write(reinterpret_cast<const char*>(&count_placeholder), 4);

    std::mt19937_64 rng(seed);
    Engine          e;
    e.use_book(false);

    int generated  = 0;
    int game_count = 0;

    while (generated < n) {
        ++game_count;
        e.new_game();

        // Random opening plies for diversity.  Pick uniformly among the legal
        // moves of the current position; this is enough to avoid identical
        // games across runs.
        for (int i = 0; i < random_open_plies; ++i) {
            MoveList ml;
            generate_legal_moves(e.position(), ml);
            if (ml.empty()) break;
            e.apply_move(ml[rng() % ml.size()]);
        }

        for (int ply = 0; ply < 100 && generated < n; ++ply) {
            MoveList ml;
            generate_legal_moves(e.position(), ml);
            if (ml.empty()) break;

            // Sample roughly every fourth ply.
            if ((rng() & 3) == 0) {
                SearchLimits lim;
                lim.max_depth = eval_depth;
                const SearchResult r = e.search(lim);
                const int score = r.score;

                const Position& pos = e.position();
                const std::uint64_t bbs[4] = {
                    pos.white_men(),   pos.white_kings(),
                    pos.black_men(),   pos.black_kings()};
                f.write(reinterpret_cast<const char*>(bbs), 32);
                const std::uint8_t stm = (pos.side_to_move() == Color::White) ? 0 : 1;
                f.write(reinterpret_cast<const char*>(&stm), 1);
                const std::int32_t s32 = static_cast<std::int32_t>(score);
                f.write(reinterpret_cast<const char*>(&s32), 4);

                ++generated;
            }

            // Advance the game with a low-depth move so positions stay diverse.
            SearchLimits lim;
            lim.max_depth = play_depth;
            const SearchResult r = e.search(lim);
            if (!e.apply_move(r.best_move)) break;
        }

        if ((game_count % 50) == 0) {
            std::cout << "  played " << game_count << " games, "
                      << generated << " / " << n << " positions\n";
        }
    }

    // Backpatch the count.
    f.seekp(4, std::ios::beg);
    const std::uint32_t count32 = static_cast<std::uint32_t>(generated);
    f.write(reinterpret_cast<const char*>(&count32), 4);
    f.close();

    std::cout << "wrote " << generated << " records to " << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --gen-data-wdl: same as --gen-data but each sample also carries the
// outcome of the game it was sampled from. The outcome is computed at
// the end of the game (no-legal-move = STM loss, 25-move rule /
// repetition / ply cap = draw) and propagated back to every sample as
// +1 (sample's STM eventually won), 0 (draw), or -1 (sample's STM lost).
//
// Per-record format (38 bytes, magic "JNNW"):
//   32 B  uint64×4 bitboards   (white_men, white_kings, black_men, black_kings)
//    1 B  uint8    stm         (0 = white to move, 1 = black to move)
//    4 B  int32    score       (centipawn, STM-POV, depth-eval search; or zero
//                               with --wdl-zero-score)
//    1 B  int8     wdl         (+1 / 0 / -1, STM-POV at sample time)
//
// Used by the WDL training pipeline (`tools/scout_wdl.py` and
// downstream variants of `train_mlp.py`) to mix score-MSE and
// outcome-BCE losses.
// -----------------------------------------------------------------------------
int run_gen_data_wdl_mode(int argc, char** argv) {
    int          n         = 10000;
    const char*  out_path  = "selfplay-wdl.bin";
    int          play_depth = 4;
    int          eval_depth = 12;        // bumped from 8 for the WDL pipeline:
                                          // ~3-5× more compute per label but
                                          // far less noise in the targets,
                                          // which is the bottleneck for any
                                          // future architecture work.
                                          // NB: the reference 1M dataset
                                          // (job 0010, master-1M.jnnw) was
                                          // labelled at depth-20 — set via
                                          // the positional `eval_depth`
                                          // arg, not this default.
    int          random_open_plies = 4;
    int          max_plies        = 200;
    int          random_seed      = 0;    // 0 → engine-fixed seed (legacy)
    const char*  nnue_path        = nullptr;
    bool         quiet_only       = false;  // skip positions with mandatory captures
    bool         sample_initial   = false;  // always sample ply 0 (subject to quiet_only)
    bool         wdl_zero_score    = false;  // --wdl-zero-score: WDL-only mode. Store score=0
                                            // and skip the otherwise unused label search,
                                            // preventing hidden TT priming of the play search.
    int          pv_extract       = 0;      // additional samples to harvest along the PV
    int          movetime_ms      = 0;      // >0 → play moves by wall-clock (Scan-style
                                            //      self-play); play_depth becomes a cap
    std::uint64_t play_max_nodes  = 0;      // --play-max-nodes N : DETERMINISTIC hard node cap
                                            //      on the PLAY+LABEL search (0 = unlimited). Bounds a
                                            //      flat/near-zero eval where alpha-beta collapses and a
                                            //      fixed-depth search would explode (from-scratch tour-0).
    SelfplaySearchLimitType search_limit_type = SelfplaySearchLimitType::Depth;
    const char*  node_budget_fixed_spec = nullptr;
    const char*  node_budget_weighted_spec = nullptr;
    const char*  node_budget_log_path = nullptr;
    jass::selfplay::SamplingGranularity node_budget_sample_per =
        jass::selfplay::SamplingGranularity::Move;
    bool         node_budget_sample_per_set = false;
    std::string  label_depth_spec;          // "endgame=16,deep-eg=20" → deeper LABEL
                                            //      search by phase (empty = eval_depth)
    std::string  play_depth_spec;           // "endgame=12,deep-eg=14" → deeper PLAY
                                            //      search by phase → accurate endgame WDL
    const char*  seed_path        = nullptr; // --seed-file : JNNW of seed positions
    int          seed_frac        = 0;       // --seed-frac : % of games started from a
                                             //      random seed (endgame COVERAGE / famine)
    bool         seed_without_replacement = false;
                                            // --seed-without-replacement : consume a
                                            //      deterministic permutation of the seed
                                            //      catalogue. Each seed starts at most one
                                            //      opening (two trajectories with
                                            //      --pair-openings). Historical sampling
                                            //      with replacement remains the default.
    int          explore_eps      = 0;       // --explore-eps : % of plies played as a
                                            //      uniform-random legal move instead of
                                            //      the search best (off-policy μ widening)
    int          explore_topk    = 0;       // --explore-topk K : on an exploration ply,
                                            //      pick uniformly among the K best-ranked
                                            //      legal moves instead of uniformly among
                                            //      ALL of them. K=0 keeps the legacy
                                            //      uniform draw. See the eps branch below
                                            //      for why the distinction matters.
    int          explore_margin  = 0;       // --explore-margin M : with --explore-topk,
                                            //      keep only the moves within M centipawns
                                            //      of the best. Rank alone says a move is
                                            //      second, not that it is CLOSE: in a
                                            //      forced position the 2nd and 3rd moves
                                            //      drop a piece, and top-k without a margin
                                            //      would play them two times out of three.
                                            //      M=0 disables the filter.
    bool         split_selfplay_rngs = false; // --split-selfplay-rngs : draw openings,
                                            //      sampling, exploration and role from
                                            //      SEPARATE streams derived from the same
                                            //      seed. Off by default so historical jobs
                                            //      reproduce bit for bit. REQUIRED for a
                                            //      paired A/B: with one shared stream, an
                                            //      arm that consumes a different number of
                                            //      draws (top-k ranks, uniform does not)
                                            //      desynchronises every later opening, and
                                            //      the arms stop being paired on the very
                                            //      thing that was supposed to be held equal.
    int          explore_decay_plies = 0;    // --explore-decay-plies D : FIX#1 label-hygiene.
                                            //      eps(ply)=explore_eps*max(0,1-ply/D) => confine
                                            //      l'exploration au debut (0 = pas de decroissance).
    bool         drop_post_eps     = false;  // --drop-post-eps : FIX#1. n'emet PAS les samples
                                            //      ply<=last_eps_ply (label contamine par un eps posterieur).
    bool         drop_plycap       = false;  // --drop-plycap : n'emet AUCUN sample d'une partie
                                            //      non resolue a max_plies (jamais de faux label DRAW).
    const char*  sample_meta_path  = nullptr; // --sample-meta-out : sidecar aligne 1:1.
    bool         sample_meta_v2    = false;   // --sample-meta-format jsm2 : contexte de partie
                                             //      JSM2. Le defaut JSM1 reste byte-compatible.
    int          adjud_material    = 0;      // --adjud-material M : FIX#2. avance materielle NETTE (men-equiv,
                                            //      dame=3) >= M tenue adjud_hold_plies => win (0 = off).
    int          adjud_hold_plies  = 10;     // --adjud-hold-plies H : plies consecutifs d'avance requis.
    bool         pair_openings     = false;  // --pair-openings : FIX#3. chaque ouverture jouee 2x, couleur
                                            //      punisher echangee => biais couleur/role s'annule dans la paire.
    bool         tb_relabel        = false;  // --tb-relabel : FIX#4. au flush, remplace le label WDL-partie par
                                            //      la valeur EGDB EXACTE des positions qui tombent dans la TB (biais 0).
    std::string  search_spec;                // --search-params : applied to PLAY+LABEL search
                                            //      (e.g. pruning OFF so self-play PUNISHES shots
                                            //      → labels teach shot-safety, cf Scan recipe)
    // Slot separation (forcing-ext SPEC). The 3 slots = test / gen-play / gen-label. The TEST
    // slot lives in the match tools (calibrate --jass-search-params). Here we split GEN:
    //   --search-params-play  : the ROLLOUT search → it decides the game OUTCOME → the WDL of every
    //                           sample. THIS is the lever for logistic-WDL (the default recipe).
    //   --search-params-label : the LABELLING search → only sets the per-sample `score` field, which
    //                           logistic-WDL training IGNORES (it matters ONLY for --target value).
    //   --asym-punisher-params: if set, ASYMMETRIC self-play. Each game a random "punisher" colour
    //                           plays with these params (e.g. ext_forcing=1) while the "victim" plays
    //                           the base play params. Manufactures the class symmetric play lacks:
    //                           vulnerable position REACHED by the (blind) victim → PUNISHED by the
    //                           (seeing) punisher → labelled LOSS (forcing-ext SPEC §4).
    // Empty per-slot spec falls back to --search-params.
    std::string  search_spec_play;
    std::string  search_spec_label;
    std::string  search_spec_punisher;

    // Scan for `--nnue PATH`, `--quiet-only` and `--pv-extract N` anywhere
    // in the args; consume them and keep the rest as the historical
    // positional slots so existing invocations stay backward-compatible.
    // Without --nnue we fall back to the embedded default network — that's
    // the Cycle 8 / pre-v5 behaviour the depth-20 1M dataset (0010) was
    // labelled with. Without --quiet-only the sampler keeps the historical
    // 1-ply-in-4 unfiltered behaviour. Without --pv-extract the labelling
    // search yields a single (position, score) record (legacy behaviour).
    std::vector<char*> positional;
    positional.reserve(static_cast<std::size_t>(argc));
    for (int i = 0; i < argc; ++i) {
        const std::string_view a{argv[i]};
        if (a == "--nnue" && i + 1 < argc) {
            nnue_path = argv[++i];
        } else if (a == "--quiet-only") {
            quiet_only = true;
        } else if (a == "--sample-initial") {
            sample_initial = true;
        } else if (a == "--wdl-zero-score") {
            wdl_zero_score = true;
        } else if (a == "--pv-extract" && i + 1 < argc) {
            const int v = parse_int_or(argv[++i], -1);
            if (v >= 0) pv_extract = v;
        } else if (a == "--movetime" && i + 1 < argc) {
            const int v = parse_int_or(argv[++i], -1);
            if (v >= 0) movetime_ms = v;
        } else if (a == "--play-max-nodes" && i + 1 < argc) {
            const long long v = std::atoll(argv[++i]);
            if (v > 0) play_max_nodes = static_cast<std::uint64_t>(v);
        } else if (a == "--search-limit" && i + 1 < argc) {
            const std::string_view value{argv[++i]};
            if (value == "depth") {
                search_limit_type = SelfplaySearchLimitType::Depth;
            } else if (value == "nodes") {
                search_limit_type = SelfplaySearchLimitType::Nodes;
            } else {
                std::cerr << "error: --search-limit must be depth or nodes\n";
                return 2;
            }
        } else if (a == "--node-budget-fixed" && i + 1 < argc) {
            node_budget_fixed_spec = argv[++i];
        } else if (a == "--node-budget-weighted" && i + 1 < argc) {
            node_budget_weighted_spec = argv[++i];
        } else if (a == "--node-budget-sample-per" && i + 1 < argc) {
            const std::string_view value{argv[++i]};
            if (value == "move") {
                node_budget_sample_per =
                    jass::selfplay::SamplingGranularity::Move;
            } else if (value == "game") {
                node_budget_sample_per =
                    jass::selfplay::SamplingGranularity::Game;
            } else {
                std::cerr << "error: --node-budget-sample-per must be move or game\n";
                return 2;
            }
            node_budget_sample_per_set = true;
        } else if (a == "--node-budget-log" && i + 1 < argc) {
            node_budget_log_path = argv[++i];
        } else if (a == "--label-depth-by-phase" && i + 1 < argc) {
            label_depth_spec = argv[++i];
        } else if (a == "--play-depth-by-phase" && i + 1 < argc) {
            play_depth_spec = argv[++i];
        } else if (a == "--seed-file" && i + 1 < argc) {
            seed_path = argv[++i];
        } else if (a == "--seed-frac" && i + 1 < argc) {
            seed_frac = parse_int_or(argv[++i], -1);
        } else if (a == "--seed-without-replacement") {
            seed_without_replacement = true;
        } else if (a == "--random-open-plies" && i + 1 < argc) {
            const int v = parse_int_or(argv[++i], -1);
            if (v >= 0) random_open_plies = v;
        } else if (a == "--explore-eps" && i + 1 < argc) {
            const int v = parse_int_or(argv[++i], -1);
            if (v >= 0) explore_eps = v;
        } else if (a == "--explore-topk" && i + 1 < argc) {
            const int v = std::atoi(argv[++i]);
            if (v >= 0) explore_topk = v;
        } else if (a == "--explore-margin" && i + 1 < argc) {
            const int v = std::atoi(argv[++i]);
            if (v >= 0) explore_margin = v;
        } else if (a == "--split-selfplay-rngs") {
            split_selfplay_rngs = true;
        } else if (a == "--explore-decay-plies" && i + 1 < argc) {
            const int v = parse_int_or(argv[++i], -1);
            if (v >= 0) explore_decay_plies = v;
        } else if (a == "--drop-post-eps") {
            drop_post_eps = true;
        } else if (a == "--drop-plycap") {
            drop_plycap = true;
        } else if (a == "--sample-meta-out") {
            if (i + 1 >= argc) {
                std::cerr << "error: --sample-meta-out requires PATH\n";
                return 2;
            }
            sample_meta_path = argv[++i];
        } else if (a == "--sample-meta-format") {
            if (i + 1 >= argc) {
                std::cerr << "error: --sample-meta-format requires jsm1 or jsm2\n";
                return 2;
            }
            const std::string_view value{argv[++i]};
            if (value == "jsm1") {
                sample_meta_v2 = false;
            } else if (value == "jsm2") {
                sample_meta_v2 = true;
            } else {
                std::cerr << "error: --sample-meta-format must be jsm1 or jsm2\n";
                return 2;
            }
        } else if (a == "--adjud-material" && i + 1 < argc) {
            const int v = parse_int_or(argv[++i], -1);
            if (v >= 0) adjud_material = v;
        } else if (a == "--adjud-hold-plies" && i + 1 < argc) {
            const int v = parse_int_or(argv[++i], -1);
            if (v >= 0) adjud_hold_plies = v;
        } else if (a == "--pair-openings") {
            pair_openings = true;
        } else if (a == "--tb-relabel") {
            tb_relabel = true;
        } else if (a == "--search-params" && i + 1 < argc) {
            search_spec = argv[++i];
        } else if (a == "--search-params-play" && i + 1 < argc) {
            search_spec_play = argv[++i];
        } else if (a == "--search-params-label" && i + 1 < argc) {
            search_spec_label = argv[++i];
        } else if (a == "--asym-punisher-params" && i + 1 < argc) {
            search_spec_punisher = argv[++i];
        } else {
            positional.push_back(argv[i]);
        }
    }
    if (wdl_zero_score && pv_extract > 0) {
        std::cerr << "error: --wdl-zero-score is incompatible with --pv-extract\n";
        return 2;
    }
    if (seed_frac < 0 || seed_frac > 100) {
        std::cerr << "error: --seed-frac must be an integer in [0,100]\n";
        return 2;
    }
    if (seed_frac > 0 && seed_path == nullptr) {
        std::cerr << "error: --seed-frac requires --seed-file\n";
        return 2;
    }
    if (seed_without_replacement && seed_path == nullptr) {
        std::cerr << "error: --seed-without-replacement requires --seed-file\n";
        return 2;
    }
    if (seed_without_replacement && seed_frac != 100) {
        std::cerr << "error: --seed-without-replacement requires --seed-frac 100\n";
        return 2;
    }
    std::optional<jass::selfplay::NodeBudgetPolicy> node_budget_policy;
    const bool has_node_budget_config = node_budget_fixed_spec != nullptr
                                     || node_budget_weighted_spec != nullptr
                                     || node_budget_sample_per_set
                                     || node_budget_log_path != nullptr;
    if (search_limit_type == SelfplaySearchLimitType::Depth) {
        if (has_node_budget_config) {
            std::cerr << "error: node-budget options require --search-limit nodes\n";
            return 2;
        }
    } else {
        if ((node_budget_fixed_spec == nullptr)
            == (node_budget_weighted_spec == nullptr)) {
            std::cerr << "error: --search-limit nodes requires exactly one of "
                         "--node-budget-fixed or --node-budget-weighted\n";
            return 2;
        }
        if (node_budget_log_path == nullptr) {
            std::cerr << "error: --search-limit nodes requires --node-budget-log PATH\n";
            return 2;
        }
        if (movetime_ms > 0) {
            std::cerr << "error: --search-limit nodes is incompatible with --movetime\n";
            return 2;
        }
        if (play_max_nodes > 0) {
            std::cerr << "error: --search-limit nodes is incompatible with the legacy "
                         "--play-max-nodes safety cap\n";
            return 2;
        }
        if (!play_depth_spec.empty()) {
            std::cerr << "error: --play-depth-by-phase is incompatible with "
                         "--search-limit nodes\n";
            return 2;
        }
        if (explore_topk > 0) {
            std::cerr << "error: --explore-topk is incompatible with "
                         "--search-limit nodes\n";
            return 2;
        }
        try {
            if (node_budget_fixed_spec != nullptr) {
                const std::uint64_t nodes =
                    jass::selfplay::parse_node_budget_integer(
                        node_budget_fixed_spec, "fixed value");
                node_budget_policy = jass::selfplay::NodeBudgetPolicy::fixed(
                    nodes, node_budget_sample_per);
            } else {
                node_budget_policy = jass::selfplay::NodeBudgetPolicy::weighted(
                    jass::selfplay::parse_weighted_node_budgets(
                        node_budget_weighted_spec),
                    node_budget_sample_per);
            }
        } catch (const std::invalid_argument& error) {
            std::cerr << "error: " << error.what() << '\n';
            return 2;
        }
    }
    const std::array<int, NUM_PHASES> label_depth =
        parse_depth_by_phase(label_depth_spec, "--label-depth-by-phase");
    const std::array<int, NUM_PHASES> play_depth_by_phase =
        parse_depth_by_phase(play_depth_spec, "--play-depth-by-phase");
    const SearchParams gen_params = jass::parse_search_params(search_spec);  // PLAY+LABEL fallback
    // Per-slot params (forcing-ext SPEC) : empty falls back to gen_params (back-compatible).
    const SearchParams play_params  = search_spec_play.empty()
        ? gen_params : jass::parse_search_params(search_spec_play);
    const SearchParams label_params = search_spec_label.empty()
        ? gen_params : jass::parse_search_params(search_spec_label);
    const bool asym_mode = !search_spec_punisher.empty();
    const SearchParams punisher_params = asym_mode
        ? jass::parse_search_params(search_spec_punisher) : play_params;
    const int p_argc = static_cast<int>(positional.size());
    char** const p_argv = positional.data();

    if (p_argc > 2) {
        int parsed = parse_int_or(p_argv[2], -1);
        if (parsed > 0) n = parsed;
    }
    if (p_argc > 3) out_path = p_argv[3];
    if (p_argc > 4) {
        int v = parse_int_or(p_argv[4], -1);
        if (v > 0) eval_depth = v;
    }
    if (p_argc > 5) {
        int v = parse_int_or(p_argv[5], -1);
        if (v > 0) play_depth = v;
    }
    if (p_argc > 6) {
        int v = parse_int_or(p_argv[6], -1);
        if (v > 0) max_plies = v;
    }
    if (p_argc > 7) {
        int v = parse_int_or(p_argv[7], -1);
        if (v > 0) random_seed = v;
    }
    if (sample_meta_v2 && sample_meta_path == nullptr) {
        std::cerr << "error: --sample-meta-format jsm2 requires --sample-meta-out PATH\n";
        return 2;
    }
    if (sample_meta_v2 && pv_extract > 0) {
        std::cerr << "error: JSM2 cannot describe --pv-extract records because they are "
                     "not positions from the played trajectory\n";
        return 2;
    }
    if (sample_meta_v2 && max_plies > 0xFFFF) {
        std::cerr << "error: JSM2 requires max_plies <= 65535\n";
        return 2;
    }
    if (node_budget_policy
        && (std::string_view{node_budget_log_path} == std::string_view{out_path}
            || (sample_meta_path != nullptr
                && std::string_view{node_budget_log_path}
                    == std::string_view{sample_meta_path}))) {
        std::cerr << "error: --node-budget-log must differ from JNNW and sample-metadata outputs\n";
        return 2;
    }

    std::cout << "gen-data-wdl: n=" << n
              << " out=" << out_path
              << " eval_depth=" << eval_depth
              << " play_depth=" << play_depth
              << " max_plies=" << max_plies
              << " seed=" << (random_seed > 0 ? std::to_string(random_seed) : "default")
              << " nnue=" << (nnue_path ? nnue_path : "(default embedded)")
              << " quiet_only=" << (quiet_only ? "true" : "false")
              << " sample_initial=" << (sample_initial ? "true" : "false")
              << " wdl_zero_score=" << (wdl_zero_score ? "true" : "false")
              << " pv_extract=" << pv_extract
              << " movetime_ms=" << movetime_ms
              << " drop_plycap=" << (drop_plycap ? "true" : "false")
              << " sample_meta=" << (sample_meta_path ? sample_meta_path : "(off)")
              << " sample_meta_format=" << (sample_meta_v2 ? "JSM2" : "JSM1");
    if (node_budget_policy) {
        std::cout << " search_limit=nodes"
                  << " node_budget_distribution="
                  << jass::selfplay::node_budget_distribution_name(
                         node_budget_policy->distribution())
                  << " node_budget_sample_per="
                  << jass::selfplay::sampling_granularity_name(
                         node_budget_policy->granularity())
                  << " node_budget_min=" << node_budget_policy->min_nodes()
                  << " node_budget_max=" << node_budget_policy->max_nodes()
                  << " node_budget_sampler_version="
                  << jass::selfplay::NODE_BUDGET_SAMPLER_VERSION
                  << " node_budget_log=" << node_budget_log_path;
    }
    {
        bool any = false;
        for (int p = 0; p < NUM_PHASES; ++p) {
            if (label_depth[p] > 0) {
                std::cout << (any ? "," : " label_depth_by_phase=")
                          << PHASE_NAMES[p] << ":" << label_depth[p];
                any = true;
            }
        }
        if (!any) std::cout << " label_depth_by_phase=(uniform eval_depth)";
    }
    {
        bool any = false;
        for (int p = 0; p < NUM_PHASES; ++p) {
            if (play_depth_by_phase[p] > 0) {
                std::cout << (any ? "," : " play_depth_by_phase=")
                          << PHASE_NAMES[p] << ":" << play_depth_by_phase[p];
                any = true;
            }
        }
        if (!any) std::cout << " play_depth_by_phase=(uniform play_depth)";
    }
    std::cout << '\n';

    // Endgame/reverse seeding (--seed-file / --seed-frac). Validate the
    // complete counted JNNW before creating the output file: a bad catalogue
    // must fail closed without leaving a plausible-looking partial corpus.
    struct SeedPos { std::uint64_t bbs[4]; std::uint8_t stm; };
    std::vector<SeedPos> seeds;
    if (seed_path) {
        std::ifstream sf(seed_path, std::ios::binary | std::ios::ate);
        if (!sf) {
            std::cerr << "error: cannot open --seed-file " << seed_path << "\n";
            return 1;
        }
        const std::streamoff file_size = sf.tellg();
        if (file_size < 8) {
            std::cerr << "error: --seed-file " << seed_path
                      << " has a truncated JNNW header\n";
            return 1;
        }
        sf.seekg(0, std::ios::beg);
        char hdr[8];
        if (!sf.read(hdr, 8) || std::memcmp(hdr, "JNNW", 4) != 0) {
            std::cerr << "error: --seed-file " << seed_path << " is not JNNW\n";
            return 1;
        }
        std::uint32_t cnt = 0;
        std::memcpy(&cnt, hdr + 4, 4);
        constexpr std::uint64_t seed_record_bytes = 38;
        const std::uint64_t expected_size =
            std::uint64_t{8}
            + static_cast<std::uint64_t>(cnt) * seed_record_bytes;
        if (static_cast<std::uint64_t>(file_size) != expected_size) {
            std::cerr << "error: --seed-file " << seed_path
                      << " size/count mismatch: bytes=" << file_size
                      << " expected=" << expected_size
                      << " records=" << cnt << "\n";
            return 1;
        }
        seeds.reserve(cnt);
        for (std::uint32_t index = 0; index < cnt; ++index) {
            char rec[38];
            if (!sf.read(rec, sizeof(rec))) {
                std::cerr << "error: --seed-file " << seed_path
                          << " truncated at record " << index << "\n";
                return 1;
            }
            SeedPos sp;
            std::memcpy(sp.bbs, rec, 32);
            sp.stm = static_cast<std::uint8_t>(rec[32]);
            if (sp.stm > 1) {
                std::cerr << "error: --seed-file " << seed_path
                          << " invalid side-to-move at record " << index << "\n";
                return 1;
            }
            seeds.push_back(sp);
        }
        if (seed_frac > 0 && seeds.empty()) {
            std::cerr << "error: --seed-file " << seed_path
                      << " is empty while --seed-frac is positive\n";
            return 1;
        }
        std::cout << "seed-file: " << seeds.size()
                  << " positions, seed_frac=" << seed_frac << "%\n";
    }

    std::ofstream node_budget_log;
    if (node_budget_policy) {
        node_budget_log.open(node_budget_log_path);
        if (!node_budget_log) {
            std::cerr << "error: cannot open " << node_budget_log_path
                      << " for writing\n";
            return 1;
        }
    }

    std::ofstream f(out_path, std::ios::binary);
    if (!f) {
        std::cerr << "error: cannot open " << out_path << " for writing\n";
        return 1;
    }

    const char magic[4] = {'J', 'N', 'N', 'W'};
    f.write(magic, 4);
    std::uint32_t count_placeholder = 0;
    f.write(reinterpret_cast<const char*>(&count_placeholder), 4);

    // Optional aligned metadata, independent from JNNW so enabling either
    // sidecar never changes the corpus bytes.
    //   JSM1: (u64 game_id, u64 opening_id, u8 seeded), 17 bytes/record.
    //   JSM2: the JSM1 prefix followed by (u16 ply, u16 game_plies,
    //         u16 last_eps_ply, i8 game_result_white, u8 flags), 25 bytes/record.
    // IMPORTANT: game_result is WHITE POV while the aligned JNNW WDL is STM POV.
    // `opening_id` groups the two repetitions created by --pair-openings, which
    // lets the Python splitter keep colour/role pairs in the same holdout fold.
    std::ofstream sample_meta;
    if (sample_meta_path) {
        sample_meta.open(sample_meta_path, std::ios::binary);
        if (!sample_meta) {
            std::cerr << "error: cannot open " << sample_meta_path << " for writing\n";
            return 1;
        }
        const char meta_magic[4] = {'J', 'S', 'M', sample_meta_v2 ? '2' : '1'};
        sample_meta.write(meta_magic, 4);
        sample_meta.write(reinterpret_cast<const char*>(&count_placeholder), 4);
    }

    // Splitmix-style scrambling of the user-provided seed so two
    // shards launched with seeds 1 and 2 yield trajectories that are
    // statistically independent (close seeds + linear PRNG → barely
    // correlated streams which would waste compute).
    const std::uint64_t seed_value = (random_seed > 0)
        ? static_cast<std::uint64_t>(static_cast<std::uint32_t>(random_seed))
              * std::uint64_t{0x9E3779B97F4A7C15}
        : std::uint64_t{0x5eed5eed5eed5eed};
    if (node_budget_policy) {
        write_node_budget_manifest(
            node_budget_log, *node_budget_policy,
            random_seed > 0 ? static_cast<std::uint64_t>(random_seed) : 0,
            seed_value);
    }
    // Un seul flux par défaut (`rng` est un alias du flux legacy), quatre flux
    // indépendants sous --split-selfplay-rngs. Les usages sont routés par rôle
    // ci-dessous : `streams.opening()`, `.sampling()`, `.exploration()`,
    // `.role()`. En mode legacy les quatre renvoient le MÊME générateur, donc
    // la séquence historique est reproduite au bit près.
    jass::selfplay::SelfplayRngStreams streams(seed_value, split_selfplay_rngs);
    std::mt19937_64& rng = streams.opening();
    std::vector<std::size_t> seed_schedule;
    std::size_t seed_schedule_cursor = 0;
    if (seed_without_replacement) {
        seed_schedule.reserve(seeds.size());
        for (std::size_t index = 0; index < seeds.size(); ++index) {
            seed_schedule.push_back(index);
        }
        std::shuffle(seed_schedule.begin(), seed_schedule.end(), rng);
    }

    // Load the user-supplied NNUE if any; keep the unique_ptr alive
    // across the whole function so the Engine can borrow the pointer.
    std::unique_ptr<INetwork> custom_nnue;
    if (nnue_path) {
        // Accept either an NNUE .bin or a PJTW .pjtw pattern eval (so self-play
        // can be driven by the pattern champion, not just NNUE) — same dispatch
        // as --depth-at-movetime / --benchmark-scan-eval.
        const std::string p{nnue_path};
        const bool is_pjtw = p.size() >= 5
                          && p.compare(p.size() - 5, 5, ".pjtw") == 0;
        std::string err;
        custom_nnue = is_pjtw ? jass::load_eval_network(p, &err)
                              : load_network(nnue_path);
        if (!custom_nnue) {
            std::cerr << "error: cannot load eval weights from "
                      << nnue_path << (err.empty() ? "" : (" : " + err)) << "\n";
            return 1;
        }
    }
    Engine          e;
    e.use_book(false);
    if (custom_nnue) {
        e.set_nnue(custom_nnue.get());
    }

    // Sample buffer for the current game. Flushed with the resolved
    // WDL label once the game ends.
    struct Sample {
        std::uint64_t bbs[4];
        std::uint8_t  stm;
        std::int32_t  score;
        int           ply;     // ply at which this position was sampled (label-hygiene instrumentation)
    };
    std::vector<Sample> game_samples;
    game_samples.reserve(64);
    // Label-hygiene instrumentation (MEASURE-ONLY, ne change PAS l'emission) :
    //   #ply-cap  = parties terminees par la limite max_plies (issue=nulle par defaut => FIX #2)
    //   #post-eps = samples situes A/AVANT le dernier coup d'exploration eps (label contamine => FIX #1)
    long long stat_plycap_games = 0, stat_contaminated = 0, stat_total_samples = 0,
              stat_dropped = 0, stat_plycap_dropped = 0, stat_adjudicated = 0,
              stat_tb_relabel = 0, stat_label_score_searches = 0,
              stat_random_open_moves = 0, stat_play_plies = 0,
              stat_eps_events = 0, stat_eps_changed_best = 0,
              stat_games_with_eps = 0, stat_topk_ranked_plies = 0,
              stat_margin_singleton = 0,
              stat_topk_duplicates = 0;
    // Profondeur EFFECTIVE du classement, relevée depuis le helper plutôt que
    // recalculée ici : le certificat d'un job doit pouvoir asserter
    // `play_depth - 1` sur ce que le binaire a vraiment fait.
    int stat_topk_rank_depth = 0;
    // Distribution des issues EMISES. Le défaut de racine nulle d'avant
    // 9c1d1e8e a vidé trois corpus de leurs nulles (4,8 % au lieu de 20,3 %)
    // sans qu'aucun compteur ne bouge : tous portaient sur les labels écrits,
    // aucun sur leur distribution. Celui-ci sort dans CHAQUE log de génération,
    // donc aussi dans les templates trop anciens pour passer par le canari de
    // fusion. Ne bloque rien — il rend le symptôme impossible à manquer.
    long long stat_wdl_loss = 0, stat_wdl_draw = 0, stat_wdl_win = 0;
    long long stat_seeded_openings = 0, stat_standard_openings = 0;
    long long stat_seed_unique_used = 0;
    NodeBudgetRunStats node_budget_stats;

    // Table dédiée au classement top-k : la garder hors de celle du moteur
    // évite que la passe de classement pollue l'ordonnancement de la partie.
    // 64 MB rather than 16 : the ranking now runs at the play depth, and the
    // children of one root transpose into each other heavily, so the table is
    // what keeps the pass affordable.
    TranspositionTable rank_tt;
    if (explore_topk > 0) rank_tt.resize_mb(64);

    int generated  = 0;
    int game_count = 0;
    std::uint64_t opening_count = 0;

    // Load the egdb tablebase if JASS_EGDB_PATH is set (no-op otherwise). Used by
    // the terminate-at-TB rule below so won/lost endgames get their EXACT result
    // instead of stalling to the draw rule (~50% of decisive finals, job 0295).
    jass::egdb::ensure_initialised();

    while (generated < n) {
        e.new_game();
        ++opening_count;
        bool opening_from_seed = false;

        // Endgame seeding : start this game from a random seed position instead
        // of the FMJD start (then the random opening plies add diversity around it).
        if (!seeds.empty() && static_cast<int>(rng() % 100) < seed_frac) {
            opening_from_seed = true;
            std::size_t seed_index = 0;
            if (seed_without_replacement) {
                if (seed_schedule_cursor >= seed_schedule.size()) {
                    std::cerr << "error: --seed-without-replacement exhausted "
                              << seed_schedule.size() << " seeds after "
                              << stat_seeded_openings << " seeded openings before reaching "
                              << n << " output positions\n";
                    return 1;
                }
                seed_index = seed_schedule[seed_schedule_cursor++];
                ++stat_seed_unique_used;
            } else {
                seed_index = static_cast<std::size_t>(rng() % seeds.size());
            }
            const SeedPos& sp = seeds[seed_index];
            Position p{};
            p.set_side_to_move(sp.stm ? Color::Black : Color::White);
            for (Bitboard b = static_cast<Bitboard>(sp.bbs[0]); b; ) p.add_piece(pop_lsb(b), Piece::WhiteMan);
            for (Bitboard b = static_cast<Bitboard>(sp.bbs[1]); b; ) p.add_piece(pop_lsb(b), Piece::WhiteKing);
            for (Bitboard b = static_cast<Bitboard>(sp.bbs[2]); b; ) p.add_piece(pop_lsb(b), Piece::BlackMan);
            for (Bitboard b = static_cast<Bitboard>(sp.bbs[3]); b; ) p.add_piece(pop_lsb(b), Piece::BlackKing);
            e.set_position(p);
        }
        if (opening_from_seed) ++stat_seeded_openings;
        else                   ++stat_standard_openings;

        for (int i = 0; i < random_open_plies; ++i) {
            MoveList ml;
            generate_legal_moves(e.position(), ml);
            if (ml.empty()) break;
            e.apply_move(ml[rng() % ml.size()]);
            ++stat_random_open_moves;
        }

        // FIX#3 : jouer l'ouverture 2x (rep 0/1) avec la couleur punisher ECHANGEE => le biais
        // couleur/role s'annule dans la paire. reps=1 si --pair-openings absent (retro-compatible).
        const Position opening_pos = e.position();
        const int reps = pair_openings ? 2 : 1;
        for (int rep = 0; rep < reps && generated < n; ++rep) {
        ++game_count;   // compte les GAMES reellement jouees (2/paire sous --pair-openings) => denominateur ply-cap correct
        e.set_position(opening_pos);
        game_samples.clear();

        // Game outcome from the final position: +1 = white won, -1 = black
        // won, 0 = draw. Initialised to "draw" because the ply-cap exit
        // path treats unresolved games as drawn.
        int outcome_white = 0;
        bool game_ended_by_loss = false;
        int  last_eps_ply = -1;     // ply du dernier coup d'exploration eps de cette partie (instrumentation FIX #1)
        bool game_had_eps = false;   // au moins un tirage epsilon dans cette partie
        bool hit_ply_cap  = true;   // suppose ply-cap ; tout break (perte/TB/25-move/adjud) le remet a false
        bool game_adjudicated = false;
        int  adjud_counter = 0;     // FIX#2 : plies consecutifs ou l'avance materielle >= adjud_material
        int  game_play_plies = 0;
        // Asymmetric self-play (forcing-ext §4) : the "punisher" colour for THIS game plays the
        // punisher_params (e.g. ext_forcing=1, sees shots) ; the "victim" colour plays play_params
        // (blind → stumbles into shots). FIX#3 : si --pair-openings, punisher=white au rep 0, black au rep 1
        // (roles echanges sur l'ouverture identique) ; sinon random par partie (comportement historique).
        const bool punisher_is_white =
            pair_openings ? (rep == 0) : ((streams.role()() & 1u) != 0u);

        for (int ply = 0; ply < max_plies; ++ply) {
            MoveList ml;
            generate_legal_moves(e.position(), ml);
            if (ml.empty()) {
                // STM has no moves → STM loses.
                outcome_white = (e.position().side_to_move() == Color::White)
                              ? -1 : +1;
                game_ended_by_loss = true;
                hit_ply_cap = false;
                break;
            }
            // Terminate-at-TB: the moment the game reaches an egdb-resolved
            // endgame, end it with the EXACT result instead of playing on.
            // Playing it out stalls ~50% of won/lost finals to the draw rule and
            // mislabels them (job 0295) — this gives clean endgame labels (and the
            // transition samples already collected inherit the correct outcome).
            // egdb-exact only (probe() = Unknown without egdb / above max_pieces /
            // <3 pieces) — never the over-claiming in-memory tables.
            if (jass::egdb::available()) {
                const jass::EndgameResult tb = jass::egdb::probe(e.position());
                if (tb == jass::EndgameResult::WhiteWin) { outcome_white = +1; game_ended_by_loss = true; hit_ply_cap = false; break; }
                if (tb == jass::EndgameResult::BlackWin) { outcome_white = -1; game_ended_by_loss = true; hit_ply_cap = false; break; }
                if (tb == jass::EndgameResult::Draw)     { outcome_white =  0; game_ended_by_loss = false; hit_ply_cap = false; break; }
            }
            // FIX#2 : adjudication materielle conservatrice. Une avance NETTE (men + 3*kings) >= adjud_material
            // tenue adjud_hold_plies consecutifs => win (les parties gagnees qui piétinent jusqu'au ply-cap
            // sont sinon etiquetees "nulle" a tort : 27-31% mesure). JAMAIS par score d'eval (circularite).
            if (adjud_material > 0) {
                const Position& mp = e.position();
                const int white_mat = static_cast<int>(popcount(mp.white_men())) + 3 * static_cast<int>(popcount(mp.white_kings()));
                const int black_mat = static_cast<int>(popcount(mp.black_men())) + 3 * static_cast<int>(popcount(mp.black_kings()));
                const int net = white_mat - black_mat;
                if (net >= adjud_material || net <= -adjud_material) {
                    if (++adjud_counter >= adjud_hold_plies) {
                        outcome_white = (net > 0) ? +1 : -1;
                        game_ended_by_loss = true;   // resolu (decisif) — chemin de flush WDL standard
                        hit_ply_cap = false;
                        game_adjudicated = true;
                        ++stat_adjudicated;
                        break;
                    }
                } else {
                    adjud_counter = 0;   // avance perdue (recapture) => reset
                }
            }
            if (e.position().halfmove_clock() >= FIFTY_MOVE_PLIES) {
                // 25-move rule: declare a draw.
                hit_ply_cap = false;
                break;
            }

            // Sample roughly every fourth ply, while we still have budget
            // and the buffer isn't huge. When `quiet_only` is set, skip
            // tactical positions (where the side to move must capture) —
            // their `score` label is the eval of THIS position but the
            // search will immediately play out the forced capture chain,
            // so the label is systematically wrong by the value of the
            // pending tactics. Filtering these is the analog of
            // Stockfish nnue-pytorch's `ensure_quiet` flag, which fixed
            // their -700 ELO syndrome on the 10M d5 dataset.
            // generate_legal_moves returns ALL captures OR all quiet
            // moves (never a mix), so `ml[0].is_capture()` is the
            // single-check tactical-position signal.
            const bool position_quiet = !ml[0].is_capture();
            const bool selected_for_sample = (sample_initial && ply == 0)
                                          || ((streams.sampling()() & 3) == 0);
            const bool sample_now = selected_for_sample
                                 && generated + static_cast<int>(game_samples.size()) < n
                                 && (!quiet_only || position_quiet);
            if (sample_now) {
                const Position&    pos = e.position();
                // Phase-dependent LABEL depth : spend deeper search where the
                // linear eval is weakest (endgames), keep opening labels cheap.
                // Default (no spec) = eval_depth everywhere (back-compatible).
                const int phase_ovr = label_depth[phase_index_of(popcount(pos.occupied()))];
                const int this_label_depth = (phase_ovr > 0) ? phase_ovr : eval_depth;
                SearchResult label_result;
                if (!wdl_zero_score) {
                    SearchLimits lim;
                    lim.max_depth = this_label_depth;
                    lim.params    = label_params;   // gen-label slot: score only
                    lim.max_nodes = play_max_nodes; // deterministic bound (flat-eval safety)
                    label_result = e.search(lim);
                    ++stat_label_score_searches;
                }
                Sample s;
                s.bbs[0] = pos.white_men();
                s.bbs[1] = pos.white_kings();
                s.bbs[2] = pos.black_men();
                s.bbs[3] = pos.black_kings();
                s.stm    = (pos.side_to_move() == Color::White) ? 0 : 1;
                s.score  = wdl_zero_score ? 0 : static_cast<std::int32_t>(label_result.score);
                s.ply    = ply;
                game_samples.push_back(s);

                // L1 multi-extraction (Stockfish `gensfen`-style). Amortize
                // the depth-`eval_depth` search over multiple labels by
                // harvesting positions along the principal variation. By
                // negamax definition, the score at PV ply k from THAT
                // position's STM POV is (-1)^k * label_result.score, so we can attach
                // exact labels to extracted positions without re-searching.
                //
                // Caveats applied here:
                //   * stride 2 — adjacent PV positions are highly
                //     correlated (one ply apart), so we only harvest at
                //     even depths from the root.
                //   * min effective depth 8 — the position at PV ply k was
                //     effectively searched at depth (eval_depth - k); we
                //     stop harvesting once that drops below 8 to keep
                //     label quality comparable to the root sample.
                //   * quiet filter applied per-position (same as the root
                //     sample).
                //   * WDL is propagated from the eventual game outcome,
                //     same as the root sample. Stockfish gensfen does the
                //     same; the position itself isn't on the played
                //     trajectory but it's on the engine's best line, so
                //     WDL is a reasonable proxy. Documented limitation.
                if (!wdl_zero_score && pv_extract > 0 && !label_result.pv.empty()) {
                    constexpr int PV_STRIDE        = 2;
                    constexpr int PV_MIN_EFF_DEPTH = 8;
                    Position pv_pos = pos;
                    int      taken  = 0;
                    for (std::size_t k = 0;
                         k < label_result.pv.size() && taken < pv_extract;
                         ++k) {
                        pv_pos = pv_pos.after(label_result.pv[k]);
                        const int depth_from_root = static_cast<int>(k) + 1;
                        const int eff_depth = this_label_depth - depth_from_root;
                        if (eff_depth < PV_MIN_EFF_DEPTH) break;
                        if (depth_from_root % PV_STRIDE != 0) continue;
                        if (generated +
                            static_cast<int>(game_samples.size()) >= n) break;

                        MoveList pv_ml;
                        generate_legal_moves(pv_pos, pv_ml);
                        if (pv_ml.empty()) break;  // terminal — no label
                        const bool pv_quiet = !pv_ml[0].is_capture();
                        if (quiet_only && !pv_quiet) continue;

                        Sample ps;
                        ps.bbs[0] = pv_pos.white_men();
                        ps.bbs[1] = pv_pos.white_kings();
                        ps.bbs[2] = pv_pos.black_men();
                        ps.bbs[3] = pv_pos.black_kings();
                        ps.stm    = (pv_pos.side_to_move() == Color::White) ? 0 : 1;
                        ps.score  = (depth_from_root & 1)
                                      ? -static_cast<std::int32_t>(label_result.score)
                                      :  static_cast<std::int32_t>(label_result.score);
                        ps.ply    = ply;   // meme ply-racine (PV extraite du sample racine)
                        game_samples.push_back(ps);
                        ++taken;
                    }
                }
            }

            SearchLimits lim;
            // Phase-dependent PLAY depth : play endgames deeper so the resolved
            // WDL outcome is accurate (the loop trains on WDL — the corrected
            // endgame densification lever, cf jobs 0254/0261). Default (empty
            // spec) = uniform play_depth (back-compatible). Endgames are cheap
            // (few pieces) so the extra depth there costs little.
            const int phase_pd =
                play_depth_by_phase[phase_index_of(popcount(e.position().occupied()))];
            lim.max_depth = node_budget_policy
                ? MAX_PLY
                : ((phase_pd > 0) ? phase_pd : play_depth);
            // gen-play slot. In asymmetric mode the side-to-move uses punisher_params when it is the
            // game's punisher colour, else play_params (the blind "victim"). Non-asym = play_params.
            const bool stm_is_punisher =
                (e.position().side_to_move() == Color::White) == punisher_is_white;
            lim.params    = (asym_mode && stm_is_punisher) ? punisher_params : play_params;
            if (movetime_ms > 0) lim.movetime_ms = movetime_ms;
            const bool search_side_white =
                e.position().side_to_move() == Color::White;
            std::uint64_t sampled_node_budget = 0;
            std::uint64_t search_elapsed_us = 0;
            if (node_budget_policy) {
                sampled_node_budget = node_budget_policy->sample(
                    seed_value, static_cast<std::uint64_t>(game_count),
                    static_cast<std::uint32_t>(ply),
                    static_cast<std::uint8_t>(search_side_white ? 0 : 1));
                lim.max_nodes = sampled_node_budget;
                lim.node_limit_mode = NodeLimitMode::Exact;
            } else {
                // Historical deterministic safety cap. This remains a hybrid
                // depth+nodes guard and is intentionally not the new nodes mode.
                lim.max_nodes = play_max_nodes;
            }
            SearchResult r;
            if (node_budget_policy) {
                const auto search_started_at = std::chrono::steady_clock::now();
                r = e.search(lim);
                search_elapsed_us = static_cast<std::uint64_t>(
                    std::chrono::duration_cast<std::chrono::microseconds>(
                        std::chrono::steady_clock::now() - search_started_at).count());
            } else {
                r = e.search(lim);
            }
            ++stat_play_plies;
            // Epsilon-random exploration : with probability explore_eps%, play a
            // uniform-random legal move instead of the search best. Visits states
            // the greedy policy never reaches (off-policy μ widening) ; safe here
            // because the label is the eventual game outcome (MC return), not a
            // bootstrapped value, so the played-out result stays truthful.
            Move play_mv = r.best_move;
            // FIX#1 : eps effectif decroissant (confine l'exploration au debut de partie).
            //   D=0 => eps constant (legacy) ; D>0 => eps*max(0,1-ply/D), nul des ply>=D.
            //   Compare en millièmes pour garder la granularite de la decroissance.
            const double eps_frac = (explore_decay_plies > 0)
                ? explore_eps * std::max(0.0, 1.0 - static_cast<double>(ply) / explore_decay_plies)
                : static_cast<double>(explore_eps);
            if (eps_frac > 0.0 && !ml.empty()
                && static_cast<double>(streams.exploration()() % 100000)
                       < eps_frac * 1000.0) {
                // --explore-topk K : draw among the K best moves rather than
                // among all of them. A uniform draw over ~8-10 legal moves is a
                // blunder nine times out of ten, so it widens the state
                // distribution toward positions-after-a-mistake — states a
                // strong opponent never reaches, and not where the evaluation
                // margin is lost. Ranking first keeps the perturbation on
                // plausible lines, which is where resolution is missing.
                //
                // The root search returns only its best move, so the ranking is
                // a separate pass over the children: alpha-beta bounds from the
                // main search would order fail-low moves arbitrarily.
                //
                // The child is searched at play_depth-1, NOT at play_depth. A
                // root search at depth d evaluates each of its children with
                // d-1 plies; restarting a root search FROM the child at depth d
                // would give it one ply more than the policy ever had. Both of
                // this file's earlier versions were wrong here in opposite
                // directions — d-2 was one ply short, d was one ply long — and
                // the invariant now lives in one tested helper (PR 384).
                //
                // The helper also fixes two silent defects: the ranking search
                // received no repetition history, and semantically identical
                // moves (Move compares capture SETS, and draughts reaches the
                // same capture by several orders) could occupy more than one
                // top-k slot, quietly biasing the uniform draw toward one move.
                if (explore_topk > 0 && ml.size() > 1) {
                    const jass::selfplay::TopKChoice choice =
                        jass::selfplay::select_topk_exploration_move(
                            e, ml, lim, explore_topk, explore_margin,
                            rank_tt, streams.exploration());
                    play_mv = choice.move;
                    stat_topk_duplicates +=
                        static_cast<long long>(choice.duplicate_candidates);
                    if (choice.ranked) {
                        ++stat_topk_ranked_plies;
                        stat_topk_rank_depth = choice.child_search_depth;
                    }
                    if (choice.margin_singleton) ++stat_margin_singleton;
                } else {
                    play_mv = ml[streams.exploration()() % ml.size()];
                }
                ++stat_eps_events;
                game_had_eps = true;
                if (play_mv != r.best_move) ++stat_eps_changed_best;
                last_eps_ply = ply;   // dernier coup d'exploration de la partie (FIX#1 filtre + instrumentation)
            }
            if (node_budget_policy) {
                node_budget_stats.record(sampled_node_budget, r, search_elapsed_us);
                const double search_time_ms =
                    static_cast<double>(search_elapsed_us) / 1'000.0;
                const double nps = search_elapsed_us > 0
                    ? static_cast<double>(r.nodes) * 1'000'000.0
                        / static_cast<double>(search_elapsed_us)
                    : 0.0;
                node_budget_log << std::fixed << std::setprecision(3)
                    << "{\"event\":\"selfplay_search\""
                    << ",\"game_id\":" << game_count
                    << ",\"ply\":" << ply
                    << ",\"side_to_move\":\""
                    << (search_side_white ? "white" : "black") << "\""
                    << ",\"search_limit_type\":\"nodes\""
                    << ",\"nodes_budget\":" << sampled_node_budget
                    << ",\"nodes_used\":" << r.nodes
                    << ",\"effective_depth\":" << r.effective_depth
                    << ",\"completed_depth\":" << r.completed_depth
                    << ",\"search_time_ms\":" << search_time_ms
                    << ",\"nps\":" << nps
                    << ",\"aborted_iteration\":"
                    << (r.aborted_iteration ? "true" : "false")
                    << ",\"stop_reason\":\""
                    << search_stop_reason_name(r.stop_reason) << "\""
                    << ",\"search_best_move\":\""
                    << format_move(r.best_move) << "\""
                    << ",\"move_selected\":\""
                    << format_move(play_mv) << "\"}\n";
            }
            if (!e.apply_move(play_mv)) break;
            ++game_play_plies;
        }
        if (node_budget_policy) {
            node_budget_log << "{\"event\":\"selfplay_game\""
                            << ",\"game_id\":" << game_count
                            << ",\"plies\":" << game_play_plies
                            << ",\"result_white\":" << outcome_white
                            << ",\"resolved\":"
                            << (!hit_ply_cap ? "true" : "false")
                            << ",\"ply_cap\":"
                            << (hit_ply_cap ? "true" : "false") << "}\n";
        }
        if (game_had_eps) ++stat_games_with_eps;
        if (hit_ply_cap) ++stat_plycap_games;   // partie terminee par max_plies (issue=nulle par defaut)

        // A ply-cap is censoring, not evidence for a draw.  Legacy jobs retain
        // the historical label unless they opt in; L3-PURE enables this flag and
        // keeps playing new games until it has N eligible records.
        if (drop_plycap && hit_ply_cap) {
            stat_total_samples += static_cast<long long>(game_samples.size());
            stat_plycap_dropped += static_cast<long long>(game_samples.size());
            continue;
        }

        // Validate the extended sidecar before writing any record from this
        // game.  In particular, an unexpected apply_move() failure leaves the
        // last buffered sample at game_play_plies; emitting it would create a
        // JSM2 record that every reader must reject (ply >= game_plies).
        if (sample_meta_v2) {
            for (const Sample& s : game_samples) {
                if (s.ply < 0 || s.ply >= game_play_plies) {
                    std::cerr
                        << "error: refusing invalid JSM2 game context before write: "
                        << "game_id=" << game_count
                        << " sample_ply=" << s.ply
                        << " game_plies=" << game_play_plies
                        << " (required 0 <= ply < game_plies)\n";
                    return 1;
                }
            }
        }

        // Flush this game's samples with the resolved WDL label. WDL is
        // computed from each sample's STM perspective: +1 means "the side
        // to move at sample time eventually won".
        for (const Sample& s : game_samples) {
            int wdl = 0;
            bool sample_tb_relabelled = false;
            if (game_ended_by_loss) {
                const int sample_stm_sign = (s.stm == 0) ? +1 : -1;
                wdl = outcome_white * sample_stm_sign;
            }
            // FIX#4 : label EGDB EXACT par-sample (biais 0, autonome = notre propre TB). Si la position
            // du sample tombe dans la tablebase => on remplace le WDL-partie par la valeur VRAIE (STM-POV).
            // No-op si --tb-relabel absent ou EGDB indisponible => emission inchangee.
            if (tb_relabel && jass::egdb::available()) {
                Position sp{};
                sp.set_side_to_move(s.stm ? Color::Black : Color::White);
                for (Bitboard b = static_cast<Bitboard>(s.bbs[0]); b; ) sp.add_piece(pop_lsb(b), Piece::WhiteMan);
                for (Bitboard b = static_cast<Bitboard>(s.bbs[1]); b; ) sp.add_piece(pop_lsb(b), Piece::WhiteKing);
                for (Bitboard b = static_cast<Bitboard>(s.bbs[2]); b; ) sp.add_piece(pop_lsb(b), Piece::BlackMan);
                for (Bitboard b = static_cast<Bitboard>(s.bbs[3]); b; ) sp.add_piece(pop_lsb(b), Piece::BlackKing);
                const jass::EndgameResult tb = jass::egdb::probe(sp);
                if      (tb == jass::EndgameResult::WhiteWin) { wdl = (s.stm == 0) ? +1 : -1; sample_tb_relabelled = true; ++stat_tb_relabel; }
                else if (tb == jass::EndgameResult::BlackWin) { wdl = (s.stm == 0) ? -1 : +1; sample_tb_relabelled = true; ++stat_tb_relabel; }
                else if (tb == jass::EndgameResult::Draw)     { wdl = 0;                       sample_tb_relabelled = true; ++stat_tb_relabel; }
                // Unknown => on garde le wdl de la partie
            }
            const std::int8_t wdl_byte = static_cast<std::int8_t>(wdl);
            // ce sample est-il contamine par l'exploration ?
            //   sample.ply <= last_eps_ply => sa partie a deraille APRES lui par un coup eps => label biaise (FIX#1)
            const bool contaminated = (s.ply <= last_eps_ply);
            ++stat_total_samples;
            if (contaminated) ++stat_contaminated;
            // FIX#1 : si --drop-post-eps, on NE l'emet PAS (label pourri) — sinon emission inchangee (MEASURE-ONLY).
            if (drop_post_eps && contaminated) { ++stat_dropped; continue; }

            // Compté ici, au point d'écriture : c'est la distribution REELLEMENT
            // émise, après tous les filtres, pas celle qu'on croit produire.
            if      (wdl_byte < 0) ++stat_wdl_loss;
            else if (wdl_byte > 0) ++stat_wdl_win;
            else                   ++stat_wdl_draw;

            f.write(reinterpret_cast<const char*>(s.bbs), 32);
            f.write(reinterpret_cast<const char*>(&s.stm), 1);
            f.write(reinterpret_cast<const char*>(&s.score), 4);
            f.write(reinterpret_cast<const char*>(&wdl_byte), 1);
            if (sample_meta.is_open()) {
                const std::uint64_t game_id = static_cast<std::uint64_t>(game_count);
                const std::uint8_t seeded = opening_from_seed ? 1u : 0u;
                sample_meta.write(reinterpret_cast<const char*>(&game_id), 8);
                sample_meta.write(reinterpret_cast<const char*>(&opening_count), 8);
                sample_meta.write(reinterpret_cast<const char*>(&seeded), 1);
                if (sample_meta_v2) {
                    const std::uint16_t sample_ply = static_cast<std::uint16_t>(s.ply);
                    const std::uint16_t game_plies = static_cast<std::uint16_t>(game_play_plies);
                    const std::uint16_t last_eps = last_eps_ply < 0
                        ? std::uint16_t{0xFFFF}
                        : static_cast<std::uint16_t>(last_eps_ply);
                    // JSM2 game_result is WHITE POV {-1,0,+1}. This deliberately
                    // differs from JNNW's side-to-move POV WDL byte above.
                    const std::int8_t game_result = static_cast<std::int8_t>(outcome_white);
                    const std::uint8_t flags = static_cast<std::uint8_t>(
                          (hit_ply_cap ? 0x01u : 0u)
                        | (game_adjudicated ? 0x02u : 0u)
                        | (sample_tb_relabelled ? 0x04u : 0u));
                    sample_meta.write(reinterpret_cast<const char*>(&sample_ply), 2);
                    sample_meta.write(reinterpret_cast<const char*>(&game_plies), 2);
                    sample_meta.write(reinterpret_cast<const char*>(&last_eps), 2);
                    sample_meta.write(reinterpret_cast<const char*>(&game_result), 1);
                    sample_meta.write(reinterpret_cast<const char*>(&flags), 1);
                }
            }
            ++generated;
            if (generated >= n) break;
        }
        }   // fin boucle rep (FIX#3 : rep 0/1 sur l'ouverture identique, roles echanges)

        if ((game_count % 50) == 0) {
            std::cout << "  played " << game_count << " games, "
                      << generated << " / " << n << " positions\n";
        }
    }

    f.seekp(4, std::ios::beg);
    const std::uint32_t count32 = static_cast<std::uint32_t>(generated);
    f.write(reinterpret_cast<const char*>(&count32), 4);
    f.close();
    if (sample_meta.is_open()) {
        sample_meta.seekp(4, std::ios::beg);
        sample_meta.write(reinterpret_cast<const char*>(&count32), 4);
        sample_meta.close();
    }

    std::cout << "wrote " << generated << " WDL records to " << out_path << "\n";
    // === LABEL-HYGIENE STATS (MEASURE-ONLY, briefing §7.0) ===
    {
        const double pc  = game_count > 0 ? 100.0 * static_cast<double>(stat_plycap_games) / game_count : 0.0;
        const double con = stat_total_samples > 0 ? 100.0 * static_cast<double>(stat_contaminated) / stat_total_samples : 0.0;
        const long long wdl_n = stat_wdl_loss + stat_wdl_draw + stat_wdl_win;
        const auto pct = [wdl_n](long long k) {
            return wdl_n > 0 ? 100.0 * static_cast<double>(k) / static_cast<double>(wdl_n) : 0.0;
        };
        std::cout << "WDLDIST records=" << wdl_n
                  << "  loss=" << stat_wdl_loss << " (" << pct(stat_wdl_loss) << "%)"
                  << "  draw=" << stat_wdl_draw << " (" << pct(stat_wdl_draw) << "%)"
                  << "  win="  << stat_wdl_win  << " (" << pct(stat_wdl_win)  << "%)\n";
        std::cout << "LABELHYG plycap_games=" << stat_plycap_games << "/" << game_count
                  << " (" << pc << "%)  contaminated_samples=" << stat_contaminated << "/" << stat_total_samples
                  << " (" << con << "%)  dropped_post_eps=" << stat_dropped
                  << "  dropped_plycap_samples=" << stat_plycap_dropped
                  << "  adjudicated=" << stat_adjudicated
                  << "  tb_relabel=" << stat_tb_relabel
                  << "  label_score_searches=" << stat_label_score_searches
                  << " (drop_post_eps=" << (drop_post_eps ? "on" : "off")
                  << " drop_plycap=" << (drop_plycap ? "on" : "off")
                  << " decay_plies=" << explore_decay_plies
                  << " adjud_material=" << adjud_material << " hold=" << adjud_hold_plies
                  << " pair_openings=" << (pair_openings ? "on" : "off")
                  << " tb_relabel=" << (tb_relabel ? "on" : "off") << ")\n";
    }
    // Stable machine-readable counters for L3 exploration DoE aggregation.
    // Counts, rather than only configured percentages, prove that the policy
    // perturbation actually fired and quantify its realised dose.
    std::cout << "EXPLORATION"
              << " random_open_plies=" << random_open_plies
              << " explore_eps=" << explore_eps
              << " explore_topk=" << explore_topk
              << " explore_margin=" << explore_margin
              << " topk_ranked_plies=" << stat_topk_ranked_plies
              << " margin_singleton_plies=" << stat_margin_singleton
              << " topk_duplicate_candidates=" << stat_topk_duplicates
              << " topk_rank_depth=" << stat_topk_rank_depth
              << " split_selfplay_rngs=" << (split_selfplay_rngs ? 1 : 0)
              << " decay_plies=" << explore_decay_plies
              << " openings=" << opening_count
              << " seeded_openings=" << stat_seeded_openings
              << " standard_openings=" << stat_standard_openings
              << " seed_catalogue_positions=" << seeds.size()
              << " seed_frac=" << seed_frac
              << " seed_without_replacement=" << (seed_without_replacement ? 1 : 0)
              << " seed_unique_used=" << (seed_without_replacement ? stat_seed_unique_used : -1)
              << " seed_reuses=" << (seed_without_replacement ? 0 : -1)
              << " games=" << game_count
              << " random_open_moves=" << stat_random_open_moves
              << " play_plies=" << stat_play_plies
              << " eps_events=" << stat_eps_events
              << " eps_changed_best=" << stat_eps_changed_best
              << " games_with_eps=" << stat_games_with_eps << "\n";
    if (node_budget_policy) {
        write_node_budget_summary(node_budget_log, node_budget_stats);
        write_node_budget_summary(std::cout, node_budget_stats);
        node_budget_log.flush();
        if (!node_budget_log) {
            std::cerr << "error: failed while writing " << node_budget_log_path
                      << '\n';
            return 1;
        }
    }
    return 0;
}

// -----------------------------------------------------------------------------
// --gen-tdleaf : self-play piloté par un PATTERN, émettant par coup la
// position FEUILLE de la PV de recherche + sa valeur (white-POV), groupée
// par partie, pour l'entraînement TD-leaf(λ) du pattern (linéaire).
// Sorties :
//   <out>        JNNW des positions feuilles (score = V_leaf white-POV,
//                wdl = result+1 ∈ {0,1,2})
//   <out>.games  une ligne par partie : "<n_records> <result>" (result ∈
//                {-1,0,1} white-POV)
// Le côté Python (tools/td_leaf_targets.py) calcule les cibles λ-return
// depuis les séquences de valeurs par partie, puis re-fit via train.py.
// -----------------------------------------------------------------------------
int run_gen_tdleaf_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --gen-tdleaf <weights.pjtw|v3> [n_games=2000] "
                     "[depth=8] [out=tdleaf.jnnw] [max_plies=200] [seed=1] "
                     "[movetime_ms=0] [search_spec]\n"
                     "  Loads any eval (pattern v1/v2 or Scan v3). With "
                     "movetime_ms>0 the budget is wall-time (depth becomes a "
                     "cap). search_spec enables the 1b search bricks during "
                     "generation (search-aware TD-leaf).\n";
        return 1;
    }
    const char* weights_path = argv[2];
    const int   n_games   = (argc > 3) ? parse_int_or(argv[3], 2000) : 2000;
    const int   depth     = (argc > 4) ? parse_int_or(argv[4], 8)    : 8;
    const char* out_path  = (argc > 5) ? argv[5] : "tdleaf.jnnw";
    const int   max_plies = (argc > 6) ? parse_int_or(argv[6], 200)  : 200;
    const std::uint64_t seed = (argc > 7)
        ? static_cast<std::uint64_t>(parse_int_or(argv[7], 1)) : 1ULL;
    const int   movetime_ms = (argc > 8) ? parse_int_or(argv[8], 0) : 0;
    const char* search_spec = (argc > 9) ? argv[9] : "";
    const SearchParams gen_params = jass::parse_search_params(search_spec);

    std::string err;
    auto pjn = jass::load_eval_network(weights_path, &err);
    if (!pjn) {
        std::cerr << "error: cannot load eval from " << weights_path
                  << " : " << err << "\n";
        return 1;
    }

    std::ofstream f(out_path, std::ios::binary);
    std::ofstream g(std::string(out_path) + ".games");
    if (!f || !g) { std::cerr << "error: cannot open output\n"; return 1; }
    const char magic[4] = {'J', 'N', 'N', 'W'};
    f.write(magic, 4);
    std::uint32_t count_placeholder = 0;
    f.write(reinterpret_cast<const char*>(&count_placeholder), 4);

    std::mt19937_64 rng(seed ? seed : 1ULL);
    std::uint32_t total_records = 0;

    struct Leaf { std::uint64_t bbs[4]; std::uint8_t stm; std::int32_t v_white; };

    for (int game = 0; game < n_games; ++game) {
        Engine e;
        e.use_book(false);
        e.new_game();
        for (int i = 0; i < 4; ++i) {           // random opening plies
            MoveList ml;
            generate_legal_moves(e.position(), ml);
            if (ml.empty()) break;
            e.apply_move(ml[rng() % ml.size()]);
        }

        std::vector<Leaf> leaves;
        int  result    = 0;                     // white-POV: +1 / 0 / -1
        int  halfmove  = 0;                     // 50-move (irreversible) counter
        bool terminated = false;

        for (int ply = 0; ply < max_plies; ++ply) {
            MoveList ml;
            generate_legal_moves(e.position(), ml);
            if (ml.empty()) {                   // side to move has no move → loses
                result = (e.position().side_to_move() == Color::White) ? -1 : +1;
                terminated = true; break;
            }
            if (halfmove >= FIFTY_MOVE_PLIES) { result = 0; terminated = true; break; }

            SearchLimits lim;
            lim.max_depth   = depth;
            lim.movetime_ms = movetime_ms;
            lim.nnue        = pjn.get();
            lim.params      = gen_params;
            const SearchResult r = e.search(lim);

            // Walk the PV to the leaf the eval was effectively read at.
            Position leaf = e.position();
            for (const auto& m : r.pv) leaf = leaf.after(m);
            const bool white_to_move = (e.position().side_to_move() == Color::White);
            Leaf L;
            L.bbs[0] = leaf.white_men();  L.bbs[1] = leaf.white_kings();
            L.bbs[2] = leaf.black_men();  L.bbs[3] = leaf.black_kings();
            L.stm     = (leaf.side_to_move() == Color::White) ? 0 : 1;
            L.v_white = static_cast<std::int32_t>(white_to_move ? r.score : -r.score);
            leaves.push_back(L);

            const bool is_capture = r.best_move.is_capture();
            if (!e.apply_move(r.best_move)) { terminated = true; break; }
            halfmove = is_capture ? 0 : halfmove + 1;
        }
        if (!terminated) result = 0;            // ply cap → draw

        for (const auto& L : leaves) {
            f.write(reinterpret_cast<const char*>(L.bbs), 32);
            f.write(reinterpret_cast<const char*>(&L.stm), 1);
            f.write(reinterpret_cast<const char*>(&L.v_white), 4);
            const std::uint8_t wdl = static_cast<std::uint8_t>(result + 1);
            f.write(reinterpret_cast<const char*>(&wdl), 1);
        }
        total_records += static_cast<std::uint32_t>(leaves.size());
        g << leaves.size() << ' ' << result << '\n';

        if ((game + 1) % 100 == 0)
            std::cout << "  " << (game + 1) << "/" << n_games << " games, "
                      << total_records << " leaf records\n";
    }

    f.seekp(4, std::ios::beg);
    f.write(reinterpret_cast<const char*>(&total_records), 4);
    f.close();
    std::cout << "wrote " << total_records << " leaf records to " << out_path
              << " (+ " << out_path << ".games index)\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --rewrite-scores-with-nnue: read a JNNW dataset and write a new one with
// the `score` field replaced by `nnue.evaluate(pos)` from a user-supplied
// network. The bitboards / STM / WDL fields are passed through unchanged.
//
// Used for G2 of docs/archives/SCAN_METHODOLOGY_GAP.md (knowledge distillation):
// take the depth-20 self-play 1M dataset (noisy score labels from search)
// and rewrite it with v7's outputs as labels (a network that's known to
// generalise). If a pattern net trained on these cleaner labels still
// flat-lines, the limit is the pattern architecture itself, not label
// noise.
// -----------------------------------------------------------------------------
int run_rewrite_scores_with_nnue_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --rewrite-scores-with-nnue "
                     "<input.jnnw> <output.jnnw> --nnue PATH\n";
        return 1;
    }
    const char* in_path  = argv[2];
    const char* out_path = argv[3];
    const char* nnue_path = nullptr;
    for (int i = 4; i < argc; ++i) {
        if (std::string_view{argv[i]} == "--nnue" && i + 1 < argc) {
            nnue_path = argv[++i];
        }
    }
    if (!nnue_path) {
        std::cerr << "error: --nnue PATH is required\n";
        return 1;
    }
    // Reject in_path == out_path: ofstream defaults to ios::trunc and would
    // wipe the input file before the read loop drains it. Path comparison
    // is textual (good enough for the runner; symlinks aren't expected).
    if (std::string_view{in_path} == std::string_view{out_path}) {
        std::cerr << "error: input and output paths are identical ("
                  << in_path << "); refusing to truncate the input\n";
        return 1;
    }
    // Accept either an NNUE .bin or a PJTW .pjtw pattern eval (so the static
    // strength proxy can score pattern evals too), same dispatch as
    // --rewrite-scores-with-search / --benchmark-scan-eval.
    const std::string np{nnue_path};
    const bool np_is_pjtw = np.size() >= 5 && np.compare(np.size() - 5, 5, ".pjtw") == 0;
    std::string np_err;
    std::unique_ptr<INetwork> nnue = np_is_pjtw ? jass::load_eval_network(np, &np_err)
                                                : load_network(nnue_path);
    if (!nnue) {
        std::cerr << "error: cannot load eval from " << nnue_path
                  << (np_err.empty() ? "" : (" : " + np_err)) << "\n";
        return 1;
    }

    std::ifstream in(in_path, std::ios::binary);
    if (!in) {
        std::cerr << "error: cannot open " << in_path << "\n";
        return 1;
    }

    // Pre-flight: derive the expected record count from the file size so
    // we can reject a header-count that doesn't match the actual content
    // BEFORE we've opened (and would have truncated) the output file.
    in.seekg(0, std::ios::end);
    const std::streampos file_end = in.tellg();
    in.seekg(0, std::ios::beg);
    if (file_end < std::streampos{8}) {
        std::cerr << "error: " << in_path << " too small for a JNNW header\n";
        return 1;
    }

    char magic[4]{};
    in.read(magic, 4);
    if (!in || std::string_view{magic, 4} != "JNNW") {
        std::cerr << "error: " << in_path << " not a JNNW file\n";
        return 1;
    }
    std::uint32_t count = 0;
    in.read(reinterpret_cast<char*>(&count), 4);
    if (!in) {
        std::cerr << "error: cannot read JNNW header\n";
        return 1;
    }
    constexpr std::size_t RECORD_SZ = 38;
    const std::size_t body_bytes  = static_cast<std::size_t>(file_end) - 8;
    if (body_bytes % RECORD_SZ != 0) {
        std::cerr << "error: " << in_path << " body size " << body_bytes
                  << " is not a multiple of " << RECORD_SZ << " bytes\n";
        return 1;
    }
    const std::size_t expected = body_bytes / RECORD_SZ;
    if (count != expected) {
        std::cerr << "error: header count " << count
                  << " disagrees with file size (" << expected
                  << " records based on " << body_bytes << " bytes)\n";
        return 1;
    }

    std::ofstream out(out_path, std::ios::binary);
    if (!out) {
        std::cerr << "error: cannot open " << out_path << " for writing\n";
        return 1;
    }
    out.write("JNNW", 4);
    out.write(reinterpret_cast<const char*>(&count), 4);

    std::cout << "rewriting " << count << " records: " << in_path
              << " → " << out_path << " (labeller: " << nnue_path << ")\n";

    // Read/write one record at a time as a fixed-size buffer; that way a
    // truncated tail is detected BEFORE any of the typed fields are
    // consumed (avoids using a partially-initialised stm / score / wdl).
    char record[RECORD_SZ];
    Position pos;
    for (std::uint32_t i = 0; i < count; ++i) {
        in.read(record, RECORD_SZ);
        if (in.gcount() != static_cast<std::streamsize>(RECORD_SZ)) {
            std::cerr << "error: short read at record " << i
                      << " (got " << in.gcount() << " of " << RECORD_SZ
                      << " bytes)\n";
            return 1;
        }
        std::uint64_t bbs[4];
        std::uint8_t  stm_byte;
        std::int8_t   wdl;
        std::memcpy(bbs,       record,      32);
        std::memcpy(&stm_byte, record + 32,  1);
        // record + 33 .. + 36: old int32 score, discarded — we overwrite
        // it in-place below before writing the record back out.
        std::memcpy(&wdl,      record + 37,  1);

        // Validate the record before reconstructing the Position. Any of
        // these would silently produce a board different from what the
        // file claims (and what would be re-emitted unchanged).
        if (stm_byte > 1) {
            std::cerr << "error: record " << i << " has invalid stm byte "
                      << static_cast<int>(stm_byte) << " (expected 0 or 1)\n";
            return 1;
        }
        const Bitboard all_pieces = bbs[0] | bbs[1] | bbs[2] | bbs[3];
        if ((all_pieces & ~PLAYABLE_BB) != 0) {
            std::cerr << "error: record " << i
                      << " has bits set outside the 50 playable squares\n";
            return 1;
        }
        if (((bbs[0] & bbs[1]) | (bbs[0] & bbs[2]) | (bbs[0] & bbs[3])
           | (bbs[1] & bbs[2]) | (bbs[1] & bbs[3]) | (bbs[2] & bbs[3])) != 0) {
            std::cerr << "error: record " << i
                      << " has overlapping bits across colour/type planes\n";
            return 1;
        }

        pos = Position{};
        pos.set_side_to_move(stm_byte == 0 ? Color::White : Color::Black);
        for (Bitboard b = bbs[0]; b; ) pos.add_piece(pop_lsb(b), Piece::WhiteMan);
        for (Bitboard b = bbs[1]; b; ) pos.add_piece(pop_lsb(b), Piece::WhiteKing);
        for (Bitboard b = bbs[2]; b; ) pos.add_piece(pop_lsb(b), Piece::BlackMan);
        for (Bitboard b = bbs[3]; b; ) pos.add_piece(pop_lsb(b), Piece::BlackKing);

        const std::int32_t new_score = static_cast<std::int32_t>(nnue->evaluate(pos));
        std::memcpy(record + 33, &new_score, 4);
        // wdl is already in record + 37; bbs and stm preserved at the
        // top of the buffer. Single write of the rewritten record.
        out.write(record, RECORD_SZ);
        if ((i + 1) % 100000 == 0) {
            std::cout << "  " << (i + 1) << " / " << count << " records\n";
        }
    }
    std::cout << "wrote " << count << " records (" << RECORD_SZ
              << " B each) to " << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --rewrite-scores-with-search: like --rewrite-scores-with-nnue, but the new
// `score` is the result of a depth-D alpha-beta SEARCH driven by a user-supplied
// eval (pattern .pjtw or NNUE .bin), not that eval in STATIC mode. A depth-D
// search is stronger than the eval it uses, so training a fresh eval on these
// labels pulls it toward the search's strength — the teacher-free bootstrap
// step (eval <- search(eval)), with no external engine. The score is the
// STM-POV search score, same convention as --gen-data.
//
// Supports --start/--count so the (per-position search) work can be sharded
// across cores: each shard writes a standalone JNNW with `count` records;
// concatenate the bodies and fix the header count (cf. job 0196's merge).
//
//   jass --rewrite-scores-with-search <input.jnnw> <output.jnnw> --nnue PATH
//        [--depth D=12] [--start S=0] [--count C]
// -----------------------------------------------------------------------------
int run_rewrite_scores_with_search_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --rewrite-scores-with-search "
                     "<input.jnnw> <output.jnnw> --nnue PATH "
                     "[--depth D] [--start S] [--count C]\n";
        return 1;
    }
    const char* in_path   = argv[2];
    const char* out_path  = argv[3];
    const char* eval_path = nullptr;
    int depth = 12;
    int start = 0;
    int want_count = -1;            // -1 = to end of file
    for (int i = 4; i < argc; ++i) {
        const std::string_view a{argv[i]};
        if      (a == "--nnue"  && i + 1 < argc) eval_path  = argv[++i];
        else if (a == "--depth" && i + 1 < argc) depth      = parse_int_or(argv[++i], depth);
        else if (a == "--start" && i + 1 < argc) start      = parse_int_or(argv[++i], 0);
        else if (a == "--count" && i + 1 < argc) want_count = parse_int_or(argv[++i], -1);
    }
    if (!eval_path) { std::cerr << "error: --nnue PATH is required\n"; return 1; }
    if (depth < 1)  { std::cerr << "error: --depth must be >= 1\n";    return 1; }
    if (start < 0)  { std::cerr << "error: --start must be >= 0\n";    return 1; }
    if (std::string_view{in_path} == std::string_view{out_path}) {
        std::cerr << "error: input and output paths are identical ("
                  << in_path << "); refusing to truncate the input\n";
        return 1;
    }

    // Accept either a PJTW pattern eval or an NNUE .bin — same dispatch as
    // --benchmark-scan-eval / the self-play generator.
    const std::string ep{eval_path};
    const bool is_pjtw = ep.size() >= 5 && ep.compare(ep.size() - 5, 5, ".pjtw") == 0;
    std::string err;
    std::unique_ptr<INetwork> eval = is_pjtw ? jass::load_eval_network(ep, &err)
                                             : load_network(eval_path);
    if (!eval) {
        std::cerr << "error: cannot load eval from " << eval_path
                  << (err.empty() ? "" : (" : " + err)) << "\n";
        return 1;
    }

    std::ifstream in(in_path, std::ios::binary);
    if (!in) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }
    in.seekg(0, std::ios::end);
    const std::streampos file_end = in.tellg();
    in.seekg(0, std::ios::beg);
    if (file_end < std::streampos{8}) {
        std::cerr << "error: " << in_path << " too small for a JNNW header\n";
        return 1;
    }
    char magic[4]{};
    in.read(magic, 4);
    if (!in || std::string_view{magic, 4} != "JNNW") {
        std::cerr << "error: " << in_path << " not a JNNW file\n";
        return 1;
    }
    std::uint32_t header_count = 0;
    in.read(reinterpret_cast<char*>(&header_count), 4);
    if (!in) { std::cerr << "error: cannot read JNNW header\n"; return 1; }
    constexpr std::size_t RECORD_SZ = 38;
    const std::size_t body_bytes = static_cast<std::size_t>(file_end) - 8;
    if (body_bytes % RECORD_SZ != 0) {
        std::cerr << "error: " << in_path << " body size " << body_bytes
                  << " is not a multiple of " << RECORD_SZ << " bytes\n";
        return 1;
    }
    const std::size_t total = body_bytes / RECORD_SZ;
    if (header_count != total) {
        std::cerr << "error: header count " << header_count
                  << " disagrees with file size (" << total << " records)\n";
        return 1;
    }
    if (static_cast<std::size_t>(start) > total) {
        std::cerr << "error: --start " << start << " exceeds record count "
                  << total << "\n";
        return 1;
    }
    const std::size_t remaining = total - static_cast<std::size_t>(start);
    const std::size_t count = (want_count < 0)
        ? remaining
        : std::min<std::size_t>(remaining, static_cast<std::size_t>(want_count));

    std::ofstream out(out_path, std::ios::binary);
    if (!out) { std::cerr << "error: cannot open " << out_path << " for writing\n"; return 1; }
    out.write("JNNW", 4);
    const std::uint32_t out_count = static_cast<std::uint32_t>(count);
    out.write(reinterpret_cast<const char*>(&out_count), 4);
    in.seekg(static_cast<std::streamoff>(8 + static_cast<std::size_t>(start) * RECORD_SZ),
             std::ios::beg);

    Engine e;
    e.use_book(false);
    e.set_nnue(eval.get());
    SearchLimits lim;
    lim.max_depth = depth;

    std::cout << "rewrite-search: " << count << " records ["
              << start << ".." << (static_cast<std::size_t>(start) + count)
              << ") depth=" << depth << "  " << in_path << " → " << out_path
              << " (eval " << eval_path << ")\n" << std::flush;

    char record[RECORD_SZ];
    Position pos;
    for (std::size_t i = 0; i < count; ++i) {
        in.read(record, RECORD_SZ);
        if (in.gcount() != static_cast<std::streamsize>(RECORD_SZ)) {
            std::cerr << "error: short read at record " << (start + i) << "\n";
            return 1;
        }
        std::uint64_t bbs[4];
        std::uint8_t  stm_byte;
        std::memcpy(bbs,       record,      32);
        std::memcpy(&stm_byte, record + 32,  1);
        // record + 33..36 (old score) is overwritten below; record + 37 (wdl)
        // is preserved untouched in the buffer.
        if (stm_byte > 1) {
            std::cerr << "error: record " << (start + i) << " has invalid stm byte "
                      << static_cast<int>(stm_byte) << "\n";
            return 1;
        }
        const Bitboard all_pieces = bbs[0] | bbs[1] | bbs[2] | bbs[3];
        if ((all_pieces & ~PLAYABLE_BB) != 0) {
            std::cerr << "error: record " << (start + i)
                      << " has bits set outside the 50 playable squares\n";
            return 1;
        }
        if (((bbs[0] & bbs[1]) | (bbs[0] & bbs[2]) | (bbs[0] & bbs[3])
           | (bbs[1] & bbs[2]) | (bbs[1] & bbs[3]) | (bbs[2] & bbs[3])) != 0) {
            std::cerr << "error: record " << (start + i)
                      << " has overlapping bits across colour/type planes\n";
            return 1;
        }

        pos = Position{};
        pos.set_side_to_move(stm_byte == 0 ? Color::White : Color::Black);
        for (Bitboard b = bbs[0]; b; ) pos.add_piece(pop_lsb(b), Piece::WhiteMan);
        for (Bitboard b = bbs[1]; b; ) pos.add_piece(pop_lsb(b), Piece::WhiteKing);
        for (Bitboard b = bbs[2]; b; ) pos.add_piece(pop_lsb(b), Piece::BlackMan);
        for (Bitboard b = bbs[3]; b; ) pos.add_piece(pop_lsb(b), Piece::BlackKing);

        e.set_position(pos);
        const SearchResult r = e.search(lim);
        const std::int32_t new_score = static_cast<std::int32_t>(r.score);
        std::memcpy(record + 33, &new_score, 4);
        out.write(record, RECORD_SZ);
        if ((i + 1) % 20000 == 0) {
            std::cout << "  " << (i + 1) << " / " << count << " records\n" << std::flush;
        }
    }
    std::cout << "wrote " << count << " records (" << RECORD_SZ
              << " B each) to " << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --dump-features: read a JNNW dataset and write, per position, a small set
// of features the men-only pattern is BLIND to, for fit-check diagnostics :
//   f0 = black mobility   (legal moves with Black to move)
//   f1 = white mobility   (legal moves with White to move)
//   f2 = black L/R balance (black_men left − right, col_of<5 = left)
//   f3 = white L/R balance
// Output format : "FEAT"(4) + count(4) + K(4=#features) + count×K float32.
// Used by pattern_jass/tools/train.py --features-file to test whether
// DYNAMIC (mobility) / global (balance) info explains the Scan−handcrafted
// residual that static men-patterns cannot fit.
// -----------------------------------------------------------------------------
int run_dump_features_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --dump-features <in.jnnw> <out.feat>\n";
        return 1;
    }
    const char* in_path  = argv[2];
    const char* out_path = argv[3];
    std::ifstream in(in_path, std::ios::binary);
    if (!in) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }
    char magic[4]; in.read(magic, 4);
    if (!in || std::string_view{magic, 4} != "JNNW") {
        std::cerr << "error: " << in_path << " not a JNNW file\n"; return 1;
    }
    std::uint32_t count = 0;
    in.read(reinterpret_cast<char*>(&count), 4);
    if (!in) { std::cerr << "error: cannot read header\n"; return 1; }

    std::ofstream out(out_path, std::ios::binary);
    if (!out) { std::cerr << "error: cannot open " << out_path << "\n"; return 1; }
    const std::uint32_t K = 4;
    out.write("FEAT", 4);
    out.write(reinterpret_cast<const char*>(&count), 4);
    out.write(reinterpret_cast<const char*>(&K), 4);

    constexpr std::size_t RECORD_SZ = 38;
    char record[RECORD_SZ];
    for (std::uint32_t i = 0; i < count; ++i) {
        in.read(record, RECORD_SZ);
        if (in.gcount() != static_cast<std::streamsize>(RECORD_SZ)) {
            std::cerr << "error: short read at record " << i << "\n"; return 1;
        }
        std::uint64_t bbs[4];
        std::memcpy(bbs, record, 32);

        auto build = [&](Color stm) {
            Position p{};
            p.set_side_to_move(stm);
            for (Bitboard b = bbs[0]; b; ) p.add_piece(pop_lsb(b), Piece::WhiteMan);
            for (Bitboard b = bbs[1]; b; ) p.add_piece(pop_lsb(b), Piece::WhiteKing);
            for (Bitboard b = bbs[2]; b; ) p.add_piece(pop_lsb(b), Piece::BlackMan);
            for (Bitboard b = bbs[3]; b; ) p.add_piece(pop_lsb(b), Piece::BlackKing);
            return p;
        };
        MoveList ml_b, ml_w;
        generate_legal_moves(build(Color::Black), ml_b);
        generate_legal_moves(build(Color::White), ml_w);

        auto lr_balance = [](Bitboard men) {
            int left = 0, right = 0;
            for (Bitboard b = men; b; ) {
                const Square s = pop_lsb(b);
                (col_of(s) < 5 ? left : right) += 1;
            }
            return static_cast<float>(left - right);
        };
        const float feats[4] = {
            static_cast<float>(ml_b.size()),
            static_cast<float>(ml_w.size()),
            lr_balance(bbs[2]),   // black men
            lr_balance(bbs[0]),   // white men
        };
        out.write(reinterpret_cast<const char*>(feats), sizeof(feats));
    }
    std::cout << "wrote " << count << " × " << K << " features to " << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --perft <depth> [fen] : move-generation correctness + speed baseline. Counts
// the leaf nodes of the legal-move tree to `depth` (the standard draughts
// "perft"). This is the GOLDEN REFERENCE for the planned movegen rewrite : any
// faster implementation must reproduce these counts bit-for-bit. Also prints
// nodes/s as the movegen+make throughput baseline. Default FEN = FMJD start.
// Known 10x10 international values from the start : 9, 81, 658, 4265, 27117,
// 167140, 1049442, 6483961, 41022423.
// -----------------------------------------------------------------------------
static std::uint64_t perft(const Position& pos, int depth) {
    MoveList ml;
    generate_legal_moves(pos, ml);
    if (depth <= 1) return ml.size();
    std::uint64_t nodes = 0;
    for (const auto& m : ml) nodes += perft(pos.after(m), depth - 1);
    return nodes;
}

int run_perft_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --perft <depth> [fen]\n";
        return 1;
    }
    const int depth = parse_int_or(argv[2], 1);
    const std::string fen = (argc > 3) ? argv[3] : "W:W31-50:B1-20";
    auto pos = Position::from_fen(fen);
    if (!pos) { std::cerr << "error: bad FEN '" << fen << "'\n"; return 1; }
    using clock = std::chrono::steady_clock;
    for (int d = 1; d <= depth; ++d) {
        const auto t0 = clock::now();
        const std::uint64_t n = perft(*pos, d);
        const auto t1 = clock::now();
        const double s = std::chrono::duration<double>(t1 - t0).count();
        std::cout << "perft(" << d << ") = " << n
                  << "   " << (s > 0 ? static_cast<std::uint64_t>(n / s) : 0)
                  << " nodes/s  (" << s << "s)\n";
    }
    return 0;
}

// -----------------------------------------------------------------------------
// --dump-legal <fen-in> <out> : batch legal-move emitter. Reads one Hub FEN per
// input line and writes, 1:1 by line order, that position's legal moves so an
// external tool (the dilf EngineProtocol backing, for adjudication-predicate
// scoring) can enumerate moves without linking the C++ engine. Per output line,
// space-separated move tokens: quiet = "from>to", capture = "from>to*c1,c2,..."
// (captured squares, FMJD 1..50, order-independent), "+" suffix if the move
// promotes. An EMPTY line means a terminal position (no legal move = stm loses).
// A bad FEN emits a single "?" token on its line. Deterministic, no eval, no DB.
// -----------------------------------------------------------------------------
int run_dump_legal_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --dump-legal <fen-in> <out>\n";
        return 1;
    }
    std::ifstream in(argv[2]);
    if (!in) { std::cerr << "error: cannot open " << argv[2] << "\n"; return 1; }
    std::ofstream out(argv[3]);
    if (!out) { std::cerr << "error: cannot open " << argv[3] << "\n"; return 1; }
    std::string line;
    std::uint64_t nlines = 0, nterminal = 0, nbad = 0;
    while (std::getline(in, line)) {
        // Strip a trailing CR (CRLF inputs) so from_fen sees a clean string.
        if (!line.empty() && line.back() == '\r') line.pop_back();
        ++nlines;
        auto pos = Position::from_fen(line);
        if (!pos) { out << "?\n"; ++nbad; continue; }
        MoveList ml;
        generate_legal_moves(*pos, ml);
        if (ml.empty()) ++nterminal;
        bool first = true;
        for (const auto& m : ml) {
            if (!first) out << ' ';
            first = false;
            out << static_cast<int>(m.from) << '>' << static_cast<int>(m.to);
            if (m.is_capture()) {
                out << '*';
                bool fc = true;
                for (int b = 0; b < NUM_SQUARES; ++b) {
                    if ((m.captured >> b) & 1ULL) {
                        if (!fc) out << ',';
                        out << (b + 1);
                        fc = false;
                    }
                }
            }
            if (m.promotes) out << '+';
        }
        out << '\n';
    }
    std::cerr << "dump-legal: " << nlines << " positions (" << nterminal
              << " terminal, " << nbad << " bad-fen) → " << argv[3] << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --dump-children <fen-in> <jsonl-out> : deterministic legal successor dump.
// One JSON array is emitted per input FEN, preserving line alignment.  This is
// intentionally eval-free: conversion_teacher.py uses it both to reconstruct
// historical sample-every=1 game boundaries and to enumerate counterfactual
// siblings before applying the same external oracle to every child.
// -----------------------------------------------------------------------------
int run_dump_children_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --dump-children <fen-in> <jsonl-out>\n";
        return 1;
    }
    std::ifstream in(argv[2]);
    if (!in) { std::cerr << "error: cannot open " << argv[2] << "\n"; return 1; }
    std::ofstream out(argv[3]);
    if (!out) { std::cerr << "error: cannot open " << argv[3] << "\n"; return 1; }
    std::string line;
    std::uint64_t nlines = 0, nchildren = 0, nbad = 0;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        ++nlines;
        auto pos = Position::from_fen(line);
        if (!pos) { out << "null\n"; ++nbad; continue; }
        MoveList ml;
        generate_legal_moves(*pos, ml);
        out << '[';
        for (std::size_t i = 0; i < ml.size(); ++i) {
            if (i) out << ',';
            const auto& move = ml[i];
            out << "{\"move\":\"" << static_cast<int>(move.from)
                << (move.is_capture() ? 'x' : '-') << static_cast<int>(move.to)
                << "\",\"capture\":" << (move.is_capture() ? "true" : "false")
                << ",\"fen\":\"" << pos->after(move).to_fen() << "\"}";
            ++nchildren;
        }
        out << "]\n";
    }
    std::cerr << "dump-children: " << nlines << " positions, " << nchildren
              << " children, " << nbad << " bad-fen -> " << argv[3] << "\n";
    return nbad == 0 ? 0 : 2;
}

// -----------------------------------------------------------------------------
// --replay-moves <games.txt> <parents.jnnw> <moves.bin> : elite-game -> master
// preference corpus. Reads one game per input line (space-separated move tokens,
// e.g. "32-28 19x28 33x22 ..."; only the FIRST and LAST square of each token are
// used, so "16x27x38" -> from=16,to=38). Replays each game from the start
// position; for every ply whose (from,to) matches a legal move it writes the
// PARENT position as a 38-byte JNNW record AND the played (from,to) as 2 bytes to
// moves.bin, kept 1:1 aligned. Feeds `--gen-siblings --played-moves` (Bonanza
// master arm): the elite move = preferred, all legal siblings = dominated. A ply
// with no legal match desynchronises the game -> that game is truncated there
// (logged). No search, no eval, no DB. Deterministic.
// -----------------------------------------------------------------------------
int run_replay_moves_mode(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "usage: jass --replay-moves <games.txt> <parents.jnnw> <moves.bin>\n";
        return 1;
    }
    std::ifstream in(argv[2]);
    if (!in) { std::cerr << "error: cannot open " << argv[2] << "\n"; return 1; }
    std::ofstream pout(argv[3], std::ios::binary);
    std::ofstream mout(argv[4], std::ios::binary);
    if (!pout || !mout) { std::cerr << "error: cannot open output\n"; return 1; }

    auto encode = [](const jass::Position& p, char r[38]) {
        std::memset(r, 0, 38);
        const std::uint64_t bbs[4] = { p.white_men(), p.white_kings(),
                                       p.black_men(), p.black_kings() };
        std::memcpy(r,      &bbs[0], 8); std::memcpy(r + 8,  &bbs[1], 8);
        std::memcpy(r + 16, &bbs[2], 8); std::memcpy(r + 24, &bbs[3], 8);
        r[32] = static_cast<char>(p.side_to_move() == jass::Color::White ? 0u : 1u);
        // bytes 33..37 (score/wdl) left zero — unused by master mode.
    };

    std::vector<char> precs;                 // buffered parent records
    std::vector<unsigned char> mrecs;        // buffered (from,to) pairs
    std::uint64_t games = 0, plies = 0, desync = 0, gtrunc = 0;
    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        // tokenize on whitespace
        std::vector<std::string> toks; std::string t;
        for (char c : line) { if (std::isspace(static_cast<unsigned char>(c))) { if (!t.empty()) { toks.push_back(t); t.clear(); } } else t.push_back(c); }
        if (!t.empty()) toks.push_back(t);
        if (toks.empty()) continue;
        ++games;
        jass::Position pos = jass::Position::start_position();
        bool truncated = false;
        for (const std::string& tok : toks) {
            // extract integer runs; from = first, to = last
            int from = -1, to = -1; std::string num;
            auto flush = [&]() { if (!num.empty()) { int v = std::atoi(num.c_str()); if (from < 0) from = v; to = v; num.clear(); } };
            for (char c : tok) { if (c >= '0' && c <= '9') num.push_back(c); else flush(); }
            flush();
            if (from < 1 || from > 50 || to < 1 || to > 50) { continue; }  // annotation/garbage token: skip
            jass::MoveList ml; jass::generate_legal_moves(pos, ml);
            int match = -1;
            for (std::size_t k = 0; k < ml.size(); ++k)
                if (static_cast<int>(ml[k].from) == from && static_cast<int>(ml[k].to) == to) { match = static_cast<int>(k); break; }
            if (match < 0) { ++desync; truncated = true; break; }  // move not legal here -> truncate game
            char r[38]; encode(pos, r);
            precs.insert(precs.end(), r, r + 38);
            mrecs.push_back(static_cast<unsigned char>(from));
            mrecs.push_back(static_cast<unsigned char>(to));
            pos = pos.after(ml[static_cast<std::size_t>(match)]);
            ++plies;
        }
        if (truncated) ++gtrunc;
    }
    const std::uint32_t count = static_cast<std::uint32_t>(precs.size() / 38);
    pout.write("JNNW", 4);
    pout.write(reinterpret_cast<const char*>(&count), 4);
    pout.write(precs.data(), static_cast<std::streamsize>(precs.size()));
    mout.write(reinterpret_cast<const char*>(mrecs.data()), static_cast<std::streamsize>(mrecs.size()));
    std::cerr << "replay-moves: " << games << " games, " << plies << " plies emitted ("
              << gtrunc << " games truncated, " << desync << " desync plies) → "
              << argv[3] << " + " << argv[4] << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --egdb-selfcheck <db_dir> [samples] [cache_mb] : the #1 validation gate for
// the external bitbase bridge. Opens the egdb_intl DB at <db_dir> and, on a
// random sample of kings-only positions that jass's own in-memory tables also
// resolve, cross-checks egdb::probe() against the reference:
//   * K-vs-K  → must be Draw (unambiguous; any other value = a mapping bug).
//   * 2v1/3v1 → wherever the in-memory bitbase asserts a DEFINITE win, egdb
//     must return the SAME absolute result (our table only flags concrete
//     wins, so this direction catches bit-layout / colour / result-mapping
//     bugs; the reverse — egdb decisive where ours is Draw/Unknown — is just
//     egdb's exact retrograde being stronger and is reported, not failed).
// A clean run (0 violations) locks the adaptation before trusting the eval.
// -----------------------------------------------------------------------------
int run_egdb_selfcheck_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --egdb-selfcheck <db_dir> [samples] [cache_mb]\n";
        return 1;
    }
    const std::string db_dir = argv[2];
    const int samples  = (argc > 3) ? parse_int_or(argv[3], 200000) : 200000;
    const int cache_mb = (argc > 4) ? parse_int_or(argv[4], 1024)   : 1024;

    if (!jass::egdb::init(db_dir, cache_mb)) {
        std::cerr << "error: egdb::init failed for '" << db_dir
                  << "' (built without -DJASS_EGDB, or no DB there)\n";
        return 1;
    }
    std::cout << "egdb opened: max_pieces=" << jass::egdb::max_pieces()
              << "  samples=" << samples << "\n";

    auto fen_of = [](const jass::Position& p) {
        auto sqs = [](jass::Bitboard b) {
            std::string s; bool first = true;
            while (b) { int q = jass::pop_lsb(b);
                if (!first) s += ','; first = false; s += std::to_string(q); }
            return s;
        };
        return std::string(p.side_to_move() == jass::Color::White ? "W" : "B")
             + ":WK" + sqs(p.white_kings()) + ":BK" + sqs(p.black_kings());
    };

    std::mt19937_64 rng(0xB17BA5E5ULL);
    // (white-kings, black-kings) configs our in-memory tables resolve.
    const std::pair<int,int> configs[] = {{1,1},{2,1},{1,2},{3,1},{1,3}};

    // egdb is the GROUND TRUTH here — our in-memory kings-only tables are a
    // shallow heuristic (KvK blanket-draw, 2v1/3v1 over-claim wins), so they
    // are NOT a valid reference. The one airtight invariant we can assert is
    // physical: a 1K-vs-1K position with NO capture available is a forced draw.
    // Everything else is reported informationally (egdb correcting our tables).
    long checked = 0, kvk_nocap_bad = 0, egdb_unknown = 0,
         egdb_win = 0, egdb_loss = 0, egdb_draw = 0, table_corrected = 0;
    int shown = 0;

    for (int i = 0; i < samples; ++i) {
        const auto [wk, bk] = configs[rng() % 5];
        // place wk+bk kings on distinct random playable squares (1..50)
        jass::Position p;
        int placed = 0; bool ok = true;
        std::array<int, 6> used{}; int nused = 0;
        auto place = [&](jass::Piece piece) {
            for (int tries = 0; tries < 64; ++tries) {
                const int sq = static_cast<int>(rng() % 50) + 1;
                bool dup = false;
                for (int u = 0; u < nused; ++u) if (used[static_cast<std::size_t>(u)] == sq) dup = true;
                if (dup) continue;
                used[static_cast<std::size_t>(nused++)] = sq;
                p.add_piece(static_cast<jass::Square>(sq), piece);
                ++placed; return true;
            }
            return false;
        };
        for (int k = 0; k < wk && ok; ++k) ok = place(jass::Piece::WhiteKing);
        for (int k = 0; k < bk && ok; ++k) ok = place(jass::Piece::BlackKing);
        if (!ok || placed != wk + bk) continue;
        p.set_side_to_move((rng() & 1) ? jass::Color::White : jass::Color::Black);

        const jass::EndgameResult got = jass::egdb::probe(p);
        ++checked;

        switch (got) {
            case jass::EndgameResult::WhiteWin:
            case jass::EndgameResult::BlackWin: ++egdb_win; break;  // (decisive)
            case jass::EndgameResult::Draw:     ++egdb_draw; break;
            default:                            ++egdb_unknown; break;
        }
        if (got == jass::EndgameResult::WhiteWin || got == jass::EndgameResult::BlackWin) {
            // (win/loss split is symmetric; egdb_loss kept for completeness)
        }

        // Hard invariant: KvK with no capture available is a forced draw, so
        // egdb must never return a DECISIVE result for it. Draw or Unknown
        // (e.g. the <3-piece guard declining db2) are both acceptable.
        const bool got_decisive = (got == jass::EndgameResult::WhiteWin
                                || got == jass::EndgameResult::BlackWin);
        if (wk == 1 && bk == 1 && got_decisive) {
            jass::MoveList ml; jass::generate_legal_moves(p, ml);
            const bool has_cap = !ml.empty() && ml[0].is_capture();
            if (!has_cap) {
                ++kvk_nocap_bad;
                if (shown++ < 12)
                    std::cout << "  INVARIANT VIOLATION (KvK no-capture not draw): egdb="
                              << static_cast<int>(got) << "  " << fen_of(p) << "\n";
            }
        }

        // Informational: where egdb corrects our shallow in-memory table.
        const jass::EndgameResult ref = (wk == 1 && bk == 1)
            ? jass::EndgameResult::Draw
            : jass::probe_kings_endgame(p);
        if (got != jass::EndgameResult::Unknown && got != ref) ++table_corrected;
    }
    (void)egdb_loss;

    jass::egdb::shutdown();
    std::cout << "\n=== egdb self-check (egdb = ground truth) ===\n"
              << "  checked positions          : " << checked << "\n"
              << "  egdb W/L decisive          : " << egdb_win << "\n"
              << "  egdb draw                  : " << egdb_draw << "\n"
              << "  egdb unknown (out of slice): " << egdb_unknown << "\n"
              << "  egdb != our in-mem table   : " << table_corrected
              << "  (informational — our tables are heuristic, not truth)\n"
              << "  KvK-no-capture NOT draw    : " << kvk_nocap_bad << "  (hard invariant)\n";
    const bool clean = (kvk_nocap_bad == 0);
    std::cout << (clean
        ? "  RESULT: invariant OK. Authoritative validation = egdb native example test.\n"
        : "  RESULT: INVARIANT VIOLATION — conversion/mapping bug, do not trust egdb.\n");
    return clean ? 0 : 1;
}

// -----------------------------------------------------------------------------
// --egdb-relabel <in.jnnw> <db_dir> [out.jnnw=in] [cache_mb=1024]
// Rewrite each JNNW record's WDL byte with the EXACT egdb result for positions
// egdb can resolve (3..max_pieces). WDL is STM-POV (+1 STM wins / 0 draw / -1
// STM loses), matching --gen-data-wdl. Records egdb cannot resolve (>max_pieces,
// or the <3-piece guard) keep their original game-outcome label. Turns noisy
// game-propagated endgame labels into ground truth.
// -----------------------------------------------------------------------------
namespace {
int wdl_from_result(jass::EndgameResult r, std::uint8_t stm) {
    if (r == jass::EndgameResult::Draw) return 0;
    const bool white_wins = (r == jass::EndgameResult::WhiteWin);
    const bool stm_white   = (stm == 0);
    return (white_wins == stm_white) ? +1 : -1;
}
jass::Position position_from_record(const char* rec) {
    std::uint64_t bbs[4]; std::memcpy(bbs, rec, 32);
    jass::Position p;
    for (jass::Bitboard b = bbs[0]; b; ) p.add_piece(jass::pop_lsb(b), jass::Piece::WhiteMan);
    for (jass::Bitboard b = bbs[1]; b; ) p.add_piece(jass::pop_lsb(b), jass::Piece::WhiteKing);
    for (jass::Bitboard b = bbs[2]; b; ) p.add_piece(jass::pop_lsb(b), jass::Piece::BlackMan);
    for (jass::Bitboard b = bbs[3]; b; ) p.add_piece(jass::pop_lsb(b), jass::Piece::BlackKing);
    p.set_side_to_move(static_cast<std::uint8_t>(rec[32]) == 0 ? jass::Color::White
                                                               : jass::Color::Black);
    return p;
}
}  // namespace

// --gen-siblings <parents.jnnw> <out.jnnw> [depth=9] [--nnue PATH] [--m-min CP=15]
//                [--max-parents N] [--max-pairs-per-parent K=16] [--seed S=1]
//                [--played-moves good.bin] [--dominated-moves bad.bin]
//   Piste (a) "depth-consistency training". Pour chaque parent QUIET (noeud sans capture),
//   recherche chaque enfant legal a profondeur fixe (eval-pur, PAS de DB => echelles comparables).
//   Valeur parent-POV d'un coup = -score(enfant). Emet les PAIRES ordonnees (better > worse) dont
//   la marge parent-POV >= m_min (cp). Sortie JNNW : records PAR DEUX (2k=better, 2k+1=worse) ;
//   score[2k] = marge (cp), wdl[2k] = pair_src (0=deep). Le trainer lit les couples consecutifs.
int run_gen_siblings_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: --gen-siblings <parents.jnnw> <out.jnnw> [depth=9] "
                     "[--nnue PATH] [--m-min CP] [--max-parents N] [--max-pairs-per-parent K]\n";
        return 2;
    }
    const std::string in_path  = argv[2];
    const std::string out_path = argv[3];
    int depth = 9;
    if (argc > 4 && argv[4][0] != '-') depth = parse_int_or(argv[4], 9);
    std::string nnue_path; int m_min = 15; long max_parents = -1; int max_pairs = 16;
    std::string moves_path;   // --played-moves : BRAS M (Bonanza). Binaire (from:u8,to:u8) par parent, ALIGNE
                              // sur les records d'entree. Si present : PAS de recherche — le coup joue = prefere,
                              // toutes les autres sœurs legales = dominees (src=MASTER). max_pairs/m_min ignores.
    std::string dominated_path; // Teacher causal: un seul mauvais coup explicite par parent. Garantit que B2/B3
                                // utilisent exactement les memes parents et paires (pas toutes les fratries).
    // --leaf-mode : MMTO (Hoki-Kaneko). Pour CHAQUE enfant, recherche a `depth` (quiescence incluse) et emet la
    //   position FEUILLE de la PV a la place de l'enfant immediat. La valeur minimax couleur-fixe d'un coup = l'eval
    //   couleur-fixe de sa feuille-PV (identite negamax), donc rank_finetune (qui signe chaque record par son stm)
    //   apprend a travers la RECHERCHE, pas sur l'eval-feuille des enfants immediats. En master+leaf : filtre working-set
    //   (ne garder que si le coup-prof n'est PAS deja en tete de la recherche, avec marge --ws-margin cp).
    bool leaf_mode = false; int ws_margin = 10; bool working_set_filter = true;
    for (int i = 4; i < argc; ++i) {
        const std::string a = argv[i];
        if      (a == "--nnue" && i + 1 < argc)                 nnue_path = argv[++i];
        else if (a == "--m-min" && i + 1 < argc)                m_min = parse_int_or(argv[++i], 15);
        else if (a == "--max-parents" && i + 1 < argc)          max_parents = parse_int_or(argv[++i], -1);
        else if (a == "--max-pairs-per-parent" && i + 1 < argc) max_pairs = parse_int_or(argv[++i], 16);
        else if (a == "--played-moves" && i + 1 < argc)         moves_path = argv[++i];
        else if (a == "--dominated-moves" && i + 1 < argc)      dominated_path = argv[++i];
        else if (a == "--leaf-mode")                            leaf_mode = true;
        else if (a == "--ws-margin" && i + 1 < argc)            ws_margin = parse_int_or(argv[++i], 10);
        else if (a == "--keep-all-pairs")                       working_set_filter = false;
    }
    const bool master_mode = !moves_path.empty();
    std::vector<std::pair<std::uint8_t,std::uint8_t>> played;   // BRAS M : coup joue par parent
    std::vector<std::pair<std::uint8_t,std::uint8_t>> dominated;
    if (!dominated_path.empty() && !master_mode) {
        std::cerr << "error: --dominated-moves requires --played-moves\n";
        return 2;
    }
    if (master_mode) {
        std::ifstream mf(moves_path, std::ios::binary);
        if (!mf) { std::cerr << "error: cannot open --played-moves " << moves_path << "\n"; return 1; }
        std::vector<char> mb((std::istreambuf_iterator<char>(mf)), std::istreambuf_iterator<char>());
        if ((mb.size() % 2) != 0) {
            std::cerr << "error: --played-moves has a truncated move byte\n";
            return 1;
        }
        for (std::size_t k = 0; k + 1 < mb.size(); k += 2)
            played.emplace_back(static_cast<std::uint8_t>(mb[k]), static_cast<std::uint8_t>(mb[k+1]));
    }
    if (!dominated_path.empty()) {
        std::ifstream mf(dominated_path, std::ios::binary);
        if (!mf) { std::cerr << "error: cannot open --dominated-moves " << dominated_path << "\n"; return 1; }
        std::vector<char> mb((std::istreambuf_iterator<char>(mf)), std::istreambuf_iterator<char>());
        if ((mb.size() % 2) != 0) {
            std::cerr << "error: --dominated-moves has a truncated move byte\n";
            return 1;
        }
        for (std::size_t k = 0; k + 1 < mb.size(); k += 2)
            dominated.emplace_back(static_cast<std::uint8_t>(mb[k]), static_cast<std::uint8_t>(mb[k+1]));
        if (dominated.size() != played.size()) {
            std::cerr << "error: played/dominated move counts differ (" << played.size()
                      << " != " << dominated.size() << ")\n";
            return 1;
        }
    }

    std::unique_ptr<INetwork> custom_nnue;
    if (!nnue_path.empty()) {
        const bool is_pjtw = nnue_path.size() >= 5
                          && nnue_path.compare(nnue_path.size() - 5, 5, ".pjtw") == 0;
        std::string err;
        custom_nnue = is_pjtw ? jass::load_eval_network(nnue_path, &err)
                              : load_network(nnue_path.c_str());
        if (!custom_nnue) { std::cerr << "error: cannot load eval from " << nnue_path << " (" << err << ")\n"; return 1; }
    }
    jass::Engine e; e.use_book(false);
    if (custom_nnue) e.set_nnue(custom_nnue.get());

    std::ifstream f(in_path, std::ios::binary);
    if (!f) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }
    char hdr[8];
    if (!f.read(hdr, 8) || std::memcmp(hdr, "JNNW", 4) != 0) { std::cerr << "error: not JNNW\n"; return 1; }
    std::uint32_t declared_nrec = 0;
    std::memcpy(&declared_nrec, hdr + 4, 4);
    std::vector<char> buf((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    f.close();
    if ((buf.size() % 38) != 0) {
        std::cerr << "error: truncated JNNW body\n";
        return 1;
    }
    const std::size_t nrec = buf.size() / 38;
    if (declared_nrec != nrec) {
        std::cerr << "error: JNNW header/body count mismatch (" << declared_nrec
                  << " != " << nrec << ")\n";
        return 1;
    }
    if (!dominated_path.empty() && dominated.size() != nrec) {
        std::cerr << "error: explicit teacher move count differs from parent records ("
                  << dominated.size() << " != " << nrec << ")\n";
        return 1;
    }

    // Echantillonnage uniforme par PAS (le corpus est ordonne par partie) ; ~3x de marge pour les
    // noeuds de capture/sans-fratrie ecartes.
    // Master mode : pas de sous-echantillonnage (aligne sur --played-moves), stride=1.
    const std::size_t stride = (master_mode || max_parents <= 0)
        ? 1 : std::max<std::size_t>(1, nrec / (static_cast<std::size_t>(max_parents) * 3 + 1));
    std::vector<char> out;                 // emitted pair records (38B each)
    long parents_seen = 0, parents_used = 0, pairs = 0, cap_nodes = 0, no_match = 0;
    long ws_already_top = 0;               // MMTO working-set : coup-prof deja en tete (rien a apprendre)
    long phase_pairs[4] = {0,0,0,0};
    double margin_sum = 0;

    struct Ch { std::int32_t pv; std::uint64_t bbs[4]; std::uint8_t stm; std::uint8_t from, to; };
    auto emit = [&](std::vector<char>& o, const Ch& x, std::int32_t score, std::int8_t wdl){
        char r[38] = {0};
        std::memcpy(r,      &x.bbs[0], 8); std::memcpy(r + 8,  &x.bbs[1], 8);
        std::memcpy(r + 16, &x.bbs[2], 8); std::memcpy(r + 24, &x.bbs[3], 8);
        r[32] = static_cast<char>(x.stm);
        std::memcpy(r + 33, &score, 4);
        r[37] = static_cast<char>(wdl);
        o.insert(o.end(), r, r + 38);
    };

    for (std::size_t pi = 0; pi < nrec; pi += stride) {
        if (max_parents >= 0 && parents_used >= max_parents) break;
        if (master_mode && pi >= played.size()) break;
        const char* rec = buf.data() + pi * 38;
        const jass::Position parent = position_from_record(rec);
        jass::MoveList ml; jass::generate_legal_moves(parent, ml);
        if (ml.size() < 2) continue;
        ++parents_seen;
        if (ml[0].is_capture()) { ++cap_nodes; continue; }   // capture node : ordre force

        std::vector<Ch> ch; ch.reserve(ml.size());
        for (std::size_t mi = 0; mi < ml.size(); ++mi) {
            const jass::Position c = parent.after(ml[mi]);
            Ch x;
            x.from = static_cast<std::uint8_t>(ml[mi].from);
            x.to   = static_cast<std::uint8_t>(ml[mi].to);
            jass::Position emit_pos = c;                     // par defaut : enfant immediat
            if (leaf_mode || !master_mode) {                 // besoin d'une recherche (BRAS S ordering, ou MMTO leaf)
                e.set_position(c);
                jass::SearchLimits lim; lim.max_depth = depth;
                const jass::SearchResult r = e.search(lim);
                x.pv = -static_cast<std::int32_t>(r.score);   // valeur parent-POV du coup
                if (leaf_mode) {                              // MMTO : position emise = FEUILLE de la PV
                    jass::Position leaf = c;
                    for (const auto& m : r.pv) leaf = leaf.after(m);
                    emit_pos = leaf;
                }
            } else x.pv = 0;
            x.bbs[0] = emit_pos.white_men();  x.bbs[1] = emit_pos.white_kings();
            x.bbs[2] = emit_pos.black_men();  x.bbs[3] = emit_pos.black_kings();
            x.stm = (emit_pos.side_to_move() == jass::Color::White) ? 0u : 1u;
            ch.push_back(x);
        }

        const int pcs = static_cast<int>(popcount(parent.whites() | parent.blacks()));
        const int band = pcs <= 12 ? 0 : (pcs <= 20 ? 1 : (pcs <= 28 ? 2 : 3));
        int emitted_here = 0;

        if (master_mode) {
            // BRAS M (Bonanza) : le coup joue = prefere ; toutes les autres sœurs = dominees. src=1 (MASTER), pas de marge.
            const std::uint8_t pf = played[pi].first, pt = played[pi].second;
            int best = -1;
            for (std::size_t k = 0; k < ch.size(); ++k) if (ch[k].from == pf && ch[k].to == pt) { best = static_cast<int>(k); break; }
            if (best < 0) { ++no_match; continue; }           // coup joue non trouve (capture/parse) : ignorer
            int explicit_bad = -1;
            if (!dominated.empty()) {
                const std::uint8_t df = dominated[pi].first, dt = dominated[pi].second;
                for (std::size_t k = 0; k < ch.size(); ++k)
                    if (ch[k].from == df && ch[k].to == dt) { explicit_bad = static_cast<int>(k); break; }
                if (explicit_bad < 0 || explicit_bad == best) { ++no_match; continue; }
            }
            if (leaf_mode && working_set_filter) {
                // MMTO working-set : si la recherche prefere DEJA le coup-prof (avec marge), rien a apprendre -> skip.
                const std::int32_t v_star = ch[static_cast<std::size_t>(best)].pv;
                std::int32_t v_top = v_star;
                if (explicit_bad >= 0) {
                    v_top = std::max(v_top, ch[static_cast<std::size_t>(explicit_bad)].pv);
                } else {
                    for (std::size_t k = 0; k < ch.size(); ++k) v_top = std::max(v_top, ch[k].pv);
                }
                if (v_top - v_star <= ws_margin) { ++ws_already_top; continue; }
            }
            // En leaf-mode (MMTO) : les feuilles-PV peuvent tomber a des PARITES differentes -> stm-feuille != stm-enfant.
            // X·w etant en BLACK-POV (fold bitboard-only), la valeur minimax black-POV = eval black-POV de la feuille (OK),
            // mais le SIGNE de la comparaison depend du stm du PARENT S (constant par parent), pas du stm de la feuille.
            // On stocke donc S dans le champ score pour que rank_finetune --leaf-pov derive le signe de S (et non du record).
            const std::int32_t sc = leaf_mode
                ? static_cast<std::int32_t>(parent.side_to_move() == jass::Color::White ? 0 : 1)
                : 0;
            for (std::size_t k = 0; k < ch.size(); ++k) {
                if (static_cast<int>(k) == best) continue;
                if (explicit_bad >= 0 && static_cast<int>(k) != explicit_bad) continue;
                emit(out, ch[static_cast<std::size_t>(best)], sc, 1);   // prefere (src=MASTER), score=stm parent (leaf)
                emit(out, ch[k], sc, 1);                                 // domine
                ++pairs; ++emitted_here; ++phase_pairs[band];
            }
        } else {
            std::sort(ch.begin(), ch.end(), [](const Ch& a, const Ch& b){ return a.pv > b.pv; });
            for (std::size_t a = 0; a < ch.size() && emitted_here < max_pairs; ++a) {
                for (std::size_t b = a + 1; b < ch.size() && emitted_here < max_pairs; ++b) {
                    const std::int32_t margin = ch[a].pv - ch[b].pv;
                    if (margin < m_min) break;               // b trie desc : rien de plus grand ensuite
                    emit(out, ch[a], margin, 0);              // better : marge + src=deep
                    emit(out, ch[b], 0, 0);                   // worse
                    ++pairs; ++emitted_here; ++phase_pairs[band]; margin_sum += margin;
                }
            }
        }
        if (emitted_here > 0) ++parents_used;
    }

    std::ofstream o(out_path, std::ios::binary);
    if (!o) { std::cerr << "error: cannot write " << out_path << "\n"; return 1; }
    const std::uint32_t nout = static_cast<std::uint32_t>(out.size() / 38);
    o.write("JNNW", 4); o.write(reinterpret_cast<const char*>(&nout), 4);
    o.write(out.data(), static_cast<std::streamsize>(out.size())); o.close();

    std::cout << "GENSIB mode=" << (master_mode ? "MASTER" : "DEEP")
              << (leaf_mode ? "+LEAF(MMTO)" : "")
              << " parents_seen=" << parents_seen << " quiet_used=" << parents_used
              << " cap_nodes=" << cap_nodes << " no_match=" << no_match
              << " ws_already_top=" << ws_already_top << " pairs=" << pairs
              << " records=" << nout << " depth=" << depth << " m_min=" << m_min
              << " ws_margin=" << ws_margin
              << " margin_mean=" << (pairs ? margin_sum / static_cast<double>(pairs) : 0.0)
              << " phase[fin/13-20/21-28/ouv]=" << phase_pairs[0] << "/" << phase_pairs[1]
              << "/" << phase_pairs[2] << "/" << phase_pairs[3]
              << " -> " << out_path << "\n";
    return 0;
}

// --egdb-audit <in.jnnw> <db_dir> [cache_mb]
//
// LECTURE SEULE. Ne relabellise rien, ne cherche rien, n'ecrit aucun corpus :
// pour chaque record tombant dans la tablebase, il compare l'etiquette PORTEE
// PAR LE CORPUS a la VERITE de jeu, et rend la matrice de confusion 3x3.
//
// Motif : le corpus WDL etiquette chaque position par le RESULTAT DE LA PARTIE.
// Sur les positions ou la tablebase sait, ce resultat peut etre faux — une
// position theoriquement nulle gagnee par une bourde ulterieure porte
// l'etiquette « gain ». Le taux de desaccord est donc une mesure DIRECTE et
// ABSOLUE du bruit d'etiquetage, pas un proxy.
//
// ⚠️ Il ne couvre que les positions a <= 7 pieces, la ou le resultat de partie
// est justement le PLUS fiable : c'est une borne OPTIMISTE du bruit reel.
int run_egdb_audit_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: --egdb-audit <in.jnnw> <db_dir> [cache_mb]\n";
        return 2;
    }
    const std::string in_path = argv[2];
    const std::string db_dir  = argv[3];
    const int cache_mb = (argc > 4) ? parse_int_or(argv[4], 1024) : 1024;

    if (!jass::egdb::init(db_dir, cache_mb)) {
        std::cerr << "error: egdb::init failed for '" << db_dir
                  << "' (built without -DJASS_EGDB, or no DB there)\n";
        return 1;
    }
    std::ifstream f(in_path, std::ios::binary);
    if (!f) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }
    char hdr[8];
    if (!f.read(hdr, 8) || std::memcmp(hdr, "JNNW", 4) != 0) {
        std::cerr << "error: " << in_path << " is not JNNW\n"; return 1;
    }
    std::vector<char> buf((std::istreambuf_iterator<char>(f)),
                          std::istreambuf_iterator<char>());
    f.close();
    const std::size_t nrec = buf.size() / 38;

    // conf[label+1][truth+1], indices 0=perte 1=nulle 2=gain, POV trait.
    long long conf[3][3] = {};
    long long in_range = 0;
    for (std::size_t i = 0; i < nrec; ++i) {
        const char* rec = buf.data() + i * 38;
        const jass::Position p = position_from_record(rec);
        const jass::EndgameResult tb = jass::egdb::probe(p);
        if (tb == jass::EndgameResult::Unknown) continue;
        const std::uint8_t stm = static_cast<std::uint8_t>(rec[32]);
        const int truth = wdl_from_result(tb, stm);
        const int label = static_cast<int>(static_cast<std::int8_t>(rec[37]));
        if (label < -1 || label > 1) continue;   // record hors contrat
        ++conf[label + 1][truth + 1];
        ++in_range;
    }
    long long agree = conf[0][0] + conf[1][1] + conf[2][2];
    // Une inversion gain<->perte est bien plus grave qu'un gain<->nulle.
    long long inverted = conf[0][2] + conf[2][0];
    const double dis = in_range > 0
        ? 100.0 * static_cast<double>(in_range - agree) / static_cast<double>(in_range) : 0.0;
    const double inv = in_range > 0
        ? 100.0 * static_cast<double>(inverted) / static_cast<double>(in_range) : 0.0;
    std::cout << "EGDBAUDIT records=" << nrec << " in_range=" << in_range
              << " (" << (nrec ? 100.0 * static_cast<double>(in_range) / static_cast<double>(nrec) : 0.0)
              << "%)  agree=" << agree
              << "  disagree=" << (in_range - agree) << " (" << dis << "%)"
              << "  inverted=" << inverted << " (" << inv << "%)\n";
    static const char* nm[3] = {"perte", "nulle", "gain"};
    for (int l = 0; l < 3; ++l) {
        std::cout << "EGDBCONF label=" << nm[l];
        for (int t = 0; t < 3; ++t) std::cout << "  verite_" << nm[t] << "=" << conf[l][t];
        std::cout << '\n';
    }
    return 0;
}

int run_egdb_relabel_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: --egdb-relabel <in.jnnw> <db_dir> [out.jnnw] [cache_mb]\n";
        return 2;
    }
    const std::string in_path  = argv[2];
    const std::string db_dir   = argv[3];
    const std::string out_path = (argc > 4) ? argv[4] : in_path;
    const int cache_mb = (argc > 5) ? parse_int_or(argv[5], 1024) : 1024;

    if (!jass::egdb::init(db_dir, cache_mb)) {
        std::cerr << "error: egdb::init failed for '" << db_dir
                  << "' (built without -DJASS_EGDB, or no DB there)\n";
        return 1;
    }
    std::ifstream f(in_path, std::ios::binary);
    if (!f) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }
    char hdr[8];
    if (!f.read(hdr, 8) || std::memcmp(hdr, "JNNW", 4) != 0) {
        std::cerr << "error: " << in_path << " is not JNNW\n"; return 1;
    }
    std::vector<char> buf((std::istreambuf_iterator<char>(f)),
                          std::istreambuf_iterator<char>());
    f.close();
    const std::size_t nrec = buf.size() / 38;

    long in_range = 0, decisive = 0, draw = 0, changed = 0, stalls = 0;
    for (std::size_t i = 0; i < nrec; ++i) {
        char* rec = buf.data() + i * 38;
        const jass::Position p = position_from_record(rec);
        const jass::EndgameResult got = jass::egdb::probe(p);  // Unknown if out of egdb range
        if (got == jass::EndgameResult::Unknown) continue;
        ++in_range;
        (got == jass::EndgameResult::Draw) ? ++draw : ++decisive;
        const std::int8_t nb = static_cast<std::int8_t>(
            wdl_from_result(got, static_cast<std::uint8_t>(rec[32])));
        // STALL = egdb says this is a WIN/LOSS but the game recorded a DRAW
        // here = the engine failed to convert (shuffled to the draw rule). The
        // headline diagnostic for the distance-aware-TB / MTC conversion fix.
        if (nb != 0 && rec[37] == 0) ++stalls;
        if (rec[37] != static_cast<char>(nb)) ++changed;
        rec[37] = static_cast<char>(nb);
    }
    jass::egdb::shutdown();

    std::ofstream o(out_path, std::ios::binary);
    if (!o) { std::cerr << "error: cannot write " << out_path << "\n"; return 1; }
    o.write("JNNW", 4);
    const std::uint32_t c32 = static_cast<std::uint32_t>(nrec);
    o.write(reinterpret_cast<const char*>(&c32), 4);
    o.write(buf.data(), static_cast<std::streamsize>(buf.size()));
    o.close();

    std::cout << "egdb-relabel: " << nrec << " records, " << in_range
              << " egdb-resolved (" << decisive << " decisive, " << draw
              << " draw), " << changed << " labels changed, " << stalls
              << " stalls (won/lost recorded draw) → " << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --deep-relabel <in.jnnw> <out.jnnw> [depth=18] [--nnue PATH] [--label-depth-by-phase SPEC] [--egdb DIR] [--cache-mb N] [--search-params SPEC] [--draw-band N]
// Independent value-target distillation (option B) : rewrite each record's SCORE
// field with the value of a DEEP jass search (STM-POV, search-amplified), and its
// WDL byte with the sign. With --egdb, endgame positions egdb can resolve get the
// EXACT value (saturated) — ground-truth anchor. The teacher is OUR OWN deep search
// (no Scan), so the static eval distilled from these labels can exceed Scan, unlike
// Scan-distillation which caps at Scan. Single-threaded — shard the input across
// cores in the job for parallelism.
// -----------------------------------------------------------------------------
int run_deep_relabel_mode(int argc, char** argv) {
    std::string in_path, out_path, nnue_path, label_spec, egdb_dir, search_spec;
    int depth = 18, cache_mb = 1024;
    std::int32_t draw_band = 50;             // |score| <= band → wdl 0 (draw-ish) ; override via --draw-band
    constexpr std::int32_t EG_SAT = 10000;  // saturated value for egdb-exact win/loss
    std::vector<std::string> pos;
    for (int i = 2; i < argc; ++i) {
        const std::string a = argv[i];
        if      (a == "--nnue" && i + 1 < argc)                 nnue_path  = argv[++i];
        else if (a == "--label-depth-by-phase" && i + 1 < argc) label_spec = argv[++i];
        else if (a == "--egdb" && i + 1 < argc)                 egdb_dir   = argv[++i];
        else if (a == "--cache-mb" && i + 1 < argc)             cache_mb   = parse_int_or(argv[++i], 1024);
        else if (a == "--search-params" && i + 1 < argc)        search_spec = argv[++i];  // e.g. pruning OFF (catch hidden shots)
        else if (a == "--draw-band" && i + 1 < argc)            draw_band  = parse_int_or(argv[++i], 50);
        else pos.push_back(a);
    }
    if (pos.size() < 2) {
        std::cerr << "usage: --deep-relabel <in.jnnw> <out.jnnw> [depth=18] "
                     "[--nnue PATH] [--label-depth-by-phase SPEC] [--egdb DIR] [--cache-mb N] [--search-params SPEC] [--draw-band N]\n";
        return 2;
    }
    in_path = pos[0]; out_path = pos[1];
    if (pos.size() > 2) { const int d = parse_int_or(pos[2].c_str(), -1); if (d > 0) depth = d; }
    const std::array<int, NUM_PHASES> label_depth =
        parse_depth_by_phase(label_spec, "--label-depth-by-phase");

    std::unique_ptr<INetwork> custom_nnue;
    if (!nnue_path.empty()) {
        const bool is_pjtw = nnue_path.size() >= 5
                          && nnue_path.compare(nnue_path.size() - 5, 5, ".pjtw") == 0;
        std::string err;
        custom_nnue = is_pjtw ? jass::load_eval_network(nnue_path, &err)
                              : load_network(nnue_path.c_str());
        if (!custom_nnue) {
            std::cerr << "error: cannot load eval weights from " << nnue_path
                      << (err.empty() ? "" : (" : " + err)) << "\n";
            return 1;
        }
    }
    const bool have_egdb = !egdb_dir.empty() && jass::egdb::init(egdb_dir, cache_mb);
    if (!egdb_dir.empty() && !have_egdb)
        std::cerr << "warning: egdb::init failed for '" << egdb_dir << "' — proceeding without exact anchor\n";

    Engine e;
    e.use_book(false);
    if (custom_nnue) e.set_nnue(custom_nnue.get());
    const SearchParams relabel_params = jass::parse_search_params(search_spec);

    std::ifstream f(in_path, std::ios::binary);
    if (!f) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }
    char hdr[8];
    if (!f.read(hdr, 8) || std::memcmp(hdr, "JNNW", 4) != 0) {
        std::cerr << "error: " << in_path << " is not JNNW\n"; return 1;
    }
    std::vector<char> buf((std::istreambuf_iterator<char>(f)),
                          std::istreambuf_iterator<char>());
    f.close();
    const std::size_t nrec = buf.size() / 38;

    long egdb_exact = 0;
    const auto t0 = std::chrono::steady_clock::now();
    for (std::size_t i = 0; i < nrec; ++i) {
        char* rec = buf.data() + i * 38;
        const Position p = position_from_record(rec);
        const std::uint8_t stm = static_cast<std::uint8_t>(rec[32]);
        std::int32_t score;
        if (have_egdb) {
            const jass::EndgameResult tb = jass::egdb::probe(p);
            if (tb != jass::EndgameResult::Unknown) {
                const int w = wdl_from_result(tb, stm);            // STM-POV {+1,0,-1}
                score = static_cast<std::int32_t>(w) * EG_SAT;
                std::memcpy(rec + 33, &score, 4);
                rec[37] = static_cast<char>(w);
                ++egdb_exact;
                continue;
            }
        }
        e.set_position(p);
        const int phase_ovr = label_depth[phase_index_of(popcount(p.occupied()))];
        SearchLimits lim;
        lim.max_depth = (phase_ovr > 0) ? phase_ovr : depth;
        lim.params    = relabel_params;                           // e.g. pruning OFF to expose hidden shots
        const SearchResult r = e.search(lim);
        score = static_cast<std::int32_t>(r.score);               // STM-POV
        std::memcpy(rec + 33, &score, 4);
        const std::int8_t wdl = (score > draw_band) ? 1 : (score < -draw_band ? -1 : 0);
        rec[37] = static_cast<char>(wdl);
        if (((i + 1) % 2000) == 0) {
            const double el = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - t0).count();
            std::cout << "  deep-relabel " << (i + 1) << " / " << nrec
                      << "  (" << (el > 0 ? (i + 1) / el : 0.0) << " pos/s)\n" << std::flush;
        }
    }
    if (have_egdb) jass::egdb::shutdown();

    std::ofstream o(out_path, std::ios::binary);
    if (!o) { std::cerr << "error: cannot write " << out_path << "\n"; return 1; }
    o.write("JNNW", 4);
    const std::uint32_t c32 = static_cast<std::uint32_t>(nrec);
    o.write(reinterpret_cast<const char*>(&c32), 4);
    o.write(buf.data(), static_cast<std::streamsize>(buf.size()));
    o.close();
    const double el = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - t0).count();
    std::cout << "deep-relabel: " << nrec << " records, depth=" << depth
              << ", egdb-exact=" << egdb_exact << ", " << el << "s ("
              << (el > 0 ? nrec / el : 0.0) << " pos/s) → " << out_path << "\n";
    return 0;
}

// Emit a deterministic pool of diverse, legal and quiet midgame positions.
// Each candidate is reached by a fresh random legal trajectory from startpos;
// only one position is retained per trajectory.  This is intended for paired
// engine gates that need hundreds of reproducible openings without depending
// on a small, hand-curated tactical corpus.
// -----------------------------------------------------------------------------
int run_gen_opening_pool_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: --gen-opening-pool <count> <out.fen> "
                     "[min_ply=8] [max_ply=32] [min_pieces=20] [seed=0]\n";
        return 2;
    }
    const int count = parse_int_or(argv[2], 768);
    const char* out_path = argv[3];
    const int min_ply = (argc > 4) ? parse_int_or(argv[4], 8) : 8;
    const int max_ply = (argc > 5) ? parse_int_or(argv[5], 32) : 32;
    const int min_pieces = (argc > 6) ? parse_int_or(argv[6], 20) : 20;
    const std::uint64_t seed = (argc > 7)
        ? static_cast<std::uint64_t>(std::stoull(argv[7]))
        : 0x4F50454E494E4755ULL;
    if (count <= 0 || min_ply < 0 || max_ply < min_ply
        || min_pieces < 2 || min_pieces > 40) {
        std::cerr << "error: invalid opening-pool bounds\n";
        return 2;
    }

    std::ofstream out(out_path);
    if (!out) {
        std::cerr << "error: cannot open " << out_path << "\n";
        return 1;
    }
    std::mt19937_64 rng(seed ? seed : 0x4F50454E494E4755ULL);
    std::unordered_set<std::string> seen;
    seen.reserve(static_cast<std::size_t>(count) * 2);
    out << "# jass deterministic legal quiet opening pool\n"
        << "# count=" << count << " min_ply=" << min_ply
        << " max_ply=" << max_ply << " min_pieces=" << min_pieces
        << " seed=" << seed << "\n";

    const long long max_attempts = static_cast<long long>(count) * 200LL + 1000LL;
    long long attempts = 0;
    int written = 0;
    while (written < count && attempts++ < max_attempts) {
        Position pos = Position::start_position();
        const int target_ply = min_ply + static_cast<int>(
            rng() % static_cast<std::uint64_t>(max_ply - min_ply + 1));
        bool terminal = false;
        for (int ply = 0; ply < target_ply; ++ply) {
            MoveList legal;
            generate_legal_moves(pos, legal);
            if (legal.empty()) { terminal = true; break; }
            pos = pos.after(legal[rng() % legal.size()]);
        }
        if (terminal) continue;
        const int pieces = static_cast<int>(
            popcount(pos.white_men() | pos.white_kings()
                   | pos.black_men() | pos.black_kings()));
        if (pieces < min_pieces) continue;
        MoveList legal;
        generate_legal_moves(pos, legal);
        if (legal.empty() || legal[0].is_capture()) continue;
        const std::string fen = pos.to_fen();
        if (!seen.insert(fen).second) continue;
        out << fen << "  # synthetic-opening-" << written
            << " ply=" << target_ply << " pieces=" << pieces << "\n";
        ++written;
    }
    if (written != count) {
        std::cerr << "error: generated " << written << "/" << count
                  << " openings after " << attempts << " attempts\n";
        return 1;
    }
    std::cout << "gen-opening-pool: wrote " << written
              << " legal quiet unique positions to " << out_path
              << " attempts=" << attempts << " seed=" << seed << "\n";
    return 0;
}

// Emit `count` random LEGAL QUIET positions (3..max_pieces pieces, >=1 per side)
// each labelled with the EXACT egdb WLD (STM-POV; score=0). Capture positions are
// skipped — the WLD value is for quiet leaves, which is what the eval scores. Free
// dense coverage of the endgame space the self-play games never reach.
// -----------------------------------------------------------------------------
int run_gen_egdb_wld_mode(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "usage: --gen-egdb-wld <count> <out.jnnw> <db_dir> "
                     "[max_pieces=7] [cache_mb=1024] [seed=0]\n";
        return 2;
    }
    const int   count     = parse_int_or(argv[2], 1000000);
    const char* out_path  = argv[3];
    const std::string db_dir = argv[4];
    int max_pieces = (argc > 5) ? parse_int_or(argv[5], 7) : 7;
    const int cache_mb = (argc > 6) ? parse_int_or(argv[6], 1024) : 1024;
    const std::uint64_t seed = (argc > 7)
        ? static_cast<std::uint64_t>(parse_int_or(argv[7], 0)) : 0xC0FFEEULL;
    if (max_pieces > 7) max_pieces = 7;     // egdb WLD covers 2..7
    if (max_pieces < 3) max_pieces = 3;     // probe() declines <3 pieces

    if (!jass::egdb::init(db_dir, cache_mb)) {
        std::cerr << "error: egdb::init failed for '" << db_dir << "'\n"; return 1;
    }
    std::ofstream f(out_path, std::ios::binary);
    if (!f) { std::cerr << "error: cannot open " << out_path << "\n"; return 1; }
    f.write("JNNW", 4);
    std::uint32_t count32 = 0; f.write(reinterpret_cast<const char*>(&count32), 4);

    std::mt19937_64 rng(seed ? seed : 0xC0FFEEULL);
    long written = 0, decisive = 0, draw = 0, tries = 0;
    const long max_tries = static_cast<long>(count) * 50L + 200000L;

    while (written < count && tries < max_tries) {
        ++tries;
        const int total = 3 + static_cast<int>(rng() % static_cast<unsigned>(max_pieces - 2));
        const int wtot  = 1 + static_cast<int>(rng() % static_cast<unsigned>(total - 1));
        const int btot  = total - wtot;
        const int wk = static_cast<int>(rng() % static_cast<unsigned>(wtot + 1)); const int wm = wtot - wk;
        const int bk = static_cast<int>(rng() % static_cast<unsigned>(btot + 1)); const int bm = btot - bk;

        jass::Position p;
        std::array<int, 8> used{}; int nused = 0; bool ok = true;
        auto place = [&](jass::Piece piece) -> bool {
            const bool wman = (piece == jass::Piece::WhiteMan);
            const bool bman = (piece == jass::Piece::BlackMan);
            for (int t = 0; t < 80; ++t) {
                const int sq = static_cast<int>(rng() % 50) + 1;
                if (wman && sq <= 5)  continue;   // white man can't sit on its promo row 1..5
                if (bman && sq >= 46) continue;   // black man can't sit on 46..50
                bool dup = false; for (int u = 0; u < nused; ++u) if (used[static_cast<std::size_t>(u)] == sq) dup = true;
                if (dup) continue;
                used[static_cast<std::size_t>(nused++)] = sq;
                p.add_piece(static_cast<jass::Square>(sq), piece);
                return true;
            }
            return false;
        };
        for (int k = 0; k < wm && ok; ++k) ok = place(jass::Piece::WhiteMan);
        for (int k = 0; k < wk && ok; ++k) ok = place(jass::Piece::WhiteKing);
        for (int k = 0; k < bm && ok; ++k) ok = place(jass::Piece::BlackMan);
        for (int k = 0; k < bk && ok; ++k) ok = place(jass::Piece::BlackKing);
        if (!ok) continue;
        p.set_side_to_move((rng() & 1) ? jass::Color::White : jass::Color::Black);

        jass::MoveList ml; jass::generate_legal_moves(p, ml);
        if (ml.empty() || ml[0].is_capture()) continue;   // quiet leaves only

        const jass::EndgameResult got = jass::egdb::probe(p);
        if (got == jass::EndgameResult::Unknown) continue;
        (got == jass::EndgameResult::Draw) ? ++draw : ++decisive;

        const std::uint64_t bbs[4] = { p.white_men(), p.white_kings(),
                                       p.black_men(), p.black_kings() };
        const std::uint8_t stmb = (p.side_to_move() == jass::Color::White) ? 0 : 1;
        const std::int32_t score = 0;
        const std::int8_t  wdlb = static_cast<std::int8_t>(
            wdl_from_result(got, stmb));
        f.write(reinterpret_cast<const char*>(bbs), 32);
        f.write(reinterpret_cast<const char*>(&stmb), 1);
        f.write(reinterpret_cast<const char*>(&score), 4);
        f.write(reinterpret_cast<const char*>(&wdlb), 1);
        ++written;
    }
    jass::egdb::shutdown();
    f.seekp(4, std::ios::beg);
    const std::uint32_t c32 = static_cast<std::uint32_t>(written);
    f.write(reinterpret_cast<const char*>(&c32), 4);
    f.close();
    std::cout << "gen-egdb-wld: wrote " << written << " / " << count << " ("
              << decisive << " decisive, " << draw << " draw) in " << tries
              << " tries → " << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --eval-selfcheck <champion.pjtw> <positions.jnnw> [n=200000]
// B2 V1 : prove the in-memory dense compaction (ScanWeights::remap) is
// BYTE-IDENTICAL to the dense gather, and microbench both. Loads the scan
// weights once, makes a dense copy and a compacted copy, evaluates every
// position both ways (asserts equality), then times each gather separately
// (eval-only throughput). No search : isolates the gather cost.
// -----------------------------------------------------------------------------
int run_eval_selfcheck_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: --eval-selfcheck <champion.pjtw> <positions.jnnw> "
                     "[n=200000]\n";
        return 2;
    }
    const std::string pjtw = argv[2], jnnw_path = argv[3];
    const long nmax = (argc > 4) ? static_cast<long>(parse_int_or(argv[4], 200000))
                                 : 200000;
    std::string err;
    auto wopt = jass::scan_eval::load_scan_weights(pjtw, &err);
    if (!wopt) {
        std::cerr << "error: load_scan_weights('" << pjtw << "'): " << err
                  << " (--eval-selfcheck requires a PJTW v3/v4 scan eval)\n";
        return 1;
    }
    jass::scan_eval::ScanWeights wfull = *wopt;   // dense (as on disk)
    jass::scan_eval::ScanWeights wden  = *wopt;   // → compacted copy
    const std::size_t n_pat_full = wfull.pat.size();
    jass::scan_eval::compact_scan_weights(wden);
    const std::size_t n_dense = wden.pat.size();
    const std::size_t remap_bytes = wden.remap.size() * sizeof(std::uint32_t)
                                  + wden.remap8.size() * sizeof(std::uint8_t);
    const char* remap_kind = !wden.remap8.empty() ? "uint8-palette"
                           : !wden.remap.empty()  ? "uint32" : "none";
    const double mem_full = static_cast<double>(n_pat_full) * sizeof(jass::scan_eval::PatPair);
    const double mem_den  = static_cast<double>(n_dense) * sizeof(jass::scan_eval::PatPair)
                          + static_cast<double>(remap_bytes);
    jass::scan_eval::ScanEvalNetwork net_full(std::move(wfull));
    jass::scan_eval::ScanEvalNetwork net_den (std::move(wden));

    std::ifstream f(jnnw_path, std::ios::binary);
    if (!f) { std::cerr << "error: cannot open " << jnnw_path << "\n"; return 1; }
    char magic[4]; std::uint32_t count32 = 0;
    f.read(magic, 4); f.read(reinterpret_cast<char*>(&count32), 4);
    if (!f || std::memcmp(magic, "JNNW", 4) != 0) {
        std::cerr << "error: " << jnnw_path << " is not JNNW\n"; return 1;
    }
    const long total = std::min<long>(nmax, static_cast<long>(count32));

    std::vector<Position> positions;
    positions.reserve(static_cast<std::size_t>(total));
    for (long i = 0; i < total; ++i) {
        std::uint64_t bbs[4]; std::uint8_t stm_byte; std::int32_t score; std::int8_t wdl;
        f.read(reinterpret_cast<char*>(bbs), 32);
        f.read(reinterpret_cast<char*>(&stm_byte), 1);
        f.read(reinterpret_cast<char*>(&score), 4);
        f.read(reinterpret_cast<char*>(&wdl), 1);
        if (!f) break;
        Position pos{};
        pos.set_side_to_move(stm_byte == 0 ? Color::White : Color::Black);
        for (Bitboard b = bbs[0]; b; ) pos.add_piece(pop_lsb(b), Piece::WhiteMan);
        for (Bitboard b = bbs[1]; b; ) pos.add_piece(pop_lsb(b), Piece::WhiteKing);
        for (Bitboard b = bbs[2]; b; ) pos.add_piece(pop_lsb(b), Piece::BlackMan);
        for (Bitboard b = bbs[3]; b; ) pos.add_piece(pop_lsb(b), Piece::BlackKing);
        positions.push_back(std::move(pos));
    }
    const long n = static_cast<long>(positions.size());
    if (n == 0) { std::cerr << "error: no positions read\n"; return 1; }

    // Correctness : eval both ways, assert identical.
    long mismatch = 0; int shown = 0;
    for (long i = 0; i < n; ++i) {
        const int a = net_full.evaluate(positions[static_cast<std::size_t>(i)]);
        const int b = net_den.evaluate(positions[static_cast<std::size_t>(i)]);
        if (a != b) {
            ++mismatch;
            if (shown < 5) { std::cerr << "  MISMATCH pos " << i << " : dense=" << a
                                       << " compact=" << b << "\n"; ++shown; }
        }
    }

    using clock = std::chrono::steady_clock;
    int sink = 0;
    for (long i = 0; i < n; ++i) sink ^= net_full.evaluate(positions[static_cast<std::size_t>(i)]);
    const auto t0 = clock::now();
    for (long i = 0; i < n; ++i) sink ^= net_full.evaluate(positions[static_cast<std::size_t>(i)]);
    const auto t1 = clock::now();
    for (long i = 0; i < n; ++i) sink ^= net_den.evaluate(positions[static_cast<std::size_t>(i)]);
    const auto t2 = clock::now();
    for (long i = 0; i < n; ++i) sink ^= net_den.evaluate(positions[static_cast<std::size_t>(i)]);
    const auto t3 = clock::now();
    const double s_full = std::chrono::duration<double>(t1 - t0).count();
    const double s_den  = std::chrono::duration<double>(t3 - t2).count();
    const double eps_full = s_full > 0 ? n / s_full : 0.0;
    const double eps_den  = s_den  > 0 ? n / s_den  : 0.0;

    std::cout << "eval-selfcheck: n=" << n << " sink=" << (sink & 1) << "\n"
              << "  BYTE-ID : mismatches=" << mismatch
              << (mismatch == 0 ? "  => IDENTICAL (byte-id OK)"
                                : "  => *** DIVERGENCE ***") << "\n"
              << "  pat_full=" << n_pat_full << " (" << mem_full / 1e6 << " MB)"
              << "  pat_dense=" << n_dense << " remap=" << remap_kind
              << " (" << mem_den / 1e6 << " MB, shrink ×"
              << (mem_den > 0 ? mem_full / mem_den : 0.0) << ")\n"
              << "  NPS eval-only : dense=" << eps_full / 1e6 << " M/s"
              << "  compact=" << eps_den / 1e6 << " M/s"
              << "  ratio=" << (eps_full > 0 ? eps_den / eps_full : 0.0)
              << " (>1 = compaction plus rapide)\n";
    return mismatch == 0 ? 0 : 1;
}

// -----------------------------------------------------------------------------
// --egdb-mtc-probe <wld_dir> <mtc_dir> [n=20000] [cache_mb=1024]
// Validate the MTC database reading + reveal the distance-to-conversion
// distribution (for designing the conversion-gradient target). For N random
// legal quiet positions: WLD-probe; on a WIN/LOSS, MTC-probe (the MTC db is only
// valid for win/loss — gate on WLD first, per the egdb guideline). MTC returns
// 1 ("< 10 plies to conversion") or the actual ply count (>= 10).
// -----------------------------------------------------------------------------
int run_egdb_mtc_probe_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: --egdb-mtc-probe <wld_dir> <mtc_dir> [n] [cache_mb]\n";
        return 2;
    }
    const std::string wld_dir = argv[2], mtc_dir = argv[3];
    const int n     = (argc > 4) ? parse_int_or(argv[4], 20000) : 20000;
    const int cache = (argc > 5) ? parse_int_or(argv[5], 1024)  : 1024;
    if (!jass::egdb::init(wld_dir, cache)) {
        std::cerr << "error: WLD init failed for '" << wld_dir << "'\n"; return 1; }
    if (!jass::egdb::init_mtc(mtc_dir, cache)) {
        std::cerr << "error: MTC init failed for '" << mtc_dir << "'\n"; return 1; }
    std::cout << "WLD max_pieces=" << jass::egdb::max_pieces()
              << "  MTC max_pieces=" << jass::egdb::mtc_max_pieces() << "\n";

    std::mt19937_64 rng(0x4D54435EULL);
    long decisive = 0, draws = 0, mtc_lt10 = 0, mtc_ge10 = 0, mtc_bad = 0, tries = 0;
    long mtc_min = 1 << 30, mtc_max = 0, mtc_sum = 0;
    int shown = 0;
    const long max_tries = static_cast<long>(n) * 50L + 200000L;
    while (decisive + draws < n && tries < max_tries) {
        ++tries;
        const int total = 3 + static_cast<int>(rng() % 5);            // 3..7
        const int wtot  = 1 + static_cast<int>(rng() % static_cast<unsigned>(total - 1));
        const int btot  = total - wtot;
        const int wk = static_cast<int>(rng() % static_cast<unsigned>(wtot + 1)); const int wm = wtot - wk;
        const int bk = static_cast<int>(rng() % static_cast<unsigned>(btot + 1)); const int bm = btot - bk;
        jass::Position p; std::array<int, 8> used{}; int nu = 0; bool ok = true;
        auto place = [&](jass::Piece piece) -> bool {
            const bool wman = (piece == jass::Piece::WhiteMan), bman = (piece == jass::Piece::BlackMan);
            for (int t = 0; t < 80; ++t) {
                const int sq = static_cast<int>(rng() % 50) + 1;
                if (wman && sq <= 5) continue;
                if (bman && sq >= 46) continue;
                bool dup = false; for (int u = 0; u < nu; ++u) if (used[static_cast<std::size_t>(u)] == sq) dup = true;
                if (dup) continue;
                used[static_cast<std::size_t>(nu++)] = sq;
                p.add_piece(static_cast<jass::Square>(sq), piece); return true;
            }
            return false;
        };
        for (int k = 0; k < wm && ok; ++k) ok = place(jass::Piece::WhiteMan);
        for (int k = 0; k < wk && ok; ++k) ok = place(jass::Piece::WhiteKing);
        for (int k = 0; k < bm && ok; ++k) ok = place(jass::Piece::BlackMan);
        for (int k = 0; k < bk && ok; ++k) ok = place(jass::Piece::BlackKing);
        if (!ok) continue;
        p.set_side_to_move((rng() & 1) ? jass::Color::White : jass::Color::Black);
        jass::MoveList ml; jass::generate_legal_moves(p, ml);
        if (ml.empty() || ml[0].is_capture()) continue;             // quiet leaves only
        const jass::EndgameResult wld = jass::egdb::probe(p);
        if (wld == jass::EndgameResult::WhiteWin || wld == jass::EndgameResult::BlackWin) {
            ++decisive;
            const int m = jass::egdb::probe_mtc(p);
            if (m == 1) ++mtc_lt10;
            else if (m >= 10) {
                ++mtc_ge10; if (m < mtc_min) mtc_min = m; if (m > mtc_max) mtc_max = m; mtc_sum += m;
                if (shown++ < 8) std::cout << "  win  MTC=" << m << " plies  ("
                                           << popcount(p.occupied()) << " pieces)\n";
            } else ++mtc_bad;                                        // 0 / negative / unexpected
        } else if (wld == jass::EndgameResult::Draw) ++draws;
    }
    jass::egdb::shutdown();
    std::cout << "\n=== MTC probe ===\n"
              << "  decisive (WLD win/loss) : " << decisive << "   draws : " << draws << "\n"
              << "  MTC < 10 plies (=1)     : " << mtc_lt10 << "\n"
              << "  MTC >= 10 (actual)      : " << mtc_ge10
              << (mtc_ge10 ? ("   range[" + std::to_string(mtc_min) + ".." + std::to_string(mtc_max)
                              + "] mean " + std::to_string(mtc_sum / std::max(1L, mtc_ge10))) : std::string())
              << "\n"
              << "  MTC bad/unavailable     : " << mtc_bad << "\n";
    std::cout << ((mtc_bad == 0 && (mtc_lt10 + mtc_ge10) > 0)
        ? "  RESULT: MTC readable, conversion-distance signal present.\n"
        : "  RESULT: check MTC (no usable distance values).\n");
    return (mtc_bad == 0 && (mtc_lt10 + mtc_ge10) > 0) ? 0 : 1;
}

// -----------------------------------------------------------------------------
// --egdb-mtc-regret <pjtw> <wld_dir> <mtc_dir> [n=20000] [cache_mb=1024] [seed=1]
// CONVERSION metric (exact, Scan-free, NOT endgame_mse — cf the 0311/0312 lesson
// that endgame_mse is decoupled from strength). Samples random WON, quiet, <=7p
// positions; the EVAL picks its move 1-ply-greedy (argmin evaluate(child) — pure
// eval preference, NO search so the core search's egdb leaf is never consulted),
// then we JUDGE that move with the perfect WLD+MTC dbs:
//   (1) win-preservation : does the move KEEP the win? (WLD-exact, dense)
//   (2) win-preservation on CRITICAL positions (a win-throwing move exists) —
//       the discriminating conversion-skill number.
//   (3) fastest-path rate : move sits on a minimal-MTC line (played==best, dense).
//   (4) MTC-regret : extra plies-to-conversion vs optimal, on the MTC>=10 subset.
// MTC is win/loss-only -> gate on WLD first (egdb guideline). probe_mtc returns 1
// for the flat <10-ply zone, so the fine regret (4) uses the >=10 subset only.
// -----------------------------------------------------------------------------
int run_egdb_mtc_regret_mode(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "usage: --egdb-mtc-regret <pjtw> <wld_dir> <mtc_dir> "
                     "[n=20000] [cache_mb=1024] [seed=1]\n";
        return 1;
    }
    const std::string pjtw = argv[2], wld_dir = argv[3], mtc_dir = argv[4];
    const long n     = (argc > 5) ? parse_int_or(argv[5], 20000) : 20000;
    const int  cache = (argc > 6) ? parse_int_or(argv[6], 1024)  : 1024;
    const std::uint64_t seed = (argc > 7)
        ? static_cast<std::uint64_t>(parse_int_or(argv[7], 1)) : 1ULL;

    if (!jass::egdb::init(wld_dir, cache)) {
        std::cerr << "error: WLD init failed for '" << wld_dir << "'\n"; return 1; }
    if (!jass::egdb::init_mtc(mtc_dir, cache)) {
        std::cerr << "error: MTC init failed for '" << mtc_dir << "'\n"; return 1; }
    std::string err;
    auto pjn = jass::load_eval_network(pjtw, &err);
    if (!pjn) { std::cerr << "error: cannot load eval '" << pjtw << "': " << err << "\n"; return 1; }

    auto is_win_for = [](jass::EndgameResult r, jass::Color c) {
        return (c == jass::Color::White && r == jass::EndgameResult::WhiteWin)
            || (c == jass::Color::Black && r == jass::EndgameResult::BlackWin);
    };
    const int MTC_INF = 1 << 30;

    std::mt19937_64 rng(seed ? seed : 1ULL);
    long sampled = 0, preserved = 0, blunders = 0, tries = 0;
    long critical = 0, critical_kept = 0;
    long onpath = 0, onpath_den = 0, mtc_pairs = 0; long long regret_sum = 0;
    const long max_tries = n * 300L;

    while (sampled < n && tries < max_tries) {
        ++tries;
        const int total = 3 + static_cast<int>(rng() % 5);            // 3..7 pieces
        const int wtot  = 1 + static_cast<int>(rng() % static_cast<unsigned>(total - 1));
        const int btot  = total - wtot;
        const int wk = static_cast<int>(rng() % static_cast<unsigned>(wtot + 1)); const int wm = wtot - wk;
        const int bk = static_cast<int>(rng() % static_cast<unsigned>(btot + 1)); const int bm = btot - bk;
        jass::Position p; std::array<int, 8> used{}; int nu = 0; bool ok = true;
        auto place = [&](jass::Piece piece) -> bool {
            const bool wman = (piece == jass::Piece::WhiteMan), bman = (piece == jass::Piece::BlackMan);
            for (int t = 0; t < 80; ++t) {
                const int sq = static_cast<int>(rng() % 50) + 1;
                if (wman && sq <= 5) continue;
                if (bman && sq >= 46) continue;
                bool dup = false; for (int u = 0; u < nu; ++u) if (used[static_cast<std::size_t>(u)] == sq) dup = true;
                if (dup) continue;
                used[static_cast<std::size_t>(nu++)] = sq;
                p.add_piece(static_cast<jass::Square>(sq), piece); return true;
            }
            return false;
        };
        for (int k = 0; k < wm && ok; ++k) ok = place(jass::Piece::WhiteMan);
        for (int k = 0; k < wk && ok; ++k) ok = place(jass::Piece::WhiteKing);
        for (int k = 0; k < bm && ok; ++k) ok = place(jass::Piece::BlackMan);
        for (int k = 0; k < bk && ok; ++k) ok = place(jass::Piece::BlackKing);
        if (!ok) continue;
        p.set_side_to_move((rng() & 1) ? jass::Color::White : jass::Color::Black);
        const jass::Color stm = p.side_to_move();

        jass::MoveList ml; jass::generate_legal_moves(p, ml);
        if (ml.empty() || ml[0].is_capture()) continue;              // quiet leaves only
        if (!is_win_for(jass::egdb::probe(p), stm)) continue;        // WON-for-stm only
        ++sampled;

        // Optimal over legal moves: min MTC among win-preserving children + a
        // count of how many moves keep the win (to flag CRITICAL positions).
        int best_mtc = MTC_INF, keep_cnt = 0;
        for (const auto& m : ml) {
            const jass::Position c = p.after(m);
            if (is_win_for(jass::egdb::probe(c), stm)) {
                ++keep_cnt;
                const int cm = jass::egdb::probe_mtc(c);
                if (cm > 0 && cm < best_mtc) best_mtc = cm;
            }
        }
        const bool is_critical = (keep_cnt < static_cast<int>(ml.size()));  // a win-throwing move exists
        if (is_critical) ++critical;

        // Eval's 1-ply-greedy choice : argmin evaluate(child) (child is opp-POV,
        // so the smallest opp-POV score is best for us). Pure eval, no search.
        jass::Move choice = ml[0]; int best_score = MTC_INF;
        for (const auto& m : ml) {
            const int s = pjn->evaluate(p.after(m));
            if (s < best_score) { best_score = s; choice = m; }
        }

        const jass::Position pc = p.after(choice);
        const bool keeps = is_win_for(jass::egdb::probe(pc), stm);
        if (!keeps) { ++blunders; continue; }
        ++preserved;
        if (is_critical) ++critical_kept;
        const int played_mtc = jass::egdb::probe_mtc(pc);
        if (best_mtc != MTC_INF && played_mtc > 0) {
            ++onpath_den;
            if (played_mtc == best_mtc) ++onpath;
            if (played_mtc >= 10 && best_mtc >= 10) { ++mtc_pairs; regret_sum += (played_mtc - best_mtc); }
        }
    }

    auto pct = [](long a, long b) { return b ? 100.0 * static_cast<double>(a) / static_cast<double>(b) : 0.0; };
    std::cout << "\n=== MTC conversion metric (eval=" << pjtw << ", 1-ply eval-greedy) ===\n"
              << "  sampled won quiet <=7p   : " << sampled << "\n"
              << "  win-preservation         : " << preserved << "/" << sampled
              << " = " << pct(preserved, sampled) << "%   (conversion BLUNDERS: " << blunders << ")\n"
              << "  win-preservation CRITICAL: " << critical_kept << "/" << critical
              << " = " << pct(critical_kept, critical) << "%   (a win-throwing move exists)\n"
              << "  fastest-path rate        : " << onpath << "/" << onpath_den
              << " = " << pct(onpath, onpath_den) << "%   (move on a minimal-MTC line)\n"
              << "  MTC-regret (MTC>=10)     : "
              << (mtc_pairs ? static_cast<double>(regret_sum) / static_cast<double>(mtc_pairs) : 0.0)
              << " plies mean (n=" << mtc_pairs << ")\n"
              << "  -> higher win-preservation(+CRITICAL) & fastest-path, lower regret = better conversion.\n";
    return (sampled > 0) ? 0 : 1;
}

// -----------------------------------------------------------------------------
// --egdb-conversion-test <pjtw> <wld_dir> <mtc_dir|off> [n=2000] [depth=12] [budget=150] [seed=1]
// Validates DISTANCE-AWARE TB PLAY (the MTC-in-search feature). Samples WON, quiet,
// <=7p positions and PLAYS THEM OUT with the FULL search (both sides use the same
// eval; egdb makes the loser resist optimally and the winner hold the win). With
// the MTC db loaded the winner plays the FASTEST conversion; pass mtc_dir=off to
// compare the ply-only distance. Reports win-within-budget %, mean plies-to-win,
// and 50-move STALL %% — fewer stalls + fewer plies with MTC = the feature works.
// -----------------------------------------------------------------------------
int run_egdb_conversion_test_mode(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "usage: --egdb-conversion-test <pjtw> <wld_dir> <mtc_dir|off> "
                     "[n=2000] [depth=12] [budget=150] [seed=1]\n";
        return 1;
    }
    const std::string pjtw = argv[2], wld_dir = argv[3], mtc_arg = argv[4];
    const long n      = (argc > 5) ? parse_int_or(argv[5], 2000) : 2000;
    const int  depth  = (argc > 6) ? parse_int_or(argv[6], 12)   : 12;
    const int  budget = (argc > 7) ? parse_int_or(argv[7], 150)  : 150;
    const std::uint64_t seed = (argc > 8)
        ? static_cast<std::uint64_t>(parse_int_or(argv[8], 1)) : 1ULL;

    if (!jass::egdb::init(wld_dir, 1024)) {
        std::cerr << "error: WLD init failed for '" << wld_dir << "'\n"; return 1; }
    const bool use_mtc = (mtc_arg != "off" && mtc_arg != "-");
    if (use_mtc && !jass::egdb::init_mtc(mtc_arg, 1024)) {
        std::cerr << "warning: MTC init failed for '" << mtc_arg << "' (falling back to ply-only)\n"; }
    std::string err;
    auto pjn = jass::load_eval_network(pjtw, &err);
    if (!pjn) { std::cerr << "error: cannot load eval '" << pjtw << "': " << err << "\n"; return 1; }

    auto is_win_for = [](jass::EndgameResult r, jass::Color c) {
        return (c == jass::Color::White && r == jass::EndgameResult::WhiteWin)
            || (c == jass::Color::Black && r == jass::EndgameResult::BlackWin);
    };

    std::mt19937_64 rng(seed ? seed : 1ULL);
    jass::Engine e; e.use_book(false);
    long sampled = 0, won = 0, stalled = 0, tries = 0; long long plies_sum = 0;
    const long max_tries = n * 300L;

    while (sampled < n && tries < max_tries) {
        ++tries;
        const int total = 3 + static_cast<int>(rng() % 5);
        const int wtot  = 1 + static_cast<int>(rng() % static_cast<unsigned>(total - 1));
        const int btot  = total - wtot;
        const int wk = static_cast<int>(rng() % static_cast<unsigned>(wtot + 1)); const int wm = wtot - wk;
        const int bk = static_cast<int>(rng() % static_cast<unsigned>(btot + 1)); const int bm = btot - bk;
        jass::Position p; std::array<int, 8> used{}; int nu = 0; bool ok = true;
        auto place = [&](jass::Piece piece) -> bool {
            const bool wman = (piece == jass::Piece::WhiteMan), bman = (piece == jass::Piece::BlackMan);
            for (int t = 0; t < 80; ++t) {
                const int sq = static_cast<int>(rng() % 50) + 1;
                if (wman && sq <= 5) continue;
                if (bman && sq >= 46) continue;
                bool dup = false; for (int u = 0; u < nu; ++u) if (used[static_cast<std::size_t>(u)] == sq) dup = true;
                if (dup) continue;
                used[static_cast<std::size_t>(nu++)] = sq;
                p.add_piece(static_cast<jass::Square>(sq), piece); return true;
            }
            return false;
        };
        for (int k = 0; k < wm && ok; ++k) ok = place(jass::Piece::WhiteMan);
        for (int k = 0; k < wk && ok; ++k) ok = place(jass::Piece::WhiteKing);
        for (int k = 0; k < bm && ok; ++k) ok = place(jass::Piece::BlackMan);
        for (int k = 0; k < bk && ok; ++k) ok = place(jass::Piece::BlackKing);
        if (!ok) continue;
        p.set_side_to_move((rng() & 1) ? jass::Color::White : jass::Color::Black);
        const jass::Color winner = p.side_to_move();

        { jass::MoveList ml0; jass::generate_legal_moves(p, ml0);
          if (ml0.empty() || ml0[0].is_capture()) continue; }
        if (!is_win_for(jass::egdb::probe(p), winner)) continue;
        ++sampled;

        // Play it out with the full search (both sides).
        jass::Position cur = p; int plies = 0, hm = 0, outcome = 0;  // +1 win, 0 stall
        while (plies < budget) {
            jass::MoveList ml; jass::generate_legal_moves(cur, ml);
            if (ml.empty()) { outcome = (cur.side_to_move() == winner) ? -1 : +1; break; }
            if (hm >= FIFTY_MOVE_PLIES) { outcome = 0; break; }
            e.set_position(cur);
            jass::SearchLimits lim; lim.max_depth = depth; lim.nnue = pjn.get();
            const jass::SearchResult r = e.search(lim);
            const bool cap = r.best_move.is_capture();
            cur = cur.after(r.best_move);
            hm = cap ? 0 : hm + 1;
            ++plies;
        }
        if (outcome == 1) { ++won; plies_sum += plies; }
        else              { ++stalled; }   // 50-move/budget without finishing (or a fluke loss)
    }

    auto pct = [](long a, long b) { return b ? 100.0 * static_cast<double>(a) / static_cast<double>(b) : 0.0; };
    std::cout << "\n=== conversion playout (eval=" << pjtw << ", depth " << depth
              << ", MTC=" << (use_mtc && jass::egdb::available_mtc() ? "ON" : "off") << ") ===\n"
              << "  sampled won quiet <=7p : " << sampled << "\n"
              << "  WON within budget      : " << won << "/" << sampled << " = " << pct(won, sampled) << "%\n"
              << "  STALLED (50-move/budget): " << stalled << "/" << sampled << " = " << pct(stalled, sampled) << "%\n"
              << "  mean plies-to-win      : " << (won ? static_cast<double>(plies_sum) / static_cast<double>(won) : 0.0) << "\n"
              << "  -> MTC ON should give MORE wins, FEWER stalls, FEWER plies than MTC off.\n";
    return (sampled > 0) ? 0 : 1;
}

// -----------------------------------------------------------------------------
// --egdb-mtc-relabel <in.jnnw> <wld_dir> <mtc_dir> [out] [cache_mb]
// CONVERSION-GRADIENT labelling. Writes a continuous win-probability target into
// each record's `score` field (as prob*10000), so training with `--target prob`
// (logistic on score/10000) keeps the prod WDL regime for most positions but
// gains a conversion gradient in the endgame:
//   * <=7-piece WLD win/loss → prob graded by conversion progress, HYBRID:
//       PROXY (fine, covers MTC's flat <10-ply zone): enemy material left + enemy
//       king centrality ; + MTC (exact, the >=10-ply maneuvering zone). Winning
//       side prob in [0.55, 1.0] (more progressed = higher), STM-POV reprojected.
//   * draw / out-of-WLD-range → fall back to the record's WDL byte (0/0.5/1).
// MTC is only valid for win/loss, so we gate on the WLD probe first (egdb rule).
// -----------------------------------------------------------------------------
int run_egdb_mtc_relabel_mode(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "usage: --egdb-mtc-relabel <in.jnnw> <wld_dir> <mtc_dir> [out] [cache_mb]\n";
        return 2;
    }
    const std::string in_path  = argv[2];
    const std::string wld_dir  = argv[3];
    const std::string mtc_dir  = argv[4];
    const std::string out_path = (argc > 5) ? argv[5] : in_path;
    const int cache = (argc > 6) ? parse_int_or(argv[6], 1024) : 1024;
    if (!jass::egdb::init(wld_dir, cache))     { std::cerr << "error: WLD init failed for '" << wld_dir << "'\n"; return 1; }
    if (!jass::egdb::init_mtc(mtc_dir, cache)) { std::cerr << "error: MTC init failed for '" << mtc_dir << "'\n"; return 1; }

    // Conversion-progress weights (prob units). PROXY complements MTC's flat
    // <10-ply zone: ALPHA per enemy piece left, GAMMA per enemy-king centrality.
    // BETA per ply beyond MTC_THRESHOLD(10) (the exact maneuvering zone).
    // Overridable via env (MTC_ALPHA/MTC_GAMMA/MTC_BETA) for sweeping without rebuild.
    double ALPHA = 0.12, GAMMA = 0.04, BETA = 0.03;   // sweep 0305 distribution optimum
    if (const char* e = std::getenv("MTC_ALPHA")) ALPHA = std::atof(e);
    if (const char* e = std::getenv("MTC_GAMMA")) GAMMA = std::atof(e);
    if (const char* e = std::getenv("MTC_BETA"))  BETA  = std::atof(e);
    std::cout << "mtc-relabel weights: ALPHA=" << ALPHA << " GAMMA=" << GAMMA
              << " BETA=" << BETA << "\n";

    std::ifstream f(in_path, std::ios::binary);
    if (!f) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }
    char hdr[8];
    if (!f.read(hdr, 8) || std::memcmp(hdr, "JNNW", 4) != 0) {
        std::cerr << "error: " << in_path << " is not JNNW\n"; return 1; }
    std::vector<char> buf((std::istreambuf_iterator<char>(f)),
                          std::istreambuf_iterator<char>());
    f.close();
    const std::size_t nrec = buf.size() / 38;

    // king centrality 0 (edge) .. 9 (centre), like scan_eval — an active enemy
    // king is harder to convert against → less progress.
    auto central = [](jass::Square s) -> double {
        const double r = static_cast<double>(jass::row_of(s));
        const double c = static_cast<double>(jass::col_of(s));
        return (4.5 - std::fabs(r - 4.5)) + (4.5 - std::fabs(c - 4.5));
    };
    long graded = 0, wld_decisive = 0, mtc_far = 0, fell_back = 0;
    for (std::size_t i = 0; i < nrec; ++i) {
        char* rec = buf.data() + i * 38;
        const jass::Position p = position_from_record(rec);
        const std::uint8_t stm = static_cast<std::uint8_t>(rec[32]);
        const jass::EndgameResult wld = jass::egdb::probe(p);  // Unknown if out of WLD range
        double prob;                                            // STM-POV win probability
        if (wld == jass::EndgameResult::WhiteWin || wld == jass::EndgameResult::BlackWin) {
            ++wld_decisive;
            const bool white_wins = (wld == jass::EndgameResult::WhiteWin);
            // Progress of the WINNING side toward the bare-king win, graded by:
            //   * PROXY (fine, covers MTC's flat <10 zone): enemy material left
            //     (fewer = closer) + enemy-king centrality (edge = more confined);
            //   * MTC (exact, the >=10-ply maneuvering zone): plies to next conversion.
            const jass::Bitboard loser_all = white_wins
                ? (p.black_men() | p.black_kings()) : (p.white_men() | p.white_kings());
            jass::Bitboard loser_kings = white_wins ? p.black_kings() : p.white_kings();
            const int    enemy_pieces  = popcount(loser_all);
            double enemy_central = 0.0;
            for (jass::Bitboard b = loser_kings; b; ) enemy_central += central(pop_lsb(b));
            const int    d        = jass::egdb::probe_mtc(p);   // 1 (<10) or actual >=10
            const double mtc_pen  = (d >= 10) ? (BETA * static_cast<double>(d - 10)) : 0.0;
            if (d >= 11) ++mtc_far;
            double winp = 1.0 - ALPHA * static_cast<double>(enemy_pieces)
                              - GAMMA * enemy_central - mtc_pen;
            winp = std::min(1.0, std::max(0.55, winp));
            const bool stm_white = (stm == 0);
            prob = (stm_white == white_wins) ? winp : (1.0 - winp);   // STM-POV
            ++graded;
        } else {
            // draw, or position outside the WLD db → keep the game-outcome WDL.
            const std::int8_t w = static_cast<std::int8_t>(rec[37]);
            prob = (w > 0) ? 1.0 : (w < 0) ? 0.0 : 0.5;
            ++fell_back;
        }
        const std::int32_t s = static_cast<std::int32_t>(std::lround(prob * 10000.0));
        std::memcpy(rec + 33, &s, 4);                          // score field = prob*10000
    }
    jass::egdb::shutdown();

    std::ofstream o(out_path, std::ios::binary);
    if (!o) { std::cerr << "error: cannot write " << out_path << "\n"; return 1; }
    o.write("JNNW", 4);
    const std::uint32_t c32 = static_cast<std::uint32_t>(nrec);
    o.write(reinterpret_cast<const char*>(&c32), 4);
    o.write(buf.data(), static_cast<std::streamsize>(buf.size()));
    o.close();

    std::cout << "egdb-mtc-relabel: " << nrec << " records, score=prob*10000 ("
              << graded << " egdb-graded incl. " << mtc_far << " MTC>=11, "
              << fell_back << " WDL-fallback) → train with --target prob → " << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --eval-position <net.pjtw> <fen> : load an eval (v1/v2 pattern or v3 Scan
// eval) and print evaluate(pos) for the given Hub FEN. stm-POV centipawns.
// Used to cross-check the Python trainer prediction against the playable C++
// eval (numeric consistency of the v3 pipeline).
// -----------------------------------------------------------------------------
int run_eval_position_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --eval-position <net.pjtw> <fen>\n";
        return 1;
    }
    std::string err;
    auto net = jass::load_eval_network(argv[2], &err);
    if (!net) {
        std::cerr << "error: cannot load eval from " << argv[2]
                  << " : " << err << "\n";
        return 1;
    }
    auto pos = Position::from_fen(argv[3]);
    if (!pos) { std::cerr << "error: bad FEN '" << argv[3] << "'\n"; return 1; }
    std::cout << net->evaluate(*pos) << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --dump-eval-features: read a JNNW dataset and write, per position, the FULL
// Scan-style "extras" feature vector (jass::scan_eval::NUM_EXTRAS dense
// features = king PST + material + mobility + balance, black-POV). This is
// the SINGLE source of truth shared with the playable v3 eval — the trainer
// (pattern_jass/tools/train.py --scan-eval) consumes this file verbatim, and
// ScanEvalNetwork::evaluate() recomputes the same vector. Format identical to
// --dump-features : "FEAT"(4) + count(4) + K(4) + count×K float32.
// -----------------------------------------------------------------------------
int run_dump_eval_features_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --dump-eval-features <in.jnnw> <out.feat>\n";
        return 1;
    }
    const char* in_path  = argv[2];
    const char* out_path = argv[3];
    std::ifstream in(in_path, std::ios::binary);
    if (!in) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }
    char magic[4]; in.read(magic, 4);
    if (!in || std::string_view{magic, 4} != "JNNW") {
        std::cerr << "error: " << in_path << " not a JNNW file\n"; return 1;
    }
    std::uint32_t count = 0;
    in.read(reinterpret_cast<char*>(&count), 4);
    if (!in) { std::cerr << "error: cannot read header\n"; return 1; }

    std::ofstream out(out_path, std::ios::binary);
    if (!out) { std::cerr << "error: cannot open " << out_path << "\n"; return 1; }
    const std::uint32_t K = static_cast<std::uint32_t>(jass::scan_eval::NUM_EXTRAS);
    out.write("FEAT", 4);
    out.write(reinterpret_cast<const char*>(&count), 4);
    out.write(reinterpret_cast<const char*>(&K), 4);

    constexpr std::size_t RECORD_SZ = 38;
    char record[RECORD_SZ];
    std::array<float, jass::scan_eval::NUM_EXTRAS> extras{};
    for (std::uint32_t i = 0; i < count; ++i) {
        in.read(record, RECORD_SZ);
        if (in.gcount() != static_cast<std::streamsize>(RECORD_SZ)) {
            std::cerr << "error: short read at record " << i << "\n"; return 1;
        }
        std::uint64_t bbs[4];
        std::memcpy(bbs, record, 32);

        Position p{};
        // Side to move is irrelevant for the position-only extras, but set it
        // so the Position invariants hold. bbs order: WhiteMan, WhiteKing,
        // BlackMan, BlackKing (cf JNNW record layout).
        for (Bitboard b = bbs[0]; b; ) p.add_piece(pop_lsb(b), Piece::WhiteMan);
        for (Bitboard b = bbs[1]; b; ) p.add_piece(pop_lsb(b), Piece::WhiteKing);
        for (Bitboard b = bbs[2]; b; ) p.add_piece(pop_lsb(b), Piece::BlackMan);
        for (Bitboard b = bbs[3]; b; ) p.add_piece(pop_lsb(b), Piece::BlackKing);

        jass::scan_eval::compute_extras(p, extras);
        out.write(reinterpret_cast<const char*>(extras.data()),
                  sizeof(float) * extras.size());
    }
    std::cout << "wrote " << count << " × " << K << " Scan-style extras to "
              << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --dump-conditional-context-v2: exact 30-wide teacher context for CTX2.
// The output is intentionally separate from the 120 production extras: these
// richer tactical signals supervise the label mapper and do not alter the
// student's inference architecture.  Format is the standard FEAT container.
// -----------------------------------------------------------------------------
int run_dump_conditional_context_v2_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --dump-conditional-context-v2 <in.jnnw> <out.feat>\n";
        return 1;
    }
    if (!jass::scan_eval::CONDITIONAL_CONTEXT_V2_AVAILABLE) {
        std::cerr << "error: CTX2 requires ENDGAME_FEATURES, KING_MOBILITY, "
                     "SCAN_PARITY and TEMPO_STAGE\n";
        return 1;
    }
    const char* in_path = argv[2];
    const char* out_path = argv[3];
    std::ifstream in(in_path, std::ios::binary);
    if (!in) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }
    char magic[4]; in.read(magic, 4);
    if (!in || std::string_view{magic, 4} != "JNNW") {
        std::cerr << "error: " << in_path << " not a JNNW file\n"; return 1;
    }
    std::uint32_t count = 0;
    in.read(reinterpret_cast<char*>(&count), 4);
    if (!in) { std::cerr << "error: cannot read header\n"; return 1; }

    std::ofstream out(out_path, std::ios::binary);
    if (!out) { std::cerr << "error: cannot open " << out_path << "\n"; return 1; }
    const std::uint32_t width = jass::scan_eval::CONDITIONAL_CONTEXT_V2_WIDTH;
    out.write("FEAT", 4);
    out.write(reinterpret_cast<const char*>(&count), 4);
    out.write(reinterpret_cast<const char*>(&width), 4);

    constexpr std::size_t RECORD_SZ = 38;
    char record[RECORD_SZ];
    std::array<float, jass::scan_eval::CONDITIONAL_CONTEXT_V2_WIDTH> context{};
    for (std::uint32_t i = 0; i < count; ++i) {
        in.read(record, RECORD_SZ);
        if (in.gcount() != static_cast<std::streamsize>(RECORD_SZ)) {
            std::cerr << "error: short read at record " << i << "\n";
            return 1;
        }
        std::uint64_t bbs[4];
        std::memcpy(bbs, record, 32);
        Position p{};
        for (Bitboard b = bbs[0]; b; ) p.add_piece(pop_lsb(b), Piece::WhiteMan);
        for (Bitboard b = bbs[1]; b; ) p.add_piece(pop_lsb(b), Piece::WhiteKing);
        for (Bitboard b = bbs[2]; b; ) p.add_piece(pop_lsb(b), Piece::BlackMan);
        for (Bitboard b = bbs[3]; b; ) p.add_piece(pop_lsb(b), Piece::BlackKing);
        if (!jass::scan_eval::compute_conditional_context_v2(p, context)) {
            std::cerr << "error: CTX2 architecture became unavailable at row " << i << "\n";
            return 1;
        }
        out.write(reinterpret_cast<const char*>(context.data()),
                  sizeof(float) * context.size());
    }
    std::cout << "wrote " << count << " x " << width
              << " CTX2 phase-tactical features to " << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --dump-quiet-flags: read a JNNW dataset and write, per position, ONE byte :
// 1 if the position is quiet (the side to move has NO mandatory capture), 0 if
// tactical. In draughts captures are forced, so a tactical position's static
// eval is meaningless (the search plays out the capture chain immediately).
// The trainer uses this sidecar to restrict the fit to quiescent positions
// (cf gen-data's --quiet-only, applied here after-the-fact on stored data).
// Format : "QIET"(4) + count(4) + count×uint8.
// -----------------------------------------------------------------------------
int run_dump_quiet_flags_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --dump-quiet-flags <in.jnnw> <out.quiet>\n";
        return 1;
    }
    const char* in_path  = argv[2];
    const char* out_path = argv[3];
    std::ifstream in(in_path, std::ios::binary);
    if (!in) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }
    char magic[4]; in.read(magic, 4);
    if (!in || std::string_view{magic, 4} != "JNNW") {
        std::cerr << "error: " << in_path << " not a JNNW file\n"; return 1;
    }
    std::uint32_t count = 0;
    in.read(reinterpret_cast<char*>(&count), 4);
    if (!in) { std::cerr << "error: cannot read header\n"; return 1; }

    std::ofstream out(out_path, std::ios::binary);
    if (!out) { std::cerr << "error: cannot open " << out_path << "\n"; return 1; }
    out.write("QIET", 4);
    out.write(reinterpret_cast<const char*>(&count), 4);

    constexpr std::size_t RECORD_SZ = 38;
    char record[RECORD_SZ];
    std::uint64_t n_quiet = 0;
    for (std::uint32_t i = 0; i < count; ++i) {
        in.read(record, RECORD_SZ);
        if (in.gcount() != static_cast<std::streamsize>(RECORD_SZ)) {
            std::cerr << "error: short read at record " << i << "\n"; return 1;
        }
        std::uint64_t bbs[4];
        std::uint8_t  stm_byte;
        std::memcpy(bbs,       record,      32);
        std::memcpy(&stm_byte, record + 32,  1);
        if (stm_byte > 1) { std::cerr << "bad stm at " << i << "\n"; return 1; }

        Position p{};
        p.set_side_to_move(stm_byte == 0 ? Color::White : Color::Black);
        for (Bitboard b = bbs[0]; b; ) p.add_piece(pop_lsb(b), Piece::WhiteMan);
        for (Bitboard b = bbs[1]; b; ) p.add_piece(pop_lsb(b), Piece::WhiteKing);
        for (Bitboard b = bbs[2]; b; ) p.add_piece(pop_lsb(b), Piece::BlackMan);
        for (Bitboard b = bbs[3]; b; ) p.add_piece(pop_lsb(b), Piece::BlackKing);

        // generate_legal_moves returns ALL captures OR all quiet moves (never a
        // mix), so the first move's capture flag classifies the position. An
        // empty movelist (no legal move = terminal) is treated as quiet.
        MoveList ml;
        generate_legal_moves(p, ml);
        const std::uint8_t quiet =
            (ml.size() == 0 || !ml[0].is_capture()) ? 1u : 0u;
        n_quiet += quiet;
        out.write(reinterpret_cast<const char*>(&quiet), 1);
    }
    std::cout << "wrote " << count << " quiet flags to " << out_path
              << " (" << n_quiet << " quiet / "
              << (count ? 100.0 * static_cast<double>(n_quiet) / count : 0.0)
              << "%)\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --symmetry-augment <in.jnnw> <out.jnnw> : write each record TWICE — the
// original, then its 180°-rotation-with-colour-swap image, the ONLY non-trivial
// geometric symmetry of the dark-square draughts board (a left-right mirror maps
// dark squares to light on an even×even board, so it is NOT usable). The
// transform is a true game symmetry : stm-POV score/wdl are PRESERVED, only the
// bitboards (swap colours + reverse the 50 bits) and the stm byte flip. Doubling
// the data with this symmetry forces the pattern tables to be consistent under
// it — the data-efficient "weight-sharing" effect (cf the Scan route).
// -----------------------------------------------------------------------------
static inline std::uint64_t rot180_50(std::uint64_t bb) noexcept {
    std::uint64_t out = 0;
    while (bb) {
        const int i = std::countr_zero(bb);
        bb &= bb - 1;
        out |= std::uint64_t{1} << (49 - i);
    }
    return out;
}

int run_symmetry_augment_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --symmetry-augment <in.jnnw> <out.jnnw>\n";
        return 1;
    }
    std::ifstream in(argv[2], std::ios::binary);
    if (!in) { std::cerr << "error: cannot open " << argv[2] << "\n"; return 1; }
    char magic[4]; in.read(magic, 4);
    if (!in || std::string_view{magic, 4} != "JNNW") {
        std::cerr << "error: " << argv[2] << " not a JNNW file\n"; return 1;
    }
    std::uint32_t count = 0; in.read(reinterpret_cast<char*>(&count), 4);
    if (!in) { std::cerr << "error: cannot read header\n"; return 1; }

    std::ofstream out(argv[3], std::ios::binary);
    if (!out) { std::cerr << "error: cannot open " << argv[3] << "\n"; return 1; }
    const std::uint32_t out_count = count * 2;
    out.write("JNNW", 4);
    out.write(reinterpret_cast<const char*>(&out_count), 4);

    constexpr std::size_t RECORD_SZ = 38;
    char rec[RECORD_SZ], aug[RECORD_SZ];
    for (std::uint32_t i = 0; i < count; ++i) {
        in.read(rec, RECORD_SZ);
        if (in.gcount() != static_cast<std::streamsize>(RECORD_SZ)) {
            std::cerr << "error: short read at " << i << "\n"; return 1;
        }
        out.write(rec, RECORD_SZ);                       // original
        std::uint64_t bbs[4];
        std::memcpy(bbs, rec, 32);
        std::uint64_t a[4];
        a[0] = rot180_50(bbs[2]);   // new WhiteMan  = rot180(old BlackMan)
        a[1] = rot180_50(bbs[3]);   // new WhiteKing = rot180(old BlackKing)
        a[2] = rot180_50(bbs[0]);   // new BlackMan  = rot180(old WhiteMan)
        a[3] = rot180_50(bbs[1]);   // new BlackKing = rot180(old WhiteKing)
        std::memcpy(aug, rec, RECORD_SZ);                // copy score+wdl as-is
        std::memcpy(aug, a, 32);
        aug[32] = static_cast<char>(rec[32] == 0 ? 1 : 0);  // flip stm
        out.write(aug, RECORD_SZ);                        // symmetry image
    }
    std::cout << "symmetry-augment: " << count << " → " << out_count
              << " records (180°+colour-swap)\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --rewrite-scores-with-handcrafted: same as --rewrite-scores-with-nnue
// but uses the handcrafted `evaluate()` instead of NNUE. Used to compute
// the per-position handcrafted baseline needed by Scan-style hybrid
// pattern training (target = NNUE_score - handcrafted_score).
// -----------------------------------------------------------------------------
int run_rewrite_scores_with_handcrafted_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --rewrite-scores-with-handcrafted "
                     "<input.jnnw> <output.jnnw>\n";
        return 1;
    }
    const char* in_path  = argv[2];
    const char* out_path = argv[3];
    if (std::string_view{in_path} == std::string_view{out_path}) {
        std::cerr << "error: input and output paths are identical\n";
        return 1;
    }

    std::ifstream in(in_path, std::ios::binary);
    if (!in) { std::cerr << "error: cannot open " << in_path << "\n"; return 1; }

    in.seekg(0, std::ios::end);
    const std::streampos file_end = in.tellg();
    in.seekg(0, std::ios::beg);
    if (file_end < std::streampos{8}) {
        std::cerr << "error: " << in_path << " too small for JNNW header\n";
        return 1;
    }
    char magic[4]{};
    in.read(magic, 4);
    if (!in || std::string_view{magic, 4} != "JNNW") {
        std::cerr << "error: " << in_path << " not a JNNW file\n";
        return 1;
    }
    std::uint32_t count = 0;
    in.read(reinterpret_cast<char*>(&count), 4);
    if (!in) { std::cerr << "error: cannot read JNNW header\n"; return 1; }

    constexpr std::size_t RECORD_SZ = 38;
    const std::size_t body_bytes  = static_cast<std::size_t>(file_end) - 8;
    if (body_bytes % RECORD_SZ != 0) {
        std::cerr << "error: body size not multiple of " << RECORD_SZ << "\n";
        return 1;
    }
    const std::size_t expected = body_bytes / RECORD_SZ;
    if (count != expected) {
        std::cerr << "error: header count " << count
                  << " != file-derived " << expected << "\n";
        return 1;
    }

    std::ofstream out(out_path, std::ios::binary);
    if (!out) { std::cerr << "error: cannot open " << out_path << "\n"; return 1; }
    out.write("JNNW", 4);
    out.write(reinterpret_cast<const char*>(&count), 4);

    std::cout << "rewriting " << count << " records (handcrafted): "
              << in_path << " → " << out_path << "\n";

    char record[RECORD_SZ];
    Position pos;
    for (std::uint32_t i = 0; i < count; ++i) {
        in.read(record, RECORD_SZ);
        if (in.gcount() != static_cast<std::streamsize>(RECORD_SZ)) {
            std::cerr << "error: short read at record " << i << "\n";
            return 1;
        }
        std::uint64_t bbs[4];
        std::uint8_t  stm_byte;
        std::memcpy(bbs,       record,      32);
        std::memcpy(&stm_byte, record + 32,  1);
        if (stm_byte > 1) { std::cerr << "bad stm at " << i << "\n"; return 1; }

        pos = Position{};
        pos.set_side_to_move(stm_byte == 0 ? Color::White : Color::Black);
        for (Bitboard b = bbs[0]; b; ) pos.add_piece(pop_lsb(b), Piece::WhiteMan);
        for (Bitboard b = bbs[1]; b; ) pos.add_piece(pop_lsb(b), Piece::WhiteKing);
        for (Bitboard b = bbs[2]; b; ) pos.add_piece(pop_lsb(b), Piece::BlackMan);
        for (Bitboard b = bbs[3]; b; ) pos.add_piece(pop_lsb(b), Piece::BlackKing);

        const std::int32_t new_score = static_cast<std::int32_t>(evaluate(pos));
        std::memcpy(record + 33, &new_score, 4);
        out.write(record, RECORD_SZ);
        if ((i + 1) % 500000 == 0) {
            std::cout << "  " << (i + 1) << " / " << count << " records\n";
        }
    }
    std::cout << "wrote " << count << " records (38 B each) to " << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --benchmark-nnue: pit a trained network (loaded from a binary weights
// file — either the raw LinearNetwork int32 layout or the JNNM-tagged
// MLPNetwork format) against the handcrafted eval. Both engines are
// otherwise identical (same depth, same threads). Plays a colour-swap
// match across the default opening pool so we get diverse games.
// -----------------------------------------------------------------------------
int run_benchmark_nnue_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --benchmark-nnue <weights.bin> [depth=6] "
                     "[pairs=1] [threads=1] [movetime_ms=0]\n"
                     "  movetime_ms > 0 caps wall time per move (depth becomes "
                     "an upper bound) ; 0 = depth-only.\n";
        return 1;
    }
    const char* weights_path = argv[2];
    const int   depth        = (argc > 3) ? parse_int_or(argv[3], 6) : 6;
    const int   pairs        = (argc > 4) ? parse_int_or(argv[4], 1) : 1;
    const int   threads      = (argc > 5) ? parse_int_or(argv[5], 1) : 1;
    const int   movetime_ms  = (argc > 6) ? parse_int_or(argv[6], 0) : 0;

    std::unique_ptr<INetwork> trained = load_network(weights_path);
    if (!trained) {
        std::cerr << "error: cannot load weights from " << weights_path << "\n";
        return 1;
    }

    EngineConfig handcrafted;
    handcrafted.max_depth   = depth;
    handcrafted.threads     = threads;
    handcrafted.movetime_ms = movetime_ms;
    handcrafted.nnue        = nullptr;

    EngineConfig nnue_cfg;
    nnue_cfg.max_depth   = depth;
    nnue_cfg.threads     = threads;
    nnue_cfg.movetime_ms = movetime_ms;
    nnue_cfg.nnue        = trained.get();

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());

    std::cout << "Benchmark: NNUE (" << weights_path
              << ") vs handcrafted, depth " << depth
              << ", threads " << threads
              << ", movetime_ms " << movetime_ms
              << ", " << total_games << " games "
              << "(" << pool.size() << " openings × " << pairs
              << " pairs × 2 colours)\n";

    // A = NNUE, B = handcrafted
    const TournamentResult r = run_tournament(nnue_cfg, handcrafted, pairs);

    std::cout << "Result: NNUE=" << r.a_wins
              << " Handcrafted=" << r.b_wins
              << " Draws="       << r.draws
              << " (total "      << r.games << ")\n";

    // A simple verdict line.  Wins are worth 1 point, draws 0.5.
    const double nnue_score = r.a_wins + 0.5 * r.draws;
    const double rate       = nnue_score / r.games;
    std::cout << "NNUE score rate: " << rate
              << " (" << nnue_score << " / " << r.games << ")\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --benchmark-pattern-jass : same shape as --benchmark-nnue, but A is a
// PatternJassNetwork (pattern_jass POC, 8 patterns × 10 squares ternary)
// vs handcrafted. Gate 2 of Phase Pattern-2 :
//   rate ≥ 0.55 → pattern infra jass fonctionne (continuer Pattern-3)
//   rate <  0.55 → pattern infra NE marche pas sur draughts (debug)
// -----------------------------------------------------------------------------
int run_benchmark_pattern_jass_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --benchmark-pattern-jass <weights.pjtw> "
                     "[depth=6] [pairs=1] [threads=1] [movetime_ms=0]\n";
        return 1;
    }
    const char* weights_path = argv[2];
    const int   depth        = (argc > 3) ? parse_int_or(argv[3], 6) : 6;
    const int   pairs        = (argc > 4) ? parse_int_or(argv[4], 1) : 1;
    const int   threads      = (argc > 5) ? parse_int_or(argv[5], 1) : 1;
    const int   movetime_ms  = (argc > 6) ? parse_int_or(argv[6], 0) : 0;

    std::string err;
    auto pjn = jass::load_pattern_jass_network(weights_path, &err);
    if (!pjn) {
        std::cerr << "error: cannot load PJTW from " << weights_path
                  << " : " << err << "\n";
        return 1;
    }

    EngineConfig pattern_cfg;
    pattern_cfg.max_depth   = depth;
    pattern_cfg.threads     = threads;
    pattern_cfg.movetime_ms = movetime_ms;
    pattern_cfg.nnue        = pjn.get();

    EngineConfig handcrafted_cfg;
    handcrafted_cfg.max_depth   = depth;
    handcrafted_cfg.threads     = threads;
    handcrafted_cfg.movetime_ms = movetime_ms;
    handcrafted_cfg.nnue        = nullptr;

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());
    std::cout << "Benchmark: PATTERN_JASS (" << weights_path
              << ", " << pjn->count() << " weights, scale=" << pjn->scale()
              << ") vs handcrafted, depth " << depth
              << ", threads " << threads
              << ", movetime_ms " << movetime_ms
              << ", " << total_games << " games "
              << "(" << pool.size() << " openings × " << pairs
              << " pairs × 2 colours)\n";

    const TournamentResult r = run_tournament(pattern_cfg, handcrafted_cfg, pairs);

    std::cout << "Result: PATTERN_JASS=" << r.a_wins
              << " Handcrafted=" << r.b_wins
              << " Draws="       << r.draws
              << " (total "      << r.games << ")\n";

    const double pattern_score = r.a_wins + 0.5 * r.draws;
    const double rate          = pattern_score / r.games;
    std::cout << "PATTERN_JASS score rate: " << rate
              << " (" << pattern_score << " / " << r.games << ")\n";
    // Gate 2 hint :
    if (rate >= 0.55) {
        std::cout << "GATE 2 PASS (rate >= 0.55)\n";
    } else {
        std::cout << "GATE 2 FAIL (rate < 0.55)\n";
    }
    return 0;
}

// -----------------------------------------------------------------------------
// --benchmark-pattern-vs-nnue : pattern (A) vs NNUE (B), same colour-swap
// match. The whole point is TIME-SEARCH: with movetime_ms > 0 the ~100×
// faster pattern eval searches much deeper than the NNUE for the same wall
// budget. At fixed depth the pattern's speed is invisible (only per-node
// quality counts) — so always run this with movetime to test whether the
// pattern's depth advantage beats the NNUE's per-node quality.
// -----------------------------------------------------------------------------
int run_benchmark_pattern_vs_nnue_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --benchmark-pattern-vs-nnue "
                     "<weights.pjtw> <nnue.bin> "
                     "[depth=64] [pairs=3] [threads=1] [movetime_ms=300] "
                     "[pattern_spec]\n"
                     "  movetime_ms > 0 is the point — pattern is ~100× faster\n"
                     "  pattern_spec = SPSA-tuned search params for side A "
                     "(e.g. \"rfp_margin=80,...\")\n";
        return 1;
    }
    const char* weights_path = argv[2];
    const char* nnue_path    = argv[3];
    const int   depth        = (argc > 4) ? parse_int_or(argv[4], 64) : 64;
    const int   pairs        = (argc > 5) ? parse_int_or(argv[5], 3) : 3;
    const int   threads      = (argc > 6) ? parse_int_or(argv[6], 1) : 1;
    const int   movetime_ms  = (argc > 7) ? parse_int_or(argv[7], 300) : 300;
    // Optional search-param spec for the PATTERN side (e.g. SPSA-tuned
    // constants), so we can test the pattern under search constants tuned
    // for it rather than for the NNUE. The NNUE side keeps the defaults.
    const char* pat_spec     = (argc > 8) ? argv[8] : "";

    std::string err;
    auto pjn = jass::load_pattern_jass_network(weights_path, &err);
    if (!pjn) {
        std::cerr << "error: cannot load PJTW from " << weights_path
                  << " : " << err << "\n";
        return 1;
    }
    std::unique_ptr<INetwork> nnue = load_network(nnue_path);
    if (!nnue) {
        std::cerr << "error: cannot load NNUE from " << nnue_path << "\n";
        return 1;
    }

    EngineConfig pattern_cfg;
    pattern_cfg.max_depth   = depth;
    pattern_cfg.threads     = threads;
    pattern_cfg.movetime_ms = movetime_ms;
    pattern_cfg.nnue        = pjn.get();
    pattern_cfg.params      = jass::parse_search_params(pat_spec);

    EngineConfig nnue_cfg;
    nnue_cfg.max_depth   = depth;
    nnue_cfg.threads     = threads;
    nnue_cfg.movetime_ms = movetime_ms;
    nnue_cfg.nnue        = nnue.get();

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());
    std::cout << "Benchmark: PATTERN(" << weights_path
              << ", " << pjn->count() << " weights) vs NNUE(" << nnue_path
              << "), depth " << depth
              << ", threads " << threads
              << ", movetime_ms " << movetime_ms
              << ", " << total_games << " games\n";

    const TournamentResult r = run_tournament(pattern_cfg, nnue_cfg, pairs);
    std::cout << "Result: PATTERN=" << r.a_wins
              << " NNUE="           << r.b_wins
              << " Draws="          << r.draws
              << " (total "         << r.games << ")\n";
    const double rate = (r.a_wins + 0.5 * r.draws) / static_cast<double>(r.games);
    std::cout << "PATTERN score rate vs NNUE: " << rate << '\n';
    return 0;
}

// -----------------------------------------------------------------------------
// --benchmark-scan-eval : the full Scan-style v3 eval (A) vs NNUE (B), same
// colour-swap match. Mirror of --benchmark-pattern-vs-nnue but loads the
// structured phase-split v3 weights (material + king PST + mobility + balance
// + men patterns, all MG/EG). movetime_ms > 0 is the point — the structured
// eval is far cheaper than the NNUE forward pass, so it searches deeper.
// -----------------------------------------------------------------------------
int run_benchmark_scan_eval_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --benchmark-scan-eval "
                     "<weights_v3.pjtw> <nnue.bin> "
                     "[depth=64] [pairs=3] [threads=1] [movetime_ms=300] "
                     "[scan_spec] [tt_mb=16]\n";
        return 1;
    }
    const char* weights_path = argv[2];
    const char* nnue_path    = argv[3];
    const int   depth        = (argc > 4) ? parse_int_or(argv[4], 64) : 64;
    const int   pairs        = (argc > 5) ? parse_int_or(argv[5], 3) : 3;
    const int   threads      = (argc > 6) ? parse_int_or(argv[6], 1) : 1;
    const int   movetime_ms  = (argc > 7) ? parse_int_or(argv[7], 300) : 300;
    const char* scan_spec    = (argc > 8) ? argv[8] : "";
    const std::size_t tt_mb  = (argc > 9)
        ? static_cast<std::size_t>(parse_int_or(argv[9], 16)) : 16;

    std::string err;
    auto net = jass::scan_eval::load_scan_eval_network(weights_path, &err);
    if (!net) {
        std::cerr << "error: cannot load v3 PJTW from " << weights_path
                  << " : " << err << "\n";
        return 1;
    }
    // Opponent: an NNUE .bin, or "hc"/"none" for the handcrafted eval (used
    // to place the v3 relative to the handcrafted baseline it replaced).
    const std::string opp{nnue_path};
    const bool opp_hc = (opp == "hc" || opp == "none" || opp == "-");
    std::unique_ptr<INetwork> nnue;
    if (!opp_hc) {
        nnue = load_network(nnue_path);
        if (!nnue) {
            std::cerr << "error: cannot load NNUE from " << nnue_path << "\n";
            return 1;
        }
    }

    EngineConfig scan_cfg;
    scan_cfg.max_depth   = depth;
    scan_cfg.threads     = threads;
    scan_cfg.movetime_ms = movetime_ms;
    scan_cfg.tt_mb       = tt_mb;
    scan_cfg.nnue        = net.get();
    scan_cfg.params      = jass::parse_search_params(scan_spec);

    EngineConfig nnue_cfg;
    nnue_cfg.max_depth   = depth;
    nnue_cfg.threads     = threads;
    nnue_cfg.movetime_ms = movetime_ms;
    nnue_cfg.tt_mb       = tt_mb;
    nnue_cfg.nnue        = nnue.get();

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());
    std::cout << "Benchmark: SCAN_EVAL(" << weights_path
              << ", " << net->count() << " weights, scale=" << net->scale()
              << ") vs NNUE(" << nnue_path << "), depth " << depth
              << ", threads " << threads
              << ", movetime_ms " << movetime_ms
              << ", " << total_games << " games\n";

    const TournamentResult r = run_tournament(scan_cfg, nnue_cfg, pairs);
    std::cout << "Result: SCAN_EVAL=" << r.a_wins
              << " NNUE="             << r.b_wins
              << " Draws="            << r.draws
              << " (total "           << r.games << ")\n";
    const double rate = (r.a_wins + 0.5 * r.draws) / static_cast<double>(r.games);
    std::cout << "SCAN_EVAL score rate vs NNUE: " << rate << '\n';
    return 0;
}

// -----------------------------------------------------------------------------
// --depth-at-movetime <netA> <netB> <movetime_ms> [tt_mb=64] [search_spec]
// Quantify the speed→depth lever : for each opening-pool position, search with
// each eval at the SAME wall-clock budget and report the depth reached (avg /
// min / max), nodes and knps. A fast eval (e.g. the v3) should reach many more
// plies than the NNUE for the same time — that gap IS the lever's size.
// net = "hc"/"none" (handcrafted), *.pjtw (pattern/Scan v3), else NNUE .bin.
// -----------------------------------------------------------------------------
// --search-profile <FEN> <depth> [movetime_ms=0] [eval.pjtw|hc]
// Run ONE search and dump where the per-node time goes (eval / movegen-capture /
// movegen-quiet / move-ordering / tt / accumulator / …) as % of total. Requires a
// build with -DJASS_TIME_BREAKDOWN=ON (else the counters stay 0). Guides the NPS axis:
// optimise the hot bucket instead of guessing. (Eval defaults to handcrafted; the
// SEARCH buckets — movegen/ordering/tt — are eval-independent.)

// --dump-sacs : read FENs from stdin, print Scan's ported add_sacs (fidelity check
// vs tools/scan_oracle). Output per line : "SACS <n> <from-to> ...".
static int run_dump_sacs_mode(int, char**) {
    jass::Engine e; e.use_book(false);
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        if (!e.set_position_fen(line)) { std::cout << "SACS bad-fen\n"; continue; }
        jass::MoveList sacs; jass::scan_add_sacs(e.position(), sacs);
        std::cout << "SACS " << sacs.size();
        for (std::size_t i = 0; i < sacs.size(); ++i)
            std::cout << " " << int(sacs[i].from) << "-" << int(sacs[i].to);
        std::cout << "\n" << std::flush;
    }
    return 0;
}

int run_search_profile_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --search-profile <FEN> <depth> [movetime_ms=0] "
                     "[eval.pjtw|hc] [search-params]\n  (build with -DJASS_TIME_BREAKDOWN=ON)\n";
        return 1;
    }
    const std::string fen     = argv[2];
    const int   depth         = parse_int_or(argv[3], 15);
    const int   movetime_ms   = (argc > 4) ? parse_int_or(argv[4], 0) : 0;
    std::unique_ptr<INetwork> net;
    if (argc > 5 && std::string(argv[5]) != "hc" && std::string(argv[5]) != "none") {
        const std::string p{argv[5]};
        const bool is_pjtw = p.size() >= 5 && p.compare(p.size() - 5, 5, ".pjtw") == 0;
        std::string err;
        net = is_pjtw ? jass::load_eval_network(p, &err) : load_network(p);
        if (!net) { std::cerr << "error: cannot load eval " << p << " : " << err << "\n"; return 1; }
    }
    Engine e; e.use_book(false);
    if (net) e.set_nnue(net.get());
    if (!e.set_position_fen(fen)) { std::cerr << "error: bad FEN: " << fen << "\n"; return 1; }

    SearchLimits lim;
    lim.max_depth   = (movetime_ms > 0) ? MAX_PLY : depth;
    lim.movetime_ms = movetime_ms;
    // Optional search-params override (argv[6]) — lets us measure EXACT node counts
    // under alternative search params (e.g. iid_min_depth=8) free of timing noise.
    if (argc > 6) lim.params = jass::parse_search_params(argv[6]);
    jass::breakdown_reset();
    const SearchResult r = e.search(lim);
    const jass::BreakdownStats s = jass::breakdown_snapshot();

    std::cout << "search-profile: depth=" << r.depth << " nodes=" << r.nodes
              << " bestmove=" << static_cast<int>(r.best_move.from) << "-"
              << static_cast<int>(r.best_move.to) << "-"
              << static_cast<int>(r.best_move.num_captures);
    // DIAG #1 : décomposition node-count (cutoff-1er, re-recherche, coups/noeud)
    std::cout << " cutoffs=" << r.cutoffs << " cut1=" << r.first_move_cutoffs
              << " research=" << r.pvs_researches << " movessearched=" << r.moves_searched;
    if (r.nodes) std::cout << "  (" << (s.total_ns ? (r.nodes * 1000ULL / std::max<std::uint64_t>(1, s.total_ns / 1000)) : 0) << " knps)";
    std::cout << "\n";
    if (s.total_ns == 0) {
        std::cout << "  (no breakdown — rebuild with -DJASS_TIME_BREAKDOWN=ON)\n";
        return 0;
    }
    const double tot = static_cast<double>(s.total_ns);
    auto line = [&](const char* name, std::uint64_t ns) {
        std::cout << "  " << std::left << std::setw(20) << name
                  << std::right << std::setw(6)
                  << (ns * 100.0 / tot) << " %\n";
    };
    std::cout.setf(std::ios::fixed); std::cout.precision(1);
    line("eval",            s.eval_ns);
    line("accumulator",     s.accumulator_ns);
    line("movegen (total)", s.movegen_ns);
    line("  - captures",    s.movegen_capture_ns);
    line("  - quiets",      s.movegen_quiet_ns);
    line("move-ordering",   s.move_ordering_ns);
    line("apply/make",      s.apply_ns);
    line("tt",              s.tt_ns);
    line("zobrist",         s.zobrist_ns);
    line("path-check",      s.path_check_ns);
    return 0;
}

int run_depth_at_movetime_mode(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "usage: jass --depth-at-movetime <netA> <netB> "
                     "<movetime_ms> [tt_mb=64] [search_spec] [threads=1]\n";
        return 1;
    }
    const std::string a_path = argv[2];
    const std::string b_path = argv[3];
    const int movetime_ms    = parse_int_or(argv[4], 300);
    const std::size_t tt_mb  = (argc > 5)
        ? static_cast<std::size_t>(parse_int_or(argv[5], 64)) : 64;
    const SearchParams params = jass::parse_search_params((argc > 6) ? argv[6] : "");
    // Optional lazy-SMP fan-out (argv[7], default 1) so this mode can measure
    // SMP scaling : depth/knps reached at the same wall-clock with N threads.
    const int threads = (argc > 7) ? parse_int_or(argv[7], 1) : 1;

    // Owned networks keep the loaded evals alive for the duration.
    std::vector<std::unique_ptr<INetwork>> owned;
    auto load_eval = [&owned](const std::string& p) -> const INetwork* {
        if (p == "hc" || p == "none" || p == "-") return nullptr;
        const bool is_pjtw = p.size() >= 5
                          && p.compare(p.size() - 5, 5, ".pjtw") == 0;
        std::string err;
        std::unique_ptr<INetwork> net =
            is_pjtw ? jass::load_eval_network(p, &err) : load_network(p);
        if (!net) {
            std::cerr << "error: cannot load eval from " << p
                      << (err.empty() ? "" : (" : " + err)) << "\n";
            std::exit(1);
        }
        owned.push_back(std::move(net));
        return owned.back().get();
    };
    const INetwork* nets[2] = { load_eval(a_path), load_eval(b_path) };
    const std::string names[2] = { a_path, b_path };

    const auto pool = default_opening_pool();
    std::cout << "depth-at-movetime : movetime=" << movetime_ms << "ms  tt="
              << tt_mb << "MB  positions=" << pool.size() << "\n";

    double avg_depth[2] = {0, 0};
    for (int s = 0; s < 2; ++s) {
        long long sum_depth = 0, sum_nodes = 0;
        int min_d = 1 << 30, max_d = 0;
        Engine eng(tt_mb);
        eng.use_book(false);
        for (const auto& pos : pool) {
            eng.new_game();          // fresh TT + history → unbiased per position
            eng.set_position(pos);
            SearchLimits lim;
            lim.max_depth   = 99;    // movetime drives depth, not the cap
            lim.movetime_ms = movetime_ms;
            lim.threads     = threads;   // lazy-SMP fan-out (SMP-scaling measure)
            lim.nnue        = nets[s];
            lim.params      = params;
            const SearchResult r = eng.search(lim);
            sum_depth += r.depth;
            sum_nodes += static_cast<long long>(r.nodes);
            if (r.depth < min_d) min_d = r.depth;
            if (r.depth > max_d) max_d = r.depth;
        }
        const double n = static_cast<double>(pool.size());
        avg_depth[s] = sum_depth / n;
        const double knps = (movetime_ms > 0)
            ? (static_cast<double>(sum_nodes) / n) / movetime_ms
            : 0.0;
        std::cout << "  " << (s == 0 ? "A " : "B ") << names[s] << "\n"
                  << "    depth avg=" << avg_depth[s]
                  << "  min=" << min_d << "  max=" << max_d
                  << "  | nodes avg=" << (sum_nodes / static_cast<long long>(pool.size()))
                  << "  knps~" << knps << "\n";
    }
    std::cout << "  → A reaches " << (avg_depth[0] - avg_depth[1])
              << " plies vs B (positive = A searches deeper for the same time)\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --benchmark-pattern-jass-nnue-skel : Option I — pattern hybride avec
// NNUE comme squelette (au lieu de handcrafted).
//   eval_final = NNUE_forward(pos) + pattern_correction(pos)
// Use case : pattern apprend le résidu Scan - v15_NNUE (squelette proche
// de Scan car v15 a été distillé sur master).
// -----------------------------------------------------------------------------
int run_benchmark_pattern_jass_nnue_skel_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --benchmark-pattern-jass-nnue-skel "
                     "<weights.pjtw> <skeleton.nnue.bin> "
                     "[depth=6] [pairs=1] [threads=1] [movetime_ms=0]\n";
        return 1;
    }
    const char* weights_path = argv[2];
    const char* nnue_path    = argv[3];
    const int   depth        = (argc > 4) ? parse_int_or(argv[4], 6) : 6;
    const int   pairs        = (argc > 5) ? parse_int_or(argv[5], 1) : 1;
    const int   threads      = (argc > 6) ? parse_int_or(argv[6], 1) : 1;
    const int   movetime_ms  = (argc > 7) ? parse_int_or(argv[7], 0) : 0;

    std::string err;
    auto pjn = jass::load_pattern_jass_network_nnue_skel(weights_path, nnue_path, &err);
    if (!pjn) {
        std::cerr << "error: cannot load pattern+nnue : " << err << "\n";
        return 1;
    }

    // Bench vs handcrafted (baseline) AND vs NNUE-only (skeleton alone).
    EngineConfig pattern_cfg;
    pattern_cfg.max_depth   = depth;
    pattern_cfg.threads     = threads;
    pattern_cfg.movetime_ms = movetime_ms;
    pattern_cfg.nnue        = pjn.get();

    EngineConfig handcrafted_cfg;
    handcrafted_cfg.max_depth   = depth;
    handcrafted_cfg.threads     = threads;
    handcrafted_cfg.movetime_ms = movetime_ms;
    handcrafted_cfg.nnue        = nullptr;

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());
    std::cout << "Benchmark: PATTERN+NNUE_SKEL (" << weights_path
              << " + " << nnue_path
              << ", " << pjn->count() << " weights, scale=" << pjn->scale()
              << ") vs handcrafted, depth " << depth
              << ", threads " << threads
              << ", movetime_ms " << movetime_ms
              << ", " << total_games << " games\n";

    const TournamentResult r = run_tournament(pattern_cfg, handcrafted_cfg, pairs);
    std::cout << "Result vs handcrafted: PATTERN+NNUE=" << r.a_wins
              << " Handcrafted=" << r.b_wins
              << " Draws="       << r.draws << '\n';
    const double rate = (r.a_wins + 0.5 * r.draws) / static_cast<double>(r.games);
    std::cout << "PATTERN+NNUE_SKEL score rate vs handcrafted: " << rate << '\n';
    return 0;
}

// -----------------------------------------------------------------------------
// --benchmark-nnue-vs-nnue: same colour-swap match as `--benchmark-nnue`,
// but A and B are both NNUE networks (any combination of LinearNetwork
// and MLPNetwork, auto-detected by `load_network`). Used to measure the
// gain of a candidate model against the current shipped default.
// -----------------------------------------------------------------------------
int run_benchmark_nnue_vs_nnue_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --benchmark-nnue-vs-nnue "
                     "<weights_a.bin> <weights_b.bin> [depth=6] [pairs=1] "
                     "[threads_a=1] [movetime_ms=0] [threads_b=threads_a]\n"
                     "  movetime_ms > 0 caps wall time per move (depth becomes "
                     "an upper bound) ; 0 = depth-only.\n"
                     "  threads_b defaults to threads_a ; pass different "
                     "values to compare SMP scaling at fixed movetime.\n";
        return 1;
    }
    const char* path_a      = argv[2];
    const char* path_b      = argv[3];
    const int   depth       = (argc > 4) ? parse_int_or(argv[4], 6) : 6;
    const int   pairs       = (argc > 5) ? parse_int_or(argv[5], 1) : 1;
    const int   threads_a   = (argc > 6) ? parse_int_or(argv[6], 1) : 1;
    const int   movetime_ms = (argc > 7) ? parse_int_or(argv[7], 0) : 0;
    const int   threads_b   = (argc > 8) ? parse_int_or(argv[8], threads_a) : threads_a;

    // Accept either an NNUE .bin or a .pjtw pattern eval for BOTH sides, so two
    // pattern evals can be compared head-to-head (eval1 vs eval0) — the sensitive
    // metric for the co-evolution loop (vs Scan at low rates is too noisy).
    auto load_any = [](const char* p) -> std::unique_ptr<INetwork> {
        const std::string_view s{p};
        if (s.size() >= 5 && s.compare(s.size() - 5, 5, ".pjtw") == 0) {
            std::string err; return jass::load_eval_network(p, &err);
        }
        return load_network(p);
    };
    std::unique_ptr<INetwork> net_a = load_any(path_a);
    if (!net_a) {
        std::cerr << "error: cannot load weights from " << path_a << "\n";
        return 1;
    }
    std::unique_ptr<INetwork> net_b = load_any(path_b);
    if (!net_b) {
        std::cerr << "error: cannot load weights from " << path_b << "\n";
        return 1;
    }

    EngineConfig cfg_a;
    cfg_a.max_depth   = depth;
    cfg_a.threads     = threads_a;
    cfg_a.movetime_ms = movetime_ms;
    cfg_a.nnue        = net_a.get();

    EngineConfig cfg_b;
    cfg_b.max_depth   = depth;
    cfg_b.threads     = threads_b;
    cfg_b.movetime_ms = movetime_ms;
    cfg_b.nnue        = net_b.get();

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());
    std::cout << "Benchmark: A=NNUE(" << path_a
              << ") vs B=NNUE(" << path_b
              << "), depth " << depth
              << ", threads " << threads_a << " vs " << threads_b
              << ", movetime_ms " << movetime_ms
              << ", " << total_games << " games "
              << "(" << pool.size() << " openings × " << pairs
              << " pairs × 2 colours)\n";

    const TournamentResult r = run_tournament(cfg_a, cfg_b, pairs);

    std::cout << "Result: A=" << r.a_wins
              << " B="        << r.b_wins
              << " Draws="    << r.draws
              << " (total "   << r.games << ")\n";

    const double a_score = r.a_wins + 0.5 * r.draws;
    const double rate    = a_score / r.games;
    std::cout << "A score rate: " << rate
              << " (" << a_score << " / " << r.games << ")\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --benchmark-search-params : in-process A/B of two SEARCH parameter sets
// (same network on both sides). Used to validate PVS (use_pvs=1 vs 0) and
// to drive SPSA tuning. The net path may be "hc"/"none" for the handcrafted
// eval. Param specs are "k=v,k=v" strings (cf src/search_params.hpp).
//   jass --benchmark-search-params <net|hc> "<A spec>" "<B spec>"
//        [depth=8] [pairs=2] [threads=1] [movetime_ms=0]
// Reports A's score rate vs B (>0.5 ⇒ A's params are stronger).
// -----------------------------------------------------------------------------
int run_benchmark_search_params_mode(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "usage: jass --benchmark-search-params <net|hc> "
                     "\"<A spec>\" \"<B spec>\" "
                     "[depth=8] [pairs=2] [threads=1] [movetime_ms=0]\n"
                     "  spec = comma-separated key=value (e.g. \"use_pvs=1\")\n";
        return 1;
    }
    const std::string net_path = argv[2];
    const char* spec_a      = argv[3];
    const char* spec_b      = argv[4];
    const int   depth       = (argc > 5) ? parse_int_or(argv[5], 8) : 8;
    const int   pairs       = (argc > 6) ? parse_int_or(argv[6], 2) : 2;
    const int   threads     = (argc > 7) ? parse_int_or(argv[7], 1) : 1;
    const int   movetime_ms = (argc > 8) ? parse_int_or(argv[8], 0) : 0;

    std::unique_ptr<INetwork> net;
    const bool handcrafted = (net_path == "hc" || net_path == "none" || net_path == "-");
    const bool is_pjtw = net_path.size() >= 5
                      && net_path.compare(net_path.size() - 5, 5, ".pjtw") == 0;
    if (!handcrafted) {
        if (is_pjtw) {
            // Pattern eval: lets SPSA tune the search constants WITH the
            // pattern as leaf eval (its score distribution differs from the
            // NNUE the constants were tuned for).
            std::string err;
            net = jass::load_eval_network(net_path, &err);
            if (!net) {
                std::cerr << "error: cannot load PJTW from " << net_path
                          << " : " << err << "\n";
                return 1;
            }
        } else {
            net = load_network(net_path);
            if (!net) {
                std::cerr << "error: cannot load network from " << net_path << "\n";
                return 1;
            }
        }
    }

    EngineConfig cfg_a;
    cfg_a.max_depth   = depth;
    cfg_a.threads     = threads;
    cfg_a.movetime_ms = movetime_ms;
    cfg_a.nnue        = net.get();
    cfg_a.params      = jass::parse_search_params(spec_a);

    EngineConfig cfg_b = cfg_a;
    cfg_b.params      = jass::parse_search_params(spec_b);

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());
    std::cout << "Benchmark: search-params A=[" << spec_a
              << "] vs B=[" << spec_b
              << "] on " << (handcrafted ? "handcrafted" : net_path)
              << ", depth " << depth
              << ", threads " << threads
              << ", movetime_ms " << movetime_ms
              << ", " << total_games << " games\n";

    const TournamentResult r = run_tournament(cfg_a, cfg_b, pairs);
    std::cout << "Result: A=" << r.a_wins
              << " B="        << r.b_wins
              << " Draws="    << r.draws
              << " (total "   << r.games << ")\n";
    const double rate = (r.a_wins + 0.5 * r.draws) / static_cast<double>(r.games);
    std::cout << "A score rate: " << rate << '\n';
    return 0;
}

// -----------------------------------------------------------------------------
// --benchmark-nnue-hybrid : Option H — NNUE résiduel + squelette handcrafted.
//   eval_final = handcrafted(pos) + residual_nnue(pos)
// A = hybrid(residual.bin), B = vanilla NNUE (ex: v15). Mesure si entraîner
// le MÊME archi sur le résidu (label - handcrafted) bat le vanilla à
// profondeur fixe — gate Option H. Cf docs/archives/PARADIGM_SHIFT_OPTIONS.md §H.
// -----------------------------------------------------------------------------
int run_benchmark_nnue_hybrid_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --benchmark-nnue-hybrid "
                     "<residual.bin> <vanilla.bin> [depth=6] [pairs=1] "
                     "[threads=1] [movetime_ms=0]\n";
        return 1;
    }
    const char* residual_path = argv[2];
    const char* vanilla_path  = argv[3];
    const int   depth       = (argc > 4) ? parse_int_or(argv[4], 6) : 6;
    const int   pairs       = (argc > 5) ? parse_int_or(argv[5], 1) : 1;
    const int   threads     = (argc > 6) ? parse_int_or(argv[6], 1) : 1;
    const int   movetime_ms = (argc > 7) ? parse_int_or(argv[7], 0) : 0;

    auto hybrid = jass::load_hybrid_handcrafted_network(residual_path);
    if (!hybrid) {
        std::cerr << "error: cannot load residual network from "
                  << residual_path << "\n";
        return 1;
    }
    std::unique_ptr<INetwork> vanilla = load_network(vanilla_path);
    if (!vanilla) {
        std::cerr << "error: cannot load vanilla network from "
                  << vanilla_path << "\n";
        return 1;
    }

    EngineConfig cfg_a;
    cfg_a.max_depth   = depth;
    cfg_a.threads     = threads;
    cfg_a.movetime_ms = movetime_ms;
    cfg_a.nnue        = hybrid.get();

    EngineConfig cfg_b;
    cfg_b.max_depth   = depth;
    cfg_b.threads     = threads;
    cfg_b.movetime_ms = movetime_ms;
    cfg_b.nnue        = vanilla.get();

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());
    std::cout << "Benchmark: A=HYBRID(handcrafted+" << residual_path
              << ") vs B=NNUE(" << vanilla_path
              << "), depth " << depth
              << ", threads " << threads
              << ", movetime_ms " << movetime_ms
              << ", " << total_games << " games\n";

    const TournamentResult r = run_tournament(cfg_a, cfg_b, pairs);
    std::cout << "Result: A(hybrid)=" << r.a_wins
              << " B(vanilla)="       << r.b_wins
              << " Draws="            << r.draws
              << " (total "           << r.games << ")\n";
    const double rate = (r.a_wins + 0.5 * r.draws) / static_cast<double>(r.games);
    std::cout << "HYBRID score rate vs vanilla: " << rate << '\n';
    return 0;
}

// -----------------------------------------------------------------------------
// --book-audit: reconstruct a Scan-style book (JBK2) as a tree by BFS from the
// start position — a position is "in book" iff its zobrist key is stored — and
// report VOLUME/structure stats (ply histogram, branching, width, leaves). It
// also writes two TSVs for the offline Scan-oracle quality check
// (tools/book_audit_vs_scan.py): internal nodes with the book's recommended
// move, and leaves with their stored score (for value calibration vs Scan).
//
// usage: jass --book-audit <book.jbk2> [out_prefix] [margin=30]
// -----------------------------------------------------------------------------
int run_book_audit_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --book-audit <book.jbk2> [out_prefix] [margin=30]\n";
        return 1;
    }
    const char* book_path = argv[2];
    const std::string prefix = (argc > 3) ? argv[3] : "book-audit";
    const int margin = (argc > 4) ? parse_int_or(argv[4], 30) : 30;

    ScanBook book;
    if (!book.load(book_path)) {
        std::cerr << "error: cannot load JBK2 book from " << book_path << "\n";
        return 1;
    }

    const Position start = Position::start_position();
    if (!book.contains(zobrist_hash(start))) {
        std::cerr << "error: start position not in book — not a from-start tree?\n";
        return 1;
    }

    std::ofstream moves_out(prefix + ".moves.tsv");
    std::ofstream leaves_out(prefix + ".leaves.tsv");
    moves_out  << "# fen\tbook_move\tscore\tn_children\tn_within_margin\tply\n";
    leaves_out << "# fen\tscore\tply\n";

    // BFS over in-book positions (a position is in book iff its key is stored).
    std::unordered_map<ZobristHash, int> seen;     // key -> ply (dedup)
    std::vector<std::pair<Position, int>> frontier;
    frontier.push_back({start, 0});
    seen[zobrist_hash(start)] = 0;

    std::vector<long> ply_hist;
    long internal = 0, leaves = 0, edges = 0, width_sum = 0;
    int  max_ply = 0;
    long root_width = 0;

    std::size_t qi = 0;
    while (qi < frontier.size()) {
        const Position pos = frontier[qi].first;
        const int ply      = frontier[qi].second;
        ++qi;
        if (ply >= static_cast<int>(ply_hist.size())) ply_hist.resize(ply + 1, 0);
        ply_hist[ply]++;
        max_ply = std::max(max_ply, ply);

        MoveList ml;
        generate_legal_moves(pos, ml);
        struct Kid { Move m; int val; ZobristHash key; Position child; };
        std::vector<Kid> kids;
        for (const auto& m : ml) {
            const Position child = pos.after(m);
            const ZobristHash k = zobrist_hash(child);
            if (auto s = book.score_of(k))
                kids.push_back({m, -*s, k, child});      // negamax: our value = -child
        }

        if (kids.empty()) {                              // leaf (book frontier)
            ++leaves;
            const int sc = book.score_of(zobrist_hash(pos)).value_or(0);
            leaves_out << pos.to_fen() << '\t' << sc << '\t' << ply << '\n';
            continue;
        }

        ++internal;
        edges += static_cast<long>(kids.size());
        int best = kids[0].val;
        for (const auto& k : kids) best = std::max(best, k.val);
        int within = 0;
        const Kid* top = &kids[0];
        for (const auto& k : kids) {
            if (k.val + margin >= best) ++within;
            if (k.val > top->val) top = &k;
        }
        width_sum += within;
        if (ply == 0) root_width = within;
        moves_out << pos.to_fen() << '\t' << format_move(top->m) << '\t'
                  << top->val << '\t' << kids.size() << '\t' << within
                  << '\t' << ply << '\n';

        for (const auto& k : kids) {
            if (seen.find(k.key) == seen.end()) {
                seen[k.key] = ply + 1;
                frontier.push_back({k.child, ply + 1});
            }
        }
    }

    const long nodes = internal + leaves;
    std::cout << "book-audit: " << book_path << "\n";
    std::cout << "  positions stored : " << book.size() << "\n";
    std::cout << "  reachable nodes  : " << nodes
              << "  (internal=" << internal << ", leaves=" << leaves << ")\n";
    std::cout << "  max ply          : " << max_ply << "\n";
    std::cout << "  root width       : " << root_width
              << " moves within " << margin << "cp of best (variety at move 1)\n";
    if (internal > 0) {
        std::cout << "  avg branching    : "
                  << (static_cast<double>(edges) / internal) << " in-book children/internal\n";
        std::cout << "  avg width        : "
                  << (static_cast<double>(width_sum) / internal)
                  << " near-best (<=" << margin << "cp) moves/internal\n";
    }
    std::cout << "  ply histogram (ply: nodes):\n";
    for (std::size_t p = 0; p < ply_hist.size(); ++p)
        std::cout << "    " << p << ": " << ply_hist[p] << "\n";
    std::cout << "  wrote " << prefix << ".moves.tsv (" << internal
              << " internal) and " << prefix << ".leaves.tsv ("
              << leaves << " leaves)\n";
    return 0;
}

// --gen-scan-book: build a Scan-style opening book by DROP-OUT BEST-FIRST
// expansion (self-play). Starting from the initial position we grow a tree:
// repeatedly descend from the root following the near-optimal moves (dropping
// lines that fall more than `drop_margin` below the best), reach an
// unexpanded leaf, expand it (search every child at `leaf_depth`), and back up
// negamax values to the root. Every visited position is written to a JBK2 file
// as (zobrist → backed-up score), which ScanBook consults at play time with a
// margin + softmax pick. This is the Scan recipe: a wide-but-sound tree over
// the relevant opening moves rather than a single stored line.
//
// usage: jass --gen-scan-book <out.jbk2> [node_budget=4000] [leaf_depth=12]
//             [drop_margin=100] [max_ply=20] [threads=nproc] [eval.pjtw]
//
// `eval.pjtw` (optional) makes the builder score leaves with the SAME pattern
// eval the engine plays matches with (loaded via --pattern), so the book's
// move ordering matches actual play. Omitted → the compiled default eval.
// -----------------------------------------------------------------------------
int run_gen_scan_book_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --gen-scan-book <out.jbk2> [node_budget=4000]"
                     " [leaf_depth=12] [drop_margin=100] [max_ply=20]"
                     " [threads=nproc] [eval.pjtw]\n";
        return 1;
    }
    const char* out_path   = argv[2];
    const int node_budget  = (argc > 3) ? parse_int_or(argv[3], 4000) : 4000;
    const int leaf_depth   = (argc > 4) ? parse_int_or(argv[4], 12)   : 12;
    const int drop_margin  = (argc > 5) ? parse_int_or(argv[5], 100)  : 100;
    const int max_ply      = (argc > 6) ? parse_int_or(argv[6], 20)   : 20;
    int threads            = (argc > 7) ? parse_int_or(argv[7], 0)    : 0;
    const char* eval_path  = (argc > 8 && argv[8][0]) ? argv[8] : nullptr;
    if (threads <= 0) {
        threads = static_cast<int>(std::thread::hardware_concurrency());
        if (threads <= 0) threads = 1;
    }

    std::unique_ptr<INetwork> owned_eval;
    const INetwork* net = default_nnue();
    if (eval_path) {
        std::string perr;
        owned_eval = jass::load_eval_network(eval_path, &perr);
        if (!owned_eval) {
            std::cerr << "error: cannot load eval from " << eval_path
                      << " : " << perr << "\n";
            return 1;
        }
        net = owned_eval.get();
        std::cout << "gen-scan-book: leaf eval = " << eval_path << "\n";
    }

    // One tree node. `score` is the negamax value from the node STM's POV: a
    // leaf score from search, then max over children of -child.score once
    // expanded. `closed` marks a node that can never be expanded further
    // (terminal, at max_ply, or all children closed).
    struct Node {
        Position              pos;
        int                   ply{0};
        int                   score{0};
        bool                  expanded{false};
        bool                  closed{false};
        std::uint64_t         visits{0};
        std::vector<std::pair<Move, std::uint32_t>> kids;  // move -> node id
        std::vector<std::uint32_t> parents;
    };
    std::vector<Node> nodes;
    std::unordered_map<ZobristHash, std::uint32_t> idx;
    nodes.reserve(static_cast<std::size_t>(node_budget) * 2);

    auto leaf_eval = [&](const Position& p) -> int {
        SearchLimits lim;
        lim.max_depth = leaf_depth;
        lim.tt_mb     = 16;
        lim.nnue      = net;
        return ::jass::search(p, lim).score;
    };

    // Root.
    {
        Node root;
        root.pos   = Position::start_position();
        root.ply   = 0;
        root.score = leaf_eval(root.pos);
        idx[zobrist_hash(root.pos)] = 0;
        nodes.push_back(std::move(root));
    }

    // Recompute a node's negamax value/closed flag from its children. Returns
    // true if either changed.
    auto recompute = [&](std::uint32_t id) -> bool {
        Node& n = nodes[id];
        if (!n.expanded) return false;
        int best = -INF_SCORE;
        bool all_closed = true;
        for (const auto& [mv, cid] : n.kids) {
            const int v = -nodes[cid].score;
            if (v > best) best = v;
            if (!nodes[cid].closed) all_closed = false;
        }
        bool changed = false;
        if (best != n.score)        { n.score = best;   changed = true; }
        if (all_closed != n.closed) { n.closed = all_closed; changed = true; }
        return changed;
    };

    // Propagate a value/closed change upward through the DAG of parents. A
    // hard cap guards against the (opening-rare) possibility of a cycle.
    auto propagate = [&](std::uint32_t from) {
        std::vector<std::uint32_t> stack(nodes[from].parents.begin(),
                                         nodes[from].parents.end());
        long guard = 0;
        const long guard_cap = static_cast<long>(nodes.size()) * 8 + 1024;
        while (!stack.empty() && guard++ < guard_cap) {
            const std::uint32_t id = stack.back(); stack.pop_back();
            if (recompute(id))
                stack.insert(stack.end(), nodes[id].parents.begin(),
                                          nodes[id].parents.end());
        }
    };

    auto expand = [&](std::uint32_t id) {
        Node& n = nodes[id];
        MoveList ml;
        generate_legal_moves(n.pos, ml);
        if (ml.empty()) {                          // terminal: STM has lost
            n.expanded = true;
            n.closed   = true;
            n.score    = -MATE_SCORE + n.ply;
            propagate(id);
            return;
        }
        // Collect children: reuse existing nodes on transposition, else create
        // and score the new ones in parallel.
        struct NewKid { Move m; Position pos; ZobristHash key; int slot; };
        std::vector<std::pair<Move, std::uint32_t>> existing;  // move, node id
        std::vector<NewKid> fresh;
        for (const auto& m : ml) {
            const Position child = n.pos.after(m);
            const ZobristHash key = zobrist_hash(child);
            const auto it = idx.find(key);
            if (it != idx.end()) existing.push_back({m, it->second});
            else fresh.push_back({m, child, key,
                                  static_cast<int>(fresh.size())});
        }
        std::vector<int> fresh_score(fresh.size(), 0);
        const int nthr = std::min<int>(threads,
                                       std::max<std::size_t>(1, fresh.size()));
        std::atomic<std::size_t> next{0};
        auto worker = [&]() {
            for (;;) {
                const std::size_t i = next.fetch_add(1);
                if (i >= fresh.size()) break;
                fresh_score[i] = leaf_eval(fresh[i].pos);
            }
        };
        std::vector<std::thread> pool;
        for (int t = 1; t < nthr; ++t) pool.emplace_back(worker);
        worker();
        for (auto& th : pool) th.join();

        // Materialise children (order does not matter for backup).
        for (const auto& [m, cid] : existing) {
            nodes[id].kids.push_back({m, cid});
            nodes[cid].parents.push_back(id);
        }
        for (std::size_t i = 0; i < fresh.size(); ++i) {
            Node c;
            c.pos    = fresh[i].pos;
            c.ply    = nodes[id].ply + 1;
            c.score  = fresh_score[i];
            c.closed = (c.ply >= max_ply);          // depth cap: never expanded
            const std::uint32_t cid = static_cast<std::uint32_t>(nodes.size());
            c.parents.push_back(id);
            idx[fresh[i].key] = cid;
            nodes.push_back(std::move(c));
            nodes[id].kids.push_back({fresh[i].m, cid});
        }
        nodes[id].expanded = true;
        recompute(id);
        propagate(id);
    };

    // Drop-out best-first descent: from the root, follow near-optimal,
    // non-closed children (preferring the least-visited to widen the tree)
    // until an unexpanded leaf is found. Returns UINT32_MAX when the root is
    // closed (whole relevant tree explored to the cap).
    auto select_leaf = [&]() -> std::uint32_t {
        for (;;) {
            std::uint32_t cur = 0;
            std::vector<std::uint32_t> path = {0};
            bool restart = false;
            for (;;) {
                Node& n = nodes[cur];
                if (!n.expanded && !n.closed) return cur;   // leaf to expand
                if (n.closed) {                              // shouldn't descend
                    if (cur == 0) return UINT32_MAX;
                    restart = true; break;
                }
                int best = -INF_SCORE;
                for (const auto& [mv, cid] : n.kids)
                    best = std::max(best, -nodes[cid].score);
                std::uint32_t pick = UINT32_MAX;
                std::uint64_t pick_visits = 0;
                int pick_val = 0;
                for (const auto& [mv, cid] : n.kids) {
                    if (nodes[cid].closed) continue;
                    const int v = -nodes[cid].score;
                    if (v + drop_margin < best) continue;    // dropped out
                    bool on_path = false;
                    for (auto pid : path) if (pid == cid) { on_path = true; break; }
                    if (on_path) continue;
                    if (pick == UINT32_MAX
                        || nodes[cid].visits < pick_visits
                        || (nodes[cid].visits == pick_visits && v > pick_val)) {
                        pick = cid; pick_visits = nodes[cid].visits; pick_val = v;
                    }
                }
                if (pick == UINT32_MAX) {            // dead end: close & retry
                    n.closed = true;
                    propagate(cur);
                    if (cur == 0) return UINT32_MAX;
                    restart = true; break;
                }
                nodes[pick].visits++;
                cur = pick;
                path.push_back(cur);
            }
            if (restart) continue;
        }
    };

    std::cout << "gen-scan-book: budget=" << node_budget
              << " leaf_depth=" << leaf_depth
              << " drop_margin=" << drop_margin
              << " max_ply=" << max_ply
              << " threads=" << threads << "\n";

    int expansions = 0;
    while (static_cast<int>(nodes.size()) < node_budget) {
        const std::uint32_t leaf = select_leaf();
        if (leaf == UINT32_MAX) {
            std::cout << "  root closed — relevant tree fully explored\n";
            break;
        }
        expand(leaf);
        if (++expansions % 100 == 0) {
            std::cout << "  expansions=" << expansions
                      << " nodes=" << nodes.size()
                      << " root_score=" << nodes[0].score << "\n";
        }
    }

    // Persist every node's backed-up score.
    ScanBook book;
    int max_reached = 0;
    for (const auto& n : nodes) {
        book.put(zobrist_hash(n.pos), n.score);
        max_reached = std::max(max_reached, n.ply);
    }
    if (!book.save(out_path)) {
        std::cerr << "error: cannot write " << out_path << "\n";
        return 1;
    }
    std::cout << "wrote " << book.size() << " positions to " << out_path
              << " (expansions=" << expansions
              << ", max_ply_reached=" << max_reached
              << ", root_score=" << nodes[0].score << ")\n";
    return 0;
}

// --build-book: read a list of FENs (one per line, `#` comments OK), evaluate
// each one with the current default NNUE at the requested depth and write a
// JBOK file mapping (zobrist → best move). Used to pre-compute an opening
// book over a curated position set; the resulting file is then loaded by the
// HUB front-end via `--book <path>`.
// -----------------------------------------------------------------------------
int run_build_book_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --build-book <fens.txt> <out.bok> [depth=12]\n";
        return 1;
    }
    const char* fens_path = argv[2];
    const char* out_path  = argv[3];
    const int   depth     = (argc > 4) ? parse_int_or(argv[4], 12) : 12;

    std::ifstream in(fens_path);
    if (!in) {
        std::cerr << "error: cannot open " << fens_path << "\n";
        return 1;
    }

    Engine e;
    e.use_book(false);                       // don't consult what we're building
    e.set_nnue(default_nnue());

    Book out_book;
    std::string line;
    int line_no    = 0;
    int processed  = 0;
    int skipped    = 0;
    while (std::getline(in, line)) {
        ++line_no;
        // Trim trailing CR (Windows line endings) + leading/trailing space.
        while (!line.empty() && (line.back() == ' ' || line.back() == '\r'
                              || line.back() == '\t'))
            line.pop_back();
        std::size_t start = 0;
        while (start < line.size() && (line[start] == ' '
                                    || line[start] == '\t'))
            ++start;
        if (start > 0) line.erase(0, start);

        if (line.empty() || line[0] == '#') continue;

        // Allow `FEN<TAB>extra,columns` — we keep only the first whitespace
        // token as the FEN string.
        std::size_t ws = line.find_first_of(" \t");
        const std::string fen = (ws == std::string::npos) ? line
                                                          : line.substr(0, ws);

        const auto pos_opt = Position::from_fen(fen);
        if (!pos_opt) {
            std::cerr << "warn: line " << line_no
                      << ": invalid FEN, skipping: " << fen << "\n";
            ++skipped;
            continue;
        }
        e.set_position(*pos_opt);
        SearchLimits lim;
        lim.max_depth = depth;
        const SearchResult r = e.search(lim);
        out_book.put(zobrist_hash(*pos_opt), r.best_move, r.score, depth);
        ++processed;
        if (processed % 100 == 0) {
            std::cout << "  processed " << processed << " positions"
                      << " (skipped " << skipped << ")\n";
        }
    }

    if (!out_book.save(out_path)) {
        std::cerr << "error: cannot write " << out_path << "\n";
        return 1;
    }
    std::cout << "wrote " << out_book.size() << " entries to "
              << out_path << " (skipped " << skipped << " invalid lines)\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --build-book-from-moves: read a TSV of (FEN<TAB>move) pairs and write a
// JBOK file mapping (zobrist → move). Unlike --build-book it does not run a
// search; each row is taken as-is. Used to assemble a master-game-frequency
// book (the upstream Python tool picks the most-played master move per
// position and feeds the result here).
// -----------------------------------------------------------------------------
int run_build_book_from_moves_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --build-book-from-moves <pairs.txt> <out.bok>\n";
        return 1;
    }
    const char* in_path  = argv[2];
    const char* out_path = argv[3];

    std::ifstream in(in_path);
    if (!in) {
        std::cerr << "error: cannot open " << in_path << "\n";
        return 1;
    }

    Book out_book;
    std::string line;
    int line_no = 0;
    int added   = 0;
    int skipped = 0;
    while (std::getline(in, line)) {
        ++line_no;
        while (!line.empty() && (line.back() == ' ' || line.back() == '\r'
                              || line.back() == '\t'))
            line.pop_back();
        if (line.empty() || line[0] == '#') continue;

        const std::size_t tab = line.find('\t');
        if (tab == std::string::npos) {
            std::cerr << "warn: line " << line_no << ": no TAB, skipping\n";
            ++skipped; continue;
        }
        const std::string fen  = line.substr(0, tab);
        const std::string mv_s = line.substr(tab + 1);

        const auto pos_opt = Position::from_fen(fen);
        if (!pos_opt) {
            std::cerr << "warn: line " << line_no
                      << ": invalid FEN, skipping\n";
            ++skipped; continue;
        }
        const auto mv_opt = parse_move(*pos_opt, mv_s);
        if (!mv_opt) {
            std::cerr << "warn: line " << line_no
                      << ": cannot parse move '" << mv_s << "', skipping\n";
            ++skipped; continue;
        }
        out_book.put(zobrist_hash(*pos_opt), *mv_opt, 0, 0);
        ++added;
        if (added % 1000 == 0)
            std::cout << "  added " << added << " entries\n";
    }
    if (!out_book.save(out_path)) {
        std::cerr << "error: cannot write " << out_path << "\n";
        return 1;
    }
    std::cout << "wrote " << out_book.size() << " entries to "
              << out_path << " (added=" << added
              << ", skipped=" << skipped << ")\n";
    return 0;
}

// Sister of --bench-eval that calls a NetworkServerClient instead of
// an in-process INetwork. Measures the round-trip IPC overhead of the
// Phase-0 eval-server prototype (see tools/nnue_eval_server.py +
// src/nnue_server_client.cpp).
int run_bench_eval_server_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --bench-eval-server <socket_path> [iters=100000]\n";
        return 1;
    }
    const char* sock_path = argv[2];
    const long long iters = (argc > 3) ? std::max<long long>(1,
        parse_int_or(argv[3], 100000)) : 100000;

    NetworkServerClient client;
    if (!client.connect(sock_path)) {
        std::cerr << "error: cannot connect to " << sock_path << "\n";
        return 1;
    }

    const auto pos_opt = Position::from_fen(
        "B:W26,29,31,32,38,42,43,46,47,K48:B3,5,9,11,12,14,16,18,K22,K25");
    if (!pos_opt) return 1;
    const Position pos = *pos_opt;

    int sink = 0;
    for (int i = 0; i < 1000; ++i) sink ^= client.evaluate(pos);  // warmup

    using clock = std::chrono::steady_clock;
    const auto t0 = clock::now();
    for (long long i = 0; i < iters; ++i) sink ^= client.evaluate(pos);
    const auto t1 = clock::now();
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count();

    const double ns_per_call = static_cast<double>(ns) / static_cast<double>(iters);
    const double evals_per_s = 1e9 / ns_per_call;
    std::cout << "bench-eval-server: socket=" << sock_path
              << " iters=" << iters
              << " total_ns=" << ns
              << " ns/call=" << ns_per_call
              << " evals/s=" << evals_per_s
              << " sink=" << sink << '\n';
    return 0;
}

// Micro-benchmark for raw NNUE evaluate() throughput. Loads `weights`,
// picks a midgame position, calls evaluate() in a tight loop, reports
// ns/call and evals/sec. Used to validate the SIMD Layer-1 refactor —
// scalar vs AVX2 column add — without paying for search overhead.
int run_bench_eval_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --bench-eval <weights.bin> [iters=1000000]\n";
        return 1;
    }
    const char* weights_path = argv[2];
    const long long iters = (argc > 3) ? std::max<long long>(1,
        parse_int_or(argv[3], 1000000)) : 1000000;

    std::unique_ptr<INetwork> net;
    {
        const std::string p{weights_path};
        const bool is_pjtw = p.size() >= 5
                          && p.compare(p.size() - 5, 5, ".pjtw") == 0;
        std::string err;
        net = is_pjtw ? jass::load_eval_network(p, &err) : load_network(p);
    }
    if (!net) {
        std::cerr << "error: cannot load weights from " << weights_path << "\n";
        return 1;
    }

    // A midgame-ish position with both colours having men + kings.
    const auto pos_opt = Position::from_fen(
        "B:W26,29,31,32,38,42,43,46,47,K48:B3,5,9,11,12,14,16,18,K22,K25");
    if (!pos_opt) {
        std::cerr << "error: built-in benchmark FEN failed to parse\n";
        return 1;
    }
    const Position pos = *pos_opt;

    // Warmup so any first-call cost (TLB, branch predictor) doesn't bias
    // the measurement.
    int sink = 0;
    for (int i = 0; i < 10000; ++i) sink ^= net->evaluate(pos);

    using clock = std::chrono::steady_clock;
    const auto t0 = clock::now();
    for (long long i = 0; i < iters; ++i) sink ^= net->evaluate(pos);
    const auto t1 = clock::now();
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count();

    const double ns_per_call  = static_cast<double>(ns) / static_cast<double>(iters);
    const double evals_per_s  = 1e9 / ns_per_call;
    std::cout << "bench-eval: weights=" << weights_path
              << " iters=" << iters
              << " total_ns=" << ns
              << " ns/call=" << ns_per_call
              << " evals/s=" << evals_per_s
              << " sink=" << sink << '\n';
    return 0;
}

int run_tournament_mode(int argc, char** argv) {
    // Usage: --tournament [depth_a] [depth_b] [pairs]
    // Defaults: depth_a=4, depth_b=6, pairs=1 (so 2 games total).
    int depth_a = 4, depth_b = 6, pairs = 1;
    if (argc > 2) depth_a = parse_int_or(argv[2], depth_a);
    if (argc > 3) depth_b = parse_int_or(argv[3], depth_b);
    if (argc > 4) pairs   = parse_int_or(argv[4], pairs);

    EngineConfig a; a.max_depth = depth_a;
    EngineConfig b; b.max_depth = depth_b;

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());
    std::cout << "Tournament: A(depth=" << depth_a
              << ") vs B(depth=" << depth_b
              << "), " << total_games << " games "
              << "(" << pool.size() << " openings × " << pairs
              << " pairs × 2 colours)\n";

    const TournamentResult r = run_tournament(a, b, pairs);
    std::cout << "Result: A=" << r.a_wins
              << " B="        << r.b_wins
              << " Draws="    << r.draws
              << " (total "   << r.games << ")\n";
    return 0;
}

int main(int argc, char** argv) {
    // First pass: one-shot subcommands. These short-circuit before the
    // HUB loop is ever started.
    for (int i = 1; i < argc; ++i) {
        const std::string_view a{argv[i]};
        if      (a == "--smoke")                    return run_smoke();
        else if (a == "--tournament")               return run_tournament_mode(argc, argv);
        else if (a == "--bench-eval")               return run_bench_eval_mode(argc, argv);
        else if (a == "--bench-eval-server")        return run_bench_eval_server_mode(argc, argv);
        else if (a == "--gen-data")                 return run_gen_data_mode(argc, argv);
        else if (a == "--gen-data-wdl")             return run_gen_data_wdl_mode(argc, argv);
        else if (a == "--gen-tdleaf")               return run_gen_tdleaf_mode(argc, argv);
        else if (a == "--rewrite-scores-with-nnue") return run_rewrite_scores_with_nnue_mode(argc, argv);
        else if (a == "--rewrite-scores-with-search") return run_rewrite_scores_with_search_mode(argc, argv);
        else if (a == "--rewrite-scores-with-handcrafted") return run_rewrite_scores_with_handcrafted_mode(argc, argv);
        else if (a == "--dump-features")            return run_dump_features_mode(argc, argv);
        else if (a == "--dump-eval-features")       return run_dump_eval_features_mode(argc, argv);
        else if (a == "--dump-conditional-context-v2") return run_dump_conditional_context_v2_mode(argc, argv);
        else if (a == "--dump-quiet-flags")         return run_dump_quiet_flags_mode(argc, argv);
        else if (a == "--symmetry-augment")         return run_symmetry_augment_mode(argc, argv);
        else if (a == "--eval-position")            return run_eval_position_mode(argc, argv);
        else if (a == "--benchmark-nnue")           return run_benchmark_nnue_mode(argc, argv);
        else if (a == "--benchmark-nnue-vs-nnue")   return run_benchmark_nnue_vs_nnue_mode(argc, argv);
        else if (a == "--benchmark-nnue-hybrid")    return run_benchmark_nnue_hybrid_mode(argc, argv);
        else if (a == "--benchmark-search-params")  return run_benchmark_search_params_mode(argc, argv);
        else if (a == "--benchmark-pattern-jass")   return run_benchmark_pattern_jass_mode(argc, argv);
        else if (a == "--benchmark-pattern-vs-nnue") return run_benchmark_pattern_vs_nnue_mode(argc, argv);
        else if (a == "--benchmark-scan-eval")      return run_benchmark_scan_eval_mode(argc, argv);
        else if (a == "--depth-at-movetime")        return run_depth_at_movetime_mode(argc, argv);
        else if (a == "--search-profile")           return run_search_profile_mode(argc, argv);
        else if (a == "--dump-sacs")                return run_dump_sacs_mode(argc, argv);
        else if (a == "--benchmark-pattern-jass-nnue-skel") return run_benchmark_pattern_jass_nnue_skel_mode(argc, argv);
        else if (a == "--gen-scan-book")            return run_gen_scan_book_mode(argc, argv);
        else if (a == "--book-audit")               return run_book_audit_mode(argc, argv);
        else if (a == "--build-book")               return run_build_book_mode(argc, argv);
        else if (a == "--build-book-from-moves")    return run_build_book_from_moves_mode(argc, argv);
        else if (a == "--perft")                    return run_perft_mode(argc, argv);
        else if (a == "--dump-legal")               return run_dump_legal_mode(argc, argv);
        else if (a == "--dump-children")            return run_dump_children_mode(argc, argv);
        else if (a == "--replay-moves")             return run_replay_moves_mode(argc, argv);
        else if (a == "--egdb-selfcheck")           return run_egdb_selfcheck_mode(argc, argv);
        else if (a == "--egdb-audit")               return run_egdb_audit_mode(argc, argv);
        else if (a == "--egdb-relabel")             return run_egdb_relabel_mode(argc, argv);
        else if (a == "--deep-relabel")             return run_deep_relabel_mode(argc, argv);
        else if (a == "--gen-siblings")             return run_gen_siblings_mode(argc, argv);
        else if (a == "--gen-opening-pool")          return run_gen_opening_pool_mode(argc, argv);
        else if (a == "--gen-egdb-wld")             return run_gen_egdb_wld_mode(argc, argv);
        else if (a == "--eval-selfcheck")           return run_eval_selfcheck_mode(argc, argv);
        else if (a == "--egdb-mtc-probe")           return run_egdb_mtc_probe_mode(argc, argv);
        else if (a == "--egdb-mtc-regret")          return run_egdb_mtc_regret_mode(argc, argv);
        else if (a == "--egdb-conversion-test")     return run_egdb_conversion_test_mode(argc, argv);
        else if (a == "--egdb-mtc-relabel")         return run_egdb_mtc_relabel_mode(argc, argv);
        else if (a == "--version") { std::cout << "Jass 0.0.1\n"; return 0; }
        else if (a == "--help") {
            std::cout <<
                "Usage: jass [--smoke|--tournament [a b pairs]|"
                            "--gen-data [N path]|--benchmark-nnue weights [d p]|"
                            "--benchmark-nnue-vs-nnue a.bin b.bin [d p]|"
                            "--build-book fens.txt out.bok [depth]|"
                            "--build-book-from-moves pairs.txt out.bok|"
                            "--no-nnue|--nnue path|--book path|--no-book|"
                            "--version|--help]\n"
                "Default: read HUB-style commands from stdin.\n"
                "  --smoke                          run a self-contained demo\n"
                "  --tournament [da db pairs]       play a colour-swap match\n"
                "                                   between depth-da and depth-db\n"
                "                                   engines (default 4 vs 6, 2 games)\n"
                "  --gen-data [N path]              write N self-play training\n"
                "                                   records to <path> (default\n"
                "                                   10000 to selfplay.bin)\n"
                "  --benchmark-nnue <weights.bin> [depth=6] [pairs=1]\n"
                "                                   pit a trained NNUE (loaded\n"
                "                                   from <weights.bin>) against\n"
                "                                   the handcrafted eval. Plays\n"
                "                                   2*pairs games per opening\n"
                "                                   from the default opening pool.\n"
                "  --benchmark-nnue-vs-nnue <a.bin> <b.bin> [depth=6] [pairs=1]\n"
                "                                   same colour-swap match but\n"
                "                                   between two NNUE networks\n"
                "                                   (any combination of Linear /\n"
                "                                   MLP, auto-detected by magic).\n"
                "  --no-nnue                        HUB mode only — disable the\n"
                "                                   embedded default NNUE and use\n"
                "                                   the handcrafted eval instead.\n"
                "  --egdb-audit <in.jnnw> <db_dir> [cache_mb]   (lecture seule)\n"
                "  --egdb-relabel <in.jnnw> <db_dir> [out.jnnw] [cache_mb]\n"
                "                                   rewrite WDL labels of <=7-piece\n"
                "                                   positions with the EXACT egdb result.\n"
                "  --deep-relabel <in.jnnw> <out.jnnw> [depth=18] [--nnue PATH] [--label-depth-by-phase SPEC] [--egdb DIR]\n"
                "                                   rewrite the SCORE field with a DEEP\n"
                "                                   search value (independent value-target\n"
                "                                   distillation) ; --egdb anchors endgames exactly.\n"
                "  --gen-egdb-wld <N> <out.jnnw> <db_dir> [max_pieces=7] [cache_mb] [seed]\n"
                "                                   emit N random quiet endgame positions\n"
                "                                   labelled with the exact egdb WLD.\n"
                "  --gen-opening-pool <N> <out.fen> [min_ply=8] [max_ply=32] [min_pieces=20] [seed=0]\n"
                "                                   emit deterministic unique legal quiet\n"
                "                                   midgame positions reached from startpos.\n"
                "  --gen-data-wdl <N> <path> [eval_depth=12] [play_depth=4] [max_plies=200] [seed=0] [--nnue PATH] [--movetime MS] [--play-depth-by-phase SPEC] [--search-limit depth|nodes] [--node-budget-fixed N | --node-budget-weighted N:W,...] [--node-budget-sample-per move|game] [--node-budget-log PATH] [--seed-file F --seed-frac P [--seed-without-replacement]] [--random-open-plies K] [--explore-eps E] [--explore-topk K] [--explore-margin M] [--quiet-only] [--sample-initial] [--wdl-zero-score] [--drop-plycap] [--sample-meta-out PATH] [--sample-meta-format jsm1|jsm2]\n"
                "                                   write N records with the\n"
                "                                   game outcome label (WDL).\n"
                "                                   --wdl-zero-score skips the\n"
                "                                   unused score-label search.\n"
                "                                   --random-open-plies K : K random\n"
                "                                   opening plies (default 4). --explore-eps E :\n"
                "                                   play E%% of plies as a random legal move\n"
                "                                   (off-policy μ widening).\n"
                "                                   --sample-initial always keeps ply 0 of each\n"
                "                                   played game (subject to --quiet-only).\n"
                "                                   --drop-plycap excludes every sample from\n"
                "                                   games unresolved at max_plies instead of\n"
                "                                   fabricating a DRAW label. --sample-meta-out\n"
                "                                   writes aligned metadata; JSM1 is the compatible\n"
                "                                   default, JSM2 adds ply/game context and flags.\n"
                "                                   --search-limit nodes requires exactly one\n"
                "                                   fixed/weighted budget plus --node-budget-log.\n"
                "                                   Weighted syntax is NODES:WEIGHT,...; the\n"
                "                                   deterministic default granularity is move.\n"
                "                                   --play-depth-by-phase\n"
                "                                   \"endgame=12,deep-eg=14\" PLAYS\n"
                "                                   those phases at a DEEPER search\n"
                "                                   (others keep play_depth) so the\n"
                "                                   endgame WDL outcomes are accurate\n"
                "                                   — the corrected endgame lever\n"
                "                                   (the loop trains on WDL, so play\n"
                "                                   endgames well, don't deepen the\n"
                "                                   unused label score or weight rows).\n"
                "                                   Higher eval_depth = cleaner\n"
                "                                   training signal; non-zero\n"
                "                                   `seed` shifts the RNG state\n"
                "                                   so parallel shards generate\n"
                "                                   independent games. Passing\n"
                "                                   `--nnue PATH` labels with that\n"
                "                                   custom network instead of the\n"
                "                                   embedded default (used to relabel\n"
                "                                   self-play data with the latest\n"
                "                                   NNUE for a Cycle N+1 retraining).\n"
                "  --build-book <fens.txt> <out.bok> [depth=12]\n"
                "                                   read FENs (one per line, #\n"
                "                                   comments OK) and write a JBOK\n"
                "                                   book with the engine's best\n"
                "                                   move at each position.\n"
                "  --build-book-from-moves <pairs.txt> <out.bok>\n"
                "                                   read FEN<TAB>move pairs and\n"
                "                                   write a JBOK book with the\n"
                "                                   given move at each position\n"
                "                                   (no search, takes rows as-is).\n"
                "  --book <path.bok>                HUB mode only — load an\n"
                "                                   opening book from <path.bok>\n"
                "                                   (replaces the hard-coded\n"
                "                                   default lines).\n"
                "  --nnue <weights.bin>             HUB mode only — load and use\n"
                "                                   <weights.bin> in place of the\n"
                "                                   embedded default NNUE.\n"
                "  --version                        print the engine version\n";
            return 0;
        }
    }

    // Second pass: HUB-mode flags.
    std::unique_ptr<INetwork> nnue_owned;
    std::unique_ptr<NetworkServerClient> nnue_server;
    const INetwork* nnue_ptr = default_nnue();  // embedded shipped weights
    const char*     book_path = nullptr;
    bool            disable_book = false;           // --no-book
    const char*     search_params_spec = nullptr;  // --search-params "k=v,k=v"
    int             tt_mb_override = 0;             // --tt-mb N (0 = default 16)
    for (int i = 1; i < argc; ++i) {
        const std::string_view a{argv[i]};
        if (a == "--no-nnue") {
            nnue_ptr = nullptr;
        } else if (a == "--nnue" && i + 1 < argc) {
            nnue_owned = load_network(argv[++i]);
            if (!nnue_owned) {
                std::cerr << "error: cannot load NNUE weights from "
                          << argv[i] << "\n";
                return 2;
            }
            nnue_ptr = nnue_owned.get();
        } else if (a == "--nnue-server" && i + 1 < argc) {
            nnue_server = std::make_unique<NetworkServerClient>();
            if (!nnue_server->connect(argv[++i])) {
                std::cerr << "error: cannot connect to NNUE server at "
                          << argv[i] << "\n";
                return 2;
            }
            nnue_ptr = nnue_server.get();
        } else if (a == "--pattern" && i + 1 < argc) {
            // HUB mode only — play with a PatternJassNetwork eval instead
            // of an NNUE, so the engine can be benchmarked vs Scan with a
            // pattern eval (the pattern is an INetwork too).
            std::string perr;
            nnue_owned = jass::load_eval_network(argv[++i], &perr);
            if (!nnue_owned) {
                std::cerr << "error: cannot load pattern weights from "
                          << argv[i] << " : " << perr << "\n";
                return 2;
            }
            nnue_ptr = nnue_owned.get();
        } else if (a == "--book" && i + 1 < argc) {
            book_path = argv[++i];
        } else if (a == "--no-book") {
            // Play every ply from search. Scan is habitually driven with
            // `book=off` in our calibration harnesses; without this the Jass
            // side kept its built-in book and the match was asymmetric.
            disable_book = true;
        } else if (a == "--search-params" && i + 1 < argc) {
            // Override the HUB engine's search constants (LMR/pruning/etc.)
            // from a "k=v,k=v" spec — lets calibrate_vs_scan tune search vs
            // Scan without a rebuild. Keys: see src/search_params.hpp.
            search_params_spec = argv[++i];
        } else if (a == "--tt-mb" && i + 1 < argc) {
            tt_mb_override = std::atoi(argv[++i]);
        }
    }

    HubFrontEnd hub(std::cin, std::cout);
    hub.set_nnue(nnue_ptr);
    if (search_params_spec) {
        hub.set_search_params(jass::parse_search_params(search_params_spec));
    }
    if (tt_mb_override > 0) {
        hub.set_tt_mb(static_cast<std::size_t>(tt_mb_override));
    }
    if (book_path) {
        if (!hub.load_book(book_path)) {
            std::cerr << "error: cannot load book from " << book_path << "\n";
            return 2;
        }
    }
    // After load_book so that `--book X --no-book` is an explicit, if odd,
    // "load it but do not consult it" rather than a silent contradiction.
    if (disable_book) {
        hub.use_book(false);
    }
    return hub.run();
}
