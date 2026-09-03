# JFI optimizer path-dependence autopsy v1

Date: 2026-09-03
Status: PREREGISTRATION. User authorized this new scientific diagnostic with `Go` after terminal JFI-A.

## 1. Frozen upstream

Terminal readout:

- job `cpx62-1758-l3-jfi-1755-readout-publish-v2`
- attempt `20260903T141716Z-6fa708d0`
- source fit `cpx62-1755-l3-jfi-factorial-l2-fit-v1`
- source attempt `20260902T201244Z-6fa708d0`
- JFI fit code `6fa708d0a293c8b39178d7202657a6875aa7cbed`
- verdict `JFI_OPTIMIZER_PATH_DEPENDENCE_DETECTED`
- all seven fit checkpoints are immutable in R2.

No fit, refit, retune, new target, new opening, strength game, Scan read or promotion is authorized by this autopsy.

## 2. Why this autopsy is required

For the two same-centre contrasts, the preregistered score-equivalence criteria are already far inside their limits, while the operational objective-difference criterion is the failing term:

- A vs B, CURRICULUM ridge centre: holdout score RMS `0.0206583850833467 cp` vs limit `0.5 cp`; serialized max abs `0.20173333333333332 cp` vs limit `2 cp`; objective abs difference `5.152022177545845e-06` vs operational limit `1e-6`.
- C vs D, zero ridge centre: holdout score RMS `0.022152334898782634 cp` vs limit `0.5 cp`; serialized max abs `0.2813333333333361 cp` vs limit `2 cp`; objective abs difference `3.6387122326897448e-06` vs operational limit `1e-6`.

The trainer objective with positive L2 is logistic loss plus a positive quadratic penalty. For a fixed design, fixed ridge centre and fixed trainable support this objective is convex. Therefore the autopsy must first distinguish a materially different production solution from an objective-tolerance / numerical-stopping artefact; it must not assume a mysterious non-convex basin.

## 3. Stage P1 — immutable gate-forensics readout

Read only the published 1758 JSON and optimizer receipts. For A/B and C/D publish, without changing any threshold:

- which of the three original path-independence criteria passed/failed;
- margin to each original threshold;
- optimizer `success`, `status`, iterations, `gradient_inf_norm`, `gtol`, `maxcor`, max iterations;
- objective difference divided by the frozen `1e-6` operational limit;
- score RMS divided by `0.5 cp` and max-abs divided by `2 cp`;
- exact model/raw-weight hashes and checkpoint count.

Classification is descriptive, not a replacement JFI-A verdict:

- `JFI_PATH_AUTOPSY_OBJECTIVE_ONLY_TRIGGER` iff both same-centre pairs pass both original score criteria and fail only the objective criterion;
- `JFI_PATH_AUTOPSY_MATERIAL_SCORE_PATH_EFFECT` iff either same-centre pair violates either original score criterion;
- `JFI_PATH_AUTOPSY_MIXED_TRIGGER` otherwise.

P1 performs zero model scoring and zero target read beyond the already-published 1758 summary.

## 4. Stage P2 — no-refit production-score decomposition

P2 is authorized only if P1 returns `OBJECTIVE_ONLY_TRIGGER`.

Reuse exactly the consumed CURRENT_2M / Context30 setup and the immutable A/B/C/D checkpoints. Reconstruct the exact historical CURRENT split and exact production feature dump. No optimizer call is permitted.

For A/B and C/D:

1. score all frozen rows with the two immutable serialized PJTW endpoints;
2. recompute train/holdout CE and verify the endpoint metrics reproduce 1755/1758 within absolute `1e-10` for CE and `1e-9 cp` for reported score RMS; otherwise technical STOP;
3. evaluate the score-space interpolation at `t = {0, 0.25, 0.5, 0.75, 1}` using linearity of the fixed PatternEval score, then compute Context30 CE at every t;
4. publish whether the data-loss curve is convex up to absolute numerical slack `1e-12` against linear interpolation of neighbouring evaluated points;
5. publish endpoint score delta RMS/max-abs on TRAIN and HOLDOUT separately and quantiles p50/p90/p99/p99.9/max of absolute score delta;
6. publish disagreement counts for score delta thresholds `{0.1, 0.5, 1, 2, 5} cp`;
7. publish parameter-displacement summaries already defined by JFI-A and reproduce their hashes.

P2 is deliberately production-score focused. It does not redefine the optimizer objective and does not infer a new optimum.

## 5. Stage P3 — stopping-tolerance diagnosis

P3 is authorized only if P2 reproduces endpoints and both same-centre score paths remain below the original JFI-A materiality limits.

Use only existing optimizer receipts plus read-only evaluations. Publish:

- final objective and gradient infinity norm for each endpoint;
- objective-gap / `gtol` diagnostics as descriptive quantities only;
- the fact that `gtol` is a gradient stopping criterion and the frozen `1e-6` objective-pair threshold is not mathematically implied by `gtol=1e-4`;
- whether each endpoint independently satisfied the frozen convergence contract (`success=true`, status 0, gradient <= gtol).

Terminal autopsy verdicts:

- `JFI_PATH_DEPENDENCE_MATERIAL_SCORE_EFFECT_CONFIRMED` if an original score materiality limit is violated on exact replay;
- `JFI_PATH_DEPENDENCE_OBJECTIVE_TOLERANCE_ONLY` if exact replay reproduces, both same-centre pairs remain within both original score limits, all four endpoint optimizers satisfy the frozen convergence contract, and the only original JFI-A trigger is the `1e-6` objective-pair threshold;
- `JFI_PATH_DEPENDENCE_AUTOPSY_TECHNICAL_INCONCLUSIVE` on replay/hash/environment mismatch;
- `JFI_PATH_DEPENDENCE_AUTOPSY_MIXED` otherwise.

## 6. Boundary after autopsy

This diagnostic does **not** silently rewrite JFI-A and does **not** launch JFI-C/ACTIVE.

If terminal verdict is `JFI_PATH_DEPENDENCE_OBJECTIVE_TOLERANCE_ONLY`, publish `NEXT_BOUNDARY__GO_JFI_PATH_AMENDMENT`. A separate explicit scientific amendment is then required before treating JFI-A as path-independent or resuming ACTIVE.

Any other scientific terminal verdict remains STOP.

## 7. Absolute guards

For every autopsy job:

`FULL_FITS=0` new fits, `REFITS=0`, `FRESH_OPENINGS=0`, `STRENGTH_GAMES=0`, `SCAN_WEIGHT_READS=0`, `SCAN_SCORE_READS=0`, `SCAN_TARGET_READS=0`, `PROMOTION_AUTHORIZED=FALSE`.
