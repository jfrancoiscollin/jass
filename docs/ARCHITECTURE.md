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
            │    ├─ time-aware iteration skip               (E, search.cpp)
            │    │   (don't start iter N+1 when last_iter*2 > remaining)
            │    ├─ run_root_window(α, β)
            │    │    └─ for each root move m:
            │    │         └─ negamax(pos.after(m), d-1, ply, -β, -α)
            │    │              ├─ stop / deadline polling   [search.cpp]
            │    │              ├─ path-dependent draws      [search.cpp]
            │    │              ├─ probe_endgame(pos)        [endgame.cpp]
            │    │              ├─ tt.probe(hash) (+ cutoff) [tt.cpp]
            │    │              ├─ generate_legal_moves(pos) [movegen.cpp]
            │    │              ├─ if depth ≤ 0: quiescence(...)
            │    │              ├─ Reverse Futility Pruning  (D, shallow)
            │    │              │   (quiet position + eval ≫ β → fail high)
            │    │              ├─ Null Move Pruning         (search.cpp)
            │    │              │   (eval ≥ β → reduced-depth probe of
            │    │              │    pos.after_null(); guarded vs zugzwang)
            │    │              ├─ Singular extension        (search.cpp)
            │    │              │   (half-depth verification of TT move)
            │    │              ├─ order_moves(...)          [search.cpp]
            │    │              │   (TT, killers, history)
            │    │              ├─ for each m:
            │    │              │   ├─ LMR reduction on late quiet moves
            │    │              │   ├─ score = -negamax(pos.after(m), …)
            │    │              │   └─ re-search at full depth if LMR'd
            │    │              │       score > α
            │    │              ├─ on cutoff: update killers + history
            │    │              └─ tt.store(hash, …)
            │    └─ aspiration retry on fail-low / fail-high
            │      (window half-width adapts to recent score volatility)
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

### Search features implemented — checklist (authoritative)

The search is **feature-complete** for a modern alpha-beta engine. Do **not**
infer that a technique is missing from a keyword `grep` on `search.cpp` — names
vary (e.g. null-move uses `null_pos`/`null_score`, LMR uses a local `r`
reduction, extensions are `singular_ext`/`promo_ext`). This table is the source
of truth; if you change the search, update it.

| Technique | Present | Where |
|---|---|---|
| Iterative deepening | ✅ | `search()` loop |
| Aspiration windows (adaptive) | ✅ | fail-low/high retry |
| Transposition table (lazy-SMP shared) | ✅ | `tt.hpp`, §TT lifecycle |
| PVS (zero-window scout + re-search) | ✅ | `is_pv_node`, `negamax` |
| Late Move Reductions (+ verified re-search) | ✅ | `lmr_reduction`, `do_lmr` |
| Late Move Pruning | ✅ | `LMP_THRESHOLD` |
| Null-move pruning (zugzwang-guarded) | ✅ | `null_pos` / `null_score` |
| Internal Iterative Deepening | ✅ | `iid_depth` |
| Singular + promotion extensions | ✅ | `singular_ext`, `promo_ext` |
| Multi-cut | ✅ | `multicut_moves` |
| Killers / history / countermoves / improving | ✅ | `order_moves` |
| Quiescence (mandatory-capture resolution) | ✅ | `quiescence()` |
| Lazy SMP (helper threads share the TT) | ✅ | §Threading model |

Most search params are **tunable** (`params.lmp_d1/d2/d3`, `use_pvs`,
`use_improving`, LMR amounts, null-move R, aspiration delta) — a calibration
lever, not a missing-feature gap.

**Tuning verdicts (2026-06-15, A/B at movetime, `SearchParams`).** Feature-complete
≠ feature-tuned. Measured calibration wins, now **default-ON**:
- **`use_improving = true`** — +21.6 Elo (job 0253; `use_conthist` was −11 → left off).
- **Endgame NMP regime** (`eg_pieces`, `eg_no_nmp`/`eg_no_lmp`/`eg_no_lmr` in
  `search_params.hpp`) : below `eg_pieces` total pieces the chosen pruning is disabled.
  **Null-move pruning is NET-NEGATIVE in jass** — draughts is zugzwang-pervasive (you
  must move; being forced to move is often bad) so NMP's "passing is safe" premise fails
  throughout the game, not just in endgames. Sweep (0256/0259) was **monotone-increasing**:
  disabling NMP below 12 pieces = +29, below 36 (≈ everywhere) = **+97 Elo**. LMR is the
  opposite (`eg_no_lmr` = −13: LMR buys the depth the search-bound endgame needs → keep
  it). Default = `eg_pieces=12, eg_no_nmp=true` (the higher threshold is being confirmed
  at mt0.5, job 0262). `eg_pieces=0` is a true no-op (popcount short-circuited away).

> Consequence for eval work: at **equal nominal depth**, with sound alpha-beta +
> quiescence, move quality is driven by the **leaf evaluation**, not by these
> search refinements (which affect *speed* / depth-in-time). When two different
> evals score ≈ the same against Scan at equal depth, the gap is the **eval**,
> not the search. (See PATTERN_PROGRAM_NOTES.md §Ré-ancrage.)

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
Storing distance-to-mate would fix this and is a future refinement —
**superseded in practice by the external egdb bitbase below** (exact WLD,
which also revealed the in-memory 2v1/3v1 tables over-claim wins).

### External egdb bitbase (Kingsrow WLD 2→7, gated `-DJASS_EGDB`)

[egdb_bridge.cpp](../src/egdb_bridge.cpp) links Ed Gilbert's `egdb_intl` to
serve **exact** win/loss/draw for ≤7-piece positions. Seam:

- `egdb::init(dir, cache_mb)` opens the driver; `egdb::probe(pos)` converts the
  jass `Position` to the gapped `EGDB_POSITION` bitboards (`spread50_to_egdb`,
  bit-for-bit validated) and looks up the WLD.
- `probe_endgame` ([endgame.cpp](../src/endgame.cpp)) consults egdb **first**,
  falling back to the in-memory tables on `Unknown`.
- **<3-piece guard**: egdb's `db2` slice returns a spurious decisive for some
  bare KvK; `probe()` declines below 3 pieces so the exact in-memory `KvK=Draw`
  shortcut wins. Default build (`JASS_EGDB` OFF) = no-op stubs.

Validation = the **native egdb example self-test** (164/164), not the in-memory
tables (a shallow heuristic). `jass --egdb-selfcheck <dir> <n>` asserts the one
airtight invariant (KvK-no-capture = Draw); see BITBASE_INTEGRATION.md.

**Terminate-at-TB** ([main.cpp](../src/main.cpp) `run_gen_data_wdl_mode`): when a
self-play game reaches an egdb-resolved (≤7-piece) position, the game ends with
the EXACT egdb result instead of being played out. Without this, ~50% of decisive
endgames stall to the FMJD draw rule and get mislabelled as draws (job 0295),
poisoning the endgame training data. Active only when `JASS_EGDB_PATH` is set
(`egdb::ensure_initialised()` + `egdb::available()`); egdb-exact only.

**Self-play data tools** (exact endgame supervision):
- `--gen-egdb-wld <N> <out> <db>` — emit N random quiet ≤7-piece positions
  labelled with exact WLD (free dense endgame coverage).
- `--egdb-relabel <in> <db> [out]` — overwrite WDL labels of ≤7-piece positions
  in a self-play dataset with the exact egdb result (idempotent); reports
  **stalls** (won/lost recorded as draw = conversion failures).

**Conversion gradient (planned)**: `egdb_intl` also reads MTC (moves-to-conversion)
and DTW databases (`is_mtc`/`is_dtw`, unified `egdb_lookup`). The WLD target is flat
on wins, so the eval cannot learn *how* to convert; the plan is to use MTC as an
**offline training target** (graded by distance-to-conversion) so the eval learns a
conversion gradient that generalises beyond the bitbase — no MTC needed at play time
(Scan-style). See [EGDB_SELFPLAY_PLAN.md](EGDB_SELFPLAY_PLAN.md).

The full target self-play loop using these is documented in
[EGDB_SELFPLAY_PLAN.md](EGDB_SELFPLAY_PLAN.md).

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
loaded from disk for a trained network.

### NNUE forms and encodings

Three `INetwork` implementations live side by side in
[nnue.hpp](../src/nnue.hpp):

| Class            | Format | Where it's used                          |
|------------------|--------|------------------------------------------|
| `LinearNetwork`  | JNNL   | 200-weight linear baseline, NumPy lstsq  |
| `MLPNetwork`     | JNNM   | float MLP, runtime hidden dims (Cycle-4a) |
| `MLPNetworkQ`    | JNNQ   | int8 quantised MLP — AVX2 (x86) +        |
|                  |        | WASM-SIMD128 (browser) shipped paths      |

Two **input encodings** are supported by both `MLPNetwork` and
`MLPNetworkQ`:

- **V2 dense** (input_dim = 200, JNNM v2 / JNNQ v1) — STM-relative
  piece bitmaps, the default since Cycle-1.
- **HalfMen-lite** (input_dim = 450, JNNM v3 / JNNQ v2) — Cycle-6c.
  Symmetric per-piece indicator features designed to give the MLP
  more capacity to learn piece-relative patterns.

The loaders auto-detect both magic and input_dim from the header
so a trained `nnue.bin` from either encoding can be dropped in
without recompiling.

### Scan-style pattern eval (`ScanEvalNetwork`, PJTW v3) — the main line

The current eval line is a **linear pattern model** in the spirit of Scan
(Letouzey), implemented in [scan_eval.cpp](../src/scan_eval.cpp) +
[pattern_jass/](../pattern_jass/). It is what the WDL self-play loop trains.

```
evaluate(pos) =  Σ_p  W_pat[ phase, offset_p + index_p(men) ]      (32→54 patterns)
              +  Σ_e  W_ext[ phase, e ] · extra_e(pos)             (106 dense extras)
   phase = stage/40 interpolation between an MG bank and an EG bank
   → black-POV piece-units → ×100 cp → flip for STM
```

- **Patterns** : each is a fixed set of 12 board squares; `index_p` is the
  base-3 code of their occupancy (empty/black/white = 3¹² = 531 441
  buckets/pattern). Geometry is the single source of truth in
  `gen_patterns.py` → `pattern.hpp` + `patterns.py`.
- **King-aware switch** (`-DJASS_KING_PATTERNS=ON`, see `src/scan_eval.hpp`). By
  default occupancy = **men only** (a king square reads as empty; the king's
  value lives in the king-PST/mobility extras). With the flag, occupancy =
  **men|kings** so a king counts as a "piece" on its square — base-3 amalgamated
  man+king, **exactly like Scan** (SCAN_ARCHITECTURE_NOTES §1), NOT base-5
  (jass v2's failed king-distinct encoding: king buckets too sparse). 100 %
  linear; the prime structural fix vs Scan's class. A king-aware build MUST pair
  with a king-aware eval: `train.py --king-patterns` (both feed `men|kings`;
  `update_all` then handles king moves AND promotions — man→king on the same
  square keeps it occupied → index unchanged). Validated `0240`: **+37 Elo vs hc**
  under distillation (men-only +78 → king-aware +115). Default OFF = true no-op
  (6408/6408 unit assertions unchanged).
- **Extras (106, dense)** : king-PST (one-hot per square per colour), material
  (men counts), mobility (men step + king slide), left-right balance — the same
  non-pattern terms Scan uses.
- **Format** : PJTW v3 — `magic, version, scale, n_pat, n_ext`, then int32
  `[pat_mg | pat_eg | ext_mg | ext_eg]`. `n_pat = NUM_PATTERNS · 531441`.
- **Speed** : an incremental accumulator (`update_all`) maintains the per-pattern
  indices across a move (≤4 squares change) so the eval is cheap in search.

### Symmetry weight-sharing (the Scan brick)

A naïve pattern table has **NUM_PATTERNS independent** weights — 32×531441 =
**17M**, which self-play cannot densely estimate (measured: ~1M buckets ever
occur, ~38 % with ≤2 visits → most weights are L2-prior noise). Scan reaches
~2500 Elo with the *same linear class* because it **ties weights across the
board's symmetry group** (`P = 2 125 820` parameters). We replicate this purely
in **training** (`pattern_jass/tools/symmetry.py` + `train.py` folds), then
**expand** the tied weights back into a standard 17M-layout PJTW v3 so the C++
eval is unchanged. Bricks (each composes; all verified to preserve the *exact*
symmetries):

| Fold (`train.py` flag) | Symmetry | Exact? | Weights (32-pat) |
|---|---|---|---|
| `--color-fold` | colour-swap antisymmetry `W[swap]=−W` | approx | 8.5M |
| `--rot-fold`   | + rot180∘colour-swap (eval negates) | **exact** | 4.9M |
| `--trans-fold` | + translation (7 translate-classes) | approx | 1.2M |
| `--full-fold`  | + left-right reflection (within-row reversal) | **exact** | 1.0M |
| `--full-fold` on **`--lr-close` geometry** (54 pat) | full group, all patterns | — | **0.6M ≈ Scan** |

The exact board symmetry is **rot180 ∘ colour-swap** (rotate 180° + swap colours
= same position from the other side → eval negates) and **left-right reflection**
(within-row reversal; a naïve file-mirror flips dark↔light, so it must be the
row reversal). Pure colour-swap and translation are *approximate* (men have a
direction; absolute position matters) but pool data and empirically lower
val-loss — validated by real-Elo A/B, not assumed. `gen_patterns.py --lr-close`
closes the geometry under `{rot180, LR}` (32→54 patterns) so the fold ties
**every** pattern, reaching ~600k dense weights at Scan's scale.

## Training & calibration pipeline (Cycles 1–6c)

The training side lives in [`tools/`](../tools) and is driven by:

```
                ┌──────────────────────────────┐
                │  --gen-data-wdl (Cycle-1)    │  WDL-labelled self-play
                │  JNNW: bitboards + STM       │  (each record carries
                │  + score + game outcome      │   both deep-search score
                └─────────────┬────────────────┘   and final result)
                              │
                              ▼
                ┌──────────────────────────────┐
                │  train_v3.py (Cycle-2)       │  Multi-arch sweep,
                │  --archs 64-32 … 1024-512    │  blended score+WDL
                │  --encoding {v2,halfmen}     │  MSE loss, val-MSE
                └─────────────┬────────────────┘   ranking, JNNM out
                              │
                              ▼
                ┌──────────────────────────────┐
                │  quantize_mlp.py (Cycle-4b)  │  Post-training int8
                │  per-tensor scales + 99.9-pct│  quantisation, runtime
                │  activation calibration      │  hidden dims, JNNQ out
                └─────────────┬────────────────┘
                              │
              ┌───────────────┼─────────────────┐
              ▼               ▼                 ▼
   ┌────────────────┐ ┌──────────────┐ ┌────────────────────┐
   │ --benchmark-   │ │ bench_arch.py│ │ calibrate_vs_scan  │
   │  nnue (vs      │ │ (Cycle-5     │ │ (vs Scan, HUB      │
   │  handcrafted,  │ │  pipeline    │ │  protocol, ELO     │
   │  sanity-check) │ │  wrapper)    │ │  estimate — the    │
   └────────────────┘ └──────────────┘ │  real KPI)         │
                                       └────────────────────┘
```

**Pattern self-play loop — the training SIGNAL (read before adding a "densify"
lever).** The full-fold king-aware loop (`train.py --scan-eval --loss logistic`)
trains on the **WDL game outcome**, NOT the per-record search `score`. This is the
load-bearing fact behind the 2026-06-15 endgame campaign:
- `--label-depth-by-phase` (deeper labelling search) is therefore a **no-op** for the
  loop (it only fills the unused `score` field) — and worse, the deeper label search
  pollutes the shared TT and perturbs the played moves (jobs 0254/0258: −80 Elo). Dead.
- `--phase-weight` (up-weight endgame rows) is **dead** in all contexts: it amplifies
  noisy endgame WDL labels (0254) and, even on perfect score labels, over-weighting the
  large-magnitude endgame targets de-calibrates the eval for the bulk (0261: −210 Elo).
- The **correct** endgame lever is `--play-depth-by-phase` (play endgames at a deeper
  search → the resolved **WDL is accurate** where it was noisy; endgames are few-piece →
  cheap). Both `--*-depth-by-phase` flags share `parse_depth_by_phase`; empty = uniform
  (back-compatible). Phase bounds match `pattern_jass/tools/train.py` and `game_autopsy`.
- For a **score** target (rich Scan-d10 teacher, not WDL), use `--target score` WITHOUT
  `--loss logistic` (logistic always trains on WDL). Score-distillation = +141 vs hc
  (job 0261), above WDL-distillation but below the self-play loop — a quality source, not
  a standalone production eval.

**Data relabelling modes** (rewrite the `score` field of a JNNW in place,
preserving bitboards/STM/WDL):
- `--rewrite-scores-with-nnue <in> <out> --nnue PATH` — new score = the network
  in **static** mode (`nnue.evaluate(pos)`).
- `--rewrite-scores-with-search <in> <out> --nnue PATH [--depth D] [--start S]
  [--count C]` — new score = a **depth-D alpha-beta search** driven by the eval
  (pattern `.pjtw` or NNUE `.bin`), STM-POV. This is the teacher-free bootstrap
  primitive (`eval ← search(eval)`): a depth-D search is stronger than the
  static eval, so training on these labels pulls a fresh eval upward, with no
  external teacher. `--start/--count` shard the per-position search across cores
  (each shard is a standalone JNNW; concatenate the bodies in order and fix the
  header count).

`tools/calibrate_vs_scan.py` also accepts **asymmetric depth**
(`--jass-depth N --scan-depth M`, backward-compatible overrides of `--depth`)
for the eval-vs-search diagnostic: how many extra plies does Jass need to match
Scan at a fixed Scan depth.

The Hetzner GitOps runner in [`infra/`](../infra/README.md) ties all
of these together: long-running gen-data / training / calibration
jobs are committed as scripts under `jobs/queue/`, the runner picks
them up, runs them on a Hetzner CCX host, and commits results back
to `jobs/results/<id>/`.

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
