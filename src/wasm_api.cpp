// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// WebAssembly bindings for the Jass engine.
//
// Built only when the project is compiled with Emscripten (`emcmake`). The
// public surface is a single JavaScript class, `Game`, that wraps a
// `jass::Position` and exposes the few operations that a UI needs:
//
//   const Module = await createJass();
//   const g = new Module.Game();              // start position, white to move
//   g.fen();                                  // → Hub-style FEN string
//   g.legalMoves();                           // → [{from,to,captures,promotes}]
//   g.applyIndex(0);                          // play the i-th legal move
//   g.bestMove(6);                            // → {from,to,...,score,depth,nodes}
//   const h = Module.Game.fromFen("W:W31-50:B1-20");
//
// The bindings deliberately do not throw across the JS/Wasm boundary. Errors
// surface as conventional return values (`fromFen` returns a default-
// constructed Game on parse failure; `applyIndex` returns `false`).

#ifdef __EMSCRIPTEN__

#include "movegen.hpp"
#include "position.hpp"
#include "search.hpp"
#include "types.hpp"

#include <emscripten/bind.h>
#include <emscripten/val.h>

#include <string>

namespace {

emscripten::val move_to_js(const jass::Move& m) {
    using emscripten::val;
    val obj = val::object();
    obj.set("from",     static_cast<int>(m.from));
    obj.set("to",       static_cast<int>(m.to));
    obj.set("promotes", m.promotes);
    val caps = val::array();
    for (std::uint8_t i = 0; i < m.num_captures; ++i) {
        caps.set(i, static_cast<int>(m.captures[i]));
    }
    obj.set("captures", caps);
    return obj;
}

class Game {
public:
    Game() : pos_(jass::Position::start_position()) {}

    static Game from_fen(const std::string& fen) {
        Game g;
        if (auto p = jass::Position::from_fen(fen); p) g.pos_ = *p;
        return g;
    }

    std::string fen()   const { return pos_.to_fen();   }
    std::string ascii() const { return pos_.to_ascii(); }

    // 0 = white to move, 1 = black to move (matches `jass::Color` ordering).
    int side_to_move() const {
        return static_cast<int>(pos_.side_to_move());
    }

    emscripten::val legal_moves() const {
        using emscripten::val;
        jass::MoveList ml;
        jass::generate_legal_moves(pos_, ml);
        val arr = val::array();
        for (std::size_t i = 0; i < ml.size(); ++i) {
            arr.set(i, move_to_js(ml[i]));
        }
        return arr;
    }

    bool apply_index(int idx) {
        jass::MoveList ml;
        jass::generate_legal_moves(pos_, ml);
        if (idx < 0 || static_cast<std::size_t>(idx) >= ml.size()) {
            return false;
        }
        pos_ = pos_.after(ml[static_cast<std::size_t>(idx)]);
        return true;
    }

    emscripten::val best_move(int depth) const {
        using emscripten::val;
        jass::SearchLimits lim;
        lim.max_depth = depth;
        const jass::SearchResult r = jass::search(pos_, lim);

        val obj = move_to_js(r.best_move);
        obj.set("score", r.score);
        obj.set("depth", r.depth);
        obj.set("nodes", static_cast<double>(r.nodes));
        return obj;
    }

private:
    jass::Position pos_;
};

}  // namespace

EMSCRIPTEN_BINDINGS(jass_module) {
    using namespace emscripten;

    class_<Game>("Game")
        .constructor<>()
        .class_function("fromFen", &Game::from_fen)
        .function("fen",         &Game::fen)
        .function("ascii",       &Game::ascii)
        .function("sideToMove",  &Game::side_to_move)
        .function("legalMoves",  &Game::legal_moves)
        .function("applyIndex",  &Game::apply_index)
        .function("bestMove",    &Game::best_move);
}

// Embind requires a translation unit with a `main` for some Emscripten
// configurations. We provide a no-op so the module loads cleanly.
int main() { return 0; }

#endif  // __EMSCRIPTEN__
