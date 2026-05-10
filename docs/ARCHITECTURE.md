# Architecture

A guided tour of how Jass is laid out and how data flows through it during
a search. Pair this document with [API.md](API.md) for the per-header
signatures and with [GLOSSARY.md](GLOSSARY.md) for the vocabulary.

## Module map

```
                         ┌──────────────────┐
                         │      types.hpp   │  Color, Piece, Square, Move
                         └────────┬─────────┘
                                  │
                    ┌─────────────┼──────────────┐
                    ▼             ▼              ▼
          ┌──────────────┐ ┌─────────────┐ ┌──────────────────┐
          │  bitboard    │ │   board     │ │ zobrist_keys     │
          │  50-bit ops  │ │ neighbour   │ │ hashing tables   │
          └──────┬───────┘ │  tables     │ └────────┬─────────┘
                 │         └──────┬──────┘          │
                 └────────────────┼─────────────────┘
                                  ▼
                          ┌────────────────┐
                          │   position     │  state + FEN + Zobrist
                          └───────┬────────┘
                                  ▼
                          ┌────────────────┐
                          │    movegen     │  legal-move generator
                          └───────┬────────┘
              ┌───────────────────┼─────────────────────┐
              ▼                   ▼                     ▼
       ┌─────────────┐    ┌─────────────────┐    ┌──────────────┐
       │   eval      │    │      tt         │    │   endgame    │
       │  + nnue     │    │  + zobrist      │    │  + bitbase   │
       └──────┬──────┘    └────────┬────────┘    └──────┬───────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   ▼
                            ┌────────────────┐
                            │     search     │  α-β + ID + qsearch
                            └────────┬───────┘   + lazy SMP
                                     ▼
              ┌───────────┬──────────┴──────────┬──────────────┐
              ▼           ▼                     ▼              ▼
        ┌─────────┐ ┌─────────┐         ┌──────────────┐ ┌──────────┐
        │  book   │ │ engine  │ ◄────── │  tournament  │ │ timemgr  │
        └─────────┘ └────┬────┘         └──────────────┘ └─────┬────┘
                         ▼                                     │
                  ┌──────────────┐  ┌─────────────────┐        │
                  │      hub     │ ◄┤  main.cpp / CLI │ ◄──────┘
                  └──────┬───────┘  └─────────────────┘
                         ▼
                  ┌──────────────┐
                  │  wasm_api    │  Embind bindings (Emscripten only)
                  └──────────────┘
```

The dependency graph is intentionally a DAG with no cycles. The two
non-obvious facts:

- `position` includes `zobrist_keys`, NOT `zobrist` (which would create a
  cycle since `zobrist.hpp` includes `position.hpp`). Keys are separated
  out so `Position::after`, `add_piece` and friends can update the hash
  incrementally.
- `endgame` is a thin façade that fans out to `bitbase` for the
  retrograde-analysis tablebase. `search` only depends on `endgame`.

## A move's life inside the search

For a single search request the call chain is:

```
caller
  └─ Engine::search(SearchLimits)              [engine.cpp]
       ├─ Book::probe(pos)                     [book.cpp]      (early-out)
       └─ jass::search(pos, lim, tt, history)  [search.cpp]
            ├─ probe_endgame(pos)              [endgame.cpp]   (root)
            ├─ for depth = 1 .. max_depth:
            │    ├─ run_root_window(α, β)
            │    │    └─ for each root move m:
            │    │         └─ negamax(pos.after(m), d-1, ply, -β, -α)
            │    │              ├─ stop polling                [search.cpp]
            │    │              ├─ path-dependent draws        [search.cpp]
            │    │              ├─ probe_endgame(pos)          [endgame.cpp]
            │    │              ├─ tt.probe(hash)              [tt.cpp]
            │    │              ├─ generate_legal_moves(pos)   [movegen.cpp]
            │    │              ├─ if depth ≤ 0: quiescence(...)
            │    │              ├─ order_moves(...)            [search.cpp]
            │    │              ├─ for each m: -negamax(pos.after(m), …)
            │    │              ├─ on cutoff: update killers + history
            │    │              └─ tt.store(hash, …)
            │    └─ aspiration retry on fail-low / fail-high
            └─ extract_pv(pos, tt)              [search.cpp]   (after last iter)
```

`Position::after(Move)` (in [position.cpp](../src/position.cpp)):
- removes the moving piece from its origin square,
- removes every captured piece in `Move::captures`,
- places the piece on `Move::to`, upgrading a man to a king if
  `Move::promotes` or if the moving piece was already a king,
