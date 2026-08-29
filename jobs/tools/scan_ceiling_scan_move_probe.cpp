// Technical-only adapter around the unmodified, pinned Scan 3.1 move generator.
// This file is compiled outside the Scan source tree and linked to its exact
// source files.  It neither changes nor copies a Scan algorithm.

#include "bb_comp.hpp"
#include "bb_index.hpp"
#include "bit.hpp"
#include "fen.hpp"
#include "gen.hpp"
#include "hash.hpp"
#include "libmy.hpp"
#include "list.hpp"
#include "move.hpp"
#include "pos.hpp"
#include "var.hpp"

#include <algorithm>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: scan_ceiling_scan_move_probe <51-char-hub-position>\n";
        return 2;
    }
    try {
        // Match Scan 3.1 main.cpp's low-level initialisation order.  The
        // variant update is followed by the same second bit::init() used by
        // Hub mode before any position is parsed.
        bit::init();
        hash::init();
        pos::init();
        var::init();
        bb::index_init();
        bb::comp_init();
        ml::rand_init();
        var::set("variant", "normal");
        var::update();
        bit::init();

        const Pos position = pos_from_hub(argv[1]);
        List moves;
        gen_moves(moves, position);
        std::vector<std::pair<std::string, std::string>> rows;
        rows.reserve(static_cast<std::size_t>(moves.size()));
        for (int index = 0; index < moves.size(); ++index) {
            const Move mv = moves[index];
            rows.emplace_back(move::to_hub(mv, position), pos_hub(position.succ(mv)));
        }
        std::sort(rows.begin(), rows.end());
        std::cout << "move\tchild_pos\n";
        for (const auto& row : rows) {
            std::cout << row.first << '\t' << row.second << '\n';
        }
    } catch (const std::exception& error) {
        std::cerr << "scan move probe error: " << error.what() << '\n';
        return 3;
    }
    return 0;
}
