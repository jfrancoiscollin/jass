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

M21-P `cpx62-1223-mini-jass-pattern-m21p-v1` completed with `FAIL`: the unique
`MIX_OUTCOME - G1_WIDE_OUTCOME` common-search effect was `-0.00107421875`, with
a 95% interval spanning zero. Its frozen result hash is
`2a376c7215212777e466fe41c7bf30a1af1d700f706ee7ca882c0fe2b3ac2745`.
The preregistered rule therefore selects the equal-volume
`G1_WIDE_OUTCOME` replay source for every non-oracle arm.

Readout `cpx62-1224-mini-jass-m21p-freeze-readout-v1` independently fetched
and verified that result, then froze 64 arena pairs per seed. Its report hash
is `db870aec453cf8876191b1624edd13045be50cf589aca33184d6175f67bae86c`.
That upstream report carried `c0_or_training_authorized: false`, as required
before the separate C0 gate ran.

C0 `cpx62-1225b-mini-jass-contextual-c0-v2` then completed `PASS` on `cpx62`
with attempt `20260810T092246Z-fe188c93`. The train-only baseline reached
Spearman `0.4012712056139121` and exact all-pairs ordering rate
`0.7111186846747267`; repeatability, POV symmetry and terminal exactness all
passed. The scalar export matched common-search actions on all `248961`
playable oracle states, with maximum value error
`1.4901161193847656e-08`. The frozen C0 report hash is
`ca0c9cb3d9f99ed9984947fe046e85b7f060ad49d10948e892d608bc99ad19f4`.
The report explicitly records `sealed_test_read: false` and
`c1_training_authorized: true`.

C1 was therefore scientifically authorized. Its first pinned execution,
`cpx62-1226-mini-jass-contextual-c1-v1`, completed 17 of 20 seed rows before
aborting on the per-checkpoint scalar-export proof. Read-only diagnosis
`cpx62-1227-mini-jass-contextual-c1-failure-readout-v1` established that no
scientific summary was published and that the failure was a float32 evaluation
order mismatch: the live scaffold summed embeddings before projection while
the exported `PatternEval` projected buckets before summation. Values remained
within the registered tolerance, but a near-tied child pair changed one action.

The corrected implementation evaluates the live scalar branch in exactly the
same floating-point order as its export and regression-tests bit-exact value
parity on the failing seed. The scientific protocol, replay, targets, weights, seeds,
arena and decision rule were unchanged. The fresh execution
`cpx62-1228-mini-jass-contextual-c1-v2` completed all 20 seeds from scratch.
Its registered arena contrast is exactly `0.0`, with 95% interval
`[-0.0018756744119172272, 0.0018756744119172272]`, so its provisional status is
`PROVISIONAL_NO_SIGNAL_REQUIRES_C2`. The registered FULL-minus-WDL development
MAE contrast is `+0.0032687276601791383`, also in the wrong direction.

Independent readout `cpx62-1229-mini-jass-contextual-c1-freeze-readout-v1`
verified the R2 inventory, result/protocol hashes, all 20 replay manifests,
both globally allocated start manifests, pairing and export proofs. It returned
`PASS_C1_FREEZE_C2_AUTHORIZED`, report hash
`1d0c02385103d6bdd31e9d070e468c450ecbf0e4a763d7ea19fff9d0c5dc192c`.
C2 is now authorized and remains mandatory. The sealed cohort is still unread;
no production Jass change or direct 10x10 transfer is authorized.

C2 `cpx62-1230-mini-jass-contextual-c2-v1` then completed all 20 fresh seeds
with exit code zero. Its FULL-minus-WDL arena mean is `-0.0009765625`, with
95% interval `[-0.002840477081808143, 0.0008873520818081428]`. Chaining C1 and
C2 gives posterior mean `-0.0004913522012578616`, 95% interval
`[-0.0017294481116230448, 0.0007467437091073216]` and
`P(score_delta > 0) = 0.21832934032972762`. The pools are compatible
(`z = 0.772971071081939`), so the frozen decision is
`REJECTED_COMBINED_EFFECT_NONPOSITIVE`, not an inconclusive heterogeneity case.
The combined value-MAE delta is also adverse (`+0.003090641609070154`) with
`P(delta < 0) = 2.0462767617133767e-48`; the registered interpretation is
therefore `neither`.

Independent readout `cpx62-1231-mini-jass-contextual-c2-freeze-readout-v1`
recomputed both full-result hashes, all 40 replay manifests, hard disjointness,
pool statistics, posterior probabilities and both heterogeneity guards without
importing the PR implementation. It returned
`PASS_C2_FREEZE_CHAINED_DECISION_FROZEN`, report hash
`b9cd48bf1469aa53765a3cf8fee5419b83ad772a3c42972b6c39d29f51a306eb`.
The single descriptive `frozen_test` read is now authorized; it cannot reopen
the decision or select a model.

