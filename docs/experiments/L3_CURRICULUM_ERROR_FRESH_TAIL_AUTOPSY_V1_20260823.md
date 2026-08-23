# CURRICULUM error residual: fresh catastrophic-tail autopsy

## Scientific status

The powered fresh confirmation in experiment 1517 is terminally negative for
the frozen residual rule (`alpha=300`, `cap=100 cp`, strict both-image change,
`threshold=10 cp`).  It produced 37 error interventions with a 67.6% positive
realisation rate, yet the mean over all error pairs was `-93.804 cp` and the
paired error-minus-control effect was `-353.568 cp`.  The control arm itself
gained `+259.764 cp`.  This is not an underpowered pass: a harmful lower tail
dominates a majority of individually positive interventions.

The tested residual rule is closed.  The 1517 population is discovery-only
from this point forward and can never be reused as validation.

## Read-only autopsy

The autopsy authenticates the immutable 1508 training atlas, the complete 1517
terminal and exact 300-pair atlas, and the independent 1517a final audit.  It
then performs exactly one diagnostic ridge fit on 1508.  No fresh row is used
by the fit.  The frozen 1517 decision rule is replayed, and cardinalities,
intervention counts, means, positive realisation rate, and bit-identical
abstentions must reproduce the certified terminal before any description is
published.

For each intervention, the report records:

1. realised and predicted advantage, distance above the frozen intervention
   threshold, anchor margins and image agreement;
2. phase, material, ply, branching, capture status, pool, opening and game;
3. raw and clipped correction deltas;
4. an exact additive decomposition over all 21 trajectory features and six
   feature families; and
5. fixed lower-tail quantiles, CVaR, catastrophic-event counts and loss-mass
   concentration.

The fixed descriptive risk factors are: predicted advantage below `20 cp`,
guard margin below `5 cp`, correction clipping, original/image anchor
disagreement, proposed capture, and proxy above `110 cp`.  A factor is called
*descriptively pool-stable* only when it has at least 12 error interventions,
at least four inside and outside observations in each pool, is at least
`200 cp` worse than its complement in each pool, and contains at least half of
the negative loss mass.  These conditions are diagnostics, not a production
gate and not a multiple-testing corrected confirmation.

Because phase was not one of those fixed binary risk factors, any phase rule is
explicitly post-hoc.  The report nevertheless publishes full phase and
pool-by-phase slices for both errors and controls, plus the exact symmetric
counterfactual that replaces every endgame intervention by the unmodified
CURRICULUM anchor.  This calculation may motivate a new preregistration; it is
not evidence that validates the phase rule.

## Fail-closed continuation

The job computes no new exact target, fits no fresh label or PatternEval model,
plays no self-play or strength game, reads no frozen cohort and promotes
nothing.  It never authorizes a refit or strength gate.

If no predeclared factor is pool-stable, this residual route remains closed.
If one is stable, the only permissible next step is a separate preregistration
that freezes one risk-aware abstention rule, followed by confirmation on two
entirely new, mutually disjoint pools.  Neither 1517 nor any historical sealed
holdout may be opened to validate that new rule.
