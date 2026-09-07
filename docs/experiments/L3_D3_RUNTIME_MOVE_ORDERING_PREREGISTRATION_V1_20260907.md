# L3 Decision Information — D3 runtime move-ordering preregistration v1

Date: 2026-09-07  
Status: **PREREGISTRATION ONLY — NO GAME / NO PROMOTION / NO BAKE BY MERGE**

## 1. Terminal prerequisite

This runtime experiment opens only because the frozen D3 relational-action residual completed successfully under its preregistration and its pre-execution square-canonicalization amendment.

Authenticated terminal source:

```text
preflight job      cpx62-1853-l3-decision-math-d3-relational-action-preflight-v1
preflight attempt  20260907T071614Z-1bea99d0
preflight code     1bea99d04ba1b4a2d79e36af8d4a1bc9be930453
preflight verdict  D3_RELATIONAL_ACTION_PREFLIGHT_COMPLETE_V1

fit job            cpx62-1854-l3-decision-math-d3-relational-action-fit-v1
fit attempt        20260907T073241Z-1bea99d0
fit code           1bea99d04ba1b4a2d79e36af8d4a1bc9be930453
fit exit           0
fit verdict        D3_RELATIONAL_ACTION_TRANSFER_ESTABLISHED_V1
adapter sha256      03cd2aa6b2a61ef8ce11dc878eb0ba13a56c8e587b49b19158135a1b64bfd4c3
adapter width       632 float64 parameters
value-model sha256  e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0
```

Frozen D3 terminal evidence is motivation only, not a tuning surface:

```text
C test CE WDL_CONTROL   2.122571165760423
C test CE D3            1.985602283467933
paired delta mean       +0.13696888229249013 nat
bootstrap 95% CI        [+0.09203260391729054, +0.18138741970328548]
C test top1 control     0.2200
C test top1 D3          0.2850
C test top2 control     0.3450
C test top2 D3          0.4425
phase-all-positive      true
STM-both-positive       true
support                 true
valid-delta-positive    true
```

No runtime integration choice below is selected by phase, STM, action-count band, parent-level delta, or any other held-out D3 diagnostic.

## 2. Scientific question

The single runtime question is:

> When the exact frozen D3 score is used only to order legal siblings, with the exact WDL_CONTROL value evaluator unchanged, does search become stronger first at equal nodes and then at equal time?

The treatment is **move ordering only**. Leaf values, alpha-beta semantics, pruning thresholds, transposition-table semantics and all value-model bytes remain unchanged.

## 3. Immutable candidate and control

### 3.1 Value evaluator

Both arms use the exact D1 `WDL_CONTROL` value artifact already authenticated by D3.

```text
WDL_CONTROL coefficient = 1.0
value-model sha256       = e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0
```

There is no WDL refit, PatternEval refit, blend, calibration, temperature or scale.

### 3.2 D3 adapter

The candidate must load the exact sealed adapter bytes from D3 terminal job 1854:

```text
artifact      D3_RELATIONAL_ADAPTER.npy
sha256        03cd2aa6b2a61ef8ce11dc878eb0ba13a56c8e587b49b19158135a1b64bfd4c3
format        npy float64
width         632
base width    158
phase blocks  4
```

The adapter is never refit, quantized, widened, sparsified, rescaled or phase-gated.

### 3.3 Authoritative square canonicalization

The preregistration amendment remains authoritative. Runtime encoding uses playable-square indices `1..50` exactly:

```text
if parent_stm == black: sq_canon = sq
if parent_stm == white: sq_canon = 51 - sq
```

The same mapping applies independently to `from_square`, `to_square` and every set captured square.

## 4. Frozen runtime score

For every legal action after it is generated, compute exactly the already-frozen D3 relational representation:

```text
from_square_onehot_50
+ to_square_onehot_50
+ captured_square_mask_50
+ num_captures / 20
+ promotes {0,1}
+ moving_king {0,1}
+ captured_kings / 20
+ material_count_delta_parent / 20
+ child_pieces / 40
+ child_legal_moves / 64
+ child_forced_capture {0,1}
= 158 dimensions
```

Place that vector into the same single phase block `P0/P1/P2/P3` used by the frozen D3 implementation, giving width 632.

The ordering score is exactly:

```text
score_D3(s,a) = v_parent_WDL_CONTROL(s,a) + phi_rel(s,a) dot beta_D3
```

No softmax is needed at runtime. No scale, temperature, clipping or learned coefficient is introduced. Higher `score_D3` means earlier search among the D3-controlled sibling tier.

