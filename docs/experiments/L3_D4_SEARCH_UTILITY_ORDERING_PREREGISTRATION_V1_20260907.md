# L3 D4 Search-Utility Ordering Preregistration V1 — 2026-09-07

## 1. Status and authority

This document preregisters a new hypothesis after the terminal D3 runtime result.

Authoritative predecessor:

- equal-node terminal job: `cpx62-1857-l3-decision-math-d3-runtime-equal-node-prereg-recovery-requeue-v1`
- equal-node attempt: `20260907T155344Z-fcdcd217`
- equal-node verdict: `D3_RUNTIME_EQUAL_NODE_NOT_ESTABLISHED_V1`
- terminal autopsy recovery job: `cpx62-1860-l3-decision-math-d3-runtime-terminal-autopsy-recovery-requeue-v1`
- autopsy attempt: `20260907T164613Z-0beb8796`
- autopsy code: `0beb8796be01a7977f1c6fe97efa4aac9fbae860`
- autopsy verdict: `D3_RUNTIME_TERMINAL_AUTOPSY_COMPLETE_V1`
- autopsy classification: `BROAD_EQUAL_NODE_SEARCH_EFFICIENCY_DEGRADATION`

D3 is scientifically closed. This document does not reopen D3, authorize D3 equal-time, retune D3, alter the D3 adapter, or reuse D3 game outcomes as a learning target.

The D3 autopsy is allowed to motivate the new scientific question: a move-ordering learner should optimize alpha-beta search utility directly rather than selected-action preference. Numerical D4 choices below are frozen by this preregistration and may not subsequently be selected, tuned, filtered, weighted, or rescaled using 1857 per-game outcomes or 1860 subgroup outcomes.

This preregistration itself authorizes **no execution**. Its side effects are exactly:

- fresh positions generated = 0
- teacher searches = 0
- model fits = 0
- strength games = 0
- promotions = 0
- bakes = 0

## 2. Frozen hypothesis

A small, cheap residual ranker trained on **observed beta-cutoff utility inside WDL_CONTROL alpha-beta search** can improve move ordering at an equal node budget without the depth loss and runtime amplification observed for D3.

The treatment is deliberately narrower than D3:

1. the production WDL evaluator is byte-identical;
2. legal TT priority is absolute and unchanged;
3. root previous-iteration/PV priority is unchanged;
4. D4 is evaluated only on the first four non-TT siblings in the existing legacy order;
5. all siblings not promoted by D4 retain their exact legacy relative order;
6. D4 uses only cheap parent/search-state/move-local features available before searching the move;
7. D4 performs no child static evaluation, no qsearch, no neural inference and no D3 scoring.

## 3. Immutable control

The control is the exact production `WDL_CONTROL` search/evaluation path current at the future D4 execution preregistration boundary.

The following are immutable throughout D4 comparison stages:

- WDL model bytes and coefficient;
- leaf value semantics;
- qsearch semantics;
- TT semantics and legal TT move priority;
- root iterative-deepening previous-best/PV priority;
- killers, history, countermove and continuation-history update semantics;
- search pruning/reduction/extension semantics;
- adjudication rules.

D4 is move-ordering only. No value mixing is permitted.

## 4. Fresh search-utility dataset

### 4.1 Root generation

A future data stage, separately implemented after this preregistration, shall generate exactly **30,000 target-blind candidate root positions** with:

- generation seed: `2026111501`
- deterministic selector prefix: `2026111502:`
- minimum source ply: 8
- maximum source ply: 32
- minimum pieces: 20
- canonical identity: board + side-to-move, with colour/STM symmetry canonicalization consistent with the existing fresh-pool tooling.

Before selection, exclude the authenticated historical identity union used by the D3 equal-node campaign, all C/D1/D2/D3 decision parents, D3 runtime preflight fixtures, all 1857 equal-node primary/harness openings, and every other previously published force/runtime/strength pool available at execution time. Exclusion is provenance-only and may not inspect target values or game outcomes.

