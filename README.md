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
  extension** with a half-depth verification search, **Late-Move
  Reduction (LMR)** on quiet moves beyond the first few, **Null
  Move Pruning (NMP)** with depth-scaled reduction guarded against
  zugzwang-like low-piece endgames, **Reverse Futility Pruning (RFP)**
  at shallow depths in quiet positions (draughts mandates the longest
  capture chain so the "quiet position" test is exact), adaptive
  aspiration windows, **time-aware iteration skipping** (don't start
  the next ID iteration when it would obviously not finish before the
  deadline), lazy SMP for multi-thread scaling, FMJD draw handling
  (25-move rule + 2-fold repetition), endgame bitbase (KvK and KKvK
  via retrograde analysis), Zobrist-keyed opening book, principal
  variation extracted from the TT, and a quiescence search that plays
  mandatory capture chains out at the leaves.
- **Evaluation — trained NNUE shipped by default**:
  - The native + WASM binaries embed a **JNNM v2** MLP (200 → 64 → 32 → 1,
    ReLU, STM-relative *V2 dense* input encoding) trained on ~100 k
    self-play positions labelled by a depth-8 search. Score rate
    **0.639** vs the handcrafted eval at depth 5 (≈ +99 ELO) at the
    time it was trained.
  - The runtime supports **two input encodings**: V2 dense (200 feat)
    and **HalfMen-lite** (450 feat, Cycle-6c — symmetric per-piece
    indicator features designed to give the MLP more capacity to
    learn piece-relative patterns).
  - The C++ MLP loader is **runtime-dimensioned** (Cycle-4a): any
    `H1 × H2` topology (any multiple of the SIMD tile size) loads
    without recompiling. Quantised `MLPNetworkQ` (JNNQ format) and
    its AVX2 + WASM-SIMD128 paths inherit this.
  - The handcrafted eval (material + PSQT + king centralisation +
    rear-diagonal support + tempo) and a `LinearNetwork` are still
    available; the engine picks via the `INetwork*` interface.
  - **Int8 quantisation** (`MLPNetworkQ`, JNNQ format) is opt-in via
    `--nnue path.bin` and was measured **at strict parity** with the
    float32 reference (16-16-4 / 36 games at depth 5) on the shipped
    64-32 MLP.
  - The **calibration target** is Scan (Fabien Letouzey, GPL3,
    ~2500 FMJD-equivalent). `tools/calibrate_vs_scan.py` plays Jass
    against Scan via the HUB protocol and reports the ELO delta. The
    NNUE pipeline (gen-data-wdl → train_v3 → quantize_mlp → calibrate)
    is wired end-to-end and driven by the Hetzner GitOps runner — see
    [`infra/README.md`](infra/README.md).
- **SIMD acceleration of the int8 forward pass**:
  - Native x86 → AVX2 (`_mm256_maddubs_epi16` + `_mm256_madd_epi16`):
    +20 % per node vs the float32 MLP.
  - Browser → WASM SIMD128 (`wasm_i16x8_extmul_*` +
    `wasm_i32x4_extadd_pairwise_*`): direct gain for the Draught
    Master web app.
  - Both paths share the same dot-product shape; CMake gates each
    with a CheckCXXCompilerFlag + `-msimd128` for Emscripten.
