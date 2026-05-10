# Jass

**Just Another Scan System** — a draughts (international 10×10) engine written
from scratch in modern C++.

## Goals

- Play international draughts at a strong level.
- Be **fully owned** by its author and distributed under a permissive licence
  (MIT) so it can be embedded freely in third-party applications, including
  the upcoming **Draught Master** web app.
- Compile both as a native binary speaking the **HUB** protocol (for use with
  standard draughts GUIs) and as a **WebAssembly** module (for browser
  integration).

## Status

Early-stage but the rules engine is in place. The repository currently
contains:

- Project layout, build system (CMake) for native and Emscripten/WASM builds.
- Core types (`Color`, `Piece`, `Square`, `Move`) and the 10×10 board
  geometry with the FMJD square numbering 1–50.
- A `Position` type with Hub-style FEN parsing/serialisation, an immutable
  `Position::after(Move)` apply, and an ASCII diagram for debugging.
- A complete legal-move generator: quiet moves for men and kings, capture
  chains in all four directions for men, full ray captures for kings, and
  the FMJD majority-capture rule (longest chain wins).
- A negamax alpha-beta search with iterative deepening, transposition
  table (Zobrist-keyed, depth-preferred replacement, mate-score adjusted),
  killer-move + history move ordering, aspiration windows around the
  iterative-deepening root, FMJD draw handling (25-move rule and 2-fold
  repetition), an endgame-knowledge probe (KvK = draw), a principal-
  variation extraction via the TT, time control (`go movetime`, `go
  infinite` + `stop`), lazy SMP for multi-thread scaling and a
  quiescence search that plays mandatory capture chains out at the
  leaves.
- A long-lived `Engine` facade that owns the TT and the game's hash
  history so successive moves of the same game share their lookup
  data and detect repetitions naturally.
- A small HUB-flavoured CLI front-end (`./build/jass`) for shell or
  GUI use.
- A static evaluation combining material (man = 100, king = 300),
  per-piece positional terms (advancement PSQT for men, centralisation
  PSQT for kings) and a small tempo bonus for the side to move.
- WebAssembly bindings via Emscripten/Embind exposing a small `Game`
  class to JavaScript (`fen`, `legalMoves`, `applyIndex`, `bestMove`,
  …) for the Draught Master web app.
- A smoke-test binary that runs a full engine-vs-engine self-play game in
  a few milliseconds end-to-end, and a unit-test runner with 350+
  assertions covering geometry, FEN, movegen edge cases, perft (up to
  depth 5: 9 / 81 / 658 / 4 265 / 27 117) and the search contract
  (legality, mate detection, forced captures, material scoring).

Coming next: a richer evaluation (piece-square tables, mobility,
advancement, tempo), transposition tables, and the HUB protocol
front-end for desktop GUIs.

## Licence and provenance

Jass is released under the **MIT licence** (see [LICENSE](LICENSE)).

It is **not** a fork or translation of any existing engine. In particular, no
code from Fabien Letouzey's *Scan* (which is GPLv3) has been read or copied.
Jass is a clean-room implementation written from public sources only:

- the FMJD rules of international draughts,
- the public HUB protocol specification,
- general public-domain knowledge of game-tree search (alpha-beta, iterative
  deepening, transposition tables, …) and bitboard techniques.

This means Jass can be embedded in proprietary or differently-licensed
projects without the contamination that a GPL dependency would impose.

## Continuous integration & WASM hosting

A GitHub Actions workflow at `.github/workflows/build.yml` runs on every
push and PR. It does three things:

1. **Native build & test** on Ubuntu — must always be green.
2. **WASM build** via Emscripten (the SDK is installed and cached on
   the runner). The artefacts `jass.js`, `jass.wasm` and `example.html`
   are uploaded to the workflow run, downloadable from the Actions tab
   under the name `jass-wasm`.
3. **GitHub Pages deploy** on pushes to `main` only — `example.html`
   becomes the site index, so the demo is reachable at
   `https://<your-user>.github.io/jass/`.

### One-time GitHub Pages setup

In the repository settings, go to **Settings → Pages** and pick
**Source: GitHub Actions**. After the next push to `main` the workflow
will publish the demo automatically; the URL is shown in the workflow
log and on the repository's Environments page.

If you only want the artefacts (no Pages), no setup is needed: every
push uploads them and they're downloadable from the run page.

## Building

### Native

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/jass            # HUB-flavoured CLI (default mode)
./build/jass --smoke    # self-contained demo (start position, depth-6
                        # search, 40-ply self-play game)
./build/jass_tests      # unit tests
```

Requires a C++20 compiler (GCC ≥ 11, Clang ≥ 13, MSVC ≥ 19.30).

The default mode reads HUB-style commands from stdin. A short interactive
session looks like:

```
hello
position startpos
go depth 6
apply 31-26
fen
quit
```

Supported commands: `hello`, `newgame`, `position startpos | fen <FEN>`,
`apply <move>`, `go depth <N> | movetime <ms> | infinite`, `stop`,
`setoption threads <N>`, `eval`, `fen`, `quit`. Move format on
input/output is `from-to` (quiet) or `fromxto` (capture). The
`bestmove` line carries `score=`, `depth=`, `nodes=` and `pv=` (the
principal variation as a comma-separated list of moves).

### WebAssembly (for Draught Master)

Requires the [Emscripten](https://emscripten.org) SDK to be installed and
`emcmake` on the `PATH`.

```sh
./wasm/build.sh
python3 -m http.server --directory build-wasm 8080
# then open http://localhost:8080/example.html
```

The produced `build-wasm/jass.js` is an **ES6 module** that loads
`build-wasm/jass.wasm` next to it. Sketch of the JS API:

```js
import createJass from './jass.js';

const Module = await createJass();
const g = new Module.Game();        // start position, white to move
g.fen();                            // → "W:W31-50:B1-20" (Hub-style)
g.legalMoves();                     // → [{from, to, captures, promotes}, …]
g.applyIndex(0);                    // play the first legal move
const best = g.bestMove(6);         // → {from, to, …, score, depth, nodes}
g.delete();                         // free the wrapped C++ object
```

`wasm/example.html` ships a runnable demo using exactly this API.

## Repository layout

```
jass/
├── LICENSE                MIT licence
├── README.md              this file
├── CMakeLists.txt         build configuration (native + WASM)
├── src/                   engine sources
│   ├── types.hpp          Color, Piece, Square, Move
│   ├── board.hpp/.cpp     10×10 geometry, neighbour tables
│   ├── bitboard.hpp       50-bit Bitboard helpers
│   ├── position.hpp/.cpp  Position + Hub-style FEN
│   ├── movegen.hpp/.cpp   move generation
│   ├── eval.hpp/.cpp      static evaluation
│   ├── search.hpp/.cpp    negamax alpha-beta with iterative deepening
│   ├── main.cpp           native smoke-test entry point
│   └── wasm_api.cpp       Embind bindings (Emscripten builds only)
├── tests/
│   ├── test_framework.hpp test scaffolding
│   ├── test_main.cpp      test runner entry point
│   ├── test_position.cpp  geometry, bitboards, FEN
│   ├── test_movegen.cpp   movegen edge cases + perft
│   └── test_search.cpp    search contract tests
└── wasm/
    ├── build.sh           Emscripten build wrapper
    └── example.html       browser demo loading the ES6 module
```
