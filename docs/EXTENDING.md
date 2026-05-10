# Extending the engine

A few cookbook-style recipes for the most likely modifications.

Every recipe ends with a *test* step. `./build/jass_tests` must stay
green after each one — that's the engine's only contract that matters.

---

## 1. Add an opening line

Goal: teach the book a new starting line so the engine plays it without
searching.

1. Open [`src/book.cpp`](../src/book.cpp).
2. Add a flat list of `(from, to)` pairs to `OPENING_LINES`. Each line
   is replayed from the standard initial position, so step 1 must be a
   move legal at the start, step 2 a move legal after step 1, and so
   on. The book stores **one** entry per position (the first arrival
   wins), so prefix-sharing lines naturally co-exist.

```cpp
const std::vector<std::vector<Step>> OPENING_LINES = {
    // … existing lines …
    {{31, 27}, {18, 22}, {27, 18}, {12, 23}},   // ← new line
};
```

3. Run `cmake --build build -j && ./build/jass_tests`.
4. Optionally, add a probe assertion in
   [`tests/test_book.cpp`](../tests/test_book.cpp).

---

## 2. Plug a new endgame into the bitbase

Goal: add support for, say, KKKvK.

The retrograde-analysis machinery is generic; what the table currently
encodes is the (count of white pieces, count of black pieces) =
`(2, 1)` shape, with the symmetric `(1, 2)` derived by colour-swap.
Adding `(3, 1)` requires:

1. Decide on an encoding. For 3 white kings + 1 black king, with
   `wk1 < wk2 < wk3`, you need ~50³ × 50 × 2 / 6 ≈ 100k slots; a
   500 KB byte table is fine.
2. In [`src/bitbase.cpp`](../src/bitbase.cpp), add a new
   `class ThreeVsOneBitbase` modelled on `TwoVsOneBitbase`:
   - Index function `(wk1, wk2, wk3, bk, stm) → flat index`.
   - `make_pos`, `child_result`, `build` mirroring the existing class.
     The `child_result` step needs an extra branch: a (3,1) parent's
     children may be (3,1) again or transition to (2,1) after a black
     capture, then to known-terminal cases.
3. In [`src/endgame.cpp`](../src/endgame.cpp), add the dispatch:

```cpp
if ((wk == 3 && bk == 1) || (wk == 1 && bk == 3)) {
    return probe_kings_endgame_3v1(pos);   // your new function
}
```

4. Add a couple of tests in
   [`tests/test_endgame.cpp`](../tests/test_endgame.cpp).

