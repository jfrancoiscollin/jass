# CTX2 Curriculum alpha=0.30 A/B/C

Date: 2026-08-17

## Motivation

The full Curriculum relabel experiment at CTX2 alpha=1 lost heavily to the
Curriculum champion in both registered strength views. The root-cause audit
showed that this did not falsify CTX2:

- CTX2 pure teacher holdout MSE was lower than CTX1 on both CURRENT_2M and
  MEGA_FULL_4M;
- CTX2 kept the correct black-POV sign;
- the counterfactual CTX2 alpha=0.30 target improved target MSE slightly;
- alpha=1 discarded the 70% terminal component, inflated target error by about
  10.7x, and shrank final model RMS by 32.7%.

The failed experiment therefore tested a different supervision regime, not a
strict replacement of CTX1 by a better conditional teacher.

## Pre-registered arms

- **A — Curriculum CTX1 alpha=0.30**: byte-reuse the certified champion from
  cpx62-1341; no refit.
- **B — Curriculum CTX2 alpha=0.30 aligned**: fit MEGA_FULL_4M from L2LOW, then
  fit CURRENT_2M from the B mega prior.
- **C — Curriculum CTX2 alpha=0.30 shuffled**: the same two-stage recipe, but
  shuffle the pure CTX2 prediction within train/holdout, opening fold,
  terminal-WDL, and four tempo-phase bins before the alpha=0.30 blend.

All student fits keep the champion architecture and optimizer recipe:
8cf exact-fold tempo, 120 extras, logistic loss, L2=1e-5, prior decay zero,
L-BFGS maxcor 20, gtol 1e-4, and at most 2000 iterations.

## Teacher reuse

The certified alpha=1 sidecars from cpx62-1384 are pure black-POV CTX2
probabilities. Reusing them is mathematically exact for recomposition:

    target = 0.70 * terminal_probability + 0.30 * pure_CTX2_probability

Their reports, corpus hashes, folds, weighting, convergence, and sidecar hashes
are authenticated before use. The CURRENT_2M recomposition is also compared
numerically with the original alpha=0.30 sidecars from home-1373.

## Guards

- no teacher refit;
- no refit of A;
- no new self-play and no frozen cohort;
- aligned and shuffled target standard deviations must each remain within 5%
  of the certified CTX1 alpha=0.30 target;
- final B and C model RMS must each remain within 20% of Curriculum;
- all four student fits must converge and consume the certified target hashes.

## Decision sequence

The fit job produces models only.

1. Primary causal gate: B-C, native 0.1 s, on two fresh disjoint opening pools.
2. Q00 depth 9 is diagnostic.
3. Only if B-C is established positive, test B-A against Curriculum.
4. No automatic promotion.

This hierarchy distinguishes “CTX2 alignment adds information” from “the new
recipe beats the current champion”.
