# L3 — DSSD general-policy capture move ordering force gate v1

Date: 2026-08-26. Status: **preregistered before any DSSD runtime strength game is generated or read**.

## Immutable upstream evidence

The runtime policy is frozen from the successful Deep Search Sibling Distillation campaign. No runtime result may alter this evidence, its weights, its support boundary, or the force protocol below.

Phase A:

- job `cpx62-1575-l3-deep-sibling-phase-a-v1`
- attempt `20260826T191127Z-f1dee26a`
- verdict `DEEP_SIBLING_RANK_SIGNAL_ESTABLISHED`
- D holdout pairwise `0.7204674361567956`
- CURRICULUM/T holdout pairwise `0.5921755036054149`
- D − T pairwise bootstrap mean `+0.12829193255138066`
- bootstrap 95% CI `[0.11110474939800696, 0.14545976877003736]`
- D top-hit `0.601018675721562`
- CURRICULUM/T top-hit `0.5074985851726089`
- frozen policy artefact `dssd-policy.json`
- policy schema `jass.deep_sibling_policy.v1`
- exactly 120 production `scan_eval::compute_extras(child)` features plus six move-local features
- separate white-parent and black-parent linear banks
- score convention `higher_is_better_for_parent`

Independent zero-refit Phase B confirmation:

- fresh selection `cpx62-1578-l3-deep-sibling-phase-b-fresh-v2`, attempt `20260826T203927Z-87475360`
- teacher `cpx62-1579-l3-deep-sibling-phase-b-teacher-v1`, attempt `20260826T210539Z-87475360`
- final readout `cpx62-1581-l3-deep-sibling-phase-b-readout-v2`, attempt `20260826T212656Z-87475360`
- verdict `DEEP_SIBLING_CONFIRMATION_ESTABLISHED`
- D pairwise `0.7260411978805384`
- CURRICULUM/T pairwise `0.6140599672785467`
- D − T bootstrap mean `+0.11198123060199161`
- bootstrap 95% CI `[0.09882705167008797, 0.1251451547451187]`
- positive D − T direction in every represented phase P0/P1/P2/P3
- policy refit `false`
- strength games `0`

CURRICULUM remains the immutable leaf evaluator, raw SHA256:

`319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`

The only policy source allowed in this experiment is the exact Phase-A `dssd-policy.json` authenticated through the immutable Phase-A result above. Packing is serialization only: no fit, normalization, rescaling, clipping, calibration, feature change, or colour-bank change is permitted.

## Scientific question

Does the already-confirmed DSSD sibling-ranking signal improve the strength of the unchanged CURRICULUM engine at fixed wall-clock search time when D is used **only** to order already-legal capture siblings?

The causal contrast is exactly:

`CURRICULUM + frozen D ordering` vs `CURRICULUM alone`.

## Runtime intervention

The same native executable is used on both sides. The candidate differs only by a wrapper/environment variable pointing to the frozen packed D policy.

Unchanged on both sides:

- leaf evaluator: byte-identical CURRICULUM
- legal move set and FMJD majority-capture rule
- alpha-beta/PVS values
- TT keys, stored values, bounds, replacement, and lookup semantics
- pruning and extension thresholds
- EGDB behavior
- book setting
- search parameters
- compiler and executable
- hardware

D is permitted to change **only the generation-order tie among already-legal capture siblings**.

The existing search hierarchy remains authoritative:

1. an internal TT move keeps its existing absolute ordering priority;
2. at the root, the previous iterative-deepening best move remains hoisted by the existing search code;
3. D only supplies the underlying order among otherwise equal capture siblings.

D never enters leaf evaluation, alpha/beta, TT value/bounds, pruning thresholds, game adjudication, legal move generation, or any policy/value blend.

## Demonstrated runtime support boundary

The runtime hook is support-bounded to:

- parent piece count **9 through 40 inclusive**; and
- at least two legal capture siblings after full capture generation and FMJD majority filtering.

Outside this domain, the legacy generated order is preserved exactly. Quiet moves are never reordered by D in v1.

For every eligible capture sibling, D receives exactly:

1. the 120 production `scan_eval::compute_extras(child)` values; then
2. `num_captures`;
3. `captured_kings`;
4. `promotes`;
5. `moving_king`;
6. `from / 50.0`;
7. `to / 50.0`.

The white-parent bank scores White-to-move parents and the black-parent bank scores Black-to-move parents. Higher score is searched first. Exact score ties remain stable in legacy generation order.

The runtime policy is dormant unless `JASS_DSSD_MOVE_ORDER_POLICY` names a valid packed policy. A requested malformed policy must fail closed. Baseline processes explicitly have both `JASS_DSSD_MOVE_ORDER_POLICY` and the historical `JASS_TB_MOVE_ORDER_POLICY` unset; DSSD candidate processes explicitly unset the historical TB-policy variable and set only `JASS_DSSD_MOVE_ORDER_POLICY`.

## Packing contract

`jobs/tools/dssd_policy_pack.py` accepts only:

- schema `jass.deep_sibling_policy.v1`
- `usable=true`
- eval width `120`
- the exact six move-feature names and order above
- score convention `higher_is_better_for_parent`
- exactly 126 finite weights in each colour bank

It serializes those 252 numbers verbatim using Python float round-trip decimal representation. The runtime file magic is `JASS_DSSD_MOVE_ORDER_POLICY_V1`. Source-policy SHA256 and packed-policy SHA256 are published and must remain unchanged through every pool.

## Preflight before strength

Before generating any fresh force pool, a dedicated cpx62 preflight must:

