# M15-C — direct conditional information in the PatternEval target

Status: preregistered and implemented, not queued. This protocol was frozen
without reading or depending on the M15-P result.

## Why this is a new experiment

C1/C2 injected context through auxiliary heads during training, then discarded
those heads when exporting the scalar `PatternEval`. Their frozen negative
decision therefore rejects that auxiliary route, not every possible use of
context. C3 subsequently established that the frozen context vector contains a
material train-only conditional signal, and that the handcrafted coefficients
were poorly calibrated.

M15-C tests the narrower, unresolved hypothesis directly: does putting an
out-of-fold estimate of conditional WDL into `ReplaySample.value_target`
improve the scalar evaluator? The deployed architecture remains unchanged:

```text
folded scalar PatternEval -> bounded search -> action
```

No context head survives training. Context changes the teacher target itself,
so every gradient applied to the model's only scalar output carries the tested
information.

## The causal control

Comparing only a conditional blend with raw outcome would confound conditional
information with generic target shrinkage. A global mean controls that broad
effect but does not match the conditional target's marginal distribution.
M15-C therefore adds a stricter within-fold permutation control: it preserves
the exact conditional-prediction multiset while breaking state alignment.

| arm | target | role |
|---|---|---|
| `OUTCOME` | terminal WDL | honest baseline |
| `GLOBAL_BLEND_50` | 50% WDL + 50% out-of-fold global mean | matched state-blind shrinkage |
| `SHUFFLED_CONTEXT_BLEND_50` | 50% WDL + 50% within-fold permuted conditional WDL | marginal-matched causal control |
| `CONTEXT_BLEND_50` | 50% WDL + 50% out-of-fold conditional WDL | primary candidate |
| `CONTEXT_ONLY` | out-of-fold conditional WDL | mechanistic diagnostic |

All five arms receive the same replay rows, policies/actions, initialization,
row order, explicit batch-index schedule, optimizer and number of updates.
Only `value_target` differs. A structure fingerprint that excludes
`value_target` must be identical across arms.

## Cross-fitting without trajectory leakage

For each of 20 fresh paired seeds (`272001` through `272020`), the shared
initial PatternEval generates one 1,024-game `G1_WIDE_OUTCOME` replay. All rows
are restricted to the immutable train cohort.

Complete games, never individual positions, are assigned to five deterministic
folds. For each held-out fold:

1. fit `tanh(context @ theta)` from zero initialization;
2. use only terminal WDL labels from the other four folds;
3. predict every row of the held-out games;
4. compute the state-blind control from the same four-fold training rows.

Within each held-out fold, conditional predictions are then put in a stable
hash order and rotated by one row. No row keeps its own prediction, no value
crosses a fold, and the fold's complete prediction multiset is unchanged. This
creates `SHUFFLED_CONTEXT_BLEND_50` without changing the smoothing term's mean,
variance or range. Its covariance with the row's state and outcome is the
factor deliberately destroyed by the control.

Thus the conditional prediction for a position never comes from a fit that saw
that game's outcome or another position in its trajectory. It uses no exact
oracle value, C3 exact-value coefficient, manual coefficient or development
label. The exact oracle is read only for train/development response diagnostics,
as in the reconstruction program, and never constructs a training target.

The fit also reports out-of-fold WDL MSE against the matched state-blind
control. This is a mechanism sanity check; it cannot rescue the primary
learning result.

## Frozen decision

The primary endpoint is paired development `zero_regret_rate` gain. A `PASS`
is conjunctive:

1. `CONTEXT_BLEND_50 - SHUFFLED_CONTEXT_BLEND_50` has a Student 95% lower
   bound above zero, attributing the gain to correct state-context alignment
   rather than the conditional prediction distribution or generic smoothing;
2. `CONTEXT_BLEND_50 - OUTCOME` has a Student 95% lower bound above zero; and
3. its mean reaches `+0.003915936905813988`, half the frozen M14-P exact-label
   response.

`CONTEXT_BLEND_50 - GLOBAL_BLEND_50` remains a secondary attribution check. If
the shuffled attribution upper bound is non-positive, or the operational upper bound
is below the practical threshold, the linear conditional-target hypothesis
fails. Otherwise the cell is inconclusive and requires a power-sized fresh
replication. `CONTEXT_ONLY`, target-to-oracle diagnostics and 128-pair common-
search arenas are descriptive and cannot rescue the gate.

A pass authorizes only a fresh-seed strength replication of
`CONTEXT_BLEND_50`. It does not select or promote a model.

## Power and independence

With conservative paired standard deviation `0.005`, 20 seeds give simulated
power `0.91149` for a 95% lower bound above zero when either conjunctive
contrast has the practical effect (`100,000` draws, seed `44120260812`). A
smaller attribution effect can therefore yield `INCONCLUSIVE`, never a false
pass. The seeds and random offsets are disjoint from C1/C2 and M15-P.

The protocol records `scientific_dependency_on_m15p_result: none`. It was
prepared while `cpx62-1237-mini-jass-pattern-m15p-v1` was running, without
reading a result from that job. Its validity and decision rule therefore do not
change with M15-P's outcome. Execution order remains a human roadmap decision.

## Scientific boundaries

- train and development are the only readable cohorts;
- the historical `frozen_test` read count remains one; zero further reads are
  authorized;
- every training target and replay-generation decision is oracle-blind;
- no automatic promotion, production Jass change or direct 10×10 transfer is
  authorized;
- this PR prepares the runner but creates no queue job.
