# JFI path-independence amendment v1

Date: 2026-09-03
Authorization: explicit user `GO JFI PATH AMENDMENT` / `Va y` after terminal P3 autopsy.
Status: frozen amendment before any JFI-C ACTIVE target read or new fit.

## 1. Evidence that authorizes this amendment

Frozen sources:

- JFI-A/B fit: `cpx62-1755-l3-jfi-factorial-l2-fit-v1`, attempt `20260902T201244Z-6fa708d0`.
- recovered readout: `cpx62-1758-l3-jfi-1755-readout-publish-v2`, attempt `20260903T141716Z-6fa708d0`.
- P1: `cpx62-1759-l3-jfi-path-autopsy-p1-v1`, verdict `JFI_PATH_AUTOPSY_OBJECTIVE_ONLY_TRIGGER`.
- P2: `cpx62-1760-l3-jfi-path-autopsy-p2-v1`, verdict `JFI_PATH_AUTOPSY_P2_READY_FOR_P3`.
- P3: `cpx62-1761-l3-jfi-path-autopsy-p3-v1`, attempt `20260903T160856Z-648d1e4e`, verdict `JFI_PATH_DEPENDENCE_OBJECTIVE_TOLERANCE_ONLY`.

P3 established all of the following on exact replay:

1. A/B and C/D remain within the original production-score materiality limits (`holdout_score_rms <= 0.5 cp`, `serialized_score_max_abs <= 2 cp`).
2. A/B/C/D independently satisfy the frozen optimizer convergence contract: `success=true`, `status=0`, `gradient_inf_norm <= gtol=1e-4`.
3. the only original JFI-A trigger was the independently frozen cross-endpoint objective-difference threshold `<=1e-6`.
4. `gtol=1e-4` is a gradient stopping criterion and does not mathematically imply that two independently converged endpoint objectives differ by `<=1e-6`.

No model, target, opening, Scan result or strength result is introduced by this amendment.

## 2. Amended JFI-A path-independence gate

For the two same-centre pairs only:

- A vs B at CURRICULUM ridge centre;
- C vs D at zero ridge centre.

A pair is path-independent iff BOTH production-score criteria pass:

```text
holdout_score_rms <= 0.5 cp
serialized_score_max_abs <= 2 cp
```

AND both endpoint optimizers independently satisfy:

```text
success = true
status = 0
gradient_inf_norm <= gtol
```

The cross-endpoint `objective_abs_difference` remains published as a diagnostic but is **not a gate**.

No numerical threshold is loosened or replaced post hoc: the two production-score thresholds are exactly the original JFI-A materiality thresholds, and optimizer convergence is exactly the frozen per-arm convergence contract already applied before readout.

## 3. Consequence for the frozen 1755 fits

A dedicated read-only amendment receipt must authenticate P3 and the frozen JFI-B L2 selection, then may issue:

```text
JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED
```

without rerunning any of the seven fits.

The frozen JFI-B one-standard-error selection remains unchanged. Exact selected value:

```text
lambda = 1e-5
```

No new lambda, fit or model selection is authorized.

## 4. JFI-B identifiability continuation

After the amendment receipt passes, run only the already-preregistered JFI-B identifiability computation on:

- exact consumed CURRENT_2M / Context30 setup;
- exact zero-init + zero-centre `D` checkpoint from 1755;
- selected `lambda=1e-5`;
- exact historical split seed `577215`;
- exact-fold / tempo-stage design.

This stage performs no optimization.

Required outputs remain the original JFI-B outputs: Fisher/curvature diagonal, visit counts, gradient/ridge diagnostics, `UNSEEN / PRIOR_DOMINATED / MIXED / DATA_DOMINATED`, effective degrees of freedom, posterior-variance proxy and family summaries.

If source hashes/replay/design mismatch, STOP technical. If identifiability completes, publish `NEXT_BOUNDARY__GO_JFI_ACTIVE`.

## 5. JFI-C ACTIVE automatic objective

The user has explicitly requested automatic continuation through JFI-C ACTIVE.

After JFI-B identifiability is complete, JFI-C may run exactly as frozen in `L3_JASS_NATIVE_IDENTIFIABILITY_ACTIVE_LEARNING_V1_20260901.md`:

- frozen 10,000,000-row Jass-only candidate universe;
- `ACTIVE_2M` vs disjoint matched `UNIFORM_2M`;
- target-blind selection before Context30 target reconstruction;
- selected lambda `1e-5`;
- ZERO init / ZERO L2 centre;
- identical 2M volume and joint strata;
- bootstrap seed `2026120104`, 100000 opening-cluster replicates;
- PASS iff `CI95_high(CE_ACTIVE - CE_UNIFORM) < 0` and at least one preregistered information diagnostic improves.

Allowed automatic actions: implementation, CI, merge, CPX62 jobs, mechanical repairs/requeues, and exact preregistered stage progression.

Automatic objective STOPS at terminal JFI-C verdict:

```text
JFI_ACTIVE_INFORMATION_GAIN_ESTABLISHED
or
JFI_ACTIVE_INFORMATION_GAIN_NOT_ESTABLISHED
```

JFI-D candidate construction and JFI-E FORCE are outside this automatic objective and require the next explicit continuation.

## 6. Absolute guards

Throughout amendment + JFI-B identifiability:

```text
NEW_FITS=0
REFITS=0
FRESH_OPENINGS=0
STRENGTH_GAMES=0
SCAN_WEIGHT_READS=0
SCAN_SCORE_READS=0
SCAN_TARGET_READS=0
PROMOTION_AUTHORIZED=FALSE
```

JFI-C may perform only its two preregistered ACTIVE/UNIFORM fits after target-blind manifests are frozen. No Scan, no retuning, no alternative selector, no extra lambda, no force, no promotion.