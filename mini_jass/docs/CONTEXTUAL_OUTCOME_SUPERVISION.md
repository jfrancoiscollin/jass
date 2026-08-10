# Contextual outcome supervision v3

## Status

Design/preregistration for Mini-Jass L1 on the architecture merged as
`folded_pattern_value`: exact side-aware folded pattern buckets, one scalar
value and moves supplied by search.

M24-P `cpx62-1217-mini-jass-pattern-m24p-v1` has returned `PASS`; its frozen
result hash is
`9447d1ea86ca2492c84aead6eedd0bbdb4bf2fbe1c7e9f3323d6d0879545cd67`.
M18-P `cpx62-1222-mini-jass-pattern-m18p-v1` then isolated a static label gap
on PatternEval; its result hash is
`2680f52319b7be31c5cb6d44c229b78c545eb21b4dc4c8be2e3f17c125da5554`.

This protocol is still not runnable. M21-P
`cpx62-1223-mini-jass-pattern-m21p-v1` is currently measuring the missing
common-search strength effect at equal replay volume. Its result hash, replay
source decision and power-sizing report must be frozen in a follow-up commit
before C0 or any contextual model may train. No production Jass change or
direct 10x10 transfer is authorized.

This remains a later factor in the PatternEval reconstruction program. A merge
of this design never queues C1 automatically and cannot displace M21-P or its
decision record.

V3 changes only the upstream evidence contract. V2 incorrectly sized from the
failed M17-P promotion cell's static zero-regret variance. V3 instead consumes
the architecture-correct M21-P paired common-search contrast, the endpoint that
C1 itself will use. No C0 evidence has been read, so this preregistration repair
does not condition on contextual results.

The v3 preparation tool is executable but deliberately non-training. Given the
completed runner status and full M21-P result, it recomputes the scientific
hash, validates all 20 per-seed arena deltas, applies the replay-source rule,
runs the frozen power simulation and writes a round-tripped freeze report. The
report always carries `c0_or_training_authorized: false`; a reviewed follow-up
commit must replace both pending sentinels with its source, pair count and hash.

## Question

Terminal W/D/L is the game truth, but copying it unchanged onto every state is
a low-bandwidth optimization target. A draw saved from a losing position and a
draw thrown away from a winning position both receive `0`.

The pattern table already observes the full board information needed to derive
material, mobility, blocked men, advancement and central presence. Context
therefore adds no information at inference. The experiment asks whether an
auxiliary objective supplies a useful **inductive bias** by orienting gradients
toward those deterministic factors, while the main target remains terminal WDL
and the deployed model remains exactly `scalar PatternEval -> search`.

## Architectural constraint: where the gradient must go

The original draft proposed independent linear readouts over active buckets.
That cannot affect `PatternEval`: active bucket IDs are fixed indices, not a
learned representation. An independent context table receives its own
gradients; the scalar `bucket_weight` receives none of them. Discarding that
readout would therefore recover the WDL-only model exactly.

V2 uses one frozen train-time scaffold for every arm, including WDL_ONLY.

For each folded bucket class `j`, learn an embedding `E_j` in `R^10`. The ten
axes reserve one value axis plus one axis per context component. With
active classes `A(s)`, reversible-plies feature `r(s)`, shared reversible
embedding `E_r` and shared bias `b_h`:

```text
h(s) = sum(j in A(s)) E_j + r(s) E_r + b_h
z_v(s) = q_v . h(s) + b_v
V(s) = tanh(z_v(s))
```

Training-only linear heads predict context, transition context and residual
from the same `h(s)`. Their losses therefore update `E_j`, which also changes
the scalar value. Separate context tables with no shared parameter path are
forbidden.

After training, export an ordinary scalar PatternEval table:

```text
bucket_weight[j] = q_v . E_j
extra_weight = q_v . E_r
bias = q_v . b_h + b_v
```

The auxiliary heads and embeddings are then discarded. The exported evaluator
must match pre-export scalar values within `1e-6` on every oracle state and
must choose the same common-search action on 100% of playable states. Failure
of either invariant invalidates the arm.

The factorized scaffold changes optimization, so it is not compared with the
old direct-table WDL checkpoint. Every C1 arm uses the same rank, parameter
initialization schedule, replay, batches, optimizer and export. The only
non-oracle factor is which frozen auxiliary loss is active.

