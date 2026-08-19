# L3 CTX3 paired PatternEval fit — conditional preregistration

This stage is launched only if `cpx62-1417` passes every exact-tanh mapper
guard. It does not alter or regenerate the 1409 corpus.

## Targets

The certified aligned CTX3 prediction is OOF on train and final-train-only on
holdout. With `alpha = 0.30`:

```text
aligned = 0.70 * terminal_WDL + 0.30 * CTX3_prediction
```

The shuffled arm uses the same prediction values after a deterministic
permutation inside cohort × opening-fold × terminal-WDL × tempo4. Therefore
the target distribution is exactly preserved inside every causal stratum while
fine state/context alignment is destroyed. Zero fixed points are mandatory.

## PatternEval fits

Exactly two arms are fitted on the same 2M rows:

- `ALIGNED`;
- `SHUFFLED`.

They share the Curriculum parent, 8cf exact-fold tempo architecture, features,
split, holdout, optimizer, regularization, weighting and iteration budget. The
target sidecar is the only difference. Both fits must converge and publish
their model, target-consumption and optimizer hashes.

This stage produces models but plays no games. Its primary downstream contrast
is aligned versus shuffled on two fresh disjoint opening pools, native primary
and Q00 diagnostic. No frozen read or automatic promotion is authorized.
