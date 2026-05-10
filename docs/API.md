# C++ API reference

Every public type and function exported by `jass_lib`, grouped by header.

The headers are deliberately small and orthogonal: the [architecture
guide](ARCHITECTURE.md) explains how they fit together at runtime.

All names live in `namespace jass`.

---

## `src/types.hpp` — core scalar types

### `enum class Color : uint8_t`

| Member | Value |
|--------|-------|
| `White` | 0 |
| `Black` | 1 |

### `Color opposite(Color c)`

Returns the opposing colour.

### `int color_index(Color c)`

Returns 0 / 1 — handy for bitboard or array indexing keyed by colour.

### `enum class Piece : uint8_t`

| Member       | Value |
|--------------|-------|
| `None`       | 0     |
| `WhiteMan`   | 1     |
| `WhiteKing`  | 2     |
| `BlackMan`   | 3     |
| `BlackKing`  | 4     |

### Piece predicates (all `constexpr`)

- `bool is_white(Piece)`, `bool is_black(Piece)`
- `bool is_man(Piece)`,  `bool is_king(Piece)`
- `Color color_of(Piece)` — undefined for `Piece::None`.

### `using Square = uint8_t`

FMJD square numbering 1–50. `0` is the sentinel `NO_SQUARE`.

```cpp
inline constexpr Square NO_SQUARE    = 0;
inline constexpr Square FIRST_SQUARE = 1;
inline constexpr Square LAST_SQUARE  = 50;
inline constexpr int    NUM_SQUARES  = 50;
inline constexpr int    BOARD_SIDE   = 10;

constexpr bool   square_is_valid(Square s);
constexpr int    square_to_bit(Square s);   // 0..49 — bitboard bit index
constexpr Square bit_to_square(int b);
```

### `struct Move`

A legal move in a single struct. Capture chains are stored as a list
of captured squares; the moving piece's path between them is implied
because they uniquely identify the chain inside the legal-move list.

```cpp
struct Move {
    Square                  from{NO_SQUARE};
    Square                  to{NO_SQUARE};
    std::uint8_t            num_captures{0};
    bool                    promotes{false};
    std::array<Square, 20>  captures{};      // valid for [0, num_captures)

    constexpr bool is_capture() const noexcept;
    constexpr bool is_quiet()   const noexcept;
};
```

`operator==` compares all fields, taking `num_captures` into account so
unused capture-array slots don't influence equality.

---

## `src/bitboard.hpp` — 50-bit bitboards

50-bit wide bitboards stored in a `std::uint64_t`. Bit `i` corresponds
to FMJD square `i + 1`; bits 50–63 are always zero.

```cpp
using Bitboard = std::uint64_t;

inline constexpr Bitboard EMPTY_BB    = 0ULL;
inline constexpr Bitboard FULL_BB     = (1ULL << NUM_SQUARES) - 1ULL;
inline constexpr Bitboard PLAYABLE_BB = FULL_BB;

constexpr Bitboard square_bb(Square s);      // single-bit mask
constexpr bool     test  (Bitboard, Square);
constexpr void     set   (Bitboard&, Square);
constexpr void     clear (Bitboard&, Square);
constexpr void     toggle(Bitboard&, Square);

constexpr int    popcount(Bitboard);         // wraps std::popcount
constexpr Square pop_lsb (Bitboard&);        // pops + returns smallest set bit
constexpr Square lsb     (Bitboard);         // peeks at smallest set bit
```

---

## `src/board.hpp` — 10×10 geometry

```cpp
enum class Dir : uint8_t {
    UpLeft = 0, UpRight = 1, DownLeft = 2, DownRight = 3,
};

inline constexpr int                       NUM_DIRS = 4;
inline constexpr std::array<Dir, NUM_DIRS> ALL_DIRS = { … };

constexpr std::array<Dir, 2> man_forward_dirs(Color c) noexcept;
```

White's "forward" is `{UpLeft, UpRight}`; black's is `{DownLeft, DownRight}`.

### Row / column helpers

