# M15-C3 — conditional and temporal target composition

Status: preregistered and implemented; not queued by this PR.

## Frozen question

Does the retained 30% conditional signal remain causal when its WDL base is
replaced by the positive M16-P temporal return, and does that temporal return
add static and playing-strength value on top of the independently replicated
conditional target?

M15-C3 is not another dose search. Alpha 30% is frozen by M15-C2R. Lambda 0.50
is frozen by M16-P. Neither component may be retuned from these fresh results.

## Six-arm paired design

Seeds `276001` through `276024` are fresh. Each seed generates a single
1,024-game `G1_WIDE_OUTCOME` replay and shares retained rows, initialization,
batch schedule and arena starts across all arms:

| arm | target |
|---|---|
| `OUTCOME` | terminal WDL |
| `LAMBDA_50` | M16-P complete-trajectory temporal return |
| `SHUFFLED_CONTEXT_30` | `0.70*OUTCOME + 0.30*shuffled_context` |
| `CONTEXT_30` | `0.70*OUTCOME + 0.30*aligned_context` |
| `SHUFFLED_COMPOSED_30` | `0.70*LAMBDA_50 + 0.30*shuffled_context` |
| `COMPOSED_30` | `0.70*LAMBDA_50 + 0.30*aligned_context` |

Conditional predictions remain five-fold, complete-game-held-out estimates of
terminal WDL. Their shuffled controls preserve fold marginals. Temporal returns
are constructed over complete contiguous generated trajectories before the
train-cohort filter. Every deployable target is oracle-blind and bounded in
`[-1, 1]` by convex construction.

## Primary composition gate

The primary passes only when paired Student 95% lower bounds are above zero on
all four axes:

1. static `COMPOSED_30 - CONTEXT_30`;
2. strength `COMPOSED_30 - CONTEXT_30`;
3. static `COMPOSED_30 - SHUFFLED_COMPOSED_30`;
4. strength `COMPOSED_30 - SHUFFLED_COMPOSED_30`.

The first pair asks whether temporal information adds value under the retained
conditional target. The second pair asks whether aligned conditional
information remains causal under the temporal base. There is no effect-size
floor: power effects are sizing inputs only.

Fresh singleton contrasts, the matched shuffled temporal increment, operational
gain over OUTCOME and the difference-in-differences interaction are reported
but cannot rescue a failed primary.

## Retention rule

Even after a primary pass, `COMPOSED_30` replaces incumbent `CONTEXT_30` only
if it also beats `LAMBDA_50` and `OUTCOME` directly in both static response and
strength.
Otherwise the incumbent remains frozen. No result automatically promotes a
model or changes production Jass.

## Power and boundaries

Twenty-four paired seeds give at least 80% simulated one-axis power for each
of the four primary intervals under conservative preregistered standard
deviations. All six arms receive 512 paired common-start arenas per seed.

The probe seed `276000` is timing-only and cannot publish scientific metrics.
M15-C3 reads train and development only. It authorizes no additional
`frozen_test` read, automatic promotion or direct 10x10 transfer.
