# Glossary

Domain vocabulary used across the Jass codebase. Two sections — first
the draughts-specific terms, then the engine-side terms that show up
mostly in `search.cpp` and around it.

## Draughts terms

**Bitbase / endgame tablebase.** A precomputed table indexed by
position that gives the theoretical result (WIN / LOSS / DRAW)
without searching. Jass currently includes a 2-vs-1 kings bitbase
built by retrograde analysis ([`src/bitbase.cpp`](../src/bitbase.cpp)).

**Capture.** A jump over an enemy piece to land on the empty square
beyond. Captures are mandatory in international draughts: when one is
available the side to move must play one. See also *majority rule*.

**FMJD.** *Fédération Mondiale du Jeu de Dames* — the international
draughts federation whose rules Jass implements. The 10×10 board, the
1–50 square numbering, and the majority-capture and 25-move rules all
come from the FMJD ruleset.

**Hub FEN.** The position-string format used by the HUB protocol and
by Jass's `Position::to_fen` / `from_fen`:
`<stm>:<W-list>:<B-list>`. See the
[FEN section in HUB.md](HUB.md#hub-fen).

**International draughts.** The 10×10 variant played in continental
Europe and worldwide tournaments, governed by the FMJD. Distinct from
American checkers (8×8, men move forward only, captures end on the
landing square — no chained captures across kings' rays).

**King.** A piece that has reached the opposite side's home rank and
been promoted. Kings move and capture along entire diagonals (any
distance), as opposed to men.

**Long diagonal.** The two main diagonals of the 10×10 board (cells 5
to 46, and 1 to 50). Control of the long diagonal is a classical
strategic theme in international draughts; in 2-vs-1 endgames it
often determines who wins.

**Majority rule (max-capture rule).** When several capture sequences
are available, only the longest (counted in number of pieces
captured) are legal. Jass enforces this in
[`src/movegen.cpp`](../src/movegen.cpp).

**Man.** A piece that has not yet reached the promotion row. Men move
one diagonal square forward at a time; they may capture in all four
directions but cannot move forward more than one square at a time.

**Multi-jump.** A single move that captures two or more pieces in
sequence. The capturing piece keeps its original kind (a man stays a
man) until the chain ends.

**Perft.** Performance test — counting the number of leaf positions
reachable from a starting position at a given depth. Used to validate
move-generator correctness. Jass matches the FMJD reference values
9 / 81 / 658 / 4 265 / 27 117 at depths 1–5 from the start.

**Promotion.** A man becomes a king when it **ends** its move on the
opposite side's home rank. Crucially, a man that *passes through* the
promotion row mid-multijump but ends elsewhere does **not** promote
(see the dedicated test in
[`tests/test_movegen.cpp`](../tests/test_movegen.cpp)).

**PSQT.** Piece-Square Table — a per-(piece-kind, square) constant
contribution to the static evaluation. Jass uses three PSQTs:
white-man advancement, black-man advancement, king centralisation
([`src/eval.cpp`](../src/eval.cpp)).

**25-move rule.** Under FMJD, a game is drawn after 25 consecutive
moves (50 plies) without a capture or a man move. Jass tracks the
counter on `Position::halfmove_clock` and the search returns 0 the
moment it reaches 50.

**3-fold repetition.** A position is drawn if it occurs three times
during the game. As a search heuristic, Jass treats the *first*
repetition as draw-equivalent (the side to move can always force a
3-fold by repeating).

## Engine terms

**Alpha-beta pruning.** The optimisation that prunes branches of the
game tree that cannot affect the final decision. Jass implements
negamax with `[α, β]` windows; a fail-high (`score ≥ β`) skips the
remaining siblings.

**Aspiration window.** A narrow `[score - δ, score + δ]` window
opened around the previous iterative-deepening iteration's score, on
the bet that the next iteration's score will land inside it. On a
fail-high or fail-low the window is widened progressively until the
search returns a score inside it.

**History heuristic.** A `[from][to]` table accumulating a
`depth²` bonus every time a quiet move causes a beta cutoff. Quiet
moves with the highest history are tried first within their bucket.
See [`src/search.cpp`](../src/search.cpp).

**Iterative deepening.** Running the search at depth 1, then 2, then
3, etc., reusing earlier-iteration results (TT entries, best-move
ordering, aspiration windows) to make the deeper iterations cheap.

**Killer moves.** Quiet moves that recently caused a beta cutoff at a
given ply. Two slots per ply; tried right after the TT-suggested
move because they tend to refute many sibling positions.

**Lazy SMP.** A simple multi-thread search where N - 1 helper
threads run independent iterative deepenings against a shared
transposition table, populating entries the main thread can reuse.
Jass uses lock-free TT access; races may cause occasional stale
reads but the search is self-correcting.

**Mate score.** A score with `|score| > MATE_SCORE − MAX_PLY`,
indicating one side has a forced win. The exact value encodes the
ply distance: `+MATE_SCORE − N` means "the side to move wins in N
plies". The TT translates these to a ply-independent encoding before
storing so an entry produced at one ply is reusable at any other
([`src/search.cpp`](../src/search.cpp)).

**Movegen.** Move generator. In Jass: a single
`generate_legal_moves(pos, out)` function that returns either all
maximum-length captures or all quiet moves, never a mix.

**Negamax.** A recursive formulation of minimax where every node
returns its score from the side-to-move's POV; the recursive call
negates the child's score. Equivalent to minimax for two-player
zero-sum games but lighter on conditionals.

**NNUE.** *Efficiently Updatable Neural Network* — a class of
evaluation networks pioneered by computer shogi and now common in
chess. Designed for sparse incremental updates on the input layer
and clipped-ReLU hidden layers. Jass ships an NNUE-*lite* framework
(single linear layer, batch evaluation only) — see
[`src/nnue.hpp`](../src/nnue.hpp).

**Principal variation (PV).** The line of play the engine expects
both sides to follow from the searched position. Jass extracts the
PV after the search by walking `best_move` pointers in the
transposition table from the root.

**Quiescence search.** A miniature search at the leaves that only
considers tactical moves (captures, in our case) so the static
eval is never asked about a position with a forced capture pending.
Without it, the search suffers from the *horizon effect* — it
misjudges leaves where the very next move would change material.

**Repetition draw.** See *3-fold repetition*.

**Static eval.** The evaluation of a position based on the position
alone, without searching ahead. In Jass: material + PSQT + support
bonus + tempo (`evaluate(pos)` in [`src/eval.cpp`](../src/eval.cpp)).

**Transposition table (TT).** A hash table indexed by Zobrist hash
that caches the result of previously searched positions. Lets the
search cut whole subtrees on a TT hit and provides move ordering on
a partial hit.

**Zobrist hash.** A 64-bit hash of a position computed by XORing one
random key per (piece, square) plus a side-to-move key. Designed to
support O(1) incremental updates on every move — Jass maintains the
hash on `Position::after`, `add_piece`, `remove_piece` and
`set_side_to_move`.
