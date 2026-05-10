# Jass

**Just Another Scan System** — an international (FMJD 10×10) draughts engine
written from scratch in modern C++ and distributed under the MIT licence.

---

## What it is

Jass is a small but complete draughts engine: it knows the FMJD rules, plays
full games, exposes a HUB-flavoured CLI for desktop GUIs and a WebAssembly
module for browsers (the **Draught Master** web app is the primary
consumer).

| Topic                  | Where to read                      |
|------------------------|------------------------------------|
| Architecture & data flow | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| HUB CLI reference        | [docs/HUB.md](docs/HUB.md)         |
| JavaScript / WASM API    | [docs/WASM.md](docs/WASM.md)       |
| C++ API (header by header) | [docs/API.md](docs/API.md)       |
| Extending the engine     | [docs/EXTENDING.md](docs/EXTENDING.md) |
| Domain glossary          | [docs/GLOSSARY.md](docs/GLOSSARY.md) |

## Highlights

- **Rules**: full FMJD movegen — quiet moves, captures in all four
  directions for men, ray captures for kings, mandatory maximum-capture
  rule, promotion only when a man *ends* on the promotion row.
  Validated by perft against the standard reference values
  (9 / 81 / 658 / 4 265 / 27 117 at depths 1–5 from the start position).
- **Search**: negamax α-β with iterative deepening, transposition
  table (Zobrist-keyed, depth-preferred replacement, mate-score
  adjusted), TT-move + killer-move + history move ordering, aspiration
  windows, lazy SMP for multi-thread scaling, FMJD draw handling
  (25-move rule + 2-fold repetition), endgame bitbase (KvK and KKvK
  via retrograde analysis), opening book, principal variation
  extracted from the TT, and a quiescence search that plays mandatory
  capture chains out at the leaves.
- **Evaluation**: material (man = 100 cp, king = 300 cp), advancement
  PSQT, edge-file penalty, back-rank guard, king centralisation,
  rear-diagonal support and a small tempo bonus. An NNUE-lite
  framework with a binary weight loader is in place for trained-
  weight drop-in.
- **Front-ends**:
  - native CLI speaking a small HUB-flavoured protocol
    (`./build/jass`),
  - WebAssembly ES6 module exposing a `Game` JS class via Embind
    (`./wasm/build.sh`),
  - a self-play tournament harness for regression testing
    (`./build/jass --tournament 4 6 1`).
- **Test suite**: 557 unit-test assertions, all passing locally;
  build passes on GCC ≥ 11 and Clang ≥ 13.

## Licence and provenance

Jass is **MIT** (see [LICENSE](LICENSE)).

It is not a fork or translation of any existing engine. In particular **no
code from Fabien Letouzey's *Scan*** (which is GPLv3) has been read or
copied. Jass is a clean-room implementation written from public sources
only:

- the FMJD rules of international draughts,
- general public-domain knowledge of game-tree search (alpha-beta,
  iterative deepening, transposition tables, …) and bitboard techniques,
- a small subset of the HUB-flavoured protocol described as needed.

This means Jass can be embedded in proprietary or differently-licensed
projects without the contamination a GPL dependency would impose.

## Quick start

### Build & run native

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j

./build/jass            # HUB-flavoured CLI (default mode, reads stdin)
./build/jass --smoke    # self-contained demo (start position, search,
                        # 40-ply self-play game)
./build/jass --tournament 4 6 1  # depth-4 vs depth-6, 2 games
./build/jass_tests      # unit tests
```

Requires a C++20 compiler (GCC ≥ 11, Clang ≥ 13, MSVC ≥ 19.30).

### A short HUB session

```text
hello
position startpos
go depth 6
apply 31-26
fen
quit
```

The full command grammar is in [docs/HUB.md](docs/HUB.md).

### Build & host the WASM module

The repository ships a CI workflow (see "Continuous integration" below)
that builds the WASM and uploads it as a workflow artefact, so most
users never need a local Emscripten install. To do it locally anyway:

```sh
./wasm/build.sh
python3 -m http.server --directory build-wasm 8080
# open http://localhost:8080/example.html
```

Sketch of the JS API:

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

Full reference: [docs/WASM.md](docs/WASM.md).

## Continuous integration & WASM hosting

`.github/workflows/build.yml` runs on every push and PR. It does three
things:

1. **Native build & test** on Ubuntu — must always be green.
2. **WASM build** via Emscripten (the SDK is installed and cached on
   the runner). The artefacts `jass.js`, `jass.wasm` and
   `example.html` are uploaded under the artefact name `jass-wasm`.
3. **GitHub Pages deploy** on pushes to `main` only — `example.html`
   becomes the site index, so the demo is reachable at
   `https://<your-user>.github.io/jass/`.

