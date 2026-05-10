// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// WebAssembly bindings for the Jass engine.
//
// Built only when the project is compiled with Emscripten (`emcmake`). The
// public surface is a single JavaScript class, `Game`, that wraps a
// `jass::Engine` and exposes the few operations that a UI needs:
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

#include "engine.hpp"
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
    Game() = default;

    static Game from_fen(const std::string& fen) {
        Game g;
        g.engine_.set_position_fen(fen);
        return g;
    }

    std::string fen()   const { return engine_.position().to_fen();   }
    std::string ascii() const { return engine_.position().to_ascii(); }

    int side_to_move() const {
        return static_cast<int>(engine_.position().side_to_move());
    }

    emscripten::val legal_moves() const {
        using emscripten::val;
        jass::MoveList ml;
        jass::generate_legal_moves(engine_.position(), ml);
        val arr = val::array();
        for (std::size_t i = 0; i < ml.size(); ++i) {
            arr.set(i, move_to_js(ml[i]));
        }
        return arr;
    }

    bool apply_index(int idx) {
        jass::MoveList ml;
        jass::generate_legal_moves(engine_.position(), ml);
        if (idx < 0 || static_cast<std::size_t>(idx) >= ml.size()) {
            return false;
        }
        return engine_.apply_move(ml[static_cast<std::size_t>(idx)]);
    }

    void new_game() { engine_.new_game(); }

    emscripten::val best_move(int depth) {
        using emscripten::val;
        const jass::SearchResult r = engine_.search(depth);
        val obj = move_to_js(r.best_move);
        obj.set("score", r.score);
        obj.set("depth", r.depth);
        obj.set("nodes", static_cast<double>(r.nodes));
        val pv = val::array();
        for (std::size_t i = 0; i < r.pv.size(); ++i) {
            pv.set(i, move_to_js(r.pv[i]));
        }
        obj.set("pv", pv);
        return obj;
    }

private:
    jass::Engine engine_;
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
        .function("newGame",     &Game::new_game)
        .function("bestMove",    &Game::best_move);
}

int main() { return 0; }

#endif  // __EMSCRIPTEN__