```cpp
constexpr int row_of(Square s);     // 0 = top (Black home), 9 = bottom
constexpr int col_of(Square s);     // 0..9 — actual board column

constexpr bool is_white_promotion_row(int row);   // row == 0
constexpr bool is_black_promotion_row(int row);   // row == 9
constexpr bool is_promotion_square(Square s, Color mover);
```

### Diagonal-neighbour table

Precomputed at compile time:

```cpp
struct NeighbourTable {
    std::array<std::array<Square, NUM_DIRS>, NUM_SQUARES + 1> data{};
};

const NeighbourTable& neighbours();
inline Square         neighbour(Square s, Dir d);
Square                ray_step (Square s, Dir d, int n);
```

`neighbour(s, d)` returns `NO_SQUARE` if `s` is on the board edge in
direction `d`. `ray_step` walks `n` neighbours and returns `NO_SQUARE`
the moment it leaves the board.

---

## `src/zobrist_keys.hpp` — Zobrist key tables

Split out of `zobrist.hpp` so `Position` can update its hash
incrementally without an include cycle.

```cpp
using ZobristHash = std::uint64_t;

struct ZobristKeys {
    std::array<std::array<std::uint64_t, NUM_SQUARES>, 4> piece;
    std::uint64_t                                         side_to_move;
};
extern const ZobristKeys ZOBRIST;

inline ZobristHash key_for_piece(Piece p, Square s) noexcept;
inline ZobristHash key_for_side_to_move() noexcept;
```

Piece-kind encoding: `0 = white man`, `1 = white king`, `2 = black
man`, `3 = black king`. `key_for_piece(Piece::None, s)` returns `0` —
safe to XOR into a running hash.

---

## `src/zobrist.hpp` — position-aware hashing

```cpp
ZobristHash zobrist_hash(const Position& pos) noexcept;
```

Returns `pos.hash()` — i.e., the cached, incrementally-maintained hash
on the position itself. Keeping the wrapper around lets callers depend
on a single header (`zobrist.hpp`) without touching `position.hpp`.

---

## `src/position.hpp` — game state

```cpp
class Position {
public:
    Position() = default;

    static Position                start_position() noexcept;
    static std::optional<Position> from_fen(std::string_view fen);

    // Bitboards
    Bitboard white_men()    const noexcept;
    Bitboard white_kings()  const noexcept;
    Bitboard black_men()    const noexcept;
    Bitboard black_kings()  const noexcept;
    Bitboard whites()       const noexcept;     // white_men() | white_kings()
    Bitboard blacks()       const noexcept;
    Bitboard occupied()     const noexcept;
    Bitboard empties()      const noexcept;     // ~occupied & PLAYABLE_BB
    Bitboard pieces_of(Color c) const noexcept;
    Bitboard men_of   (Color c) const noexcept;
    Bitboard kings_of (Color c) const noexcept;

    // Scalars
    Color  side_to_move()    const noexcept;
    int    halfmove_clock()  const noexcept;    // FMJD 25-move counter
    void   set_halfmove_clock(int c) noexcept;

    // Cached Zobrist hash, kept up to date by every mutator below.
    ZobristHash hash() const noexcept;

    // Mutators (low-level)
    void clear() noexcept;
    void set_side_to_move(Color c) noexcept;
    void add_piece   (Square s, Piece p) noexcept;   // assert: empty there
    void remove_piece(Square s, Piece p) noexcept;   // assert: piece is `p`

    // Single-piece query
    Piece piece_at(Square s) const noexcept;

    // Immutable apply: returns a new Position resulting from playing m.
    // Behaviour is undefined if m is not in generate_legal_moves(*this).
    Position after(const Move& m) const noexcept;

    // Serialisation
    std::string to_fen()   const;     // Hub-style "<stm>:W…:B…"
    std::string to_ascii() const;     // multi-line debug diagram

    friend bool operator==(const Position& a, const Position& b) noexcept;
};
```

