# WebAssembly / JavaScript API

When built through Emscripten, Jass produces an ES6 module
(`jass.js` + `jass.wasm`) that exposes a single JavaScript class —
`Game` — wrapping the C++ `Engine`.

This document is the contract used by the Draught Master web app and
any other browser front-end.

## Building

### Via GitHub Actions (recommended)

`.github/workflows/build.yml` builds the WASM on every push, uploads
the artefacts under the workflow-artefact name `jass-wasm`, and
optionally publishes a demo site to GitHub Pages on `main`. See the
[CI section of the README](../README.md#continuous-integration--wasm-hosting).

### Locally

Requires the [Emscripten](https://emscripten.org) SDK, with `emcmake`
on `PATH`:

```sh
./wasm/build.sh
# Output:
#   build-wasm/jass.js
#   build-wasm/jass.wasm
#   build-wasm/example.html
```

The default build is `Release` with `-O3` and `-sASSERTIONS=0`. Pass
`./wasm/build.sh Debug` for an unoptimised build with assertions.

## Loading the module

`jass.js` is an ES6 module with a default export named `createJass`
(set via `-sEXPORT_NAME=createJass` in CMake). It returns a Promise
that resolves to a `Module` object once the WASM has finished
instantiating:

```js
import createJass from './jass.js';

const Module = await createJass();
```

The module is configured with:
- `MODULARIZE=1`, `EXPORT_ES6=1`     → ES6 module shape
- `ENVIRONMENT=web,worker`           → loadable in a page or in a Worker
- `ALLOW_MEMORY_GROWTH=1`            → heap can grow as needed
- `FILESYSTEM=0`                     → no `FS` shim (smaller bundle)

A static server is required to serve the `.wasm` file with the right
MIME type — `python3 -m http.server` works, opening the HTML directly
via `file://` does not.

## The `Game` class

```js
const g = new Module.Game();        // start position, white to move
```

All operations below are members of the returned `g` instance.

| Method                  | Returns                | Notes |
|-------------------------|------------------------|-------|
| `g.fen()`               | `string`               | Hub-style FEN of the current position. |
| `g.ascii()`             | `string`               | Multi-line ASCII diagram (debugging). |
| `g.sideToMove()`        | `0 \| 1`               | `0` = white, `1` = black (matches the C++ `Color` enum). |
| `g.legalMoves()`        | `Move[]` (see below)   | All legal moves in the current position. |
| `g.applyIndex(i)`       | `boolean`              | Plays the i-th move from `legalMoves()`. Returns `false` on out-of-range or if the move turned out to be illegal. |
| `g.newGame()`           | `void`                 | Reset to the standard initial position; clears the engine's transposition table and game-history. |
| `g.bestMove(depth)`     | `BestMove` (see below) | Run the engine to the requested depth. Synchronous (blocks the JS thread). |
| `g.delete()`            | `void`                 | **Required** to free the underlying C++ object. Embind objects are not garbage-collected. |

### `Module.Game.fromFen(fen: string)`

Static factory that builds a `Game` initialised to a Hub-style FEN
position. Returns a default-constructed `Game` (start position) on a
parse error — there is no way to throw across the JS/Wasm boundary.

```js
const g = Module.Game.fromFen("W:WK28:BK1");
```

### `Move` shape

`legalMoves()` returns an array of plain objects. `bestMove()` returns
a single object with the same shape plus search metadata:

```js
{
    from:     1..50,           // FMJD square number of the moving piece's origin
    to:       1..50,           // destination square
    captures: number[],        // FMJD squares of captured pieces, in capture order
    promotes: boolean,         // true iff a man ends on the promotion row
    /* extra fields on bestMove() only: */
    score:    number,          // STM-relative score in centipawns; mate ≈ ±29 935
    depth:    number,          // last completed iterative-deepening depth (0 if from book)
    nodes:    number,          // total nodes visited (0 if from book)
    pv:       Move[],          // principal variation (omitted if empty)
}
```

## A complete session

```js
import createJass from './jass.js';

(async () => {
    const Module = await createJass();
    const g = new Module.Game();

    console.log(g.ascii());

    while (true) {
        const moves = g.legalMoves();
        if (moves.length === 0) {
            console.log('Game over.');
            break;
        }
        const best = g.bestMove(6);
        console.log('Engine plays', best.from, '→', best.to,
                    'score', best.score, 'nodes', best.nodes);
        // Find the index of `best` in `moves` and apply it
        // (or use the move's from/to via your own helper).
        const idx = moves.findIndex(m =>
            m.from === best.from && m.to === best.to);
        if (idx < 0) break;          // shouldn't happen
        g.applyIndex(idx);
    }

    g.delete();   // free the wrapped C++ object
})();
```

The bundled [`wasm/example.html`](../wasm/example.html) ships exactly
this kind of demo: it loads the module, prints the start position,
asks the engine for a move at depth 6 and shows the result with
elapsed time.

## Performance notes

- Search runs **synchronously** on the calling thread. For long
  searches in a UI, run the WASM module from inside a Web Worker
  so the browser stays responsive.
- The transposition table lives inside the C++ `Engine` and is reused
  across `bestMove()` calls — a second search at the same depth on the
  same position visits noticeably fewer nodes.
- `g.bestMove(depth)` is the only knob currently exposed. Time-budget
  searches (`movetime`, `wtime/btime/...`) are available in the HUB CLI
  but have not been wired into the WASM façade yet — extending the
  `Game` class is a small, mechanical change (see
  [EXTENDING.md](EXTENDING.md)).
- Lazy SMP (multi-threaded search) requires `pthread` support in the
  Emscripten build, which is **not** enabled by default. Single-thread
  performance is what the current artefacts ship.

## Compatibility

The module targets **modern browsers with ES6 module + WebAssembly +
optional `BigInt` support** — i.e., everything from 2020 onward. There
is no fallback for older runtimes.

## Memory management

Embind-wrapped C++ objects do **not** participate in JavaScript garbage
collection. Always call `g.delete()` when you're done with a `Game`
instance, otherwise you'll leak its `Engine` (which itself holds the
TT and the hash history).