Rank candidates by SHA256 of `2026111502:` concatenated with canonical identity. Select the first exactly **4,000 roots** after exclusion.

Root split is immutable and happens before any teacher search:

- roots 0..3199: TRAIN (3,200)
- roots 3200..3599: VALID (400)
- roots 3600..3999: TEST (400)

No root may move between splits.

### 4.2 Control teacher search

Each selected root receives exactly one WDL_CONTROL search with:

- exact node limit: 50,000 nodes
- node-limit mode: exact
- threads: 1
- opening book: OFF
- TT reset between top-level roots
- no D4 and no D3 treatment active
- no game outcome produced or read.

This search may emit diagnostic trace rows only. It may not modify search decisions.

### 4.3 Eligible internal node

An internal search node is eligible only when all are true:

- search ply >= 1 (root nodes are excluded);
- parent piece count is 9..40 inclusive;
- remaining nominal depth >= 3 plies;
- legal move count is 2..16 inclusive;
- at least two legal non-TT candidate moves exist;
- any legal TT move remains outside the D4 candidate set and retains absolute production priority;
- the node terminates by a beta cutoff;
- the beta-cutoff-causing move is among the first `min(4, non_tt_count)` moves in the exact legacy non-TT order captured before any child is searched.

For each eligible node, the label is exactly the **observed move that caused the beta cutoff** in the unmodified WDL_CONTROL search.

Forbidden labels include best game move, game result, Elo, WDL outcome of a played game, qscore, q5/q50/q200, SearchDecisionTrace selected action, B3/full-ladder 1843 values, D3 score, D3 game outcome, and any new deep-search teacher value unrelated to the observed cutoff event.

### 4.4 Leakage control and exact example counts

Examples inherit their root split. Before final selection, remove from all splits any canonical `(parent position, side to move, remaining depth, alpha, beta, ordered candidate identities)` key that occurs in more than one root split.

Within each split, rank remaining examples by SHA256 of `D4-EXAMPLE-2026111502:` plus the canonical example key. Select exactly:

- TRAIN: 96,000 examples
- VALID: 12,000 examples
- TEST: 12,000 examples

If any split lacks its exact required support, the stage is **technical/support INVALID** and no fit is allowed.

Minimum TEST support after exact selection:

- each phase P0/P1/P2/P3: >= 500 examples.

## 5. Runtime feature contract

### 5.1 Phase blocks

Four phase blocks are fixed by parent piece count:

- P0: 33..40 pieces
- P1: 25..32 pieces
- P2: 17..24 pieces
- P3: 9..16 pieces

Below 9 pieces D4 is unsupported and exact legacy ordering is preserved.

### 5.2 Square canonicalization

Move-square features use playable squares 1..50. For a white side-to-move parent, canonicalize move squares with `51 - sq` before deriving row/column features. Black side-to-move uses the native square. Production `row_of`/`col_of` semantics are authoritative after square canonicalization.

### 5.3 Exact 24-dimensional move vector

For each of the top-four legacy non-TT candidates, compute exactly these 24 features in this order:

0. `legacy_rank_norm = (legacy_rank_1_based - 1) / 3`
1. `depth_norm = min(remaining_depth, 16) / 16`
2. `ply_norm = min(search_ply, 64) / 64`
3. `legal_count_norm = min(legal_move_count, 16) / 16`
4. `piece_count_norm = parent_piece_count / 40`
5. `capture_node = 1` iff the legal move set is a capture move set, else 0
6. `zero_window = 1` iff `beta - alpha <= 1`, else 0
7. `move_is_capture`
8. `capture_count_norm = min(move.num_captures, 10) / 10`
9. `promotes`
10. `mover_is_king` in the parent position
11. `killer0_match`
12. `killer1_match`
13. `countermove_match`
14. `history_squash = h / (abs(h) + 16384)` where `h` is the exact production history value for the move
15. `conthist_squash = c / (abs(c) + 16384)` where `c` is the exact production continuation-history value, or 0 when continuation history/previous move is unavailable
16. canonical `from_row / 9`
17. canonical `from_col / 9`
18. canonical `to_row / 9`
19. canonical `to_col / 9`
20. `abs(to_row - from_row) / 9`
21. `abs(to_col - from_col) / 9`
22. `destination_edge = 1` iff canonical destination row or column is 0 or 9, else 0
23. `destination_center = 1 - min(1, (abs(to_row - 4.5) + abs(to_col - 4.5)) / 9)`

