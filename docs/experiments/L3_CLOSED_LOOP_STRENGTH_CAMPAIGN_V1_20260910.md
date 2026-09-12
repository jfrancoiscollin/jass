# L3 Closed-Loop Strength (CLS) — Campaign V1

Date: 2026-09-10. Status: **master plan / prospective campaign after ED4**.

## Purpose

CLS replaces proxy-led progression with a closed-loop strength program. The core loop is:

`teacher_k -> student_k -> runtime/search gate -> Elo-vs-parent gate -> bake -> teacher_{k+1}`

Teacher fidelity is a diagnostic/training signal, not the terminal judge. No model replaces `CURRICULUM` without a real strength-at-time gate.

## Fixed anchors

- Production anchor: immutable `CURRICULUM` promoted 2026-08-15. It remains in every generation gauntlet as a drift sentinel.
- Parent-direct comparison: each child must justify continuation against its direct parent.
- External reference: Scan is measured periodically as a ceiling/reference, not as the per-generation continuation criterion.

A child may continue to the next generation only if it improves search efficiency or external strength and does not exhibit meaningful regression against the fixed CURRICULUM anchor.

## Campaign phases

### CLS-D — Diagnosis

Before the first new closed-loop generation, run read-only diagnostics:

1. DEEP512 Jass-vs-Scan completed nominal depth / node-growth / throughput diagnostic (`L3_DEPTH_GROWTH_JASS_VS_SCAN_V2_20260910.md`).
2. Mirror scale with a deep Jass reference to bound shared-evaluator bias.
3. Search profile: NPS, eval calls, qnodes, TT hit/cutoff behavior, ordering and nodes-to-depth.
4. Draw rate, pentanomial distribution and CPX62 pair throughput.

These jobs are `DIAGNOSTIC_ONLY` and cannot alter ED4 or consume fresh confirmation data.

### CLS-G0 — Runtime catastrophe gate

Before opening any fresh strength cohort for a candidate, measure runtime cost prospectively. A hard catastrophe floor must be frozen before the first CLS candidate. The detailed gate must consider at least NPS, completed nominal depth, nodes-to-depth and search-transfer quality. The purpose is to eliminate cases like a candidate that gains offline fidelity but destroys search throughput.

### CLS-L — Learning objective attribution

If diagnosis supports evaluation as a meaningful lever, run a preregistered three-arm causal comparison at identical architecture, corpus, regularization and runtime representation:

- teacher-local only;
- WDL-global only;
- mixed teacher + WDL.

For the mixed arm, gradient normalization is estimated on TRAIN only and frozen before any confirmation read; lambda is fixed to `0.5` in normalized gradient space. No confirmation sweep is allowed.

The current one-axis campaign rule must be explicitly amended before this experiment; it must not be bypassed implicitly.

Historical preregistered candidates such as `hier-l2` and `CONTEXT_30` are reconsidered only if diagnosis says evaluation remains the main actionable lever.

### CLS-S — Search transfer

Candidate and parent use identical search code/configuration except evaluator bytes. Required observables include fixed-node root decision quality, completed nominal depth, nodes-to-depth and runtime cost. Teacher agreement alone cannot authorize continuation.

### CLS-E — Strength-at-time gate

Every candidate that survives offline/runtime/search gates must play a paired color-reversed gauntlet at fixed time/control. Pentanomial scoring is preferred when supported by measured draw rate and pair throughput. SPRT boundaries are sized only from measured CPX62 throughput/variance and frozen before execution.

Primary continuation opponent: direct parent.
Fixed drift sentinel: CURRICULUM.

No promotion without a strength-at-time result.

### CLS-R — Reinjection and teacher regeneration

Only after a child clears the runtime/search and strength gates may it be baked as the next evaluator and used to regenerate `teacher_{k+1}`. The regenerated teacher is immutable and provenance-sealed before the next student fit.

Continuation stops after two consecutive generations without improvement in search-transfer or strength-at-time. Convergence in teacher agreement alone is never success.

## Governance

Retain the existing Jass provenance layer intact: immutable code/data pins, SHA256 receipts, fail-closed launch profiles, frozen cohorts, explicit consumed-data tracking, reproducible jobs and technical incident registry.

Multiplicities and alpha accounting apply only to actual confirmatory claims. Read-only diagnostics and cheap reusable proxy screens are not promoted to confirmatory evidence.

## Relationship to ED4

ED4 completes under its already-frozen contract. CLS does **not** retroactively modify ED4 thresholds, alpha, candidate bytes or confirmation data. An ED4 green result means only: candidate merits a real strength-at-time gate. ED4 alone cannot replace CURRICULUM.

If ED4 is blocked by a genuinely new evidence/resource class, that block is recorded independently; CLS-D diagnostics may still proceed.

## First execution order

1. Finish ED4/C0C under its frozen rules.
2. In parallel, implement and run `L3_DEPTH_GROWTH_JASS_VS_SCAN_V2_20260910.md`.
3. Run mirror scale and draw/pentanomial throughput diagnostics.
4. Publish a bottleneck classification: SEARCH / DECISION-EVAL / COST / mixed.
5. Amend the next-candidate contract with runtime catastrophe gate + CURRICULUM fixed anchor.
6. Only then open CLS generation 1.

## Terminal states

- `CLS_DIAGNOSIS_COMPLETE_V1`
- `CLS_GENERATION_CONTINUE_V1`
- `CLS_GENERATION_STOP_NO_EXTERNAL_PROGRESS_V1`
- `CLS_CANDIDATE_STRENGTH_SUPPORTED_V1`
- `CLS_CANDIDATE_STRENGTH_NOT_SUPPORTED_V1`
- `CLS_BLOCKED_BY_EVIDENCE_OR_RESOURCE_V1`

No automatic promotion is authorized by this master plan.