- **Training & book pipelines**:
  - `--gen-data` produces a self-play dataset with labels from a
    depth-8 search; **`--gen-data-wdl`** (Cycle-1) adds the game's
    win-draw-loss outcome to each record (38 B JNNW format), used by
    the blended-target trainer below.
  - `tools/train.py` (NumPy lstsq) fits the `LinearNetwork`,
    `tools/train_mlp.py` (PyTorch + Adam, early-stop) fits a single
    fixed-arch MLP, and **`tools/train_v3.py`** (Cycle-2) compares
    several MLP architectures on a JNNW dataset with a blended
    score-and-WDL MSE loss and reports which one generalises best.
    Supports both V2 and HalfMen-lite input encodings via
    `--encoding {v2,halfmen}`.
  - `tools/quantize_mlp.py` does post-training int8 quantisation
    with 99.9-pct activation calibration; the JNNQ header carries
    the runtime hidden dims so any trained topology loads back.
  - `tools/calibrate_vs_scan.py` plays Jass vs Scan over the HUB
    protocol and reports a Jass-side ELO estimate — the absolute
    strength yardstick the project is tuning against.
  - `--build-book` consumes a FEN list and writes a **JBOK** binary
    book (`PackedMove`-keyed, 16 B per entry); `--book path.bok`
    loads it at startup. **`tools/merge_jbok.py`** merges several
    partial JBOKs into one (used to parallelise `--build-book` at
    the shell level since the C++ side is single-threaded).
  - Mobile-friendly GitHub Actions workflows (`train-nnue`,
    `benchmark-nnue`, `benchmark-nnue-vs-nnue`, `build-book`,
    `gen-data-wdl`) trigger the whole pipeline from a tap.
- **Hetzner GitOps runner** (see [`infra/README.md`](infra/README.md)):
  a single Hetzner cloud machine (CCX-class) bootstrapped from
  `infra/bootstrap.sh` polls the repo every 5 min, runs the scripts
  in `jobs/queue/`, and commits results back to `jobs/results/<id>/`.
  Pause/resume via a committed flag file (`jobs/state/runner-paused`),
  no SSH required for normal operation. The full
  gen-data → train → quantise → calibrate cycle has been driven this
  way end to end.
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

./build/jass_tests              # unit tests (722 assertions)
```

Requires a C++20 compiler (GCC ≥ 11, Clang ≥ 13, MSVC ≥ 19.30). On
x86, AVX2 is opted in automatically through `-mavx2` (see CMake's
`Jass: AVX2 enabled` line); pass `-DJASS_ENABLE_SIMD=OFF` to keep the
binary portable to older CPUs.

### Training & book pipelines

```sh
# --- Cycle-1 onwards: WDL-labelled data (recommended for new training) ---
# Generate a self-play dataset, each record carrying both a deep-search
# score and the eventual win/draw/loss outcome of the game.
./build/jass --gen-data-wdl 100000 selfplay.bin 20 4 200 1
#                            n      out         eval_d play_d max_plies seed

# Multi-arch trainer with blended score+WDL MSE loss (Cycle-2). Picks
# whichever architecture generalises best on a held-out split.
python3 tools/train_v3.py --data selfplay.bin \
    --archs 64-32 128-64 256-128 512-256 --encoding halfmen \
    --epochs 30 --out-dir trained_v3

# Post-training int8 quantisation (4× smaller, AVX2/WASM-SIMD path).
python3 tools/quantize_mlp.py --in trained_v3/nnue-256-128.bin \
    --data selfplay.bin --out nnue-256-128-q.bin

# Benchmark against the handcrafted eval (sanity, depth-controlled).
./build/jass --benchmark-nnue nnue-256-128-q.bin 5 2

# Calibrate vs Scan (Fabien Letouzey) — the real strength yardstick.
# Scan ships pre-built at github.com/rhalbersma/scan; clone, then:
python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan /tmp/scan/scan_linux \
    --nnue nnue-256-128-q.bin --movetime 1.0 --pairs 3

# --- Legacy single-arch path (kept for the embedded LinearNetwork / MLP) ---
./build/jass --gen-data 100000 selfplay.bin           # score-only, no WDL
python3 tools/train.py     --data selfplay.bin --out linear.bin
python3 tools/train_mlp.py --data selfplay.bin --out mlp.bin

# --- Opening books (JBOK) ---
# Build directly (single-threaded C++):
./build/jass --build-book fens.txt book.bok 12
# Or shell-parallelise across N cores then merge:
split -n l/4 fens.txt chunk-
for f in chunk-*; do
    ./build/jass --build-book "$f" "partial-$f.bok" 12 &
