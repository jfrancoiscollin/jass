# M21-P — generation composition on PatternEval

## Why this cell is next

M17-P2R established compounding on the architecture that can be transferred to
production: folded, side-aware, scalar `PatternEval` followed by search. M18-P
then decomposed the static development response. It found a large
`G1_WIDE - G1_ONLY` zero-regret gain, but no practical `MIX - G1_WIDE` static
gain and no sequential-optimizer gain.

That does not settle playing strength. Historical M21 found that static oracle
response and arena strength can move differently, but that evidence came from
the retired MLP/policy-head laboratory. M21-P reconstructs the strength question
without importing that incompatible evidence.

## Frozen question

Does an outcome-labelled mixture of generations G1 through G8 produce a
stronger scalar PatternEval than an equal-size outcome-labelled pool generated
entirely by the initial model?

The primary contrast is:

```text
MIX_OUTCOME - G1_WIDE_OUTCOME
```

Both arms contain exactly the same number of unique replay rows, use the same
initial PatternEval, consume the same batch-index schedule, and play the same
paired development starts and colours against that initial model. The primary
endpoint is the paired common-search arena-score difference across 20 fresh
seeds. Development zero-regret and value-sign differences are diagnostic and
cannot override the arena.

The cell passes only when the mean arena gain is at least `+0.05` and the lower
Student-t 95% bound is strictly above zero. It fails only when the upper bound
excludes `+0.05`; otherwise it is explicitly inconclusive.

## Controls

- `G1_WIDE_OUTCOME - G1_ONLY_OUTCOME`: unique sample volume;
- `G8_ONLY_OUTCOME - G1_ONLY_OUTCOME`: recency;
- `MIX_OUTCOME - G1_ONLY_OUTCOME`: historical combined contrast;
- `G1_PLUS_NOVEL_LATE_OUTCOME - G1_ONLY_OUTCOME`: late novelty;
- `G1_PLUS_NOVEL_LATE_OUTCOME - G1_PLUS_MATCHED_LATE_OUTCOME`: novelty versus
  observable material/side/mobility reweighting.

All training targets are terminal self-play outcomes. Oracle values are read
only to compute development diagnostics. `frozen_test` stays sealed.

## Evidence boundaries

The protocol pins M17-P2R result
`c868949d2f1027889e6e76fd081e763aedcac7840f6105e1f18175e5c66685ea`
and M18-P result
`2680f52319b7be31c5cb6d44c229b78c545eb21b4dc4c8be2e3f17c125da5554`.
No result is promotable and no direct 10×10 transfer is authorized. A positive
first pool requires a fresh-seed replication before any transfer decision.

Draft PR #441 remains a later label-objective factor. Its contextual scaffold
must not be introduced into M21-P because that would change both replay
composition and training objective in the same causal cell.
