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
#include "scan_eval.hpp"
#include "search.hpp"
#include "tournament.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <random>
#include <string>
#include <vector>
#include <string_view>

using namespace jass;

namespace {

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
//    4 B  int32    score       (centipawn, STM-POV, depth-eval search)
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
    int          pv_extract       = 0;      // additional samples to harvest along the PV
    int          movetime_ms      = 0;      // >0 → play moves by wall-clock (Scan-style
                                            //      self-play); play_depth becomes a cap
    std::string  label_depth_spec;          // "endgame=16,deep-eg=20" → deeper LABEL
                                            //      search by phase (empty = eval_depth)
    std::string  play_depth_spec;           // "endgame=12,deep-eg=14" → deeper PLAY
                                            //      search by phase → accurate endgame WDL

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
        } else if (a == "--pv-extract" && i + 1 < argc) {
            const int v = parse_int_or(argv[++i], -1);
            if (v >= 0) pv_extract = v;
        } else if (a == "--movetime" && i + 1 < argc) {
            const int v = parse_int_or(argv[++i], -1);
            if (v >= 0) movetime_ms = v;
        } else if (a == "--label-depth-by-phase" && i + 1 < argc) {
            label_depth_spec = argv[++i];
        } else if (a == "--play-depth-by-phase" && i + 1 < argc) {
            play_depth_spec = argv[++i];
        } else {
            positional.push_back(argv[i]);
        }
    }
    const std::array<int, NUM_PHASES> label_depth =
        parse_depth_by_phase(label_depth_spec, "--label-depth-by-phase");
    const std::array<int, NUM_PHASES> play_depth_by_phase =
        parse_depth_by_phase(play_depth_spec, "--play-depth-by-phase");
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

    std::cout << "gen-data-wdl: n=" << n
              << " out=" << out_path
              << " eval_depth=" << eval_depth
              << " play_depth=" << play_depth
              << " max_plies=" << max_plies
              << " seed=" << (random_seed > 0 ? std::to_string(random_seed) : "default")
              << " nnue=" << (nnue_path ? nnue_path : "(default embedded)")
              << " quiet_only=" << (quiet_only ? "true" : "false")
              << " pv_extract=" << pv_extract
              << " movetime_ms=" << movetime_ms;
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

    std::ofstream f(out_path, std::ios::binary);
    if (!f) {
        std::cerr << "error: cannot open " << out_path << " for writing\n";
        return 1;
    }

    const char magic[4] = {'J', 'N', 'N', 'W'};
    f.write(magic, 4);
    std::uint32_t count_placeholder = 0;
    f.write(reinterpret_cast<const char*>(&count_placeholder), 4);

    // Splitmix-style scrambling of the user-provided seed so two
    // shards launched with seeds 1 and 2 yield trajectories that are
    // statistically independent (close seeds + linear PRNG → barely
    // correlated streams which would waste compute).
    const std::uint64_t seed_value = (random_seed > 0)
        ? static_cast<std::uint64_t>(static_cast<std::uint32_t>(random_seed))
              * std::uint64_t{0x9E3779B97F4A7C15}
        : std::uint64_t{0x5eed5eed5eed5eed};
    std::mt19937_64 rng(seed_value);
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
    };
    std::vector<Sample> game_samples;
    game_samples.reserve(64);

    int generated  = 0;
    int game_count = 0;

    while (generated < n) {
        ++game_count;
        e.new_game();
        game_samples.clear();

        for (int i = 0; i < random_open_plies; ++i) {
            MoveList ml;
            generate_legal_moves(e.position(), ml);
            if (ml.empty()) break;
            e.apply_move(ml[rng() % ml.size()]);
        }

        // Game outcome from the final position: +1 = white won, -1 = black
        // won, 0 = draw. Initialised to "draw" because the ply-cap exit
        // path treats unresolved games as drawn.
        int outcome_white = 0;
        bool game_ended_by_loss = false;

        for (int ply = 0; ply < max_plies; ++ply) {
            MoveList ml;
            generate_legal_moves(e.position(), ml);
            if (ml.empty()) {
                // STM has no moves → STM loses.
                outcome_white = (e.position().side_to_move() == Color::White)
                              ? -1 : +1;
                game_ended_by_loss = true;
                break;
            }
            if (e.position().halfmove_clock() >= FIFTY_MOVE_PLIES) {
                // 25-move rule: declare a draw.
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
            const bool sample_now     = (rng() & 3) == 0
                                     && generated + static_cast<int>(game_samples.size()) < n
                                     && (!quiet_only || position_quiet);
            if (sample_now) {
                const Position&    pos = e.position();
                // Phase-dependent LABEL depth : spend deeper search where the
                // linear eval is weakest (endgames), keep opening labels cheap.
                // Default (no spec) = eval_depth everywhere (back-compatible).
                const int phase_ovr = label_depth[phase_index_of(popcount(pos.occupied()))];
                const int this_label_depth = (phase_ovr > 0) ? phase_ovr : eval_depth;
                SearchLimits lim;
                lim.max_depth = this_label_depth;
                const SearchResult r = e.search(lim);
                Sample s;
                s.bbs[0] = pos.white_men();
                s.bbs[1] = pos.white_kings();
                s.bbs[2] = pos.black_men();
                s.bbs[3] = pos.black_kings();
                s.stm    = (pos.side_to_move() == Color::White) ? 0 : 1;
                s.score  = static_cast<std::int32_t>(r.score);
                game_samples.push_back(s);

                // L1 multi-extraction (Stockfish `gensfen`-style). Amortize
                // the depth-`eval_depth` search over multiple labels by
                // harvesting positions along the principal variation. By
                // negamax definition, the score at PV ply k from THAT
                // position's STM POV is (-1)^k * r.score, so we can attach
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
                if (pv_extract > 0 && !r.pv.empty()) {
                    constexpr int PV_STRIDE        = 2;
                    constexpr int PV_MIN_EFF_DEPTH = 8;
                    Position pv_pos = pos;
                    int      taken  = 0;
                    for (std::size_t k = 0;
                         k < r.pv.size() && taken < pv_extract;
                         ++k) {
                        pv_pos = pv_pos.after(r.pv[k]);
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
                                      ? -static_cast<std::int32_t>(r.score)
                                      :  static_cast<std::int32_t>(r.score);
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
            lim.max_depth = (phase_pd > 0) ? phase_pd : play_depth;
            if (movetime_ms > 0) lim.movetime_ms = movetime_ms;
            const SearchResult r = e.search(lim);
            if (!e.apply_move(r.best_move)) break;
        }

        // Flush this game's samples with the resolved WDL label. WDL is
        // computed from each sample's STM perspective: +1 means "the side
        // to move at sample time eventually won".
        for (const Sample& s : game_samples) {
            int wdl = 0;
            if (game_ended_by_loss) {
                const int sample_stm_sign = (s.stm == 0) ? +1 : -1;
                wdl = outcome_white * sample_stm_sign;
            }
            const std::int8_t wdl_byte = static_cast<std::int8_t>(wdl);

            f.write(reinterpret_cast<const char*>(s.bbs), 32);
            f.write(reinterpret_cast<const char*>(&s.stm), 1);
            f.write(reinterpret_cast<const char*>(&s.score), 4);
            f.write(reinterpret_cast<const char*>(&wdl_byte), 1);
            ++generated;
            if (generated >= n) break;
        }

        if ((game_count % 50) == 0) {
            std::cout << "  played " << game_count << " games, "
                      << generated << " / " << n << " positions\n";
        }
    }

    f.seekp(4, std::ios::beg);
    const std::uint32_t count32 = static_cast<std::uint32_t>(generated);
    f.write(reinterpret_cast<const char*>(&count32), 4);
    f.close();

    std::cout << "wrote " << generated << " WDL records to " << out_path << "\n";
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
// Used for G2 of docs/SCAN_METHODOLOGY_GAP.md (knowledge distillation):
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

    std::unique_ptr<INetwork> net_a = load_network(path_a);
    if (!net_a) {
        std::cerr << "error: cannot load weights from " << path_a << "\n";
        return 1;
    }
    std::unique_ptr<INetwork> net_b = load_network(path_b);
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
// profondeur fixe — gate Option H. Cf docs/PARADIGM_SHIFT_OPTIONS.md §H.
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
        else if (a == "--benchmark-pattern-jass-nnue-skel") return run_benchmark_pattern_jass_nnue_skel_mode(argc, argv);
        else if (a == "--build-book")               return run_build_book_mode(argc, argv);
        else if (a == "--build-book-from-moves")    return run_build_book_from_moves_mode(argc, argv);
        else if (a == "--perft")                    return run_perft_mode(argc, argv);
        else if (a == "--version") { std::cout << "Jass 0.0.1\n"; return 0; }
        else if (a == "--help") {
            std::cout <<
                "Usage: jass [--smoke|--tournament [a b pairs]|"
                            "--gen-data [N path]|--benchmark-nnue weights [d p]|"
                            "--benchmark-nnue-vs-nnue a.bin b.bin [d p]|"
                            "--build-book fens.txt out.bok [depth]|"
                            "--build-book-from-moves pairs.txt out.bok|"
                            "--no-nnue|--nnue path|--book path|--version|--help]\n"
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
                "  --gen-data-wdl <N> <path> [eval_depth=12] [play_depth=4] [max_plies=200] [seed=0] [--nnue PATH] [--movetime MS] [--play-depth-by-phase SPEC]\n"
                "                                   write N records with the\n"
                "                                   game outcome label (WDL).\n"
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
        }
    }

    HubFrontEnd hub(std::cin, std::cout);
    hub.set_nnue(nnue_ptr);
    if (book_path) {
        if (!hub.load_book(book_path)) {
            std::cerr << "error: cannot load book from " << book_path << "\n";
            return 2;
        }
    }
    return hub.run();
}
