# Jass

**Just Another Scan System** — an international (FMJD 10×10) draughts engine
written from scratch in modern C++ and **dual-licensed** (AGPL v3 +
commercial — see [LICENSING.md](LICENSING.md)).

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
  table (Zobrist-keyed, 4-way clusters, 6-bit generation counter for
  cross-move ageing, mate-score adjusted, PackedMove storage),
  TT-move + killer-move + history move ordering, **singular
  extension** with a half-depth verification search, adaptive
  aspiration windows, lazy SMP for multi-thread scaling, FMJD draw
  handling (25-move rule + 2-fold repetition), endgame bitbase
  (KvK and KKvK via retrograde analysis), Zobrist-keyed opening book,
  principal variation extracted from the TT, and a quiescence search
  that plays mandatory capture chains out at the leaves.
- **Evaluation — trained NNUE shipped by default**:
  - The native + WASM binaries embed a small **MLP** (200 → 64 → 32 → 1,
    ReLU, STM-relative input encoding) trained on ~100 k self-play
    positions labelled by a depth-8 search. Score rate **0.639** vs
    the original handcrafted eval at depth 5 (≈ +99 ELO), itself
    +120 ELO above the hand-tuned constants → cumulative ≈ **+220 ELO**
    over the historic baseline.
  - The handcrafted eval (material + PSQT + king centralisation +
    rear-diagonal support + tempo) and a `LinearNetwork` are still
    available; the engine picks via the new `INetwork*` interface.
  - **Int8 quantisation** (`MLPNetworkQ`, JNNQ format) is opt-in via
    `--nnue path.bin` and is **at strict parity** with the float32
    reference (16-16-4 / 36 games at depth 5).
- **SIMD acceleration of the int8 forward pass**:
  - Native x86 → AVX2 (`_mm256_maddubs_epi16` + `_mm256_madd_epi16`):
    +20 % per node vs the float32 MLP.
  - Browser → WASM SIMD128 (`wasm_i16x8_extmul_*` +
    `wasm_i32x4_extadd_pairwise_*`): direct gain for the Draught
    Master web app.
  - Both paths share the same dot-product shape; CMake gates each
    with a CheckCXXCompilerFlag + `-msimd128` for Emscripten.
- **Training & book pipelines**:
  - `--gen-data` generates labelled self-play datasets;
    `tools/train.py` (NumPy lstsq) fits the `LinearNetwork` and
    `tools/train_mlp.py` (PyTorch + Adam, early-stop) fits the MLP.
    `tools/quantize_mlp.py` does post-training int8 quantisation with
    99.9-pct activation calibration.
  - `--build-book` consumes a FEN list and writes a **JBOK** binary
    book (`PackedMove`-keyed, 16 B per entry); `--book path.bok`
    loads it at startup.
  - Mobile-friendly GitHub Actions workflows (`train-nnue`,
    `benchmark-nnue`, `benchmark-nnue-vs-nnue`, `build-book`) trigger
    the whole pipeline from a tap.
- **Front-ends**:
  - native CLI speaking a small HUB-flavoured protocol
    (`./build/jass`) — supports `--nnue`, `--no-nnue`, `--book`,
    `--build-book`, `--benchmark-nnue`, `--benchmark-nnue-vs-nnue`,
    `--gen-data`, `--tournament`, `--smoke`,
  - WebAssembly ES6 module exposing a `Game` JS class via Embind
    (`./wasm/build.sh`) — the embedded NNUE is active out of the box,
  - a self-play tournament harness for regression testing
    (`./build/jass --tournament 4 6 1`).
- **Test suite**: 672 unit-test assertions, all passing locally;
  build passes on GCC ≥ 11 and Clang ≥ 13.

## Licence and provenance

Jass is **dual-licensed**:

- **GNU Affero General Public License v3.0 or later** for OSS use —
  full text in [LICENSE](LICENSE).
- A **commercial licence** is available for embedders who can't (or
  won't) comply with the AGPL share-alike + network-use clauses. See
  [LICENSING.md](LICENSING.md) for the contact path.

Jass is **not** a fork or translation of any existing engine. In
particular **no code from Fabien Letouzey's *Scan*** (which is GPLv3)
has been read or copied. Jass is a clean-room implementation written
from public sources only:

