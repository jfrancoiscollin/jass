# JFI v1 — positive-lambda convergence amendment

Date: 2026-09-02
Status: **FROZEN BEFORE ANY JFI-A/B HOLDOUT READOUT**
Parent preregistration: `L3_JASS_NATIVE_IDENTIFIABILITY_ACTIVE_LEARNING_V1_20260901.md`

## Triggering observation

The canonical recovery run

```text
cpx62-1750-l3-jfi-factorial-l2-fit-v1
attempt 20260902T072254Z-25bb488e
science code 25bb488e19bb4bf6e7d696294defaf083142f927
```

completed all seven physical optimizer runs but stopped at the sealed convergence verifier before `jfi_fit_readout.py` ran. Read-only diagnostics 1751/1752 established:

```text
A       : converged, nit=791,  grad_inf=9.193565157611444e-05
B       : converged, nit=1723, grad_inf=7.531230035407657e-05
C       : converged, nit=1038, grad_inf=9.593100920931436e-05
D=1e-5 : converged, nit=1416, grad_inf=7.453395510355985e-05
L2=0    : max_iter=2000, grad_inf=2.100706724469531e-03 (diagnostic-only)
L2=1e-6 : max_iter=2000, grad_inf=7.859293474997341e-04 (NOT converged)
L2=1e-4 : converged, nit=497,  grad_inf=8.611817233364673e-05
```

The failing `1e-6` arm stopped because the frozen iteration ceiling was reached, not because of a system/runtime crash and not because of an alternate SciPy success criterion. No JFI-A/B readout artifact, selected lambda, identifiability result, force result, or scientific verdict was published.

## One-time frozen repair

The scientific convergence target is **unchanged**:

```text
lbfgs_gtol = 1e-4
lbfgs_maxcor = 20
loss / data / split / targets / initialization / ridge centres / lambdas unchanged
```

Only the non-selective optimizer safety ceiling is amended:

```text
strictly positive lambda arms: max_iter = 6000
lambda = 0 diagnostic arm:     max_iter = 2000
```

The 6000 ceiling applies uniformly to A, B, C, D (`1e-5`), `1e-6`, and `1e-4`. It is not selected from holdout CE or strength. Arms that reach `gtol` terminate normally before the ceiling. The unregularized `lambda=0` arm remains diagnostic-only and is not required to converge.

If **any strictly positive lambda arm** still fails the original `gtol=1e-4` convergence contract by 6000 iterations, JFI-A/B stops. There is no second ceiling increase, no lambda deletion, no replacement grid point, and no post-hoc optimizer retuning in JFI v1.

## Re-execution rule

Because the failed 1750 run did not preserve the fitted PJTW/raw-weight state before the convergence guard, the seven physical fits must be replayed from the same frozen inputs under this amendment. The replay must also checkpoint all seven PJTW models and the four A/B/C/D raw-weight arrays into immutable artifacts immediately after fitting and before convergence/readout checks. This checkpointing is technical-only and does not alter model bytes.

## Guards

Unchanged:

```text
SCAN_WEIGHT_READS = 0
SCAN_SCORE_READS = 0
SCAN_TARGET_READS = 0
FRESH_OPENINGS = 0
STRENGTH_GAMES = 0
PROMOTION_AUTHORIZED = FALSE
```

No new model search, feature, L2 point, data selection rule, target, seed, force pool, or promotion rule is introduced by this amendment.