Forbidden runtime inputs to the D3 score:

```text
q5/q50/q200 scores
1843/full-ladder values
SearchDecisionTrace fields
search bounds
node counts
elapsed time
history score
killer score
TT score
teacher labels
split/provenance identity
D1/D2 scores or autopsy deltas
WDL targets
```

## 5. Frozen integration semantics

The baseline arm is the unmodified search ordering of the implementation commit used for this experiment.

The candidate differs only in the relative order of non-authoritative siblings:

```text
1. existing root/PV forced priority remains first and unchanged
2. existing legal TT move priority remains first within its current authoritative tier and unchanged
3. all remaining legal moves are sorted by descending score_D3
4. exact existing legacy move-order score is used only as the first deterministic tie-break
5. semantic move identity is the final deterministic tie-break
```

D3 does not directly modify:

```text
leaf/static evaluation
returned search score
alpha/beta windows
aspiration semantics
LMR/RFP/NMP/singular thresholds
qsearch semantics
TT probe/write/replacement rules
history/killer update formulas
repetition or draw rules
move legality
TB/EGDB values
```

Different ordering may naturally change the explored tree and therefore downstream history/TT contents during a search. That is part of the causal ordering treatment and must not be manually compensated.

## 6. Mandatory zero-game runtime preflight

Before any game, a separate implementation/preflight stage must prove all of the following:

```text
exact adapter sha256 authenticated
exact WDL_CONTROL sha256 authenticated
D3 width = 632 and canonical mapping = 1..50 / white:51-sq
candidate/control leaf evaluations byte-identical on a deterministic fixture
candidate with D3 disabled reproduces control best move/score/PV/nodes exactly
root/PV priority semantics unchanged
TT priority semantics unchanged
no value blend/scale/temperature
qscore reads = 0
SearchDecisionTrace reads = 0
1843/full-ladder reads = 0
teacher/model search = 0
fits/refits = 0
strength games = 0
promotion = false
bake = false
```

Use a deterministic legal-position fixture generated independently of C valid/test and independently of all strength pools. Freeze fixture generation seed as:

```text
runtime_preflight_fixture_seed = 2026111299
positions = 128
```

The preflight may publish CPU/wall overhead of feature construction as a diagnostic. No cost observation may change the score formula, feature set, application depth, adapter bytes, pool sizes, node budget or time budget.

Preflight terminal verdicts:

```text
D3_RUNTIME_MOVE_ORDERING_PREFLIGHT_COMPLETE_V1
D3_RUNTIME_MOVE_ORDERING_PREFLIGHT_INVALID_V1
```

`INVALID` is technical/provenance only and may authorize plumbing repair under the same science.

## 7. Equal-node causal gate

Equal-node is the first and mandatory game gate. Equal-time is forbidden unless equal-node passes.

### 7.1 Fresh target-blind pool

Generate exactly 30000 legal candidate positions without reading D3/WDL/CURRICULUM scores:

```text
min_ply          = 8
max_ply          = 32
min_pieces       = 20
generation_seed  = 2026111301
```

Exclude every published strength/force/runtime pool available at launch plus all C SiblingDataset-v2 parent identities and all D3 preflight fixtures. The exclusion set may grow only to include newly published prior cohorts; it may never remove an already forbidden cohort.

Canonical deduplication is board + STM with rotate180+colour-swap equivalence.

Order surviving identities by:

```text
SHA256("2026111302:" + canonical_identity)
```

Freeze:

```text
first 750 openings = EQUAL_NODE_PRIMARY
next 100 openings  = EQUAL_NODE_HARNESS
```

Every opening is played in both colours:

```text
primary = 1500 games
harness = 200 games
```

No opening may overlap the later equal-time pool.

### 7.2 Engine contract

For every equal-node game:

```text
threads              = 1
book                 = OFF
EGDB/TB               = identical both arms
search state          = fresh per game
TT                    = fresh per game
node budget           = 20000 nodes per move each arm
movetime              = disabled
max plies             = 160
candidate evaluator   = exact WDL_CONTROL
control evaluator     = exact WDL_CONTROL
only treatment        = D3 move ordering defined in Section 5
```

Skipped games, timeouts and crashes are never converted to draws.

### 7.3 Harness cell

`EQUAL_NODE_HARNESS` plays control vs the byte-identical control under the same node budget. Each colour-paired opening must be complementary or two draws.

Require exactly:

```text
aggregate score arm A = 0.5
paired complementarity failures = 0
game skipped = 0
```

Any failure is `D3_RUNTIME_EQUAL_NODE_INVALID_V1`, never neutral evidence.

