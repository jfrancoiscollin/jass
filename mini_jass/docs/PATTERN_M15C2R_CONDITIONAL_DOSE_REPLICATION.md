# M15-C2R — independent conditional-dose replication

Status: **PASS — alpha 0.30 independently replicated and retained.**

## Frozen question

Does the aligned 30% conditional target independently replicate both its
development zero-regret gain and its paired strength gain on 20 fresh seeds?
If it does, does the discovery lead at 40% independently beat 30% on both
static response and strength?

M15-C2R preserves the completed M15-C2 result and hash. It does not reinterpret
the discovery seeds and cannot use the 40% arm to rescue a failed 30% primary.

## Arms and fresh evidence

Seeds `275001` through `275020` are disjoint from M15-C2 and M16-P. Every seed
generates one new 1,024-game `G1_WIDE_OUTCOME` replay. Five arms share retained
rows, initialization, batch schedule and update count:

| arm | role |
|---|---|
| `OUTCOME` | honest WDL baseline |
| `SHUFFLED_CONTEXT_30` | marginal-matched causal control for 30% |
| `CONTEXT_30` | sole primary replication |
| `SHUFFLED_CONTEXT_40` | marginal-matched causal control for 40% |
| `CONTEXT_40` | preregistered secondary dose |

The five-fold complete-game conditional model and within-fold permutation are
unchanged in method but receive new namespaces. No oracle value enters a
training target.

## Primary replication gate

Alpha 30% replicates only if the paired Student 95% lower bounds are strictly
above zero for all four contrasts:

1. static `CONTEXT_30 - SHUFFLED_CONTEXT_30`;
2. static `CONTEXT_30 - OUTCOME`;
3. strength `CONTEXT_30 - SHUFFLED_CONTEXT_30`;
4. strength `CONTEXT_30 - OUTCOME`.

There is no positive effect-size floor. An interval crossing zero is
inconclusive; an upper bound at or below zero is a failure to replicate.

## Secondary 40% rule

The 40% arm cannot rescue the primary. It can replace 30% as the retained dose
only after 30% passes and only if:

- its own static and strength attribution and operational intervals are all
  strictly positive;
- direct paired `CONTEXT_40 - CONTEXT_30` intervals are strictly positive for
  both development zero-regret and strength.

Otherwise 30% remains the retained dose. The direct static discovery contrast
was `+0.00128545`, 95% CI `[+0.00101161, +0.00155929]`, positive on 20/20
M15-C2 seeds. With a conservative paired SD of `0.001`, 20 fresh seeds provide
`84.42%` simulated power for a `+0.0007` effect. This is sizing only, not a
decision floor.

## Strength and boundaries

All five arms play 512 paired common-start arenas against the same OUTCOME
model and reuse identical development starts within a seed. No new
`frozen_test` read, automatic promotion, production change or direct 10×10
transfer is authorized. A positive result selects only the dose for a later
controlled composition experiment.

## Result

M15-C2R completed as `cpx62-1242-mini-jass-pattern-m15c2r-v1`, attempt
`20260811T063640Z-c7d2e378`. Alpha 30 passed all four primary intervals:

- static attribution `+0.00637905`, 95% CI
  `[+0.00562358, +0.00713451]`;
- static operational `+0.00289494`,
  `[+0.00239577, +0.00339412]`;
- strength attribution `+0.00153809`,
  `[+0.00043769, +0.00263848]`;
- strength operational `+0.00205078`,
  `[+0.00101385, +0.00308772]`.

Alpha 40 passed its own controls and beat 30 in static response by
`+0.00150639` (`[+0.00114956, +0.00186321]`), but its direct strength advantage
was only `+0.00009766` (`[-0.00041922, +0.00061453]`). It therefore cannot
replace alpha 30. Result hash:
`d240e5c006b9e7463221bbae4e639d80dbc8773840c2310b64ed9df1bd45ae25`.

The retained decision is to compose alpha 30 with M16-P `LAMBDA_50` under the
separate M15-C3 preregistration. No model is promoted by this result.
