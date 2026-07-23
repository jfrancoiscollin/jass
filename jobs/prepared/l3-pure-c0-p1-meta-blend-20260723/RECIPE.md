# L3-PURE C0/P1 meta-evaluation

This experiment creates no training data and performs no self-play for training.
It combines the immutable PJTW v3 weights of C0 A-G3 and P1-0842 G4 by convex
interpolation, preserving the common 8cf geometry and evaluating every arm with
the same fully pinned Q00 search fingerprint.

## Selection and confirmation

Four predeclared blends are screened at depth 8 with C0 weights 0.25, 0.50,
0.75 and 0.875. The selection rule maximizes the weaker of the two paired scores
against C0 and P1, then the mean score, on 128 fresh deterministic openings.

The selected blend is then evaluated on a disjoint 256-opening pool against each
parent under two primary views: Q00 depth 9 and Q00 0.3 seconds per move. All
opening pools are disjoint from DILF and from the earlier 0907 reinforcement pool.

`META_SUPERIOR_TO_BOTH` requires all four point estimates above 50%, and for each
parent the combined depth+movetime score must be at least 50.5% with the lower
95% confidence bound above 50%.

Promotion and automatic continuation are always forbidden.