- authenticate the exact Phase-A and Phase-B successful attempts above;
- authenticate the CURRICULUM SHA256 above;
- fetch the exact Phase-A policy and pack it deterministically twice to byte-identical output;
- build native Jass with the normal production architecture and real EGDB support;
- run native tests and the DSSD packer/contract tests;
- prove baseline policy OFF starts normally;
- prove candidate policy ON starts normally;
- prove malformed DSSD policy exits non-zero rather than silently falling back;
- prove support bounds 9 and 40 are eligible while 8 is reserved for the historical TB policy and outside DSSD support;
- prove no self-play, PatternEval fit, T refit, frozen-cohort read, strength game, or promotion occurs in preflight.

Any preflight failure is technical only and may be repaired without changing this protocol.

## Runtime-cost profile — diagnostic only

Before Pool 1 strength, profile baseline and DSSD candidate on exactly 512 capture-eligible parents selected deterministically from the already-frozen DSSD corpus without using D correctness or force outcomes. Selection uses only parent identity/phase and move metadata; teacher scores are not selection inputs.

For both engines, at native `0.1 s` and Q00 depth 9, record where available:

- wall time
- nodes
- completed depth
- NPS
- cutoffs
- first-move cutoffs (`cut1`)
- PVS researches
- moves searched

Also publish the number of profiled positions inside the 9–40 multi-capture support. These diagnostics can explain a force result but can never select, reject, retune, rescale, or disable D.

## Fresh force Pool 1

The pool is generated only after this document and runtime implementation are committed.

Frozen parameters:

- generator: Jass `--gen-opening-pool`
- candidates: `60,000`
- generator depth: `8`
- max plies during pool generation: `32`
- random opening plies: `20`
- Pool-1 candidate seed: `2026083301`
- select first `3,000` unique exact board+STM states after exclusions
- candidate generation is repeated and must be byte-identical
- colour pairing/reversal: mandatory

Pool-1 roots must be exact-state disjoint from:

- the 8,000 frozen Phase-A DSSD selected parents;
- the 2,000 frozen Phase-B fresh selected parents;
- every historical force pool already excluded by the established TB-policy force harness, including the two TB-policy pools themselves.

Exact overlap is excluded, not tolerated. The overlap receipts are published before matches begin. No D score, teacher score, game result, or future force result participates in pool selection.

## Pool-1 strength views

Exactly one causal contrast:

`DSSD_D vs BASELINE_CURRICULUM`.

Primary native view:

- `0.1 s / move`
- `3,000` openings × paired/reversed colours = **6,000 games**
- fixed wall clock prices the runtime cost of D automatically

Mechanistic diagnostic view:

- Q00 depth `9`
- same 3,000 openings × paired/reversed colours = **6,000 games**
- Q00 can never rescue a native failure

Paired opening-cluster bootstrap:

- samples: `200,000`
- Pool-1 bootstrap seed: `2026083311`

Publish at minimum:

- W/D/L and score rate for DSSD_D
- Elo and ordinary CI95
- paired-opening bootstrap CI95 and `P(score > 0.5)`
- technical errors by side
- runtime-cost profile
- D activation/support diagnostics available from the harness
- executable/code SHA
- CURRICULUM raw SHA256
- source D policy SHA256 and packed D policy SHA256
- pool provenance, deterministic-generation receipt, and all overlap counts

## Pool-1 decision — frozen before results

Let `p1_native` be DSSD_D's paired native score rate.

- if `p1_native <= 0.5`: verdict `DSSD_MOVE_ORDERING_NOT_SUPPORTED`; stop, no replication;
- if `p1_native > 0.5`: authorize exactly one unchanged fresh Pool-2 replication regardless of Pool-1 CI width.

No weight, feature, support boundary, ordering rule, search parameter, time budget, pool-selection rule, or runtime implementation may change between pools.

## Pool 2 if and only if Pool 1 is positive

Frozen parameters:

- candidates `60,000`
- same depth/maxplies/random-open settings
- Pool-2 candidate seed `2026083302`
- first `3,000` unique states after all prior exclusions plus exact Pool-1 exclusion
- native `0.1 s`: 6,000 games
- Q00 depth 9: 6,000 games
- paired bootstrap samples `200,000`
- Pool-2 bootstrap seed `2026083321`
- chained native paired-opening bootstrap seed `2026083399`, `200,000` samples

Final `DSSD_MOVE_ORDERING_SUPPORTED` requires all of:

1. Pool-1 native point estimate `> 0.5`;
2. Pool-2 native point estimate `> 0.5`;
3. chained native paired-opening bootstrap 95% lower bound `> 0.5`;
4. no material technical-error asymmetry;
5. identical executable, CURRICULUM bytes, source D policy bytes, packed D policy bytes, support boundary, and protocol across pools.

If both native pool directions are positive but chained CI95 lower bound does not clear 0.5, verdict `DSSD_MOVE_ORDERING_INCONCLUSIVE`.

Any non-positive Pool-2 native direction yields `DSSD_MOVE_ORDERING_NOT_SUPPORTED`.

Q00 never rescues native.

## Explicit prohibitions

Throughout this experiment:

- zero new self-play for learning
- zero PatternEval fits
- zero CURRICULUM/T refit
- zero D refit
- zero policy weight tuning or rescaling
- zero policy/value blending
- zero frozen-cohort reads for selection
- zero automatic promotion

A supported result establishes only that the frozen, independently confirmed DSSD head improves alpha-beta search as capture ordering at fixed wall-clock time. It does **not** authorize promotion, a T refit, or a richer D. Those require separate user authorization and a new preregistration.