### One-time GitHub Pages setup

In the repository settings, go to **Settings → Pages** and pick
**Source: GitHub Actions**. After the next push to `main` the workflow
will publish the demo automatically; the URL is shown in the workflow
log and on the repository's Environments page.

If you only want the artefacts (no Pages), no setup is needed.

## Repository layout

```
jass/
├── LICENSE                MIT licence
├── README.md              this file
├── CMakeLists.txt         build configuration (native + WASM)
├── .github/workflows/     CI: native build, WASM build, Pages deploy
├── docs/                  reference documentation
│   ├── ARCHITECTURE.md    module map and data-flow
│   ├── HUB.md             CLI command reference
│   ├── WASM.md            JS / WebAssembly API
│   ├── API.md             C++ header reference
│   ├── EXTENDING.md       recipes (new bitbase, eval term, book line, …)
│   └── GLOSSARY.md        draughts and engine terms
├── src/                   engine sources
│   ├── types.hpp                   Color, Piece, Square, Move
│   ├── bitboard.hpp                50-bit Bitboard helpers
│   ├── board.hpp / .cpp            10×10 geometry, neighbour tables
│   ├── position.hpp / .cpp         Position + Hub-style FEN
│   │                               + incremental Zobrist
│   ├── movegen.hpp / .cpp          legal-move generator
│   ├── eval.hpp / .cpp             handcrafted static evaluation
│   ├── nnue.hpp / .cpp             linear-network eval framework
│   ├── zobrist_keys.hpp            Zobrist key tables (no Position dep)
│   ├── zobrist.hpp / .cpp          Position-aware Zobrist hash
│   ├── tt.hpp / .cpp               transposition table
│   ├── search.hpp / .cpp           negamax α-β + ID + qsearch + lazy SMP
│   ├── endgame.hpp / .cpp          high-level endgame probe façade
│   ├── bitbase.hpp / .cpp          retrograde-analysis 2-vs-1 bitbase
│   ├── book.hpp / .cpp             tiny built-in opening book
│   ├── timemgr.hpp / .cpp          tournament time-budget helper
│   ├── tournament.hpp / .cpp       self-play tournament harness
│   ├── engine.hpp / .cpp           long-lived facade (TT + history + book)
│   ├── hub.hpp / .cpp              HUB-flavoured CLI front-end
│   ├── main.cpp                    native entry point
│   └── wasm_api.cpp                Embind bindings (Emscripten only)
├── tests/                 unit tests (single executable, 557 assertions)
│   ├── test_framework.hpp test scaffolding (JASS_CHECK macros)
│   ├── test_main.cpp      runs every per-topic group
│   ├── test_position.cpp  geometry, bitboards, FEN
│   ├── test_movegen.cpp   movegen edge cases + perft
│   ├── test_search.cpp    eval invariants + search contract
│   ├── test_tt.cpp        Zobrist + TT
│   ├── test_engine.cpp    Engine facade
│   ├── test_draws.cpp     25-move rule + 2-fold repetition
│   ├── test_endgame.cpp   endgame probe + bitbase integration
│   ├── test_book.cpp      opening book
│   ├── test_tournament.cpp self-play tournament harness
│   ├── test_nnue.cpp      NNUE-lite framework
│   └── test_hub.cpp       CLI front-end (move I/O + sessions)
└── wasm/
    ├── build.sh           Emscripten build wrapper
    └── example.html       browser demo loading the ES6 module
```

## Contributing & extending

If you want to add a new opening line, plug a new endgame into the
bitbase, tweak the evaluation, swap the NNUE weights, or add a HUB
command, the recipes are in [docs/EXTENDING.md](docs/EXTENDING.md).

When sending a patch:

- Build must be green (`cmake --build build -j`).
- All tests must pass (`./build/jass_tests`).
- Keep the clean-room policy: do not look at any GPLed engine's source
  while writing Jass code.