- flips `side_to_move`,
- updates the half-move clock (reset on a capture or man move,
  incremented on a king's quiet move),
- maintains the Zobrist hash incrementally (no full rehash).

## Threading model (lazy SMP)

When `SearchLimits.threads > 1` the search spawns `threads - 1` helper
threads inside [search.cpp](../src/search.cpp).  Each helper invokes
`jass::search(pos, hlim, tt, history)` again with `threads = 1` and a
shared `helper_stop` atomic.  Helpers don't return a result; they just
populate the (shared) transposition table for the main thread to reuse.

Synchronisation:
- The `TranspositionTable` is read and written without locks. Concurrent
  races may yield occasional stale entries; the search is self-
  correcting (move legality is verified on use, scores are merely
  hints). This is the standard lazy-SMP trade-off.
- The main thread sets `helper_stop` after its iterative deepening
  finishes and joins every helper before returning.

## TT lifecycle

- `Engine` owns one `TranspositionTable`. Across `Engine::search` calls
  the table is reused (warm), which is the whole point of having an
  Engine.
- `Engine::new_game()` calls `TranspositionTable::clear()`, which fills
  every slot with a default `TTEntry` (key = 0, bound = `Bound::None`).
- `Engine::set_position(...)` does NOT clear the table — entries from a
  previous game might still apply by hash, and stale entries are
  rejected at probe time anyway.
- Inside `search`, mate scores are translated to a ply-independent
  encoding before storing and translated back on probe so an entry
  produced at one ply is reusable at any other.

## Endgame bitbase build flow

The 2-vs-1 kings tablebase ([bitbase.cpp](../src/bitbase.cpp)) is built
lazily on the first probe via `std::call_once`, so the cost is paid
only by sessions that actually reach an endgame.

Build pseudocode:

```
1. Allocate a flat 50 × 50 × 50 × 2 table, all entries Unknown.

2. Pass 0 (terminal sweep):
     For every (wk1<wk2, bk all distinct, stm) build the corresponding
     Position, generate its legal moves; if the list is empty, label
     the entry Loss-for-STM.

3. Iterate (forward retrograde):
     repeat:
       changed = false
       For every Unknown entry:
         For each legal move:
           child_result = lookup(child)   // recursive in our table or
                                          //   {Win/Loss for terminal
                                          //    "no pieces" children, or
                                          //    Draw for any KvK child}
         if any child is Win-for-us : mark Win-for-us, changed = true
         else if all children are  : mark Loss-for-us, changed = true
              Loss-for-us
     until !changed

4. Anything still Unknown is a Draw.
```

The mirror "1 white king vs 2 black kings" is handled at probe time by
colour-swapping the position and inverting the result.

Trade-off: the FMJD 16-move drawing rule for kings-only endgames is
NOT modelled. A small minority of the WIN-marked positions are in fact
drawn under FMJD because the strong side cannot mate within 16 plies.
Storing distance-to-mate would fix this and is a future refinement.

## Evaluation pipeline

```
evaluate(pos)                         [eval.cpp]
  ├─ for each white man:    +MAN_VALUE  + WHITE_MAN_PSQT[s]
  ├─ for each white king:   +KING_VALUE + KING_PSQT[s]
  ├─ for each black man:    -MAN_VALUE  - BLACK_MAN_PSQT[s]
  ├─ for each black king:   -KING_VALUE - KING_PSQT[s]
  ├─ + support_score(white) - support_score(black)
  ├─ ± TEMPO_BONUS    (depending on side to move)
  └─ flip sign if side_to_move == Black   (side-to-move POV result)
```

`support_score` is the only term that depends on adjacent pieces, not
just the moving piece's square; everything else is a flat per-piece
table that fits inside a constexpr-built array.

`evaluate_nnue(pos)` ([nnue.cpp](../src/nnue.cpp)) is the same shape
but expressed as a (square × piece-kind) weight matrix that can be
loaded from disk for a future trained network.

## Front-ends

- **`main.cpp`** parses a small handful of CLI flags
  (`--smoke`, `--tournament`, `--version`, `--help`) and otherwise
  hands control to `HubFrontEnd`.
- **`hub.cpp`** owns one `Engine`, reads stdin line-by-line and writes
  to stdout under a mutex (so a worker thread emitting `bestmove` and
  the main thread emitting `ok`/`error` cannot interleave).  Long
  searches run in `worker_` (a `std::thread`); `stop` and `quit` set
  the atomic `stop_flag_` and join.
- **`wasm_api.cpp`** is a thin Embind wrapper around `Engine` that
  exposes a `Game` JavaScript class. It is compiled only when the
  build is driven through `emcmake`; under a normal Linux build it
  expands to nothing because the whole file is gated on
  `#ifdef __EMSCRIPTEN__`.
- **`tournament.cpp`** drives two `Engine` instances against each
  other for regression testing. Each engine keeps its own
  `hash_history` so the search's repetition detection works correctly.

## Build configuration switching

`CMakeLists.txt` chooses between native and WASM front-ends via the
`EMSCRIPTEN` CMake variable:

```cmake
if(EMSCRIPTEN)
    add_executable(jass src/wasm_api.cpp)   # produces jass.js + jass.wasm
else()
    add_executable(jass src/main.cpp)       # produces ./jass
endif()
```

Both targets link the same `jass_lib` static library, so every change
to engine code is exercised by both pipelines.