done; wait
python3 tools/merge_jbok.py --out book.bok partial-*.bok

# --- Head-to-head comparison of two networks ---
./build/jass --benchmark-nnue-vs-nnue netA.bin netB.bin 5 5
```

All of the above are also wired as one-tap GitHub Actions workflows
(`train-nnue`, `benchmark-nnue`, `build-book`, `gen-data-wdl`) — see
"Continuous integration" below. For long-running multi-day datasets the
**Hetzner GitOps runner** in [`infra/`](infra/README.md) is what
actually drives the pipeline in practice.

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
│   ├── build-book.yml     workflow_dispatch: --build-book from FEN list
│   └── gen-data-wdl.yml   workflow_dispatch: matrix-sharded WDL self-play
├── docs/                  reference documentation
│   ├── ARCHITECTURE.md    module map and data-flow
│   ├── HUB.md             CLI command reference
│   ├── WASM.md            JS / WebAssembly API
│   ├── API.md             C++ header reference
│   ├── EXTENDING.md       recipes (new bitbase, eval term, book line, …)
│   └── GLOSSARY.md        draughts and engine terms
├── positions (2).fen      77 560-position FEN list (Hub-style) staged at
│                          repo root for an opening-book build via
│                          `--build-book` / `jobs/queue/0013-build-book.sh`
├── infra/                 Hetzner GitOps runner (see infra/README.md)
│   ├── bootstrap.sh       one-shot installer for a fresh Ubuntu 24.04
│   ├── runner.py          tick body — git pull, reap, heartbeat, pick
│   ├── jass-runner.{service,timer}   systemd unit + 5-min timer
│   └── README.md          runner usage + pause/resume via flag file
├── jobs/                  GitOps job queue (written to by maintainers,
│   │                      executed by the runner on a Hetzner host)
│   ├── queue/             one shell script per job; runner picks the
│   │                      oldest numeric prefix that has no status.json
│   ├── results/<id>/      output.log, status.json, artefacts/ per job
│   └── state/             in-flight.json (current job), runner-paused
│                          (pause flag), _runner/progress.json (heartbeat)
├── tools/                 Python tooling for the training pipeline
│   ├── train.py           LinearNetwork trainer (NumPy lstsq)
│   ├── train_mlp.py       MLPNetwork trainer (PyTorch + Adam)
│   ├── train_v3.py        Cycle-2 multi-arch MLP trainer over a JNNW
│   │                      dataset; blended score+WDL MSE loss
│   ├── scout_wdl.py       experimental WDL-only scout (precursor to v3)
│   ├── scout_halfmen.py   HalfMen-encoding scout for arch search
│   ├── bench_arch.py      Cycle-5 end-to-end pipeline (train → quantise
│   │                      → jass) for a single arch — convenience wrapper
│   ├── quantize_mlp.py    post-training int8 quantisation (writes JNNQ)
│   ├── calibrate_vs_scan.py  HUB-protocol Jass-vs-Scan match runner
│   │                      with ELO estimate
│   └── merge_jbok.py      merge partial JBOK files (parallelised
│                          --build-book at the shell level)
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
├── tests/                 unit tests (single executable, 722 assertions)
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

## Roadmap — extraction depuis le framework `dilf`

The sister repository [`jfrancoiscollin/dilf`](https://github.com/jfrancoiscollin/dilf)
(MIT-licensed, Python) builds a deterministic pedagogy framework on top of a
~6 100-page corpus of international-draughts reference books (Dubois and
others). It targets a *human* user via Draught Master, not the engine — its
motif detectors, feature extractors, and verdict classifier encode heuristics
that humans use to compensate for shallow calculation, which a depth-20+
search already sees through.

What dilf produces *as a side effect* is highly valuable to jass, however:
the extraction pipeline turns book PDFs into structured Python fixtures
(annotated FENs, best-move labels, motif tags). Three artefacts will be
folded back into jass once dilf has produced enough material — none of them
require importing dilf itself; we only consume its data exports.

| Artefact (dilf side)                                | jass entry point                          | Cycle  | Expected ELO |
|-----------------------------------------------------|-------------------------------------------|--------|---|
| `dubois_diagrams.py` (FEN + best-move + motif tag)  | new `--bench-tactics` mode + a fixture    | **7-A** | indirect — KPI that reveals where jass weakens, then guides training |
| Opening positions extracted from `dubois_ouvertures.pdf` | append to `positions (2).fen`, requeue 0013 to rebuild book | **7-B** | +30 to +80 (curated theory > self-search depth-12) |
| `MoveVerdict` records from analysing master games   | new label source for `train_v3.py`, blended with `--gen-data-wdl` | **8** | +30 to +100 (cleaner training signal than self-play) |

**What we explicitly will *not* import from dilf**:

- The `MotifDetector` chain (coup royal, coup turc, …) — the engine sees the
  result of the combination at the leaf; naming the pattern adds nothing.
- The `Features` dataclass as additional NNUE inputs — modern NNUE learns
  these implicitly; hard-coding them typically *degrades* generalisation.
- The `Verdict` classifier — jass already classifies move quality via
  depth-N score deltas inside `--benchmark-nnue`.
- The `BookRAG` / `claude_writer` / `UserProfile` layers — pure user-facing
  pedagogy, irrelevant to engine strength.

**Blocker**: dilf's CV pipeline (`scripts/extract_diagrams.py`) needs to have
produced enough hand-verified fixtures from the corpus before Cycle 7-A is
worth scaffolding. As of this commit, only `pedagogy/tests/fixtures/dubois_diagrams.py`
exists as a starter sample. We track that progress externally; this section
exists so the path is documented and the constraints are explicit.

**Sequencing**:

1. **Today**: Cycle 1–6c done, Cycle 7-pre (calibrate-vs-Scan, opening book
   from existing 77 K positions) running on the Hetzner runner.
2. **When dilf has ≥ 1 000 verified fixtures**: Cycle 7-A — add
   `--bench-tactics`, a one-shot job `0014-bench-tactics.sh`, and a parser
   in `tools/dilf_to_tactics.py` that converts `dubois_diagrams.py` into a
   jass-friendly FEN+expected-move fixture. ~1 h dev.
3. **When dilf's opening section is extracted**: Cycle 7-B — a parser
   `tools/dilf_to_book_fens.py` that appends curated openings to the
   existing FEN list, requeue 0013 to rebuild. ~30 min dev.
4. **Cycle 8** — pipeline `dilf-master-game-PDN → MoveVerdict → JNNW
   custom records → blend with --gen-data-wdl in train_v3`. ~3–5 h dev,
   gates on having enough analysed master games.

This roadmap is intentionally *pull*-based: jass does not depend on dilf to
reach competitive strength via the existing NNUE + α-β path. dilf material
is an accelerator on top, available when ready.

## Roadmap — extraction de master games (Cycle 8 data source)

Cycle 8 of the dilf roadmap above blends master-game labels with self-play
records into the `train_v3` training corpus. The *source* of those master
games doesn't have to be dilf's PDF→fixture extraction — there are direct,
already-structured sources of FMJD-level games that bypass the entire CV
pipeline. This section enumerates them so we can pick the right one when
the cycle is triggered.

### Candidate sources

| Source                                | Format             | Volume (est.)                       | Effort           |
|---------------------------------------|--------------------|-------------------------------------|------------------|
| **Lidraughts.org** ⭐                  | Public API + monthly PDN database dumps (Lichess-style; Lidraughts is its draughts sibling, also AGPL) | Millions of games/month, filterable by rating | Very low — API calls, no scraping |
| Toernooibase Dammen (KNDB, NL)        | HTML pages with PDN downloads per tournament | Decades of WC / European / KNDB tournaments | Moderate — HTML scraping + PDN parsing |
| FMJD.org direct                        | Tournament results pages, occasional PDN | Variable per event; many PDFs, few structured PDN | High — no API, inconsistent format, lots of PDF |
| Curated GitHub PDN collections         | `git clone` ready  | A few thousand well-curated WC games | Very low — but limited size |

**Recommended default: Lidraughts.** Same reasoning as benching against Scan
rather than Athénan — pick the source whose data is open, structured, and
scriptable. Filter `rating ≥ 2200` to approximate FMJD-strong play.

### Time estimate

Concrete numbers for **200 000 games**, assuming Lidraughts mirrors Lichess's
well-documented patterns (this is the part to verify on first contact, not
inferred from a current spec):

| Phase                                          | Wall time on a normal connection |
|------------------------------------------------|----------------------------------|
| Discovery (build candidate user/event list, identify the right monthly dump) | 30–60 min |
| Download (monthly DB dump path: a few-GB `.pdn.zst`; API path: a few hundred batched requests) | 30 min – 2 h |
| Parse + filter to (FEN, side-to-move, game-outcome) records | 30–60 min CPU |
| **Total (first run, end-to-end)**              | **~2–4 h wall time**             |
| Subsequent incremental fetches                 | Minutes (only new months) |

At ~80 plies/game, 200 000 games → **~16 M positions** with WDL labels — far
beyond the 1 M we generate by self-play, and at a quality level that
self-play cannot reach by construction.

### Caveats — what I do not know with certainty

- The exact current Lidraughts API endpoints and rate limits — Lichess
  changes its API over time and Lidraughts likely tracks it; first task of
  the implementation is to *read its docs*, not assume.
- Whether Toernooibase's terms of service permit automated download — to
  read in their footer before scraping. Public-tournament game scores are
  generally not copyrightable as facts, but a database compilation may be.
- The exact PDN dialect served by each source (FMJD / Dutch / HUB variants
  differ in coordinate encoding and capture notation). Our `--gen-data-wdl`
  output uses the Hub-style FEN, so the converter will need to normalise.

### Plan (when triggered)

1. **Cycle 8-pre — `tools/fetch_lidraughts_games.py`**
   - Hit Lidraughts API (or download the monthly DB dump and filter).
   - Apply `--min-rating` filter (default 2200).
   - Parse each PDN into `(FEN, stm, ply, game_result)` tuples.
   - Emit one JNNW-format file at the same on-disk layout as `--gen-data-wdl`
     produces (38 B per record, magic header, sortable). One Python script,
     no C++ changes.
2. **Cycle 8 — `train_v3.py` blended source**
   - Add a `--master-data PATH` argument that consumes the JNNW from 8-pre
     alongside the existing self-play data.
   - Add a `--master-weight FLOAT` to control the relative importance of
     master labels vs self-play in the MSE loss (e.g. 5× more weight per
     master record).
   - Empirical sweep to find the right ratio.
3. **Cycle 8-bis (optional) — `tools/scrape_toernooibase.py`**
   - Same output format, different source.
   - Use to add explicit FMJD-pedigree provenance on top of Lidraughts
     rating-filtered data. ~3–5× less data but higher provenance.

### Independence from dilf

This path is **fully independent** of dilf's CV pipeline. The dilf roadmap
above remains useful for **tactics test fixtures (Cycle 7-A)** and
**curated openings (Cycle 7-B)**, but for Cycle 8 the master-game label
source via Lidraughts is strictly easier and arrives sooner. If dilf later
exposes annotated master games (with motif tags), they can be folded in as
a *third* source with higher weight — not a precondition.

## Contributing & extending

If you want to add a new opening line, plug a new endgame into the
bitbase, tweak the evaluation, swap the NNUE weights, or add a HUB
command, the recipes are in [docs/EXTENDING.md](docs/EXTENDING.md).

When sending a patch:

- Build must be green (`cmake --build build -j`).
- All tests must pass (`./build/jass_tests`).
- Keep the clean-room policy: do not look at any GPLed engine's source
  while writing Jass code.
