# CURRICULUM error residual stable-subspace screen

This is a training-only, read-only screen over the immutable 1508 gate-fit
population and its already materialized exact action values.  It consumes no
fresh confirmation label and computes no new exact target.

The residual regularization is frozen at `alpha=300`, independently of the
fresh 1523/1524 results.  Five component-safe opening/game folds and one full
fit are reconstructed with fold-local RMS.  A coefficient belongs to the
candidate mutable subspace only when all of these pre-registered conditions
hold:

1. its sign is non-zero and identical in all five fold fits and the full fit;
2. it is among the six largest absolute coefficients in at least four folds;
3. it is among the six largest absolute coefficients in the full fit;
4. its coefficient-of-variation in absolute fold coefficient is at most 0.75.

The whole screen additionally requires a minimum pairwise coefficient cosine
of 0.75, a minimum pairwise top-six Jaccard of 0.40, five non-empty folds and
between two and eight selected features.  The signed support is published with
a canonical SHA-256.

A pass establishes only a candidate subspace.  It does not authorize a refit,
production use, strength games or promotion.  A separately pre-registered
anchored refit may be prepared only after an independent fresh confirmation
passes.  That later refit must preserve the CURRICULUM PatternEval bytes,
freeze every residual coefficient outside this support, and remain exactly
identical outside the pre-registered endgame eligibility rule.

Forbidden actions in this screen: feature-audit or outer-confirm reads, fresh
targets, PatternEval or production fits, self-play, strength games, frozen
reads, promotion and automatic continuation.