Equality compares the four bitboards plus side-to-move; the half-move
clock and Zobrist hash are deliberately excluded (they are derived
metadata).

---

## `src/movegen.hpp` — legal-move generation

```cpp
class MoveList {
public:
    void          clear()                         noexcept;
    void          push (const Move& m);
    std::size_t   size()                          const noexcept;
    bool          empty()                         const noexcept;
    Move&         operator[](std::size_t i)       noexcept;
    const Move&   operator[](std::size_t i)       const noexcept;
    /* begin() / end() iterators present */
};

void generate_legal_moves(const Position& pos, MoveList& out);
```

Behaviour:
- If at least one capture exists in `pos`, the output contains **only**
  the maximum-length capture chains (FMJD majority-capture rule). All
  entries in that case satisfy `is_capture()`.
- Otherwise the output contains every quiet move (men step one
  diagonal forward; kings ray-slide along all four diagonals until
  they hit a piece).
- An empty list means the side to move has no legal moves and has lost.

The output is appended to `out` after a `clear()` — callers may pass a
reused `MoveList` to avoid re-allocation.

---

## `src/eval.hpp` — handcrafted static evaluation

```cpp
inline constexpr int MAN_VALUE    = 100;
inline constexpr int KING_VALUE   = 300;
inline constexpr int TEMPO_BONUS  = 5;

int evaluate(const Position& pos) noexcept;
```

Returns the score from the side-to-move's POV (positive = good for
STM), in centipawns. Composition of terms:

| Term | Effect |
|------|--------|
| Material | `+MAN_VALUE` per man, `+KING_VALUE` per king, sign by colour. |
| Advancement PSQT (men) | up to `+36 cp` for a man one square from promotion. |
| Edge-file penalty (men) | `-3 cp` for files 0 and 9. |
| Back-rank guard (men) | `+5 cp` for men still on the home rank. |
| Centralisation PSQT (kings) | up to `+14 cp` near the centre. |
| Support bonus (men) | `+5 cp` per friendly piece on a rear diagonal. |
| Tempo | `±TEMPO_BONUS` for the side to move. |

---

## `src/nnue.hpp` — NNUE-lite framework

```cpp
class LinearNetwork {
public:
    LinearNetwork();                              // handcrafted-equivalent weights

    int  evaluate(const Position& pos) const noexcept;

    bool load(std::string_view path);             // raw int32, square-major
    bool save(std::string_view path) const;
};

int evaluate_nnue(const Position& pos);
```

Weight array: `int32_t[NUM_SQUARES][4]`, kinds in the standard order
`{white man, white king, black man, black king}`. The default-
constructed network produces a score within tempo magnitude of the
handcrafted `evaluate()`.

`evaluate_nnue` is a thin façade over an internal default-constructed
`LinearNetwork`. The search currently uses `evaluate()` only;
`evaluate_nnue()` is intended for A/B harnesses with trained weights
loaded.

---

## `src/tt.hpp` — transposition table

```cpp
enum class Bound : uint8_t {
    None  = 0, Exact = 1, Lower = 2, Upper = 3,
};

struct TTEntry {
    ZobristHash  key{0};
    Move         best_move{};
    int16_t      score{0};
    int8_t       depth{-1};
    Bound        bound{Bound::None};
};

class TranspositionTable {
public:
    TranspositionTable();                         // default size 16 MB

    void resize_mb(std::size_t mb);               // rounds count down to power of 2
    void clear();

    bool probe(ZobristHash key, TTEntry& out) const noexcept;
    void store(ZobristHash    key,
               const Move&    best_move,
               int            score,
               int            depth,
               Bound          bound) noexcept;

    std::size_t size() const noexcept;            // slot count (power of 2)
};
```

Replacement policy: depth-preferred (a slot is only overwritten when
the new entry was searched at least as deep as the current occupant).

