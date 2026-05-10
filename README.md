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
- A negamax alpha-beta search with iterative deepening, plus a flat
  material evaluation (man = 100, king = 300, side-to-move relative).
- A smoke-test binary that runs a full engine-vs-engine self-play game in
  a few milliseconds end-to-end, and a unit-test runner with 350+
  assertions covering geometry, FEN, movegen edge cases, perft (up to
  depth 5: 9 / 81 / 658 / 4 265 / 27 117) and the search contract
  (legality, mate detection, forced captures, material scoring).

Coming next: WASM bindings for Draught Master, then a richer evaluation
(piece-square tables, mobility, advancement, tempo), transposition
tables, and the HUB protocol front-end.

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

## Building

### Native

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/jass        # smoke-test entry point
./build/jass_tests  # unit tests
```

Requires a C++20 compiler (GCC ≥ 11, Clang ≥ 13, MSVC ≥ 19.30).

### WebAssembly (for Draught Master)

Requires the [Emscripten](https://emscripten.org) SDK to be installed and
`emcmake` on the `PATH`.

```sh
./wasm/build.sh
```

The produced `build-wasm/jass.{js,wasm}` can be loaded directly from a
browser.

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
│   ├── movegen.hpp/.cpp   move generation (skeleton)
│   └── main.cpp           smoke-test entry point
├── tests/
│   └── test_position.cpp  unit tests
└── wasm/
    └── build.sh           Emscripten build script
```
