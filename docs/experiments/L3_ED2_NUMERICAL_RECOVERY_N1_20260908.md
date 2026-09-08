# ED2-N1 — numerical recovery with exact TRAIN reuse

2026-09-08. Current explicit mandate: « Va y diag répare relance ».
This is an explicit numerical optimizer amendment, NOT a silent change to the
frozen ED2-P1 recipe. Original preregistration and failed attempt remain intact.
No label/data/feature/model-selection amendment and no threshold relaxation.

## Authenticated diagnosis

1876 / 20260908T182614Z-27c30b3f / code
27c30b3f5b4bc4ee971bb4acfcf0a423e124f7da failed with exit 2. Diagnostic
1877 / 20260908T185207Z-e7b9320a authenticated _FAILED, full inventory/checksums
and the pipeline log. The exact failure is:

    optimizer did not converge: STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT

The last phase is fit-point. No POINT/PARTIAL model, model seal or TEST result
was published. The source log SHA256 is
833fb7cf36eae30d4aa9e0efa20531cf75363e0e1a53114856ceecc1f9c8eecc.
The failed POINT optimizer invocation is historical and is not counted as a
successful fit. We do not claim to have measured its Hessian conditioning or
otherwise established the deeper reason it needed more than 500 iterations.

TRAIN completed: 9,952 label rows / 9,944 actual searches, 273,460,000 requested
Scan nodes, 37.85717358501279 seconds of teacher batch wall time. PARTIAL has
477 supported parents, 17,622 edges and 0.6886808047772325 mean coverage;
POINT has 24,276 edges. All existing support gates pass. This is not evidence
of improved evaluation. TEST remains untouched.

## Numerical change, prospectively frozen before the resumed fits

Original optimizer was float64 L-BFGS-B, maxiter=500, maxcor=10, gtol=1e-6,
ftol=1e-12, maxls=30. It is NOT rerun with a looser convergence gate or a larger
iteration budget. The N1 pair uses scipy `trust-exact` and the analytical
240-by-240 Hessian, same zero initialization and maxiter=500. Fixed settings:

    gtol=1e-6, initial_trust_radius=1.0, max_trust_radius=1000.0, eta=0.15

Both arms use this same solver; one invocation each, no restarts, sweep or
checkpoint choice. The original objective and analytical gradient functions are
called directly. Only the Hessian computation and optimizer are different.
No feature normalization/reparameterization, ridge change or change in WDL/pair
weights. L2 remains 0.001, both loss coefficients remain 1, parent normalizer
remains 512. The exact original data, comparisons, architecture and BASE apply.

The Hessian is the sum of nonnegative logistic weighted outer products plus
0.001 I. Thus the mathematical objective is strongly convex with a unique
minimizer. Every returned candidate additionally requires finite values,
optimizer success AND norm2(original gradient)<=1e-6. This implies the original
infinity-norm gradient threshold too; there is no objective-value early stopping.
Record ||g||^2/(2*0.001), the strong-convexity upper bound on the mathematical
objective gap (subject to floating-point numerical accuracy). This certifies
optimization, NOT generalization, native decision quality or Elo.

Official solver reference: scipy.optimize.minimize(method='trust-exact'),
https://docs.scipy.org/doc/scipy/reference/optimize.minimize-trustexact.html .

## Recovery contract and information boundary

Require the exact failed 1876 identity, log failure, recipe, complete 8-shard
TRAIN hashes, original source seal and absence of any prior model/TEST artifacts
in its full inventory. No partial harvest. Source seal remains
31f763049fef50544bd1cbb240eeb4f51670728ae0697a77e982186df007152c.
Reauthenticate completed READY P0 1875, its exact 512 TRAIN / 256 TEST / 16
calibration parents, benchmark/cross-parent exclusions and spending gates.

Reproduce the historical WDL subset selection and native BASE train/replay
tables exactly; compare hashes/content to the authenticated 1876 artifacts.
Reconstruct pair support from the reused labels and require exact equality.
Copy the eight sealed teacher files byte-for-byte. New TRAIN searches=0;
273,460,000 requested training nodes are reused rather than recomputed.
There is no fallback that regenerates TRAIN on a failed reuse check.

The existing controller handles both fits, quantization, native PJTW reload,
model sealing, first TEST200k calls and readout unchanged. Its isolated process
is explicitly wired to the N1 fit and TRAIN reuse adapters. The old source files
are not edited. TEST workers remain the original scorer; TEST labels are first
produced only after both quantized artifacts have been sealed. Holdout targets
are accessed only afterward. No numerical choice uses TEST or holdout metrics.

## Unchanged scientific acceptance and bounded execution

Retain every ED2-P1 gate: two positive lower 95% regret-improvement bounds
(PARTIAL against BASE and POINT); no lower top-hit; harmed<=improved against
BASE; historical WDL logloss upper 95% delta<=0.002 and Brier delta<=0.002.
Same parent/phase/STM and opening-cluster bootstraps, 20,000 draws and seeds.
Same post-quantization native decisions. Same 240 existing extras, frozen PJTW
header/pattern bytes and WDL_CONTROL hash; CURRICULUM remains champion.

Terminal verdicts are separately versioned by replacing the ED2_ prefix with
ED2_N1_, including ED2_N1_PARTIAL_ORDER_VALUE_SIGNAL_V1 and
ED2_N1_PARTIAL_ORDER_VALUE_NOT_SUPPORTED_V1. Numerical failure still fails
closed, not a scientific negative. No automatic next run on success or failure.

Same 300-second cap per fit, 2700-second overall stage, eight single-thread
Scan TEST workers, original measured batch cap and 30-second RPC caps. At most
486,800,000 NEW requested Scan nodes (2434 TEST children x 200k; rule-terminal
children cost zero). No new calibration, TRAIN search, Jass search, Elo,
self-play, promotion or bake. These are spending/time limits, not ETAs.
Signal-safe process-tree cleanup and narrow source/build publication cleanup
are inherited from the already tested ED2 entrypoint/finalizer.

## Validation

Eleven new local tests pass: objective/gradient identity, finite-difference
Hessian, positive ridge curvature under rank deficiency, actual 240-coordinate
synthetic solve with original-gradient certificate, nonfinite refusal, failed
identity gates, full-inventory model/TEST exclusion, seal/recipe corruption,
unexpected failure rejection and exact TRAIN/native/WDL reuse without search.
The local objective reference is a verbatim excerpt of the authenticated original
function, not a locally cloned repository. Dedicated CI repeats against the full
repository and builds/runs the unchanged native artifact tests before queueing.
Python compile checks pass. No actual failed-corpus refit was run while selecting
this fixed numerical recovery; no TEST values have been inspected.
