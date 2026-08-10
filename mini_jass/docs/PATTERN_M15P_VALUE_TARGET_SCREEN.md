# M15-P — deployable value targets on PatternEval

Status: preregistered and implemented, not queued. No result from this cell has
been observed.

## Why this is the next reconstruction cell

M14-P established a small but precise train-label upper bound on the correct
architecture: exact labels improved development zero-regret by
`+0.0078318738` over terminal self-play WDL, with 95% interval
`[+0.0069308046, +0.0087329430]`. M21-P later rejected generation-history
mixing for strength and froze `G1_WIDE_OUTCOME` as the equal-volume replay
source for downstream factors.

The contextual C1/C2 experiment is closed with
`REJECTED_COMBINED_EFFECT_NONPOSITIVE`. C3 found that its handcrafted context
baseline was poorly calibrated on train, but it did not establish a playing
strength gain and cannot reopen that decision. M15-P therefore resumes the
baseline PatternEval reconstruction instead of tuning contextual coefficients.

## Question

Can an oracle-blind value target recover at least half of the exact-label
zero-regret gap while leaving the deployed architecture unchanged?

The deployed path remains:

```text
folded scalar PatternEval -> bounded search -> action
```

There is no policy head. All non-oracle arms use the same initial evaluator,
generated positions, actions, row order, batch indices and optimizer schedule.
Only the scalar value target consumed by `train_from_replay` differs.

## Replay and arms

For each of 20 fresh paired seeds (`271001` through `271020`), the shared
initial PatternEval generates one 1,024-game `G1_WIDE_OUTCOME` replay. Rows are
filtered to the immutable train cohort before any target is constructed.

| arm | training target | role |
|---|---|---|
| `OUTCOME` | terminal self-play WDL | honest baseline |
| `SEARCH_ROOT` | clipped bounded-negamax root score | mechanistic, non-oracle |
| `BLEND_50` | 50% outcome + 50% root score | sole primary candidate |
| `EXACT_ORACLE` | exact train-state value | diagnostic upper bound only |

The root score is already produced by the oracle-blind search that generated
the replay. Search-trace game/ply and state identities must match every consumed
row. The trace's best action and the replay's behavior action are both retained
but need not match: the frozen top-two behavior may deliberately play the
second-ranked move. A separate structure fingerprint excludes only
`value_target` and must be identical across all four arms. The ordinary replay
fingerprint is retained per arm so that the intended target difference remains
auditable.

`SEARCH_ROOT` cannot rescue a failed `BLEND_50` primary. This hierarchy is
frozen to avoid selecting the better of two deployable arms after observation.

## Primary decision

The primary endpoint is paired development `zero_regret_rate` gain:

```text
BLEND_50 - OUTCOME
```

The exact arm simultaneously re-estimates `EXACT_ORACLE - OUTCOME` on this
wider replay. The primary passes only if:

1. the exact gap has a paired Student 95% lower bound above zero;
2. the primary lower bound is above zero; and
3. the primary mean reaches
   `max(0.0039159369, 0.5 * within-cell exact gap mean)`.

The absolute floor is half of the already frozen M14-P effect, so an observed
small exact gap cannot lower the practical threshold after the run.

If the primary upper bound is below that required gain, M15-P fails and M16-P
temporal targets become the next prepared hypothesis. If the interval still
contains the threshold, the result is inconclusive and M15-P is replicated at
a power-sized fresh seed count. A pass authorizes only a fresh-seed strength
replication of `BLEND_50`; it does not promote a model.

Direct candidate-versus-`OUTCOME` common-search arenas from 128 shared
development starts are descriptive. They cannot overturn the registered
zero-regret decision.

## Power and runtime contract

The frozen simulation uses a conservative paired standard deviation of
`0.005`, larger than the M14-P paired standard deviation. At the absolute
minimum effect `0.0039159369`, 20 paired seeds give estimated power `0.91212`
for a Student 95% lower bound above zero (`100,000` simulations, seed
`44120260811`).

The job reports progress after every seed and retains per-seed audit rows.
There is no parallel shard, so the runner uses a cell timeout rather than a
shard timeout. The queue wrapper must still publish a measured cpx62 ETA,
disk guard and hard attempt cap before launch.

## Scientific boundaries

- train and development are the only cohorts this cell may read;
- the historical `frozen_test` read count is already one and M15-P authorizes
  zero additional reads;
- only `EXACT_ORACLE` may consume solved values as a training signal;
- sample generation, selection and every deployable target remain oracle-blind;
- every arm is non-promotable;
- no production Jass change or direct 10×10 transfer is authorized.
