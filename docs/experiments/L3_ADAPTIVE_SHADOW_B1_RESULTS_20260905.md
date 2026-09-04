# Adaptive sibling shadow B1 — historical diagnostic

Date: 2026-09-05 (Europe/Paris).

This is the historical B1 diagnostic from the [decision-information plan](L3_DECISION_INFORMATION_IMPLEMENTATION_PLAN_V1_20260903.md), PR #771. It does not confirm a racing policy or authorize B3.

## Immutable execution

```text
job     cpx62-1769-l3-decision-math-adaptive-shadow-b1-v1
attempt 20260904T221533Z-db6e6a5c
code    db6e6a5ce88fdd48f8e9b3c998974ceb4f31085e
host    cpx62
start   2026-09-04T22:15:37+00:00
end     2026-09-04T22:20:56+00:00
exit    0
verdict B1_HISTORICAL_SHADOW_COMPLETE
```

Result prefix:
`r2:jass-data/runs/cpx62-1769-l3-decision-math-adaptive-shadow-b1-v1/20260904T221533Z-db6e6a5c`.

The unchanged script was moved from `queue/` to `queue/pending/` and CPX62 was routed from completed job 1768 to 1769 in control commit `557e7d5ac3`. Its blob remained `3a1878d4d888986114cc05dee7d84be6d7a23498`.

The source is historical DSSD Phase A, job `cpx62-1574-l3-deep-sibling-teacher-v2`, attempt `20260826T185527Z-a6da4a0b`, code `a6da4a0b9d724d6b70b9a65d49f222dd1d82b08f`: 74,449 sibling rows. B1 uses the complete table as development data.

## Frozen diagnostic policy

Unresolved siblings receive q5k. The q5k margin is 100 cp, the q50 margin is 60 cp, and each stage retains at least two survivors where possible. Row-index ordering breaks ties. Terminal/TB exact wins may shortcut at zero simulated search cost. q200 values do not determine survival. A sole unresolved survivor may be selected without q200 and is marked uncertified.

The historical denominator includes every recorded q5k/q50/q200 search, including exact rows. Therefore savings over the full table can include exact shortcuts and must not be interpreted as savings solely from eliminating uncertain siblings.

## Authenticated metric publication

Job `cpx62-1770-l3-decision-math-b1-terminal-readout-v1`, attempt `20260904T224748Z-db6e6a5c`, completed with exit `0` at `2026-09-04T22:53:16+00:00`. It authenticated the completed 1769 manifest, inventory and checksums, verified the source identities, and checked agreement between `ADAPTIVE_SHADOW_B1.json` and `ADAPTIVE_SHADOW_B1_READOUT.json`. Its `scientific-summary.json` is included in the [control status](https://github.com/jfrancoiscollin/jass-control/blob/main/status/cpx62-1770-l3-decision-math-b1-terminal-readout-v1.json). It performed no replay, search, fit, game or new confirmation-data read.

| Metric | Authenticated value |
|---|---:|
| Parents / sibling rows | 8,000 / 74,449 |
| Fully non-exact parents | 7,982 |
| Historical full-ladder nodes | 18,542,435,675 |
| Simulated shadow nodes | 10,789,907,706 |
| Node ratio | 0.5819034723980511 |
| Simulated saving | 41.809652760194893% |
| Same deterministic row as full q200 | 96.425% |
| Mean raw q200 regret (`mean_q200_regret_cp`) | 95.749 |
| p95 raw q200 regret | 0 |
| Regret >=100 | 0.4% (32 parents) |
| Exact-win shortcuts | 13 parents |
| Uncertified shadow choices | 0 |

```text
ADAPTIVE_SHADOW_B1.json SHA256
f786210b41490feb32e582bd6075e38b765ef53d5330525b66792cf10e7dd9c0

ADAPTIVE_SHADOW_B1_READOUT.json SHA256
cc7ae960c0f34d865ce25ad05c31f82f5049ea30a9ed99b89a17a2154c60bd45

historical teacher-groups.tsv.gz SHA256
bed80165f2e1249dbc8d0416237250a9ae0c62bcf0900816f60a8fc72c78ac76
```

The row-match rate represents 286 differing row choices. It does not distinguish a q200 tie from a worse q200 choice. The zero p95 and large mean require a tail decomposition: the underlying score scale can include mate-band values as well as finite evaluation scores. The mean is preserved as published; it is not a measured strength loss or a basis for dismissing those rare events.

Read-only development job `cpx62-1771-l3-decision-math-b1-regret-autopsy-v1` was queued to reproduce the frozen B1 report exactly, decompose phase/STM and q5/q50 elimination, separate mate-band changes from finite-score regret and zero-regret ties, and test allocation invariance to q200 perturbations. It changes no margin and consumes no fresh confirmation cohort. This diagnostic precedes freezing B2 endpoints; proposed B2 thresholds must not be applied retrospectively as a B1 verdict.

## Continuation boundaries

```text
NEW_SEARCHES = 0
NEW_FITS = 0
STRENGTH_GAMES = 0
PROMOTION_AUTHORIZED = FALSE
REAL_ADAPTIVE_TEACHER_AUTHORIZED = FALSE
NEXT_STAGE = B2_PREREGISTER_CONFIRMATION_ONLY
```

The passive SearchDecisionTrace workstream A can proceed independently. B2 requires a separately frozen confirmation; the B1 terminal is not a confirmation gate.

Known compatible historical tables cannot be treated as an untouched confirmation reserve: Phase A was consumed by B1; Phase B was subsequently assigned to development/training in [Rich-D](L3_RICH_D_TEACHER_TO_T_V1_20260827.md); Phase C was exposed for budget exploration in [micro-search](L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.md); and A/B/C were explicitly classified as development/training in [T2](L3_T2_PHASE_SPECIALIST_DEEP_FRESH_V1_20260828.md). Later T2/T3 q1000 tables also lack the q5k observation needed by this frozen policy.

A fresh B2 cohort therefore needs its own preregistration, admissibility and overlap receipts, frozen endpoints and phase/colour support checks. No historical result is reclassified as fresh confirmation.
