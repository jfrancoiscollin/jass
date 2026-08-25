# L3 — exact-D tablebase-frontier policy as capture move ordering v1

Date: 2026-08-25. Status: **preregistered before search integration strength games and before any fresh force-pool result is read**.

## Upstream evidence

The only policy source is the immutable successful learnability job:

- job `cpx62-1566-l3-tb-frontier-archive-learnability-v1`
- attempt `20260825T203056Z-eb2a520b`
- code `eb2a520b0a24caec8a3477ff0acaca851bafa5b4`
- verdict `TB_FRONTIER_RANK_SIGNAL_ESTABLISHED`
- 15,763 symmetry-canonical parents, 3,136 parent-disjoint holdout parents
- CURRICULUM holdout pairwise accuracy `0.6124099820867199`
- learned D holdout pairwise accuracy `0.7058565278790088`
- D − CURRICULUM pairwise delta `+0.09344654579228878`, bootstrap 95% CI `[0.07505604277273002, 0.11191479096035059]`
- top-hit delta `+0.0859375`, bootstrap 95% CI `[0.06584821428571429, 0.10602678571428571]`
- all 16 label shams were negative and the true delta exceeded all shams.

The policy artifact is `artefacts/policy.json` from that exact attempt. It has schema `jass.tb_move_order_policy.v1`, 120 raw production eval features plus six move-local features, separate white-parent / black-parent banks, and score convention `higher_is_better_for_parent`.

CURRICULUM remains the immutable leaf evaluator:

`319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`

No scalar refit is allowed in this protocol.

## Scientific question

Does the independently established exact sibling-ranking signal improve alpha-beta search at fixed wall-clock time when it is used only to choose the order in which legal captures are searched?

The intervention is deliberately narrower than a new evaluator:

```text
leaf value / T          = byte-identical CURRICULUM
legal move set          = identical
TT value / bounds       = identical
alpha-beta / PVS        = identical
pruning thresholds      = identical
EGDB                     = identical
capture generation set  = identical
capture initial order   = D score instead of generation order, only in support domain
```

## Runtime support domain

The learned policy is applied **only** at parents with exactly 8 pieces and at least two legal capture moves.

This is the exact support domain of the upstream teacher: an 8-piece capture necessarily produces a child with at most 7 pieces, inside the CPX62 EGDB coverage used to generate the labels. V1 therefore makes no claim that a policy trained at the 8→≤7 frontier generalises to 9+, 20- or 40-piece positions.

Outside this domain, move generation and order are byte-for-byte the legacy path.

Within this domain:

1. legal captures and FMJD majority filtering are completed first;
2. each legal child is represented by `scan_eval::compute_extras(child)` (120 values) plus exactly:
   - `num_captures`
   - `captured_kings`
   - `promotes`
   - `moving_king`
   - `from / 50.0`
   - `to / 50.0`
3. D scores each child with the frozen colour bank;
4. captures are stably sorted descending by D score.

The existing search hierarchy stays authoritative:

- an internal TT move still receives the existing `1,000,000` ordering priority and therefore remains first;
- at the root, the previous iterative-deepening best move is still hoisted before the next iteration;
- D only replaces the otherwise generation-order tie among capture siblings.

The policy does **not** probe EGDB at runtime.

## Activation and causal baseline

The implementation is dormant unless `JASS_TB_MOVE_ORDER_POLICY` points to a valid packed policy file. A requested malformed/mismatched policy fails closed. The same native executable is used for both players:

- `BASELINE`: same executable, environment variable absent;
- `POLICY_D`: a minimal wrapper sets `JASS_TB_MOVE_ORDER_POLICY=<frozen packed policy>` then `exec`s that exact executable.

Therefore code, compiler, search constants, CURRICULUM model, EGDB and hardware are identical. The only manipulated factor is D capture ordering in the frozen 8-piece support domain.

## Runtime-cost profile — diagnostic, never selective

Before strength, run a deterministic paired profile on 512 symmetry-canonical 8-piece parents taken from the frozen 1565 corpus, selected only by the already-frozen parent fingerprint order/hash and without using D correctness or game results.