Initialization is also preregistered: SHA-256 counter-normal v1 keyed by the
paired seed, embedding standard deviation `0.01`, zero shared/value biases,
value head equal to the first basis vector, and auxiliary-head standard
deviation `1/sqrt(10)`. Every head is initialized in every arm, including the
control, before the initial exportable-value hash is recorded.

## Records and targets

For a sampled pre-move state `s_t` and its recorded selected move:

1. `Z_t`: terminal WDL from the side-to-move POV, unchanged.
2. `C(s_t)`: deterministic context vector from the board/rule record.
3. `DeltaC_t`: context change after the recorded move, with both vectors
   represented from the mover POV.
4. `B(C(s_t))`: frozen deterministic scalar baseline.
5. `Rctx_t = clip(Z_t - B(C(s_t)), -1.5, +1.5)`.

The main value loss always targets `Z_t` in deployable arms. `DeltaC` and
`Rctx` never select moves, weight samples or alter replay generation in C0-C3.

## Deterministic context v1

Components remain separate and approximately normalized to `[-1,+1]`:

- man material difference;
- king material difference;
- legal-action count difference;
- legal capturing-action count difference after mandatory/max-capture
  filtering;
- promotion-distance pressure;
- blocked-man count difference;
- normalized man advancement difference;
- occupancy difference on a hashed central-region mask;
- exact terminal flag.

Every difference is own minus opponent from the requested POV. Opponent
mobility is computed by the rule move generator on the same board with the
queried side to move; it is not inferred from the current side's actions.
Material normalizers, promotion rows, the central mask and move-count
normalizers come from frozen rule/geometry constants and are included in the
feature-definition hash.

For a move `s_t -> s_{t+1}`:

```text
DeltaC_t = C_mover(s_{t+1}) - C_mover(s_t)
```

Subtracting two uncorrected side-to-move vectors is forbidden. Determinism,
rotation/colour symmetry and terminal behavior are exact test invariants.

## Frozen contextual baseline

The residual baseline is fixed before C0:

```text
raw = sum_i w_i C_i
B(C) = tanh(raw / 1.50)
```

Weights are, in component order:

```text
men=1.00, kings=1.50, mobility=0.20, capture_options=0.15,
promotion_pressure=0.20, blocked_men=-0.15, advancement=0.10,
center=0.05, terminal=0.00
```

These coefficients are not tuned in C0. Fitting or changing them after any
development/frozen-test read is forbidden.

The `terminal_flag` context component must be exact, but its baseline weight is
deliberately `0`. `B(C)` is a non-oracle positional expectation, not a second
encoding of the game outcome. Residual targets are built only for non-terminal
pre-move training states. The C0 terminal gate validates feature extraction;
it does not require the contextual baseline to predict terminal WDL exactly.

## C0: preregistered protocol-validity gate

C0 may read exact values only on the `train` cohort. It does not choose among
models or remove individual arms. It applies the decision frozen here:

- deterministic repeats must be byte-identical;
- POV symmetry maximum absolute error must be `0`;
- context `terminal_flag` exactness must be `1.0`;
- Spearman correlation of `B(C)` with exact value must be at least `0.30`;
- pairwise ordering rate against exact value must be at least `0.55`.

Pairwise ordering is computed on train-state pairs with unequal exact values;
a baseline tie counts as one half. Eligible pairs are ordered by
`sha256(split_manifest_hash || min_state_id || max_state_id)` and the first
`100000` are used. This rule is included in the protocol hash.

If any threshold fails, the result is
`ABORT_C1_AND_REVISE_PREREGISTRATION`. C1 does not run, no coefficient changes,
and no residual/full arm is silently downgraded to exploratory. A revised
baseline requires a new schema/version and fresh C0 evidence.

## Losses and frozen C1 arms

All component-vector losses use mean squared error reduced first over
components, then over the batch. No auxiliary-weight screen is permitted.

```text
WDL_ONLY:
  L = L_wdl

WDL_PLUS_CONTEXT:
  L = L_wdl + 0.25 L_context

WDL_PLUS_DELTA_CONTEXT:
  L = L_wdl + 0.25 L_delta_context

WDL_PLUS_RESIDUAL:
  L = L_wdl + 0.25 L_residual

WDL_PLUS_FULL_CONTEXT:
  L = L_wdl + (1/12) L_context
            + (1/12) L_delta_context
            + (1/12) L_residual
```

The full arm retains total auxiliary weight `0.25`, matching each single-channel
arm instead of receiving three times the auxiliary dose.

