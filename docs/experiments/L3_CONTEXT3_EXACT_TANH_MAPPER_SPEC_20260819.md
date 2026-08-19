# L3 CTX3 exact tanh mapper causal screen — preregistration

## Authorization

`cpx62-1416b-l3-context3-independent-information-screen-v1`, attempt
`20260819T070756Z-95059c8e`, passed all nine independent-information guards.
It authorizes an exact mapper screen, not a PatternEval fit.

## Immutable inputs

- corpus: 1409, exactly 2M positions;
- train/holdout split: the 1416b opening-disjoint split;
- selected CTX3 bank: read from the authenticated 1416b report and never
  reselected on holdout;
- five folds by `opening_id`, seed `20260811`;
- fold-local positive RMS and `game_equal` row weighting.

## Arms

1. `CTX2`: exact tanh-linear mapper on the original 30 dimensions;
2. `CTX3_ALIGNED`: exact tanh-linear mapper on CTX2 plus the 1416b-selected
   nonlinear antisymmetric directions;
3. `CTX3_FEATURE_SHUFFLED`: identical CTX3 mapper after permuting only the new
   directions within cohort × fold × tempo4 × material5.

Every arm has five OOF fits and one final-train fit. Convergence is mandatory.

## Gates

All conditions must pass:

- CTX3 aligned beats CTX2 with IC95 strictly above zero on train OOF;
- CTX3 aligned beats CTX2 with IC95 strictly above zero on holdout;
- CTX3 aligned beats feature-shuffled CTX3 with IC95 strictly above zero on
  train OOF;
- CTX3 aligned beats feature-shuffled CTX3 with IC95 strictly above zero on
  holdout;
- at least four of five OOF folds are positive for each primary contrast;
- all 18 mapper fits converge;
- the feature permutation has zero fixed points.

Intervals use 5,000 opening-cluster bootstrap replicates. A PASS authorizes
construction of paired aligned/shuffled target sidecars and PatternEval fits on
this same corpus. A FAIL closes this selected CTX3 mapper family. No self-play,
PatternEval, force game, frozen read, or promotion occurs in this screen.
