# B3 fresh teacher source-publication contract incident — 1838

Date: 2026-09-06

Classification: **TECHNICAL**

Affected scientific stage:

```text
job     cpx62-1838-l3-decision-math-b3-fresh-adaptive-teacher-v1
attempt 20260906T151340Z-0f6dd960
code    0f6dd960218d8625c77dde651f6ebf553333fdd9
state   failed
exit    2
```

The generic stage receipt classifies the failure as `STAGE_EXIT_CODE` during `EXECUTE`, after runner inputs were authenticated and before any required fresh-teacher output was published. No fit, strength game, promotion or bake was authorized or executed. This is not a negative B3 scientific verdict.

## Root cause

The sealed B3 source-selection publication is produced by the audited B2-derived `publish_prepared()` contract. Its `selection` object publishes the total population as:

```text
parents = 4000
```

and represents the frozen quota by the exact eight `cells` entries, each equal to `500`. It also publishes `forbidden_overlap=0` and `target_blind=true`.

The fresh-teacher consumer incorrectly required two undeclared aliases:

```text
selected = 4000
cell_quota = 500
```

Those keys are not part of the sealed publication schema. The consumer therefore rejected a valid authenticated 1837 source publication before the teacher corpus could be published.

This is a producer/consumer schema-adapter defect. The scientific population, source bytes, cells, policy and budgets are unchanged.

## Durable invariant

Downstream consumers must authenticate the **actual sealed producer schema**, not a synthetic test-only facsimile:

```text
selection.parents == 4000
len(selection.cells) == 8
all(selection.cells[cell] == 500)
selection.forbidden_overlap == 0
selection.target_blind == true
```

No `selected` or `cell_quota` alias may be invented unless it is explicitly added to the producer contract by a separately reviewed schema migration.

Regression fixtures for a sealed publication consumer must mirror the producer's real field names.

## Correction

The repair changes only the fresh-teacher source-publication validation:

- require `selection.parents == 4000`;
- preserve exact descriptor authentication of `parents.jnnw`, `parents.tsv` and ordered identities;
- preserve eight cells at exactly 500 each;
- preserve `forbidden_overlap=0` and `target_blind=true`;
- remove the undeclared `selected` and `cell_quota` requirements;
- add a regression proving the old aliases cannot substitute for the real `parents` field.

No change is made to:

```text
M5 = 100
M50 = 60
minimum_survivors = 2
budgets = 5000 / 50000 / 200000 exact nodes
source job/attempt 1837
4000 fresh parents / 500 per cell
CURRICULUM
exact/TB semantics
teacher rendered bytes
reference-audit barrier
fit/game/promotion/bake authorization
```

## Diagnostic side note

The first read-only failure-log diagnostic, job 1839, was rejected at the generic wrapper with exit 64 because its manually supplied stage-spec SHA256 did not match the actual spec bytes. It never executed the diagnostic stage and did not read teacher/scientific data. The corrected spec SHA was computed from the actual repository bytes before any retry.

## Closure condition

This incident remains **MITIGATED** until a new immutable fresh-teacher job on the repaired code authenticates the exact 1837 source and terminates with:

```text
B3_FRESH_ADAPTIVE_TEACHER_COMPLETE_V1
```

Only that terminal proof closes the incident and authorizes the preregistered audit-subset seal.
