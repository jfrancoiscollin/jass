# Contextual outcome supervision v2

## Status

Design/preregistration for Mini-Jass L1 on the architecture merged as
`folded_pattern_value`: exact side-aware folded pattern buckets, one scalar
value and moves supplied by search.

This protocol is not runnable until M24-P
`cpx62-1217-mini-jass-pattern-m24p-v1` has returned `PASS` and its result hash
has been frozen into the implementation config. No production Jass change or
direct 10x10 transfer is authorized.

## Question

Terminal W/D/L is the game truth, but copying it unchanged onto every state is
a low-bandwidth credit signal. A draw saved from a losing position and a draw
thrown away from a winning position both receive `0`.

The experiment asks whether deterministic board context can improve the
learned scalar evaluator while the main target remains terminal WDL and while
the deployed model remains exactly `scalar PatternEval -> search`.

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

## C0: preregistered protocol-validity gate

C0 may read exact values only on the `train` cohort. It does not choose among
models or remove individual arms. It applies the decision frozen here:

- deterministic repeats must be byte-identical;
- POV symmetry maximum absolute error must be `0`;
- terminal exactness must be `1.0`;
- Spearman correlation of `B(C)` with exact value must be at least `0.10`;
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

The paired seeds are fixed to `270501..270520` (inclusive). Each seed uses the
four paired arena starts from `configs/l1_pattern_reconstruction_loop.yaml`,
with both candidate colours and identical search settings. The single
confirmatory contrast is:

```text
WDL_PLUS_FULL_CONTEXT minus WDL_ONLY
```

The primary endpoint is paired common-search arena score minus `0.5`. PASS
requires the lower bound of a paired-seed Student-t 95% confidence interval to
be strictly greater than zero. The three single-channel arms are mechanistic
and exploratory; they cannot independently support a multiplicity-unadjusted
PASS claim.

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
already fixed. After every C1 checkpoint, replay hash, export proof and protocol
hash are frozen, `frozen_test` is read once for WDL_ONLY and
WDL_PLUS_FULL_CONTEXT together. It is descriptive and cannot select a model.

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

C2 opens only after a C1 confirmatory PASS. It repeats the full-vs-WDL contrast
on fresh seeds before interpreting the single-channel diagnostics. C3 may then
compare the frozen handcrafted baseline with a train-only fitted baseline; it
is a new experiment and cannot reuse C1's sealed test read.

Potential-based reward shaping is outside C0-C3. Feeding `DeltaC`, `Rctx` or
context scores back into behavior would change the replay distribution and
requires a separate preregistration.

## Required implementation objects

- `context.py`: exact feature definitions and POV/symmetry tests;
- `context_targets.py`: delta, baseline and residual construction;
- `context_scaffold.py`: shared rank-10 training scaffold and exact scalar
  export;
- `run_contextual_outcome_supervision.py`: C0/C1 contracts and reporting;
- focused tests for leakage, replay identity, gradient coupling and export
  parity.

The implementation must prove that an auxiliary loss changes at least one
exported scalar bucket weight while holding WDL batches fixed. This catches the
original no-gradient-path failure directly.

## Boundaries

- `promotable: false`;
- `production_jass_changes_authorized: false`;
- `direct_10x10_transfer_authorized: false`;
- no C1 launch before a frozen M24-P PASS result hash;
- any protocol change after C0 requires a new version and fresh evidence.
