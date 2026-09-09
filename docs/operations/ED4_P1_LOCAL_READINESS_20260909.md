# ED4-P1 — local readiness, before CI and target-host admission

Date: 2026-09-09. Scope: the autonomous campaign and the ED4 real fit are
preregistered in commit `94b3b4a1a`; the initial implementation is recorded in
`cdfacd068`. No real TRAIN/replay values or production model were read, no real
fit was executed, and no CPX/control job was queued during this preparation.

The campaign requires four gates before scale-up review: valid native candidate,
fresh static decisions, independent fresh WDL outcomes, and transfer inside
equal-node search. Adaptive attempts consume prospectively allocated alpha;
failed confirmations cannot become new holdouts. ED3 remains closed.

## Implemented path

The ED4 entrypoint authenticates the four exact source roles, verifies TRAIN
ownership and the sealed replay indices, maps sparse global rows into local
feature order, and checks native BASE parity before fitting. It performs one
fixed solve, checks the actual quantized residual against the original objective,
reloads the native candidate twice on TRAIN and replay, and seals it only after
all checks. Production also requires the authenticated rehearsal and exact
numeric report, float64 beta and PJTW identity. HARD and SOFT are metadata-only
controls in this stage.

Identical-input derivative caching and one logit computation per derivative call
preserve the P0 formula bit for bit on the frozen fixture. No coefficient,
optimizer setting, threshold, feature, seed or scientific gate changed.

## Completed local validation

Linux runtime: Python **3.14.4**, NumPy **2.5.2**, SciPy **1.18.0**, matching the
observed CPX numeric package versions. Host/runtime launch admission is still
required; matching version strings do not replace it.

- 11 focused math/cache/missing-native tests passed on Windows with zero actual
  optimizer calls.
- 18 focused Linux tests passed in 5.824 seconds, including the real input
  loader with fabricated sealed sources, sparse row IDs, NaN outside selected
  replay targets, native I/O, and the original publisher/checksum readback.
- The initial exact launch profile passed 31 tests in 9.521 seconds. Final
  review added the required 3 GiB disk guard before input downloads, on both
  result and artifact volumes. The updated exact profile passed **33 tests**,
  zero errors, failures or skips, in **9.754 seconds**. Boundary tests prove
  insufficient space causes a technical refusal with zero input reads/fits,
  while exactly 3 GiB permits authentication.
- The freshly compiled unchanged C++ evaluator passed the same full synthetic
  rehearsal and production fixture; their candidate bytes were identical.
- That evaluator also passed the complete fixed P0 recheck. Manifest report
  SHA256: `629a5415c6eec3a48528b3d34182141646fc89fca98abfaee65abadee8beb3bc`.
  Numerical solution matches the earlier P0 solver report, including gradient
  norm `7.767141045280521e-7` and minimum eigenvalue `0.0009228207471059007`.
- The actual native fit then passed through the original stage runner, result
  publisher, authenticated readback, corruption refusal and missing-marker
  refusal in one additional test (8.254 seconds).

Explicit preparation ledger: **17 synthetic optimizer invocations** (4 in the
focused Linux suite, 2 in native rehearsal/production, 2 in the P0 recheck, 4 in
the initial launch profile, 1 in actual-native publication, 4 in the updated
33-test launch profile); **0 real fits**.
The initial local build setup failures occurred before any optimization.
They are recorded as TI-027 and TI-028 and are technical, not scientific results.
The missing disk guard was caught in local review and is recorded as TI-029.
An initial attempt to invoke its tests with the bare Windows Python lacked
SciPy and stopped at import; the installed Linux runtime ran the complete suite.
No solver ran in that failed import attempt. The native evaluator and numerical
code remain unchanged by the disk guard; their earlier actual-native receipts
are supplemented by the new guard and complete launch-profile checks.

## Measured launch sizing and remaining evidence

Read-only CPX observation: hostname `cpx62`, 16 available CPUs, 575790 MiB free,
load approximately 0.09. Queues were empty. The authenticated metadata-only
read of ED3 job 1882 / `20260908T220255Z-20a5e4eb` showed its stage running
22:03:09–22:03:25 UTC; its published status spans 22:03:00–22:08:08 UTC.
Its stage receipt SHA256 is
`86e959c431bc7a0992e7db29501406ee4b5330976773b604c939ecbbad507d4b`.

Planning estimate: 5–10 minutes per ED4 full rehearsal/production, informed by
that transport/publication anchor and allowing for a different solve trajectory.
This is not a guaranteed runtime. Each uses all 512 parents and 8192 replay rows,
one-thread numeric libraries, a 300-second solve cap, 900-second stage cap and
1500-second outer admission cap. Production awaits successful same-code rehearsal
publication and authenticated output readback. A cap failure cannot trigger a
parameter change inside V1.

The new CI workflow is prepared locally. **No ED4-P1 CI success, target-host
rehearsal, real candidate, fresh WDL guard or search gain is claimed.** Publication
of the new branch and merging P0 PR #884 were refused by automatic approval
review and explicit user approvals are pending. Repository checks verified the
destination as `https://github.com/jfrancoiscollin/jass.git`, public, owned by the
connected `jfrancoiscollin` account with ADMIN access. Those checks did not remove
the reviewer's requirement for explicit authorization of the new public payload.

Route: Sol for prospective scientific contracts; Terra plus root review and
completion for implementation. The goal remains active and unachieved.