No additional feature may be added. No feature may read a child evaluation, child WDL, D3 adapter output, tablebase value, qscore, or game result.

## 6. Frozen model and fit

D4 is one phase-blocked linear residual model:

- 24 features per candidate;
- 4 phase blocks;
- exactly 96 trainable float64 coefficients;
- no intercept outside the 24 features;
- no hidden layer;
- no temperature parameter;
- no runtime scaling parameter;
- no ensemble.

For a candidate of legacy non-TT rank `r` in {1,2,3,4}:

`baseline_logit = -(r - 1)`

`d4_logit = baseline_logit + beta_phase dot x`

At `beta = 0`, D4 reproduces the exact frozen baseline top-four ranking.

Fit exactly once on TRAIN only with listwise cross entropy to the observed beta-cutoff-causing move plus L2 regularization:

- L2: `1e-3`
- initialization: all 96 coefficients exactly zero
- optimizer: L-BFGS-B
- `max_iter = 500`
- `maxcor = 10`
- `gtol = 1e-6`

No hyperparameter sweep, lambda sweep, temperature sweep, feature search, model search, seed search, early-stopping selection, refit, or VALID-driven selection is allowed.

Seal model bytes before reading VALID or TEST metrics.

## 7. Offline terminal gate

After model seal, evaluate VALID and TEST without modification.

Primary TEST metrics:

- baseline and D4 listwise cross entropy for the observed cutoff move;
- cutoff-move top-1 accuracy;
- mean reciprocal rank;
- per-phase cross entropy and top-1;
- fraction of nodes whose legacy first move is preserved;
- fraction of legacy non-first cutoff labels promoted to rank 1.

Paired bootstrap TEST CE gain `CE_baseline - CE_D4` with:

- repetitions: 200,000
- seed: `2026111503`
- resampling unit: eligible node/example.

`D4_SEARCH_UTILITY_OFFLINE_ESTABLISHED_V1` requires all:

1. TEST mean CE gain > 0;
2. TEST bootstrap 95% LCB of CE gain > 0;
3. TEST D4 cutoff-move top-1 accuracy > baseline top-1 accuracy;
4. all four TEST phases have non-negative mean CE gain;
5. exact model width/provenance and all forbidden-read counters pass.

Otherwise the terminal scientific verdict is `D4_SEARCH_UTILITY_OFFLINE_NOT_ESTABLISHED_V1` and D4 stops. Technical/provenance failures are `D4_SEARCH_UTILITY_OFFLINE_INVALID_V1` and are not scientific negatives.

## 8. Runtime integration contract

Only an offline ESTABLISHED verdict may authorize implementation of the runtime candidate.

At every supported internal node:

1. generate and legacy-order moves exactly as control;
2. preserve legal TT move absolute priority;
3. take the first up to four non-TT moves in that legacy order;
4. compute D4 logits for only those candidates;
5. select the highest D4 logit; ties preserve lower legacy rank;
6. hoist only that selected non-TT candidate to the front of the non-TT tail;
7. preserve exact legacy relative order of every other move.

Root previous-iteration best/PV priority remains unchanged and D4 does not reorder ahead of it.

D4 must not construct child positions solely for scoring, call the evaluator, call qsearch, probe tablebases, or invoke any neural/D3 model during ordering.

## 9. Mandatory zero-game runtime preflight

Before any strength game, a separately queued zero-game preflight must prove:

- D4 OFF candidate/control byte-semantic identity for best move, score, PV, node count and existing search diagnostic counters;
- WDL leaf bytes and evaluator calls unchanged;
- TT/root priorities unchanged;
- <9-piece exact legacy identity;
- D4 ON treatment exercised on supported nodes;
- malformed model/provenance fails closed.