Mate scores are translated to a ply-independent encoding **outside**
the TT, in `search.cpp` — see [ARCHITECTURE.md](ARCHITECTURE.md#tt-lifecycle).

---

## `src/search.hpp` — game-tree search

```cpp
inline constexpr int MATE_SCORE = 30000;
inline constexpr int INF_SCORE  = 31000;
inline constexpr int MAX_PLY    = 64;
inline constexpr int FIFTY_MOVE_PLIES = 50;

constexpr bool is_mate_score(int s) noexcept;     // |s| > MATE_SCORE - MAX_PLY

struct SearchLimits {
    int          max_depth   = 6;
    std::size_t  tt_mb       = 1;                 // used only by the 2-arg overload
    int          movetime_ms = 0;                 // 0 = unlimited
    const std::atomic<bool>* stop_flag = nullptr; // external interrupt
    int          threads     = 1;                 // lazy SMP fan-out
};

struct SearchResult {
    Move              best_move{};
    int               score{0};
    int               depth{0};
    std::uint64_t     nodes{0};
    std::vector<Move> pv;                         // pv[0] == best_move
    bool              from_book{false};           // engine-only field
};

SearchResult search(const Position& pos, const SearchLimits& limits);
SearchResult search(const Position& pos, const SearchLimits& limits,
                    TranspositionTable& tt);
SearchResult search(const Position& pos, const SearchLimits& limits,
                    TranspositionTable& tt,
                    const std::vector<ZobristHash>& game_history);

std::vector<Move> extract_pv(const Position&            start,
                             const TranspositionTable&  tt,
                             int                        max_len = MAX_PLY);
```

Behaviour:
- The 2-arg overload allocates a fresh TT sized from `limits.tt_mb`.
- The 3-arg overload reuses the caller-owned TT.
- The 4-arg overload additionally consumes a Zobrist history of game
  predecessors for repetition detection. Use it through `Engine` —
  managing the history yourself is awkward.
- Iterative deepening from 1 up to `max_depth`. Aborted iterations are
  discarded and the previous-iteration result is returned.
- A position with a known endgame result (`probe_endgame`) returns
  immediately at any node with the bitbase score.
- Lazy SMP: when `threads > 1`, helper threads share the TT.

---

## `src/endgame.hpp` — endgame-knowledge probe

```cpp
enum class EndgameResult : uint8_t {
    Unknown   = 0,                                // not in the tablebase
    Draw      = 1,
    WhiteWin  = 2,
    BlackWin  = 3,
};

EndgameResult probe_endgame(const Position& pos) noexcept;
```

Currently recognises:
- KvK   → `Draw` (always, by FMJD rules).
- KKvK / KvKK → delegated to the retrograde bitbase (`bitbase.hpp`).

Anything else returns `Unknown` and the search falls through to its
normal evaluation.

---

## `src/bitbase.hpp` — retrograde-analysis bitbase

```cpp
EndgameResult probe_kings_endgame(const Position& pos);
```

Lazily builds the 2-vs-1 kings tablebase on the first probe (~0.5 s).
The mirror "1 white king vs 2 black kings" is handled at probe time
by colour-swapping the position and inverting the result.

Caveat: the FMJD 16-move drawing rule is not modelled, so the bitbase
sometimes labels a position as WIN that is actually drawn under FMJD
rules (the strong side cannot mate within 16 plies).

---

## `src/book.hpp` — opening book

```cpp
class Book {
public:
    Book();                                       // populates from built-in lines

    std::optional<Move> probe(const Position& pos) const;
    std::size_t         size() const noexcept;
};
```

Built-in lines: a small hand-written set of elementary opening pushes
(32-28, 33-29, 31-26, 34-30, 35-30 plus a few obvious replies). Each
line is replayed at construction time to populate a hash → move map.

`probe(pos)` returns the stored move only if it is still legal in
`pos` — protects against stale entries and hash collisions.

---

## `src/timemgr.hpp` — tournament time-budget helper

```cpp
struct TimeBudget {
    int wtime_ms   = 0;
    int btime_ms   = 0;
    int winc_ms    = 0;
    int binc_ms    = 0;
    int movestogo  = 0;          // 0 → open-ended
};

int compute_movetime_ms(const TimeBudget& tb, Color stm) noexcept;
```

Formula: `total / moves_left + (inc * 4 / 5)`, capped at `total / 4`,
floored at 5 ms. `moves_left = min(movestogo, 30)` (or 30 if
`movestogo == 0`).

Returns 0 if no time information was provided — callers can then fall
back to a depth-limited search.

---

## `src/tournament.hpp` — self-play harness

```cpp
struct EngineConfig {
    int  max_depth   = 6;
    int  threads     = 1;
    int  movetime_ms = 0;
    bool use_book    = false;
};

enum class GameOutcome : uint8_t {
    WhiteWin, BlackWin, Draw,
};

struct GameRecord {
    GameOutcome outcome;
    int         plies;
    const char* reason;          // "no legal moves" / "25-move rule" / …
};

GameRecord play_game(const EngineConfig& white_cfg,
                     const EngineConfig& black_cfg,
                     int                 max_plies = 300);

struct TournamentResult {
    int a_wins = 0;
    int b_wins = 0;
    int draws  = 0;
};

TournamentResult run_tournament(const EngineConfig& a,
                                const EngineConfig& b,
                                int                 pairs     = 1,
                                int                 max_plies = 300);
```

`run_tournament(a, b, pairs)` plays `pairs * 2` games in colour-swap
pairs (A as white then B as white). Both engines stay in lock-step via
`apply_move` so their internal hash histories are accurate for the
search's own repetition detection.

---

## `src/engine.hpp` — long-lived facade

```cpp
class Engine {
public:
    Engine();                                     // 16 MB default TT
    explicit Engine(std::size_t tt_mb);

    void  new_game();                             // reset position; clear TT + history
    void  set_position    (const Position& pos)        noexcept;
    bool  set_position_fen(std::string_view fen);

    const Position& position() const noexcept;

    bool apply_move(const Move& m);               // false on illegal m

    SearchResult search(int max_depth);
    SearchResult search(const SearchLimits& limits);

    void  clear_tt()                       noexcept;
    void  resize_tt_mb(std::size_t mb);
    std::size_t tt_size() const            noexcept;

    const std::vector<ZobristHash>& hash_history() const noexcept;

    void use_book(bool yes) noexcept;
    bool book_enabled()      const noexcept;
};
```

Owns: the current `Position`, a `TranspositionTable`, the game's
predecessors-only Zobrist hash history, and a `Book`.

`search(int)` and `search(SearchLimits)` consult the opening book
first when enabled; on a hit they return immediately with
`from_book = true` and `depth = nodes = 0`. Otherwise they delegate
to the free function `jass::search` with the engine's TT and history.

---

## `src/hub.hpp` — HUB-flavoured CLI

```cpp
class HubFrontEnd {
public:
    HubFrontEnd(std::istream& in, std::ostream& out);
    ~HubFrontEnd();                               // signals stop, joins worker

    int run();                                    // blocks until EOF / `quit`
};

std::optional<Move> parse_move (const Position& pos, std::string_view text);
std::string         format_move(const Move& m);
```

- `parse_move` accepts `from-to` / `fromxto` / multi-jump
  `fromxsq1xsq2x...to`. The first matching legal move (from + to) is
  returned; arbitrary intermediate stops are tolerated.
- `format_move` emits `from-to` for quiet moves and `fromxto` for
  captures.

Full command grammar: [HUB.md](HUB.md).

---

## Conventions across the codebase

- `noexcept` is used wherever it's true and stable; absence of it
  signals "may throw" (e.g. file I/O in `LinearNetwork::load`).
- `Position` is value-typed, ~32 bytes, cheap to copy. The search
  copies positions freely via `pos.after(m)`.
- Bitboards are passed by value (always `uint64_t`).
- `MoveList` is reused across calls in hot paths to avoid allocation.
- All tests live under `tests/` and are linked into a single
  `jass_tests` executable. The test framework macros are in
  [`tests/test_framework.hpp`](../tests/test_framework.hpp).