The 16-move drawing rule is still not modelled — see the caveat in
[ARCHITECTURE.md](ARCHITECTURE.md#endgame-bitbase-build-flow).

---

## 3. Add a handcrafted evaluation term

Goal: add, e.g., a "king-on-long-diagonal" bonus.

1. In [`src/eval.cpp`](../src/eval.cpp):
   - Add a constant for the term's weight.
   - Either bake it into the relevant PSQT table at construction time
     (if it depends only on the piece's square and kind) or compute
     it as a runtime function called from `evaluate(pos)`.
   - Add a corresponding contribution to `evaluate_nnue`'s default
     weights in [`src/nnue.cpp`](../src/nnue.cpp), so the two stay
     in rough agreement.
2. Add a discriminating test in
   [`tests/test_search.cpp`](../tests/test_search.cpp): show that two
   positions identical except for the new term have the expected
   ordering.

The existing tests are deliberately tolerant of small eval changes
(they assert sign and ordering, not exact values), so a small new
term should not break the suite.

---

## 4. Replace the NNUE weights

Goal: drop trained weights into the engine.

1. Train a network whose forward pass matches `LinearNetwork::evaluate`:
   inputs are 200 binary features `[square 0..49] × [piece-kind 0..3]`,
   output is a single int (centipawn-scaled).
2. Export the weights as `int32_t[NUM_SQUARES][4]` in little-endian
   square-major order. In Python: `numpy.tofile('weights.bin')` does
   exactly that for an `int32` array.
3. In your application code:

```cpp
LinearNetwork net;
net.load("weights.bin");
const int score = net.evaluate(pos);
```

4. To make the *search* use the network, swap the `evaluate(pos)` call
   in [`src/search.cpp`](../src/search.cpp) for
   `evaluate_nnue(pos)` (and update the leaf-only `quiescence`
   accordingly). Re-run the test suite.

A real NNUE pipeline (sparse incremental updates, hidden layers,
clipped-ReLU) requires more substantial framework changes — the
single-layer `LinearNetwork` is the proof-of-concept that the loader
format works.

---

## 5. Add a HUB command

Goal: extend the CLI with, e.g., a new `pondering` flag.

1. In [`src/hub.hpp`](../src/hub.hpp), declare a new `cmd_*` member
   on `HubFrontEnd` and update the comment block at the top with the
   new command's syntax.
2. In [`src/hub.cpp`](../src/hub.cpp):
   - Add a new branch to the `dispatch(...)` if/else chain.
   - Implement the body. Use `emit_ok()` / `emit_error()` for
     responses; if you need to write multiple lines, hold
     `out_mutex_` for the duration so worker output doesn't
     interleave.
   - If the command needs to interact with a running search, set
     `stop_flag_` and call `wait_for_worker()` before doing so.
3. Add a session-style test in
   [`tests/test_hub.cpp`](../tests/test_hub.cpp): pipe the command
   through `drive_session(...)` and assert the expected substring
   appears in the output.

---

## 6. Add a search heuristic (e.g., null-move pruning)

The current search is linear and easy to follow:
[`src/search.cpp`](../src/search.cpp). The principal hooks:

- `Searcher::negamax` is the per-node entry point. Every new
  pruning/extension idea attaches here.
- Move ordering happens in `order_moves` (called from `negamax`).
  Add a new score band (above killers, below TT-move) for any new
  prioritised category.
- The aspiration window logic lives in the iterative-deepening loop
  inside the top-level `search` overloads.
- Beta-cutoff bookkeeping (killers, history) is at the very bottom of
  `negamax`'s move loop.

Test new heuristics by running a `--tournament` between the modified
build and the previous one (`./build/jass --tournament 4 4 5` is a
quick 10-game sanity check). For correctness, perft and the existing
search tests must remain green.

---

## 7. Expose a new field in the WASM `Game` class

Goal: extend the JavaScript API.

1. In [`src/wasm_api.cpp`](../src/wasm_api.cpp):
   - Add a new method to the `Game` C++ class that returns either a
     primitive (`int`, `bool`, `std::string`) or `emscripten::val`
     (for arrays / objects).
   - Register it in the `EMSCRIPTEN_BINDINGS(jass_module)` block.
2. Rebuild the WASM (CI does this automatically) and update
   [`docs/WASM.md`](WASM.md) with the new method's signature.

Note: `wasm_api.cpp` is gated on `#ifdef __EMSCRIPTEN__`, so a normal
native build is unaffected.

---

## 8. Add a unit-test group

1. Create `tests/test_<topic>.cpp`. Include
   `"test_framework.hpp"` and define one or more `void test_*()`
   functions plus a single `void run_<topic>_tests()` at the bottom.
2. Declare the runner in
   [`tests/test_framework.hpp`](../tests/test_framework.hpp).
3. Call it from
   [`tests/test_main.cpp`](../tests/test_main.cpp).
4. Add the new file to `add_executable(jass_tests …)` in
   [`CMakeLists.txt`](../CMakeLists.txt).

`JASS_CHECK(cond)` and `JASS_CHECK_EQ(a, b)` are the two assertion
macros. Failure prints file:line and the source text of the
expression; the runner returns 1 if any assertion fails.

---

## Things you should NOT do

- **Read GPLed engine source.** Jass's clean-room policy is its
  whole point — it's what lets it ship under MIT. If you want to
  borrow an idea, derive it from a paper, blog post, or your own
  thinking, not from another engine's source.
- **Disable `-Wall -Wextra -Wpedantic`.** Warnings are escalations
  to errors in CI for good reason.
- **Skip the test suite.** A green test suite is the contract the
  rest of the codebase counts on. Adding a feature without a
  matching assertion is regression-prone.