That unique read, `cpx62-1232-mini-jass-contextual-sealed-read-v1`, completed
successfully on all 39,688 frozen states and all 20 paired seeds. The registered
common-search FULL-minus-WDL contrast is `+0.000390625`, with 95% interval
`[-0.0010501078533483965, 0.0018313578533483968]`: no robust playing-strength
effect. The all-state response diagnostics are consistently adverse for FULL:
value MAE `+0.00286865234375`, sign accuracy `-0.0022336726466438083`, selected
regret `+0.0020337261818862114`, and optimal-top1/zero-regret rate
`-0.001178545658622615`. The run records `sealed_test_read_count: 1`, performed
no training or selection, and leaves the frozen decision unchanged as
`REJECTED_COMBINED_EFFECT_NONPOSITIVE`. Its result hash is
`bcacf5dca4ea2509da91ab3c0aceaea5de057a3197b3b31599a2d36e91d3783c`.

This remains a later factor in the PatternEval reconstruction program. A merge
of this design never queues C1 automatically and cannot displace M21-P or its
decision record.

V3 changes only the upstream evidence contract. V2 incorrectly sized from the
failed M17-P promotion cell's static zero-regret variance. V3 instead consumes
the architecture-correct M21-P paired common-search contrast, the endpoint that
C1 itself will use. No C0 evidence has been read, so this preregistration repair
does not condition on contextual results.

The v3 preparation tool is executable but deliberately non-training. It
recomputed the scientific hash, validated all 20 per-seed arena deltas, applied
the replay-source rule, ran the frozen power simulation and wrote a
round-tripped freeze report. The source, pair count and report hash above are
now pinned in the configuration; the report's
`c0_or_training_authorized: false` remains binding.

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

For L1, men and kings are divided by the two-piece-per-side bound, legal moves
by the exhaustive maximum `8`, and capture options by the exhaustive maximum
`4`. Promotion pressure is summed normalized progress toward the promotion row
and divided by two; an advanced man has progressed strictly beyond the middle
row. Blocked men have no empty forward quiet destination. The central mask is
the five playable squares `[3, 4, 6, 8, 9]`. The complete definition is frozen
as `c036cdc3677d094fd9bfaf46e0042ee6c43b60ba2816219deecfb52d1b395e03`.

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

Pairwise ordering is computed exactly over every train-state pair with unequal
exact values; a baseline tie counts as one half. The implementation uses
sorted rank counts, so it obtains the all-pairs statistic without materializing
the quadratic pair table. This deterministic estimator is included in the
protocol hash.

If any threshold fails, the result is
`ABORT_C1_AND_REVISE_PREREGISTRATION`. C1 does not run, no coefficient changes,
and no residual/full arm is silently downgraded to exploratory. A revised
baseline requires a new schema/version and fresh C0 evidence.

The same run also instantiates the rank-10 scaffold deterministically, exports
it to scalar PatternEval, and compares both value and one-ply common-search
actions on every oracle state. Maximum value error must be at most `1e-6` and
the action match rate exactly `1.0`; otherwise the same fail-closed result is
issued. This proof reads rule state/transition data, not sealed exact labels.

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

The frozen M21-P standard deviation is `0.004319942195275082`; the conservative
floor therefore sets the random-effect standard deviation to `0.10`. Estimated
powers for 64, 128 and 256 pairs per seed are respectively `0.88898`,
`0.94967` and `0.97226`, so the registered smallest qualifying size is 64.

## C1 pairing

The complete replay pack is generated once and frozen before any arm trains.
Every non-oracle arm must prove:

- identical replay fingerprint, sample IDs and terminal WDL values;
- identical exportable-value initial-state hash;
- identical rank-10 scaffold initialization schedule;
- identical batch indices and order;
- identical optimizer hyperparameters and step count;
- identical common-search arena starts, colours and seeds.

The executable realization records the behavior action on every replay row;
the transition target is reconstructed from that action and the rule child
table, never guessed from the policy target. For each paired seed, one fresh
1024-game generation-1 `G1_WIDE_OUTCOME` pack is generated by the scalar export
of the shared initial scaffold. Every generated row whose pre-move state is in
`train` is retained, hashed and then reused byte-for-byte by all deployable
arms. All arms consume the same explicit 1024-by-128 batch-index matrix.

Train starts and development arena starts are SHA-256-ranked into immutable
manifests before training. Allocation is global across the registered C1 and
C2 seed lists: no reserved start state can occur in two pool/seed rows. Each
arena row contains exactly 64 unique non-terminal development starts; because
the list length equals the pair count, every start is consumed exactly once
per arm with both colours. C2's rows are reserved but not read or played by the
C1 runner.

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
The frozen estimator treats each pool's paired mean as normal with its plug-in
paired standard error (`sd(ddof=1) / sqrt(20)`). Starting from an improper flat
prior, C1 then C2 are combined by the algebraically equivalent inverse-variance
normal update. A zero-SE pool is an exact point mass. Strict-threshold
probabilities use the normal survival function; this definition is frozen
before any C2 data exist.
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

### C3 diagnostic contract

