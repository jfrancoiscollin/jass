# L3 Scan-oracle Gate 0 — pre-execution runtime amendment v1 — 2026-09-07

Status: frozen **before the first Gate 0 execution**. No Gate 0 parent search, Scan score readout, candidate metric, or verdict has been produced yet.

## Reason

The first implementation targeted HOME and enabled the external EGDB build used by the historical Scan-ceiling sibling benchmark. The retrospective D3 question is different: it asks whether the cheap screen would have rejected the **actual sealed D3 runtime treatment** before its equal-node match. The D3 equal-node candidate/control binaries were built without `JASS_EGDB`; adding external EGDB to Gate 0 would silently change the runtime being retrospectively screened.

HOME also did not claim the queued, unexecuted `home-1691` job. That pending job is cancelled before claim and before any target data are read.

## Frozen amendment

For the first retrospective D3 Gate 0 and subsequent comparisons intended to screen the same production runtime family:

- host: `cpx62`;
- external EGDB build/probing: **OFF**, matching the D3 equal-node runtime;
- all other Gate 0 science is unchanged: same frozen 512 parent IDs, Scan200k external sibling reference, exact 20k Jass nodes, WDL_CONTROL bytes, D3 adapter bytes, threads=1, book OFF, fresh engine per parent, same metrics/bootstrap/thresholds;
- zero new Scan searches, zero games, zero fits.

This amendment is not selected from results. No Gate 0 result existed when it was frozen.

D4 remains governed by its own frozen runtime contract. If a future D4 runtime candidate is screened by Gate 0, its control/candidate build must match the D4 runtime preflight environment rather than inherit D3-specific settings by accident.