Fixtures:

- exactly 256 deterministic positions
- fixture seed: `2026111599`
- exact node budget: 20,000 per search
- threads: 1
- book: OFF
- three timing repetitions per arm per fixture after one untimed warmup.

Runtime-cost gate uses the median over fixture-level candidate/control wall-time ratios. It must be `<= 1.05`. Candidate and control must have equal evaluator-call counts on identity-comparable fixtures. Failure of the cost/integrity preflight stops D4 before any game.

## 10. Equal-node causal gate

Only a successful zero-game preflight authorizes equal-node.

Fresh pool:

- generate exactly 30,000 target-blind candidates
- generation seed: `2026111601`
- selector prefix: `2026111602:`
- min ply 8, max ply 32, min pieces 20
- exclude all historical pools plus all D4 teacher roots/examples and preflight fixtures
- first 1,000 eligible canonical openings: PRIMARY
- next 100 disjoint openings: identical-control HARNESS
- both colours.

Games:

- PRIMARY: 2,000 games, D4 vs WDL_CONTROL
- HARNESS: 200 games, WDL_CONTROL vs byte-identical WDL_CONTROL
- exact 20,000 nodes/move
- threads: 1
- book: OFF
- max plies: 160.

Paired bootstrap:

- 200,000 repetitions
- seed: `2026111603`
- resampling unit: opening pair.

`D4_RUNTIME_EQUAL_NODE_ESTABLISHED_V1` requires:

1. primary point score > 0.5;
2. bootstrap 95% LCB Elo > 0;
3. identical-control harness exact score 0.5 with complementary paired results;
4. D4 treatment exercised and WDL/value identity checks pass.

Harness/treatment integrity failure is technical `D4_RUNTIME_EQUAL_NODE_INVALID_V1`. A valid failure of either scientific gate is `D4_RUNTIME_EQUAL_NODE_NOT_ESTABLISHED_V1` and is terminal: no retuning and no equal-time.

## 11. Equal-time continuation, frozen now but gated

Only `D4_RUNTIME_EQUAL_NODE_ESTABLISHED_V1` authorizes equal-time.

Fresh equal-time pool:

- exactly 30,000 candidates
- generation seed: `2026111701`
- selector prefix: `2026111702:`
- exclude every prior D4/D3/historical pool
- first 3,000 eligible openings
- both colours = 6,000 games.

Runtime:

- 0.1 s/move
- node limit disabled
- threads: 1
- book: OFF
- max plies: 160.

Paired bootstrap:

- 200,000 repetitions
- seed: `2026111703`.

Equal-time ESTABLISHED requires point score > 0.5 and bootstrap 95% LCB Elo > 0, with all integrity/provenance gates passing.

Even equal-time ESTABLISHED does **not** authorize automatic promotion or bake. Promotion requires a separate preregistration.

## 12. Forbidden retrospective adaptation

After this document is merged, the following are forbidden without declaring D4 terminal and opening a genuinely new hypothesis:

- changing any D4 seed, root/example count, feature, transform, phase boundary, model width, regularization, optimizer setting, top-four scope, runtime-cost threshold, game count or causal gate using results from 1857, 1860, future D4 TRAIN/VALID/TEST, preflight, equal-node or equal-time;
- using 1857 game outcomes as labels, weights, filters or model-selection evidence;
- using 1860 colour/phase/result subgroups to choose a D4 subgroup deployment;
- adding qscore, SearchDecisionTrace selected-action targets, B3/full-ladder 1843 targets or a deep value teacher;
- D3 retuning or D3/D4 blending;
- automatic promotion/bake.

Technical failures may be repaired plumbing-only with regression coverage and immutable requeue IDs, while preserving this scientific contract exactly.

## 13. Authorization boundary

Merge of this preregistration authorizes only implementation/preflight plumbing for the frozen D4 program. It does not itself authorize generation, teacher search, fit, strength games, promotion or bake.
