# B3 adaptive counter contract incident — 1832

Date: 2026-09-06

Classification: **TECHNICAL**

Scientific impact: **none**. No fit, strength game, promotion, bake, policy retuning, threshold change, cohort change, or new scientific observation was produced by the failed attempt.

## Affected job

- job: `cpx62-1832-l3-decision-math-b3-real-adaptive-parity-v1`
- attempt: `20260906T122307Z-4483a39b`
- code: `4483a39b773d318792ba6edada39225c55b7ab34`
- terminal state: `failed`
- exit code: `2`
- stage verdict: none
- next stage emitted by failure handling: `STOP_B3_PARITY_TECHNICAL`

The stage aborted while collecting the real B3 adaptive-teacher parity evidence. The visible failure was:

```text
StageError: B3 teacher shard 11 failed rc=-6
terminate called after throwing an instance of 'std::runtime_error'
what(): B2 teacher counter contract mismatch
```

## Root cause

The B3 source renderer intentionally starts from the audited B2 full-teacher adapter and then replaces the unconditional full-ladder loop with the frozen B3 adaptive 100/60/2 racing policy.

The B2 adapter also injected a report-time counter assertion suitable only for a full ladder:

```text
q5 searches == emitted siblings
q50 searches == emitted siblings
q200 searches == emitted siblings
```

After the B3 loop replacement, that inherited assertion remained in the rendered source. For a real adaptive teacher it is structurally false by design because later horizons are evaluated only for survivors. The C++ report writer therefore aborted before B3 parity could be evaluated.

This was an adapter-composition defect, not a failure of the B3 science.

## Durable invariant

A B3 adaptive teacher must satisfy nested search-count invariants rather than B2 full-ladder equality:

```text
q200_searches <= q50_searches <= q5_searches <= emitted_siblings
engine_constructions == q5_searches + q50_searches + q200_searches
```

The B3 renderer must also fail closed if the inherited B2 full-ladder counter contract survives the source transformation.

These invariants constrain accounting only. They do not alter:

- `M5 = 100 cp`
- `M50 = 60 cp`
- `minimum_survivors = 2`
- search budgets `5k / 50k / 200k`
- exact/TB shortcut semantics
- authenticated B2 inputs
- cohort or allocation
- fit/game/promotion/bake authorization

## Correction

Jass PR #808 (`fix: use adaptive counter contract for B3 teacher`) replaced the inherited B2 report assertion with the B3 nested-horizon counter contract and added regression coverage proving that:

1. the B2 full-ladder assertion is absent from rendered B3 source;
2. the B3 nested adaptive assertion is present;
3. the frozen 100/60/2 policy and 5k/50k/200k budgets remain unchanged.

Merged code SHA:

`7756fac99ed5d4767aa4bc5d6beff402884008a6`

The dedicated `b3-real-adaptive-teacher` workflow passed after the correction, including source rendering, CLI execution and renderer/parity contract tests.

## Minimal rerun

jass-control PR #529 queued a new immutable rerun rather than overwriting the failed 1832 history:

- job: `cpx62-1833-l3-decision-math-b3-real-adaptive-parity-rerun-v1`
- code: `7756fac99ed5d4767aa4bc5d6beff402884008a6`
- spec: `specs/b3-real-adaptive-parity-rerun-v1.json`
- stage-spec SHA256: `ff804adfc9c178c8255a97967ee373076822d4272212a9f9e0477ca963515380`

## Terminal runtime proof

Job 1833 completed successfully on CPX62:

- attempt: `20260906T124918Z-7756fac9`
- terminal state: `completed`
- exit code: `0`
- verdict: `B3_REAL_ADAPTIVE_TEACHER_PARITY_ESTABLISHED_V1`
- parents replayed: `4000`
- emitted sibling rows: `37811`
- q5 searches: `37789`
- q50 searches: `25854`
- q200 searches: `21420`
- engine constructions: `85063`
- parity mismatches: `0`
- total nodes: `5648041210`
- next stage: `B3_FRESH_ADAPTIVE_CORPUS_PREREGISTRATION`
- fresh B3 generation authorized: `true`

The runtime counts satisfy the corrected nested invariant:

```text
21420 <= 25854 <= 37789 <= 37811
85063 == 37789 + 25854 + 21420
```

The rerun preserved zero fits, zero strength games, zero promotions and zero bakes. TI-011 is therefore **CLOSED**.