`ORACLE_VALUE_DIAGNOSTIC` replaces the main target with the exact train-cohort
value. It is an explicitly declared diagnostic training-signal boundary
crossing, is excluded from the primary hypothesis and is never promotable.

## M21-P replay-source decision

The replay source used by every C1 arm is selected by one rule frozen before
the M21-P result is read:

- M21-P `PASS`: use the architecture-correct `MIX_OUTCOME` pack;
- M21-P `FAIL`: use the equal-volume `G1_WIDE_OUTCOME` pack;
- M21-P `INCONCLUSIVE`, failed runner state or fewer than one mean advancing
  generation: `ABORT_AND_RESOLVE_M21P`.

This is upstream model-family selection, not arm-specific sample selection.
Once chosen, the same immutable pack, IDs and WDL targets feed every non-oracle
context arm. The M21-P result hash and chosen source are part of the C1 protocol
hash and cannot change between C1 and C2.

## Power sizing before C1

The original four arena pairs per seed had a minimum detectable score effect
around `0.229` at 80% power, larger than the effects this laboratory normally
needs to distinguish. That design is retired.

The Bessel-corrected standard deviation of M21-P's 20 per-seed
`MIX_OUTCOME - G1_WIDE_OUTCOME` common-search arena-score differences is the
measured variance input. The value used for sizing is
`max(measured_sd, 0.10)`, and within-arm game variance keeps its worst-case
`0.25` bound. The observed M21-P standard deviation is not deconvolved to
remove its existing arena noise before being used as the random-effect term;
adding prospective game noise therefore remains deliberately conservative.
That value is fed to the frozen
`m21p_common_search_random_effects_v1` simulation (`100000` repetitions, seed
`44120260810`). The implementation selects the smallest number of pairs per
seed in:

```text
64 / 128 / 256
```

that provides at least 80% power for a true score delta of `+0.10` under the
C1 provisional Student-t rule. Sixty-four is an unconditional floor. Missing
per-seed common-search data, an unfrozen M21-P result hash, an invalid variance
estimate, or failure of all three candidates produces
`ABORT_AND_REVISE_PREREGISTRATION`; it cannot silently choose a sample size.
The M21-P result hash, variance input, selected pair count, estimated power and
power-report hash are frozen before any C1 model trains.

## C1 pairing

The complete replay pack is generated once and frozen before any arm trains.
Every non-oracle arm must prove:

- identical replay fingerprint, sample IDs and terminal WDL values;
- identical exportable-value initial-state hash;
- identical rank-10 scaffold initialization schedule;
- identical batch indices and order;
- identical optimizer hyperparameters and step count;
- identical common-search arena starts, colours and seeds.

The gradients cannot be identical because the losses intentionally differ;
the old phrase `same_optimizer_updates` is therefore replaced by the exact
schedule/batch invariants above.

Pool A seeds are fixed to `270501..270520` (inclusive). Each seed uses the
power-selected number of colour-paired starts, with identical search settings
between arms. The single registered contrast is:

```text
WDL_PLUS_FULL_CONTEXT minus WDL_ONLY
```

The primary endpoint is paired common-search arena score minus `0.5`. A lower
bound of the paired-seed Student-t 95% interval strictly above zero is labelled
`PROVISIONAL_POSITIVE_REQUIRES_C2`; every other result is
`PROVISIONAL_NO_SIGNAL_REQUIRES_C2`. C1 can issue neither PASS nor FAIL. The
three single-channel arms are mechanistic and exploratory; they cannot support
a multiplicity-unadjusted claim.

## Mandatory C2 replication and the only final decision

C2 runs regardless of whether C1 is positive, flat or negative. It repeats
only WDL_ONLY and WDL_PLUS_FULL_CONTEXT with fresh seeds `270601..270620`, a
training replay disjoint from C1 and disjoint arena starts. The recipe and the
power-selected pair count remain unchanged.

Pool A and pool B are reported separately before they are chained. The flat
prior for C1 is updated by pool A, and that posterior becomes the prior for C2.
The pools must pass both hard disjointness and the heterogeneity guard:

```text
z = abs(delta_A - delta_B) / sqrt(se_A^2 + se_B^2) <= 1.96
```

Only the chained result may establish a force signal: compatible pools and
`P(score_delta > 0) > 0.95`. A non-positive combined effect or contradictory
pools is a rejection; every other result is inconclusive. Posterior
probabilities above score deltas `0`, `0.03`, `0.05`, `0.10` and `0.14`, plus
the 95% interval, are always published. No result promotes a model
automatically.