- the FMJD rules of international draughts,
- general public-domain knowledge of game-tree search (alpha-beta,
  iterative deepening, transposition tables, …) and bitboard techniques,
- a small subset of the HUB-flavoured protocol described as needed.

That clean-room provenance is what makes the dual-licensing model
possible: the copyright is wholly owned by the author and can be
relicensed to any party that requests a commercial grant.
Contributors are expected to sign the small CLA in
[CONTRIBUTING.md](CONTRIBUTING.md) for the same reason.

## Quick start

### Build & run native

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j

./build/jass                    # HUB-flavoured CLI (reads stdin)
./build/jass --smoke            # self-contained demo
./build/jass --tournament 4 6 1 # depth-4 vs depth-6, 2 games

./build/jass --nnue mlp.bin     # swap the embedded NNUE for an alternate
./build/jass --no-nnue          # fall back to the handcrafted eval
./build/jass --book book.bok    # load an external opening book

./build/jass_tests              # unit tests (672 assertions)
```

Requires a C++20 compiler (GCC ≥ 11, Clang ≥ 13, MSVC ≥ 19.30). On
x86, AVX2 is opted in automatically through `-mavx2` (see CMake's
`Jass: AVX2 enabled` line); pass `-DJASS_ENABLE_SIMD=OFF` to keep the
binary portable to older CPUs.

### Training & book pipelines

```sh
# Generate self-play data labelled by depth-8 search.
./build/jass --gen-data 100000 selfplay.bin

# Train a linear NNUE (NumPy closed-form lstsq, ~30 s).
python3 tools/train.py     --data selfplay.bin --out linear.bin

# Train the MLP (PyTorch + Adam, ~3-5 min on 100k records).
python3 tools/train_mlp.py --data selfplay.bin --out mlp.bin

# Post-training int8 quantisation (4× smaller on disk, AVX2/WASM SIMD).
python3 tools/quantize_mlp.py --in mlp.bin --data selfplay.bin --out mlp-q.bin

# Build a JBOK opening book from a FEN list at depth 12.
./build/jass --build-book fens.txt book.bok 12

# Benchmark a network against the handcrafted eval.
./build/jass --benchmark-nnue mlp.bin 5 2

# Benchmark two networks head-to-head.
./build/jass --benchmark-nnue-vs-nnue mlp.bin linear.bin 5 5
```

All of the above are also wired as one-tap GitHub Actions workflows
(`train-nnue`, `benchmark-nnue`, `build-book`) — see "Continuous
integration" below.

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

The repository ships **four** workflows; one runs on every commit, the
other three are manual triggers designed to be invoked from the
GitHub mobile UI.

### `build.yml` — on every push & PR

1. **Native build & test** on Ubuntu — must always be green.
2. **WASM build** via Emscripten (SDK installed and cached). Artefacts
   `jass.js`, `jass.wasm` and `example.html` are uploaded under the
   artefact name `jass-wasm`.
3. **GitHub Pages deploy** on pushes to `main` only — `example.html`
   becomes the site index, demo reachable at
   `https://<your-user>.github.io/jass/`.

### `train-nnue.yml` — workflow_dispatch

Generates a self-play dataset (`--gen-data`) and trains either the
`LinearNetwork` (NumPy lstsq) or the `MLPNetwork` (PyTorch + Adam).
Inputs: `records` (10k / 100k / 1M) and `model` (linear / mlp).
Uploads `nnue.bin` as the `nnue-weights` artefact.

### `benchmark-nnue.yml` — workflow_dispatch

Runs a colour-swap tournament. With just `weights_path` set it pits
the network against the handcrafted eval (`--benchmark-nnue`); add
`weights_b_path` to compare two NNUE networks head-to-head
(`--benchmark-nnue-vs-nnue`). Reports score rate and uploads the
result.

### `build-book.yml` — workflow_dispatch

Reads a FEN list from the repo, evaluates each position with the
embedded NNUE at the requested depth and writes a JBOK book. Uploads
the resulting `book.bok` as the `opening-book` artefact. Designed for
ingesting external curated position sets without embedding their
evaluations.

### One-time GitHub Pages setup

In the repository settings, go to **Settings → Pages** and pick
**Source: GitHub Actions**. After the next push to `main` the workflow
will publish the demo automatically; the URL is shown in the workflow
log and on the repository's Environments page.

