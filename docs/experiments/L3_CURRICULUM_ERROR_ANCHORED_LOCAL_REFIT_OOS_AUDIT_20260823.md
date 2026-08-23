# CURRICULUM anchored local refit: sealed OOS audit

The anchored model is compared with the already confirmed `alpha=300`,
`cap=100`, strict 10 cp endgame-abstention baseline on exactly the same 600
new pairs.  These pairs come from two new 300-pair pools and are disjoint by
opening and source game from all discovery, confirmation and fit populations.
Their order is frozen before any depth-12 target is reconstructed.

This is an incremental audit: every regret value is `anchored - baseline` on
the same state.  PASS requires jointly:

- at least 20 changed error decisions, 12 changed control decisions and 32
  changed decisions in total;
- combined error-regret and paired error-minus-control bootstrap 95% lower
  bounds strictly above zero;
- positive error and paired point estimates in both pools;
- incremental control mean at least -1 cp globally and in both pools;
- at least 60% positive realization on anchored error interventions;
- absolute calibration bias no more than 2 cp worse than baseline;
- aligned symmetry at least 70% and symmetry drop at most two points;
- exact CURRICULUM decisions in endgame and outside the fixed risk gate;
- byte-identical PatternEval SHA-256 and bit-identical coefficients outside
  the certified support.

The audit performs no fit or strength game.  Only a joint PASS authorizes a
separate two-pool strength-gate preregistration.  Promotion remains forbidden.
