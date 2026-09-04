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

Read-only development job `cpx62-1771-l3-decision-math-b1-regret-autopsy-v1` completed with exit `0`, attempt `20260904T230418Z-db6e6a5c`, on the same pinned code. It ran from `2026-09-04T23:04:22+00:00` to `2026-09-04T23:09:41+00:00` and published `B1_REGRET_AUTOPSY_COMPLETE_DEVELOPMENT_ONLY`. The [control receipt](https://github.com/jfrancoiscollin/jass-control/blob/main/status/cpx62-1771-l3-decision-math-b1-regret-autopsy-v1.json) embeds its 43,499-byte scientific summary. Its full per-parent diagnostic is `artefacts/all-parent-autopsy.json` under `r2:jass-data/runs/cpx62-1771-l3-decision-math-b1-regret-autopsy-v1/20260904T230418Z-db6e6a5c`.

The job authenticated the original teacher and B1 input hashes above and reproduced the frozen B1 report exactly. Negating and zeroing every q200 value left both survivor stages and simulated node charges unchanged. It changed no margin and consumed no fresh confirmation cohort. Proposed B2 thresholds must not be applied retrospectively as a B1 verdict.

## Historical regret autopsy

Of 286 differing row choices, 80 are equal-q200 ties and 206 have positive regret. The full-q200 reference was eliminated at q5 in 222 cases and at q50 in 64; there was no surviving-reference mismatch or exact-choice mismatch. All 32 cases with raw regret at least 100 are fully non-exact parents. Maximum raw regret is 29,684 and the sum over 8,000 parents is 765,992.

The 7,982 fully non-exact parents retain 41.809460700151246% simulated saving, 96.41693811074918% same-row match and mean raw regret 95.96492107241293. Exact shortcuts therefore do not explain the aggregate saving in this cohort.

| Phase / STM | Parents | Saving | Same row | Mean raw regret | Regret >=100 |
|---|---:|---:|---:|---:|---:|
| P0 / 0 | 987 | 29.2673% | 99.2908% | 0.0729 | 0 |
| P0 / 1 | 1,013 | 29.3927% | 99.5064% | 0.1570 | 0 |
| P1 / 0 | 984 | 38.8710% | 98.7805% | 29.3821 | 2 |
| P1 / 1 | 1,016 | 37.4529% | 98.7205% | 0.2382 | 0 |
| P2 / 0 | 1,020 | 53.0808% | 94.3137% | 201.8363 | 10 |
| P2 / 1 | 980 | 52.3010% | 96.0204% | 90.7224 | 5 |
| P3 / 0 | 979 | 51.1731% | 92.8498% | 241.6118 | 8 |
| P3 / 1 | 1,021 | 51.0162% | 91.9687% | 201.0656 | 7 |

Phase intervals are P0=30–40, P1=20–29, P2=12–19 and P3=9–11 pieces. These are descriptive development results, without a post-hoc pass/fail threshold. The late-phase concentration must be addressed explicitly in a future confirmation protocol.

No unresolved teacher row has completed depth zero at q5, q50 or q200. The 22 zero-depth rows at each budget are all exact rows; this is not evidence of incomplete unresolved labels. The diagnostic did not establish every other search-observation validity condition merely from this depth check.

The machine summary's score-class decomposition uses strict thresholds `q > 29936` and `q < -29936`. It reports 7 class downgrades, 4 within-class distance changes and 195 positive regrets in the residual `finite` class. **That residual class must not be interpreted as ordinary evaluation centipawns:** the detailed cases include scores such as 29916 and -29917 outside those thresholds. These machine fields and the raw results remain frozen.

The pinned teacher loads PatternJass, whose evaluation output is clamped to `[-20000,20000]`. The search deliberately encodes a direct WLD tablebase win/loss below the true-mate threshold as `±(29935 - dist)`, where `dist` includes search ply and available capped MTC information. Consequently the residual `finite` class mixes evaluation-compatible values with reserved high-magnitude score encodings. A stored score alone does not identify the internal node or tablebase hit that produced it; quiescence terminal values and propagated search scores also require care.

Among the 32 raw >=100 cases, 25 contain values in the direct-TB-compatible band, one contains a true-mate-band value and six contain only evaluation-compatible values (differences 121, 203, 126, 119, 467 and 132). A new read-only provenance diagnostic will join immediate child exactness, observed EGDB entry on the stored PV prefix and completion/stop receipts. Those are separate evidence axes: an absent PV entry does not prove an absence of TB search, and a descendant TB hit does not make the child immediately exact. This interpretation changes neither the frozen policy nor its original diagnostic verdict.

## Continuation boundaries

```text
NEW_SEARCHES = 0
NEW_FITS = 0
STRENGTH_GAMES = 0
PROMOTION_AUTHORIZED = FALSE
REAL_ADAPTIVE_TEACHER_AUTHORIZED = FALSE
NEXT_STAGE = B2_PREREGISTER_CONFIRMATION_ONLY
```

The passive SearchDecisionTrace workstream A proceeds independently: A1/A2 was merged in [PR #773](https://github.com/jfrancoiscollin/jass/pull/773), commit `107be69832111354cd61504aff208458979f26e9`, after the complete native suite (27,444 assertions), independent review and green native/Python/WASM CI. A3 exporter/readout remains the next instrumentation deliverable. B2 requires a separately frozen confirmation; the B1 terminal is not a confirmation gate.

Known compatible historical tables cannot be treated as an untouched confirmation reserve: Phase A was consumed by B1; Phase B was subsequently assigned to development/training in [Rich-D](L3_RICH_D_TEACHER_TO_T_V1_20260827.md); Phase C was exposed for budget exploration in [micro-search](L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.md); and A/B/C were explicitly classified as development/training in [T2](L3_T2_PHASE_SPECIALIST_DEEP_FRESH_V1_20260828.md). Later T2/T3 q1000 tables also lack the q5k observation needed by this frozen policy.

A fresh B2 cohort therefore needs its own preregistration, admissibility and overlap receipts, frozen endpoints and phase/colour support checks. No historical result is reclassified as fresh confirmation.