If you only want the artefacts (no Pages), no setup is needed.

## Repository layout

```
jass/
├── LICENSE                full AGPL v3 text (the OSS half of dual licence)
├── LICENSING.md           dual-licensing explanation + commercial contact
├── CONTRIBUTING.md        contribution rules + CLA
├── README.md              this file
├── CMakeLists.txt         build configuration (native + WASM + SIMD opt-in)
├── nnue.bin               default NNUE weights (MLP v2 100k), embedded at build
├── cmake/
│   └── nnue_default_data.cpp.in   template that CMake fills with nnue.bin's bytes
├── .github/workflows/
│   ├── build.yml          native + WASM build, GitHub Pages deploy
│   ├── train-nnue.yml     workflow_dispatch: --gen-data + trainer
│   ├── benchmark-nnue.yml workflow_dispatch: --benchmark-nnue[-vs-nnue]
│   └── build-book.yml     workflow_dispatch: --build-book from FEN list
├── docs/                  reference documentation
│   ├── ARCHITECTURE.md    module map and data-flow
│   ├── HUB.md             CLI command reference
│   ├── WASM.md            JS / WebAssembly API
│   ├── API.md             C++ header reference
│   ├── EXTENDING.md       recipes (new bitbase, eval term, book line, …)
│   └── GLOSSARY.md        draughts and engine terms
├── tools/                 Python tooling for the training pipeline
│   ├── train.py           LinearNetwork trainer (NumPy lstsq)
│   ├── train_mlp.py       MLPNetwork trainer (PyTorch + Adam)
│   └── quantize_mlp.py    post-training int8 quantisation (writes JNNQ)
├── src/                   engine sources
│   ├── types.hpp                   Color, Piece, Square, Move
│   ├── bitboard.hpp                50-bit Bitboard helpers
│   ├── board.hpp / .cpp            10×10 geometry, neighbour tables
│   ├── position.hpp / .cpp         Position + Hub-style FEN
│   │                               + incremental Zobrist
│   ├── movegen.hpp / .cpp          legal-move generator
│   ├── eval.hpp / .cpp             handcrafted static evaluation
│   ├── nnue.hpp / .cpp             INetwork interface + Linear / MLP / MLPQ
│   │                               (scalar + AVX2 + WASM SIMD128 paths)
│   ├── nnue_default_data.hpp       declares the embedded weight blob
│   ├── zobrist_keys.hpp            Zobrist key tables (no Position dep)
│   ├── zobrist.hpp / .cpp          Position-aware Zobrist hash
│   ├── tt.hpp / .cpp               TT with 4-way clusters + 6-bit generation
│   ├── search.hpp / .cpp           negamax α-β + ID + qsearch + lazy SMP
│   │                               + singular extension
│   ├── endgame.hpp / .cpp          high-level endgame probe façade
│   ├── bitbase.hpp / .cpp          retrograde-analysis 2-vs-1 bitbase
│   ├── book.hpp / .cpp             opening book (hard-coded lines + JBOK loader)
│   ├── timemgr.hpp / .cpp          tournament time-budget helper
│   ├── tournament.hpp / .cpp       self-play tournament harness
│   ├── engine.hpp / .cpp           long-lived facade (TT + history + book + NNUE)
│   ├── hub.hpp / .cpp              HUB-flavoured CLI front-end
│   ├── main.cpp                    native entry point
│   └── wasm_api.cpp                Embind bindings (Emscripten only)
├── tests/                 unit tests (single executable, 672 assertions)
│   ├── test_framework.hpp test scaffolding (JASS_CHECK macros)
│   ├── test_main.cpp      runs every per-topic group
│   ├── test_position.cpp  geometry, bitboards, FEN
│   ├── test_movegen.cpp   movegen edge cases + perft
│   ├── test_search.cpp    eval invariants + search contract
│   ├── test_tt.cpp        Zobrist + TT
│   ├── test_engine.cpp    Engine facade (incl. set_nnue / load_book)
│   ├── test_draws.cpp     25-move rule + 2-fold repetition
│   ├── test_endgame.cpp   endgame probe + bitbase integration
│   ├── test_book.cpp      opening book + JBOK save/load round-trip
│   ├── test_tournament.cpp self-play tournament harness
│   ├── test_nnue.cpp      Linear + MLP + MLPQ networks, default_nnue dispatch
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
