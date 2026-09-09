# ED4-P0 — synthetic choice-set preflight completed

Date: 2026-09-09. Terminal: **`ED4_CHOICE_SET_OBJECTIVE_PREFLIGHT_COMPLETE_V1`**.
Classification: `SYNTHETIC_TECHNICAL_ONLY`. This is technical preparation,
with no real fit, candidate or scientific decision-quality result.

## Prospective identity and publication

[Protocol](L3_ED4_CHOICE_SET_PREFLIGHT_V1_20260909.md) frozen in
`92531f728c596092e92113651d3ea26bc6f3ed8a`; implementation and 16 literal native
records frozen in `9fc97e8cf07c73435f7b16b9f2bea08144f39da8`, before tests.
The connected GitHub app published the workflow as
`0c3f3729dca52c4fa536404b11b50b4e2192096d`; identical workflow content was
verified locally before opening [PR #884](https://github.com/jfrancoiscollin/jass/pull/884).

[CI 34342663391](https://github.com/jfrancoiscollin/jass/actions/runs/34342663391)
checked out that exact head, built the unchanged C++ evaluator, and completed
successfully at 10:54:44 UTC. The full preflight took 2.520 seconds, excluding
dependency installation/build, with one-CPU affinity and one-thread numeric
libraries. Nine contract tests passed locally and in CI; they invoked no actual
optimizer. The complete CI preflight invoked the fixed optimizer exactly twice.

Artifact `10100400102`, ZIP SHA256
`7857a81a291c653dc6d41a96cd0261b712bc4cc39972cb26748b439a2684812c`, was downloaded
and authenticated against the GitHub artifact digest. Its manifest authenticates
report SHA256 `a74ba30d888fe7fd6437327a55c2db1b2cdf665cbc12be37993f556bc617400d`.
All seven reported source hashes match the immutable Git blobs.
[Full authenticated receipt](receipts/ed4-p0-34342663391-readback.json).

## Observed synthetic checks

The fixed seed-910 fixture has 24 parents, 96 sibling rows, 192 replay rows and
240 coordinates. Both zero-initialized solves gave byte-identical vectors and
identical reports, with 13 iterations each. No parameter was changed after freeze.

| Check | Observed | Frozen requirement |
| --- | ---: | ---: |
| Initial objective | 1.2361819706299166 | reference at zero |
| Final objective | 0.6233682262555197 | no worse than initial + 1e-12 |
| Gradient L2 norm | 7.767141045280521e-7 | <= 1e-6 |
| Minimum Hessian eigenvalue | 0.0009228207471059007 | >= -1e-8 |
| Hessian asymmetry at solution | 1.9895196601282805e-13 | <= 1e-10 |
| Quantized objective | 0.6238940797087539 | no worse than initial + 1e-12 |
| Native maximum logit error | 4.440892098500626e-16 | <= 1e-9 |

The seven prescribed central-difference gradient and Hessian checks passed.
Unsupported/all-terminal cases, extreme logits, edge direction, parent sign,
invalid inputs and missing-native refusal also passed. The analytic saddle had
zero gradient and minimum curvature -0.06410416666666668; the gate rejected a
mocked optimizer success there, as required, with zero extra optimizer calls.

Native checks used the ordinary 4,251,528-pattern / 120-extra PJTW v3 layout,
synthetic zero weights, and a nonzero synthetic residual changing 238 extras.
Header/pattern bytes were preserved; scale-1000 ties-to-even, feature order,
linear reconstruction and integer-score identity passed. Two separate processes
reloaded the quantized fixture after the baseline process. These development-only
fixture models were not published as candidates.

## Scope and next boundary

This objective can be nonconvex. The accepted point is only an approximate
second-order stationary point on the specified trajectory; no global optimum,
general convergence guarantee, calibration improvement or better decisions are
established by this synthetic result.

Ledger for this receipt: **2 synthetic optimizer invocations**, 0 real fits,
real-data/model reads, real candidates, searches, games, control-queue mutations,
promotions or bakes. Each ordinary CI rerun produces and counts its own receipt;
it is not another scientific experiment or an authorization to fit real data.

Next: `REVIEW_AND_PREREGISTER_ED4_CANDIDATE`. A real candidate fit needs its
separate authorized stage and complete launch rehearsal. A future confirmation
needs a fresh, disjoint, target-blind preregistration with decision and independent
WDL gates before target reads. `automatic_continuation=false`,
`runtime_authorized=false`; **`STOP_ED3`** and **`CURRICULUM`** remain unchanged.

Route: Sol for the scientific contract, Terra for implementation and review.
