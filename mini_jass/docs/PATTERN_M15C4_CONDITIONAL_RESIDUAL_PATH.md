# M15-C4 — separate conditional residual path

Status: preregistered and implemented; probe and full run are not queued by
this PR.

## Frozen question

M15-C3 established that both conditional and temporal information remain live,
but its convex target average could not preserve both incremental signals at
once. M15-C4 asks whether the interference comes from forcing both signals
through one optimisation path.

The experiment keeps `LAMBDA_50` whole and adds only the conditional correction
relative to terminal WDL:

```text
ADDITIVE_30 = clip(LAMBDA_50 + 0.30*(conditional_prediction - OUTCOME), -1, 1)
```

This differs from the closed M15-C3 formula
`0.70*LAMBDA_50 + 0.30*conditional_prediction`, which diluted the temporal
target by construction.

## Seven-arm paired design

Seeds `277001` through `277024` are fresh. Every seed shares one 1,024-game
replay, initial zero `PatternEval`, explicit batch schedule and 512-pair
development-start arena across:

| arm | target and optimisation path |
|---|---|
| `OUTCOME` | terminal WDL, direct 2,048-step fit |
| `LAMBDA_50` | temporal return, direct 2,048-step fit |
| `CONTEXT_30` | retained `0.70*OUTCOME + 0.30*context`, direct fit |
| `SHUFFLED_ADDITIVE_30` | additive formula with within-fold shuffled context, direct fit |
| `ADDITIVE_30` | aligned additive formula, direct fit |
| `SHUFFLED_RESIDUAL_30` | 1,024-step temporal base plus 1,024-step shuffled residual |
| `RESIDUAL_30` | 1,024-step temporal base plus 1,024-step aligned residual |

The aligned and shuffled residual arms share the exact frozen temporal base.
Only a zero-initialised residual table is updated in stage two. Direct and
residual versions consume identical value targets and have the same effective
2,048 optimiser updates; the factor under test is the allocation of those
updates to a separate path.

## No inference architecture change

`PatternEval` is linear before its final `tanh`. After training, the temporal
and residual table weights and biases are added. The arena sees one ordinary
`folded_pattern_value` model with the same parameter count, no sidecar and no
policy head. Every seed checks the collapsed model against the two-path value
on every L1 state with maximum absolute tolerance `1e-7`.

## Primary causal gate

All four paired Student 95% lower bounds must exceed zero:

1. static `RESIDUAL_30 - ADDITIVE_30`;
2. strength `RESIDUAL_30 - ADDITIVE_30`;
3. static `RESIDUAL_30 - SHUFFLED_RESIDUAL_30`;
4. strength `RESIDUAL_30 - SHUFFLED_RESIDUAL_30`.

The first pair attributes any gain to the separate optimisation path while
holding the final target fixed. The second attributes it to aligned
conditional information under that path. The direct additive control and both
single-signal arms are descriptive and cannot rescue a failed primary. There
is no decision effect floor; the power effects are sizing inputs only.

Even after a primary pass, `RESIDUAL_30` replaces incumbent `CONTEXT_30` only
if it beats `CONTEXT_30`, `LAMBDA_50` and `OUTCOME` in both static response and
paired strength. Otherwise `CONTEXT_30` remains retained.

## Power, probe and boundaries

Twenty-four paired seeds provide at least 83.6% simulated one-axis power on
each primary interval under the frozen conservative deviations. Probe seed
`277000` is timing-only and cannot publish scientific metrics.

M15-C4 reads train and development only. It authorises no additional
`frozen_test` read, automatic promotion, production change or direct 10x10
transfer. Queueing the cpx62 probe requires a separate post-sizing human GO.
