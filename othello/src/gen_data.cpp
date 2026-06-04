// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Self-play generator CLI :
//   othello_gen_data <n_games> <out.bin>
//                    [random_plies=8] [search_depth=4]
//                    [sample_stride=4] [seed=42]
//
// Pipeline per game :
//   1. Start from start_position()
//   2. First `random_plies` non-pass moves : uniform random from legal
//   3. Remaining moves : alpha-beta at `search_depth`
//   4. Sample positions every `sample_stride` plies during the
//      engine phase (records buffered)
//   5. At game end, label each buffered record with the absolute
//      outcome (+1 black wins, -1 white wins, 0 draw)
//   6. Append to output stream

#include "board.hpp"
#include "eval.hpp"
#include "gen_data.hpp"
#include "movegen.hpp"
#include "search.hpp"

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <random>
#include <vector>

namespace {

using namespace othello;

void write_u32(std::ostream& os, std::uint32_t v) {
    unsigned char buf[4];
    buf[0] = static_cast<unsigned char>(v & 0xFF);
    buf[1] = static_cast<unsigned char>((v >> 8) & 0xFF);
    buf[2] = static_cast<unsigned char>((v >> 16) & 0xFF);
    buf[3] = static_cast<unsigned char>((v >> 24) & 0xFF);
    os.write(reinterpret_cast<char*>(buf), 4);
}

void write_u64(std::ostream& os, std::uint64_t v) {
    unsigned char buf[8];
    for (int i = 0; i < 8; ++i) {
        buf[i] = static_cast<unsigned char>((v >> (i * 8)) & 0xFF);
    }
    os.write(reinterpret_cast<char*>(buf), 8);
}

void write_record(std::ostream& os, const GenRecord& r) {
    write_u64(os, r.black);
    write_u64(os, r.white);
    const unsigned char tail[2] = {r.stm, static_cast<unsigned char>(r.label)};
    os.write(reinterpret_cast<const char*>(tail), 2);
}

Square random_legal(const Board& b, std::mt19937& rng) {
    MoveList ml;
    generate_legal_moves(b, ml);
    if (ml.empty()) return NO_SQUARE;
    std::uniform_int_distribution<std::size_t> dist(0, ml.size() - 1);
    return ml[dist(rng)];
}

// Play one self-play game, append sampled records to `out`. Returns
// the absolute outcome (+1 black wins, -1 white, 0 draw).
int play_one(std::vector<GenRecord>& out,
             int random_plies, int search_depth, int sample_stride,
             std::mt19937& rng,
             SearchConfig& search_cfg) {
    Board b = Board::start_position();
    int random_done = 0;
    int engine_plies = 0;

    // Remember which records belong to this game so we can label them
    // at the end with the absolute outcome.
    const std::size_t first_idx = out.size();

    while (!b.is_game_over()) {
        Square mv = NO_SQUARE;
        const bool in_random_phase = random_done < random_plies;
        MoveList ml;
        generate_legal_moves(b, ml);

        if (ml.empty()) {
            // Forced pass — does not count toward random_plies cap.
            apply_move(b, NO_SQUARE);
            continue;
        }

        if (in_random_phase) {
            mv = random_legal(b, rng);
            ++random_done;
        } else {
            mv = search(b, search_cfg).best_move;
            // Sample BEFORE applying the engine move, at the chosen stride.
            if ((engine_plies % sample_stride) == 0) {
                GenRecord r;
                r.black = b.black;
                r.white = b.white;
                r.stm   = (b.stm == Color::Black) ? 0 : 1;
                r.label = 0;  // filled in at game end
                out.push_back(r);
            }
            ++engine_plies;
        }
        apply_move(b, mv);
    }

    // Final outcome from absolute (black POV) perspective.
    const int blk = b.black_count();
    const int wht = b.white_count();
    int outcome = 0;
    if      (blk > wht) outcome = +1;
    else if (blk < wht) outcome = -1;

    for (std::size_t i = first_idx; i < out.size(); ++i) {
        out[i].label = static_cast<std::int8_t>(outcome);
    }
    return outcome;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: othello_gen_data <n_games> <out.bin> "
                     "[random_plies=8] [search_depth=4] "
                     "[sample_stride=4] [seed=42]\n";
        return 1;
    }
    const int n_games       = std::atoi(argv[1]);
    const char* out_path    = argv[2];
    const int random_plies  = (argc > 3) ? std::atoi(argv[3]) : 8;
    const int search_depth  = (argc > 4) ? std::atoi(argv[4]) : 4;
    const int sample_stride = (argc > 5) ? std::atoi(argv[5]) : 4;
    const std::uint32_t seed = (argc > 6)
        ? static_cast<std::uint32_t>(std::atoi(argv[6])) : 42U;

    std::cout << "gen_data : n_games=" << n_games
              << " out=" << out_path
              << " random_plies=" << random_plies
              << " search_depth=" << search_depth
              << " sample_stride=" << sample_stride
              << " seed=" << seed << "\n";

    std::ofstream ofs(out_path, std::ios::binary);
    if (!ofs) {
        std::cerr << "error: cannot open " << out_path << " for writing\n";
        return 2;
    }
    // Write placeholder header — count is filled in after we know the total.
    write_u32(ofs, GEN_DATA_MAGIC);
    write_u32(ofs, GEN_DATA_VERSION);
    write_u32(ofs, 0);  // count placeholder
    write_u32(ofs, 0);  // reserved

    std::mt19937 rng(seed);
    SearchConfig search_cfg;
    search_cfg.max_depth = search_depth;

    std::vector<GenRecord> buffer;
    buffer.reserve(64);
    std::size_t total_records = 0;
    int blk_wins = 0, wht_wins = 0, draws = 0;
    const auto start = std::chrono::steady_clock::now();

    for (int g = 0; g < n_games; ++g) {
        buffer.clear();
        const int outcome = play_one(buffer, random_plies, search_depth,
                                     sample_stride, rng, search_cfg);
        for (const auto& r : buffer) write_record(ofs, r);
        total_records += buffer.size();
        if      (outcome > 0) ++blk_wins;
        else if (outcome < 0) ++wht_wins;
        else                  ++draws;

        if (((g + 1) % 100) == 0 || (g + 1) == n_games) {
            const auto now = std::chrono::steady_clock::now();
            const auto sec = std::chrono::duration_cast<std::chrono::seconds>(
                                 now - start).count();
            std::cout << "  game " << (g + 1) << "/" << n_games
                      << "  records=" << total_records
                      << "  B/W/D=" << blk_wins << "/" << wht_wins << "/" << draws
                      << "  elapsed=" << sec << "s\n";
        }
    }

    // Patch the header count.
    ofs.seekp(8);
    write_u32(ofs, static_cast<std::uint32_t>(total_records));
    ofs.close();

    const auto end = std::chrono::steady_clock::now();
    const auto sec = std::chrono::duration_cast<std::chrono::seconds>(
                         end - start).count();
    std::cout << "done : " << total_records << " records, "
              << "B/W/D=" << blk_wins << "/" << wht_wins << "/" << draws
              << ", wall=" << sec << "s\n";
    return 0;
}