### 7.4 Primary statistic

Primary score:

```text
score = (wins + 0.5*draws) / games
Elo   = 400 * log10(score / (1-score))
```

Paired bootstrap resamples the 750 opening pairs:

```text
replications = 200000
seed         = 2026111303
CI           = percentile 95%
```

Publish W/D/L, paired score, Elo, CI95, mean depth, completed depth, total nodes, eval calls, D3 feature calls, wall time and candidate/control node-use diagnostics.

Equal-node scientific PASS requires all support/harness gates and:

```text
point score_D3 > 0.5
LCB95(Elo_D3_vs_WDL_CONTROL) > 0
```

Terminal verdicts:

```text
D3_RUNTIME_EQUAL_NODE_ESTABLISHED_V1
D3_RUNTIME_EQUAL_NODE_NOT_ESTABLISHED_V1
D3_RUNTIME_EQUAL_NODE_INVALID_V1
```

`NOT_ESTABLISHED` is a scientific STOP. It authorizes no scale, retuning, phase gating, feature change, alternative adapter or equal-time game.

## 8. Equal-time practical gate

This gate is authorized only by `D3_RUNTIME_EQUAL_NODE_ESTABLISHED_V1`. It remains a move-ordering-only comparison against the same exact WDL_CONTROL evaluator, so the only treatment remains D3 ordering.

### 8.1 Fresh independent pool

Generate a disjoint target-blind pool with:

```text
candidate positions = 30000
min_ply             = 8
max_ply             = 32
min_pieces          = 20
generation_seed     = 2026111401
selector            = SHA256("2026111402:" + canonical_identity)
openings            = first 3000 surviving identities
```

Exclude all equal-node openings, all D3 preflight fixtures, C parents and all previously published strength/force/runtime pools. Play every opening in both colours:

```text
6000 games total
```

### 8.2 Equal-time contract

```text
threads              = 1
book                 = OFF
EGDB/TB               = identical both arms
search state          = fresh per game
TT                    = fresh per game
movetime              = 0.1 seconds per move each arm
node limit            = disabled
max plies             = 160
candidate evaluator   = exact WDL_CONTROL
control evaluator     = exact WDL_CONTROL
only treatment        = D3 move ordering
```

No movetime calibration or arm-specific time allowance is permitted after preregistration.

Paired bootstrap:

```text
replications = 200000
seed         = 2026111403
CI           = percentile 95%
```

Publish W/D/L, paired score, Elo, CI95, nodes/move, depth, eval calls, D3 feature calls and wall time.

Equal-time PASS requires:

```text
game skipped = 0
point score_D3 > 0.5
LCB95(Elo_D3_vs_WDL_CONTROL) > 0
```

Terminal verdicts:

```text
D3_RUNTIME_EQUAL_TIME_ESTABLISHED_V1
D3_RUNTIME_EQUAL_TIME_NOT_ESTABLISHED_V1
D3_RUNTIME_EQUAL_TIME_INVALID_V1
```

An equal-time PASS does **not** promote anything. It authorizes only preparation of a new, separately preregistered force comparison against the current champion `CURRICULUM` if such a comparison is desired.

## 9. Programme-wide stopping and exclusions

This preregistration explicitly forbids:

```text
D3 refit or adapter modification
feature add/remove/ablation
phase-conditional enable/disable
STM-conditional enable/disable
action-count-conditional enable/disable
runtime scale or temperature
WDL/PatternEval refit
q5/q50/q200 target or feature reads
1843/full-ladder target reads
SearchDecisionTrace as D3 input
new teacher search
new model search
lambda/L2 sweep
root-budget changes
pruning-threshold changes
LMR/RFP/NMP changes
strength comparison against CURRICULUM before a separate force preregistration
promotion
bake
champion replacement
automatic continuation after a scientific negative verdict
```

Technical failures may be repaired and requeued immutably only if the treatment, pools, seeds, budgets, statistics, gates and stopping rules above remain unchanged.

## 10. Execution order and authorization boundary

```text
merge/freeze this preregistration
 -> implementation + deterministic tests only
 -> zero-game runtime preflight
 -> if preflight COMPLETE: equal-node primary + harness
 -> if and only if equal-node ESTABLISHED: equal-time gate
 -> if equal-time ESTABLISHED: STOP and optionally prepare a separate CURRICULUM force preregistration
```

Merging this document does not itself authorize implementation to play games. The first game is authorized only after the runtime implementation and zero-game preflight are separately implemented, merged and authenticated under this frozen contract.
