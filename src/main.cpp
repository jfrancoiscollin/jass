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
#include "nnue.hpp"
#include "nnue_server_client.hpp"
#include "position.hpp"
#include "search.hpp"
#include "tournament.hpp"

#include <algorithm>
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

    if (argc > 2) {
        int parsed = parse_int_or(argv[2], -1);
        if (parsed > 0) n = parsed;
    }
    if (argc > 3) out_path = argv[3];

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

    std::mt19937_64 rng(0x5eed5eed5eed5eedULL);
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
        } else {
            positional.push_back(argv[i]);
        }
    }
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
              << '\n';

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
        custom_nnue = load_network(nnue_path);
        if (!custom_nnue) {
            std::cerr << "error: cannot load NNUE weights from "
                      << nnue_path << "\n";
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
                SearchLimits lim;
                lim.max_depth = eval_depth;
                const SearchResult r = e.search(lim);
                const Position&    pos = e.position();
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
                        const int eff_depth = eval_depth - depth_from_root;
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
            lim.max_depth = play_depth;
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
    std::unique_ptr<INetwork> nnue = load_network(nnue_path);
    if (!nnue) {
        std::cerr << "error: cannot load NNUE from " << nnue_path << "\n";
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
// --benchmark-nnue: pit a trained network (loaded from a binary weights
// file — either the raw LinearNetwork int32 layout or the JNNM-tagged
// MLPNetwork format) against the handcrafted eval. Both engines are
// otherwise identical (same depth, same threads). Plays a colour-swap
// match across the default opening pool so we get diverse games.
// -----------------------------------------------------------------------------
int run_benchmark_nnue_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --benchmark-nnue <weights.bin> [depth=6] "
                     "[pairs=1] [threads=1]\n";
        return 1;
    }
    const char* weights_path = argv[2];
    const int   depth   = (argc > 3) ? parse_int_or(argv[3], 6) : 6;
    const int   pairs   = (argc > 4) ? parse_int_or(argv[4], 1) : 1;
    const int   threads = (argc > 5) ? parse_int_or(argv[5], 1) : 1;

    std::unique_ptr<INetwork> trained = load_network(weights_path);
    if (!trained) {
        std::cerr << "error: cannot load weights from " << weights_path << "\n";
        return 1;
    }

    EngineConfig handcrafted;
    handcrafted.max_depth = depth;
    handcrafted.threads   = threads;
    handcrafted.nnue      = nullptr;

    EngineConfig nnue_cfg;
    nnue_cfg.max_depth = depth;
    nnue_cfg.threads   = threads;
    nnue_cfg.nnue      = trained.get();

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());

    std::cout << "Benchmark: NNUE (" << weights_path
              << ") vs handcrafted, depth " << depth
              << ", threads " << threads
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
// --benchmark-nnue-vs-nnue: same colour-swap match as `--benchmark-nnue`,
// but A and B are both NNUE networks (any combination of LinearNetwork
// and MLPNetwork, auto-detected by `load_network`). Used to measure the
// gain of a candidate model against the current shipped default.
// -----------------------------------------------------------------------------
int run_benchmark_nnue_vs_nnue_mode(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: jass --benchmark-nnue-vs-nnue "
                     "<weights_a.bin> <weights_b.bin> [depth=6] [pairs=1] "
                     "[threads=1]\n";
        return 1;
    }
    const char* path_a  = argv[2];
    const char* path_b  = argv[3];
    const int   depth   = (argc > 4) ? parse_int_or(argv[4], 6) : 6;
    const int   pairs   = (argc > 5) ? parse_int_or(argv[5], 1) : 1;
    const int   threads = (argc > 6) ? parse_int_or(argv[6], 1) : 1;

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
    cfg_a.max_depth = depth;
    cfg_a.threads   = threads;
    cfg_a.nnue      = net_a.get();

    EngineConfig cfg_b;
    cfg_b.max_depth = depth;
    cfg_b.threads   = threads;
    cfg_b.nnue      = net_b.get();

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());
    std::cout << "Benchmark: A=NNUE(" << path_a
              << ") vs B=NNUE(" << path_b
              << "), depth " << depth
              << ", threads " << threads
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

    std::unique_ptr<INetwork> net = load_network(weights_path);
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
        else if (a == "--rewrite-scores-with-nnue") return run_rewrite_scores_with_nnue_mode(argc, argv);
        else if (a == "--benchmark-nnue")           return run_benchmark_nnue_mode(argc, argv);
        else if (a == "--benchmark-nnue-vs-nnue")   return run_benchmark_nnue_vs_nnue_mode(argc, argv);
        else if (a == "--build-book")               return run_build_book_mode(argc, argv);
        else if (a == "--build-book-from-moves")    return run_build_book_from_moves_mode(argc, argv);
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
                "  --gen-data-wdl <N> <path> [eval_depth=12] [play_depth=4] [max_plies=200] [seed=0] [--nnue PATH]\n"
                "                                   write N records with the\n"
                "                                   game outcome label (WDL).\n"
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