## Registered calibration mechanism

The force endpoint remains the common-search arena. Calibration is a separate
mechanism readout, not a substitute PASS criterion. The registered development
metric is paired `value_mae(FULL) - value_mae(WDL)`, chained over the same two
disjoint pools. A calibration mechanism signal requires compatible pools and
`P(delta_value_mae < 0) > 0.95`.

`value_sign_accuracy`, value Spearman, mean selected regret and static
zero-regret are descriptive. They may explain a result but cannot select a
model, change a weight or rescue a failed force claim. The report must classify
the outcome as exactly one of:

- calibration and force improve: the inductive bias pays in play;
- calibration improves without force: the channel moves values but not play;
- force improves without calibration: the gain is not explained by the
  registered mechanism;
- neither improves: no evidence for the mechanism or force.

This makes an arena-null/calibration-positive result informative rather than a
generic experimental failure.

## Descriptive cost of the scaffold family

The rank-10 scaffold has about 181k train-time parameters before export, versus
18,127 scalar PatternEval parameters. All causal C1/C2 arms pay that capacity,
so their contrast remains clean. Separately, every WDL_ONLY export is compared
descriptively with a direct-table WDL fit starting from the same scalar state
and using the same replay, batches and optimizer schedule. Common-search arena,
static zero-regret and value MAE are reported. This comparison cannot enter
C1, C2, model selection or promotion; it only reveals whether the scaffold
family itself carries a cost.

Static exact-value sign/order/regret, WDL calibration and context strata are
secondary development diagnostics. Search arena remains primary.

## Cohorts and the one sealed read

The immutable L1 split is:

```text
train / development / frozen_test
split_seed = 20260806
manifest_hash = 9e4021da3331bc6ed4976f0ef9baa3c8721a4458c092420749588fbe84e35524
```

There is no `confirmation` cohort. C0 oracle characterization uses `train`.
Development diagnostics may not change weights or arms because all recipes are
already fixed. After C1 and C2 checkpoints, replay hashes, export proofs,
disjointness proof and protocol hash are frozen; `frozen_test` is then read once
for WDL_ONLY and WDL_PLUS_FULL_CONTEXT together. It is descriptive and cannot
select a model.

## Oracle boundary

Oracle access is scoped, not globally described as observer-only:

- C0: train-cohort observer for the frozen validity gate;
- C1 ORACLE_VALUE_DIAGNOSTIC: train-only diagnostic training signal;
- C3: train-only diagnostic target for fitting `B(C)`;
- deployable arms: forbidden in generation, target construction, sample
  selection, loss weighting and promotion.

Diagnostic checkpoints and summaries are stored under distinct schemas and
cannot enter a deployable checkpoint path.

## Later stages

C2 is mandatory and was fixed before C1; it is not opened by a favourable C1
read. Only after the chained C1+C2 decision may the single-channel diagnostics
be interpreted. C3 may then compare the frozen handcrafted baseline with a
train-only fitted baseline; it is a new experiment and cannot reuse the sealed
test read.

Potential-based reward shaping is outside C0-C3. Feeding `DeltaC`, `Rctx` or
context scores back into behavior would change the replay distribution and
requires a separate preregistration.

## Required implementation objects

- `context.py`: exact feature definitions and POV/symmetry tests;
- `context_targets.py`: delta, baseline and residual construction;
- `context_scaffold.py`: shared rank-10 training scaffold and exact scalar
  export;
- `context_power.py`: M21-P arena-variance validation, frozen sizing simulation and
  fail-closed selection of arena pairs;
- `prepare_contextual_outcome_supervision.py`: runner/science validation and
  non-training freeze-report writer;
- `run_contextual_outcome_supervision.py`: C0/C1 contracts and reporting;
- focused tests for leakage, replay/pool disjointness, power sizing, chained
  decision, gradient coupling and export parity.

The implementation must prove that an auxiliary loss changes at least one
exported scalar bucket weight while holding WDL batches fixed. This catches the
original no-gradient-path failure directly.

## Boundaries

- `promotable: false`;
- `production_jass_changes_authorized: false`;
- `direct_10x10_transfer_authorized: false`;
- no C0/C1 launch before the frozen M24-P and M18-P hashes, the completed M21-P
  result, a frozen replay-source decision and an M21-P-derived power-sizing PASS;
- any protocol change after C0 requires a new version and fresh evidence.
