// Diagnostic helper compiled against the frozen Scan 3.1 source bundle.
// Reads one standard Scan FEN per line and prints:
//   EVAL<TAB>zero-based-index<TAB>side-to-move-score
//
// It deliberately calls Scan's eval() directly: no search, quiescence or
// protocol layer can contaminate the static-parity gate.

#include "bb_comp.hpp"
#include "bb_index.hpp"
#include "bit.hpp"
#include "eval.hpp"
#include "fen.hpp"
#include "hash.hpp"
#include "libmy.hpp"
#include "pos.hpp"
#include "var.hpp"

#include <cstdlib>
#include <iostream>
#include <string>

int main() {
    bit::init();
    hash::init();
    pos::init();
    var::init();
    bb::index_init();
    bb::comp_init();
    ml::rand_init();
    var::load("scan.ini");
    bit::init();  // depends on the loaded variant
    eval_init();

    std::string fen;
    std::size_t index = 0;
    while (std::getline(std::cin, fen)) {
        if (fen.empty()) continue;
        try {
            const Pos pos = pos_from_fen(fen);
            std::cout << "EVAL\t" << index << '\t'
                      << static_cast<int>(eval(pos)) << '\n';
        } catch (...) {
            std::cerr << "invalid FEN at input " << index << ": " << fen << '\n';
            return EXIT_FAILURE;
        }
        ++index;
    }
    return EXIT_SUCCESS;
}
