# CURRICULUM error learning: anchored local refit preregistration

This transition is legal only when two independent screens pass jointly:

1. the 600-pair fresh endgame-abstention confirmation;
2. the immutable-1508 five-fold stable-coefficient screen.

No out-of-sample label is inspected by this preregistration.  The confirmed
600-pair corpus becomes training-only after its terminal confirmation and can
never serve as the out-of-sample audit.

The CURRICULUM PatternEval model and engine remain byte-identical.  The full
`alpha=300` residual fit on immutable 1508 supplies the frozen feature means,
RMS values and base coefficient vector.  Only the signed support certified by
the stability screen may receive a delta.  Every other coefficient remains
bit-identical.  The single delta fit uses equal total weight for immutable
1508 and confirmed fresh non-endgame rows, a ridge penalty of 300 around zero,
a global support-delta norm cap of 20% of the base support norm, a per-weight
cap of 25%, and forbids sign flips.  There is no hyperparameter search.

Production remains symmetric and conservative: endgame and states outside the
fixed risk gate choose the exact CURRICULUM anchor; only non-endgame states
inside the gate may use the anchored residual with the already confirmed
`cap=100`, `strict_both_change`, 10 cp rule.

The later out-of-sample audit uses exactly 600 new pairs from two newly seeded
pools, with opening/game disjointness, target-free ordering, canonical
uniqueness and maximum two states per source game.  All gates are joint:

- incremental error-regret and paired 95% bootstrap lower bounds above zero;
- at least 20 changed error decisions, 12 changed control decisions and 32
  changed decisions in total relative to the confirmed baseline rule;
- positive incremental error and paired point estimates in both pools;
- incremental control mean at least -1 cp globally and in each pool;
- positive-realisation, calibration and symmetry guards;
- exact endgame/outside-gate decisions;
- exact PatternEval bytes, means/RMS and all coefficients outside support.

Only an OOS PASS may authorize two strength gates on fresh disjoint pools.
This preregistration itself performs no fit, target read, self-play, strength
game, frozen read or promotion and never continues automatically.