C3 is now specified as a five-fold, canonical-grouped cross-validation over
non-terminal `train` states only. Raw colour/rotation views of one canonical
state always remain in the same fold. It compares three mappings from the same
nine frozen context features to exact train-only value:

- the original handcrafted `baseline_v1`;
- an odd, no-intercept tanh-linear mapping fitted by deterministic weighted
  Gauss-Newton with fixed ridge and optimizer controls;
- a fold-trained exact-context conditional-mean lookup, used only to reveal a
  possible nonlinear mapping gap.

The diagnostic reports out-of-fold MAE, RMSE, Spearman and exact pairwise
ordering. A mapping gap requires both at least `+0.02` Spearman and `0.01` MAE
reduction versus the handcrafted baseline. Linear success is reported as
`LINEAR_CALIBRATION_GAP_OBSERVED`; lookup-only success as
`NONLINEAR_MAPPING_GAP_OBSERVED`; otherwise the result is
`NO_MATERIAL_TRAIN_ONLY_CONTEXT_GAIN`.

C3 reads neither `development` nor `frozen_test`, does not train any C1/C2 arm,
cannot reopen their rejection, and cannot select, promote or transfer a model.
Its protocol hash is
`1ec2f8e510137714fc95635b11c7ae98400d1ba9ccf0efa2ac37bc0ae20769da`.

C3 `cpx62-1235-mini-jass-contextual-c3-v2` completed on 174,201 non-terminal
train states (144,275 canonical classes). The handcrafted baseline obtained
Spearman `0.40687870785203495`, MAE `0.8216837965714316` and pairwise ordering
`0.7234129771095114`. The canonical-grouped out-of-fold tanh-linear fit reached
Spearman `0.5728855160076164`, MAE `0.661842558653182` and ordering
`0.8168700340403888`: gains of `+0.16600680815558144` Spearman and
`0.15984123791824967` MAE reduction. The context lookup reached Spearman
`0.7331005017886004` and MAE `0.3764197387335693`.

The preregistered interpretation is therefore
`LINEAR_CALIBRATION_GAP_OBSERVED`: the handcrafted coefficients were a material
source of misspecification, and the frozen context vector also supports useful
nonlinear structure on train. This does **not** rescue the tested auxiliary,
whose C1/C2 and sealed playing-strength decision remains rejected. A follow-up
using the fitted baseline would be a new experiment and requires a new untouched
evaluation cohort; the consumed `frozen_test` cannot be reused.

Readout `cpx62-1236-mini-jass-contextual-c3-freeze-readout-v1` independently
verified the R2 inventory, result/protocol content hashes, metric deltas,
five-fold accounting and interpretation rule. It returned
`PASS_C3_FREEZE_DIAGNOSTIC_FROZEN`, report hash
`3c4c795ce336b535c3c9d0ef98d99cd0c967719805848e6002914ad254f47cd4`.

The scope of the negative result is now explicit. C1/C2 tested auxiliary
context heads whose outputs were discarded at scalar export; they did not test
injecting a cross-fitted conditional estimate directly into the scalar WDL
target. M15-C preregisters that distinct mechanism with a within-fold,
marginal-matched shuffled-context control. It does not reopen or reinterpret the frozen C1/C2 decision,
reuse `frozen_test`, or import C3's exact-value fitted coefficients. See
[`PATTERN_M15C_CONDITIONAL_TARGET_SCREEN.md`](PATTERN_M15C_CONDITIONAL_TARGET_SCREEN.md).

Potential-based reward shaping is outside C0-C3. Feeding `DeltaC`, `Rctx` or
context scores back into behavior would change the replay distribution and
requires a separate preregistration.

## Implementation boundary

- implemented here: `context.py`, `context_targets.py`,
  `context_scaffold.py`, `context_power.py`, the non-training M21-P preparation
  tool, the fail-closed C0-only runner, `context_replay.py`,
  `context_training.py`, the C1-only runner, the C2-only runner, the frozen
  sequential decision estimator and the single descriptive sealed-read runner;
- implemented tests: rule equivalence, POV/symmetry, leakage rejection, exact
  rank metrics, deterministic scaffold initialization, gradient coupling and
  scalar export parity, transition identity, replay/start manifests, paired
  schedules and auxiliary-to-export coupling;
- completed and independently frozen for C1: the selected `G1_WIDE_OUTCOME`
  generator, all five deployable arms, direct-table descriptive control,
  global C1/C2 start reservation, provisional reporting and per-checkpoint
  full-oracle export proofs;
- completed and independently frozen for C2: fresh pool-B execution, all 40
  replay-manifest disjointness checks and the chained force/mechanism decision;
- completed sealed confirmation: both arms and all 20 paired seeds were read
  together exactly once; no training, decision reopening, model selection or
  promotion occurred. The result does not alter the already frozen rejection.
- prepared C3 diagnostic: canonical-grouped train-only calibration and mapping
  checks, now completed and independently frozen with explicit zero reads of
  development and frozen test.

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