For BASELINE and POLICY_D on every position record:

- wall time per `go`;
- nodes;
- completed depth/effective reported depth;
- cutoffs;
- first-move cutoffs (`cut1`);
- PVS researches;
- moves searched.

Profile at native `0.1 s` and Q00 depth 9. Report ratios/deltas including nodes per wall-second and `cut1/cutoffs`. These diagnostics may explain a strength result but **cannot select, reject, retune, rescale or disable the policy**. No threshold is imposed on NPS.

## Fresh strength pool 1

Generate a fresh deterministic force pool only after this preregistration:

- generator: Jass `--gen-opening-pool`
- candidates: 60,000
- generator depth: 8
- max plies: 32
- random opening plies: 20
- pool-1 seed: `2026083001`
- select first 3,000 unique exact board+STM states after exclusions using `select_independent_opening_pool.py`;
- candidate generation is repeated twice and must be byte-identical;
- colours are paired/reversed.

The pool is excluded against the fixed historical force-pool list already used by the context3/1562 gates, and against any earlier pool supplied to the selector. Pool-2, if authorised, additionally excludes pool-1.

Because the D training parents all contain exactly 8 pieces while the force-pool generation is an opening/midgame generator, exact state overlap with D parents is also checked; any overlap is excluded rather than tolerated.

## Strength views

Exactly one causal contrast:

`POLICY_D vs BASELINE_CURRICULUM`

Pool 1:

- native primary: `0.1 s / move`, 3,000 openings × colour pair = **6,000 games**;
- Q00 diagnostic: depth 9, same 3,000 openings × colour pair = **6,000 games**;
- total pool-1 strength games = **12,000**;
- paired opening-cluster bootstrap: 200,000 resamples;
- pool-1 bootstrap seed `2026083011`;
- standard current Q00 search fingerprint, identical for both players;
- no book asymmetry, same EGDB, same TT/search parameters.

The native view is the causal primary because it automatically prices the runtime cost of D. Q00 is mechanistic diagnostic only.

## Pool-1 decision

Let `p1_native` be POLICY_D's paired native score rate.

- if `p1_native <= 0.5`, verdict `TB_POLICY_MOVE_ORDERING_NOT_SUPPORTED`; no replication;
- if `p1_native > 0.5`, exactly one unchanged fresh pool-2 replication is authorised, regardless of whether pool-1 CI already excludes 0.5;
- an established native regression is also `TB_POLICY_MOVE_ORDERING_NOT_SUPPORTED`.

No parameter, feature, support boundary, weight scaling, search budget or runtime implementation may change between pools.

## Pool 2 if authorised

- candidate seed `2026083002`;
- 60,000 candidates, first 3,000 unique after the same historical exclusions plus exact pool-1 exclusion;
- native 0.1 s primary and Q00 depth9 diagnostic;
- 6,000 games per view, 12,000 total;
- pool-2 bootstrap seed `2026083021`;
- chained native paired-opening bootstrap seed `2026083099`, 200,000 samples.

Final `TB_POLICY_MOVE_ORDERING_SUPPORTED` requires:

1. native point estimate `> 0.5` on both independent pools;
2. chained native bootstrap 95% lower bound `> 0.5`;
3. no technical error asymmetry;
4. CURRICULUM bytes and the packed D policy are unchanged across both pools.

If both pool directions are positive but the chained lower bound does not clear 0.5, verdict `TB_POLICY_MOVE_ORDERING_INCONCLUSIVE`. Any non-positive pool-2 direction yields `TB_POLICY_MOVE_ORDERING_NOT_SUPPORTED`.

Q00 can never rescue a native failure.

## Promotion / continuation

- zero self-play;
- zero PatternEval refits;
- zero frozen-cohort reads;
- no policy weight tuning;
- no automatic promotion.

A supported result establishes only that the exact-frontier D head improves search when used as ordering inside its demonstrated 8-piece support domain. A later experiment may extend the teacher to positions outside tablebase (deeper-search sibling rankings) or distil the head to a cheaper representation, but neither is part of this protocol.
