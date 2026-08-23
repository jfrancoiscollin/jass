# CURRICULUM error learning: endgame-abstention confirmation

This job is permitted only after the target-free availability screen passes.
It consumes the frozen candidate order and reconstructs exact depth-12 action
values in batches until the first 600 valid error/control pairs are fixed.
Fresh labels never participate in a fit or in candidate ranking.

The real residual model is fit once on the immutable 1508 training population
with `alpha=300`. Its `cap=100`, `strict_both_change` and 10 cp threshold are
unchanged. One thousand shuffled-label fits are diagnostics only. For every
real and shuffled model, a production `endgame` phase forces the byte-identical
CURRICULUM action; every non-endgame decision is the unmodified frozen residual
decision.

The preregistered PASS requires all of the following jointly:

- exactly 600 pairs and at least 60 error, 40 control and 100 total
  interventions;
- at least 25 error and 18 control interventions in each pool;
- global error and paired 95% bootstrap lower bounds above zero;
- positive error and paired point estimates in both pools;
- control mean at least -2 cp globally and in both pools;
- error positive-realisation rate at least 60%, aligned symmetry at least 70%
  and symmetry drop at most two percentage points;
- exactly zero endgame interventions, anchor identity in endgame and residual
  identity outside endgame;
- the real paired mean above the q99 of the 1,000 stratified shuffled fits.

A PASS authorizes only a separate preregistration for the strongly anchored
local refit and its out-of-sample audit. PatternEval production fits, strength
games, frozen reads and promotion remain forbidden.
