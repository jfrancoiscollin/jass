# HUB-flavoured CLI reference

`./build/jass` (without arguments) reads HUB-style commands on stdin and
writes responses on stdout, line by line. This is the form a draughts
GUI expects when launching an engine.

This document specifies every command the front-end accepts and every
line it can emit. The protocol is a deliberately minimal subset designed
to be easy to drive by hand and from another program; richer HUB
extensions (`level`, `ponder`, …) can be layered on top later without
breaking the commands listed here.

## General syntax rules

- **One command per line.** A line is the substring up to the next
  newline.
- **Leading and trailing whitespace** are trimmed.
- **Tokens** are whitespace-separated (spaces or tabs).
- The first token is the **command name**; the rest are its arguments.
- Empty lines are ignored.
- Every response also fits on one line, with key/value pairs joined by
  `=` (no spaces inside a single key/value).
- Unknown commands produce an `error unknown command` line and the
  loop continues.

## Commands

### `hello`

Handshake. Identifies the engine.

```text
> hello
< id name=Jass version=0.0.1 author="Jean-François Collin"
< ready
```

### `newgame`

Reset to the standard initial position, clear the transposition table
and the game's hash history. A subsequent `apply` will start a fresh
game.

```text
> newgame
< ok
```

### `position startpos`

Same as `newgame` but specifically signals "use the standard starting
layout".

```text
> position startpos
< ok
```

### `position fen <FEN>`

Replace the current position with the given Hub-style FEN string. See
[Move and FEN notation](#move-and-fen-notation) below for the FEN
grammar.

```text
> position fen W:W31-50:B1-20
< ok
```

On a malformed FEN:

```text
> position fen garbage
< error bad fen
```

### `apply <move>`

Play one move. The move must be legal in the current position. Both
quiet (`from-to`) and capture (`fromxto`) notations are accepted.

```text
> apply 31-26
< ok

> apply 28x17
< ok
```

On an illegal move (or a syntactically valid move that simply isn't in
the legal-move list):

```text
> apply 1-2
< error apply: not a legal move
```

### `go [...]`

Start a search and emit a `bestmove` line when it completes. The `go`
command accepts any combination of the following key/value tokens, in
any order:

| Token | Argument | Meaning |
|-------|----------|---------|
| `depth`     | `<int>`  | Iterative deepening up to this depth. |
| `movetime`  | `<ms>`   | Hard wall-clock cap (synchronous). |
| `infinite`  | (none)   | Search until `stop`. Runs in a worker thread. |
| `wtime`     | `<ms>`   | White's remaining clock (tournament budget). |
| `btime`     | `<ms>`   | Black's remaining clock. |
| `winc`      | `<ms>`   | Increment per move, white. |
| `binc`      | `<ms>`   | Increment per move, black. |
| `movestogo` | `<int>`  | Moves until the next time control. |

Defaults:
- `go` (no args) → `depth 6`.
- `go infinite` → search to `MAX_PLY`, controlled by `stop`.
- `go movetime <ms>` → search as deep as time allows.
- A tournament-style budget (`wtime/btime/[winc/binc/movestogo]`) is
  converted to a per-move `movetime` via the formula in
  [`src/timemgr.cpp`](../src/timemgr.cpp).

Examples:

```text
> go depth 8
< bestmove 31-26 score=0 depth=8 nodes=49735 pv=31-26,17-21,…
```

```text
> go movetime 200
< bestmove 35-30 score=2 depth=11 nodes=162816 pv=35-30,…
```

```text
> go wtime 60000 btime 60000 winc 1000 binc 1000
< bestmove 32-28 score=5 depth=10 nodes=87432 pv=32-28,…
```

```text
> go infinite
> stop
< bestmove 34-30 score=-1 depth=14 nodes=...
```

When the chosen move came from the opening book, the line carries
`book=1` and `depth=0 nodes=0`:

```text
> go depth 6
< bestmove 32-28 score=0 depth=0 nodes=0 book=1 pv=32-28
```

### `stop`

Interrupt the current search. If a worker thread is running (`go
infinite`) it is signalled to abandon the search and joined; the
`bestmove` line for the (possibly partial) result has been emitted by
the worker before `stop` returns. If no search is running, `stop` is a
no-op.

### `setoption threads <N>`

Set the number of search threads (lazy SMP) for subsequent `go`
commands. `N` must be ≥ 1. Default is 1.

```text
> setoption threads 4
< ok
```

### `eval`

Print the static evaluation of the current position from White's point
of view, in centipawns.

```text
> eval
< eval 5
```

### `fen`

Print the current position as a Hub-style FEN.

```text
> fen
< fen W:W26,32,33,34,35,…:B1,2,3,…
```

### `quit`

Stop any running worker and exit the loop. End-of-file on stdin has
the same effect.

## `bestmove` line format

```
bestmove <move> score=<int> depth=<int> nodes=<int> [book=1] [pv=<m1>,<m2>,…]
```

| Field   | Meaning |
|---------|---------|
| `<move>` | The chosen move, in the move notation below. |
| `score=` | Score from the side-to-move's POV, in centipawns. Mate scores are around `±29 935` (close to `MATE_SCORE − MAX_PLY − 1`). |
| `depth=` | Last fully-completed iterative-deepening depth. |
| `nodes=` | Total nodes visited in the search. |
| `book=1` | Present only when the move came from the opening book. |
| `pv=`    | The principal variation as a comma-separated list of moves, walked from the TT after the search completes. |

## Move and FEN notation

### Squares

The 50 playable (dark) squares of the 10×10 board are numbered 1–50
in the standard FMJD convention: 1–5 across the top row of Black's
side, 46–50 across the bottom row of White's side, increasing left to
right and row by row.

### Move notation (CLI input/output)

- Quiet move: `from-to`        — e.g. `31-26`.
- Capture:    `fromxto`        — e.g. `28x17`.
- Multi-jump capture: any sequence of `<sq>x<sq>x...` is accepted on
  input (e.g. `28x19x10`); the engine resolves the captured-piece
  path against the legal-move list using the (from, to) endpoints.
  On output, `format_move` always emits the compact `fromxto` form.

### Hub FEN

```
<stm> ":" <colour-list> ":" <colour-list>
```

Where:

- `<stm>` is `W` or `B`.
- Each `<colour-list>` starts with the colour letter (`W` or `B`) and
  is followed by a comma-separated list of entries.
- Each entry is either a single square (`32`), a range (`31-50`) or
  the same prefixed by `K` to denote a king (`K28`, `K30-32`). `K`
  applies to that entry only; the colour letter is **not** repeated
  per entry.

Examples:

| FEN | Meaning |
|-----|---------|
| `W:W31-50:B1-20` | Standard initial position, white to move. |
| `B:WK28:BK1` | One white king on 28, one black king on 1, black to move. |
| `W:WK28,K33,41:BK1` | Two white kings + a man vs one black king. |

The half-move clock (FMJD 25-move-rule counter) is **not** encoded in
this minimal FEN format — it is treated as 0 on parse.

## Threading and ordering of output

The HUB front-end has a worker thread for `go infinite`. Output is
serialised behind a small mutex, so a `bestmove` line emitted by the
worker can never interleave with any line emitted by the main thread.
Within a single thread, lines are emitted in the order their commands
arrived.

## Exit codes

`./build/jass` always returns 0 from a clean exit (`quit` or stdin
EOF). Crash-style exits (e.g., a SIGSEGV in the engine) propagate the
default OS signal; they are bugs and should be reported.
