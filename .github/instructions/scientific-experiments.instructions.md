---
applyTo: "docs/experiments/**/*.md,docs/*.md,jobs/**/*.py,jobs/**/*.sh,jobs/prereg/**,tools/**/*.py,pattern_jass/**/*.py"
---

# Scientific experiment and preregistration instructions

These files can define or execute experiments. Treat changes here as science-sensitive by default.

## Before editing

- Read `docs/L3_CURRENT.md` and the experiment's preregistration/result document when one exists.
- Identify whether the requested change is **technical** (implementation of an already-fixed contract) or **scientific** (changes what is measured, trained, selected, compared, or accepted).
- Do not mix those two categories silently in one patch.

## Preregistration invariants

Once an experiment is preregistered or its train/freeze has started, do not alter in place:

- candidate or baseline identity;
- feature inputs or feature order;
- training corpus or split/priority rules;
- seeds or deterministic selection rules;
- optimizer/loss/epochs/batch/stopping policy;
- search/teacher budgets used as targets;
- sample sizes, cells, phase/color balance;
- thresholds, gates, confidence criteria, or terminal verdict mapping;
- information-barrier rules controlling when scores/labels/metrics may be read.

A scientifically necessary change after preregistration requires a new explicit experiment/version and a new preregistration. Preserve the prior terminal history unchanged.

## Target blindness and leakage

- Selection must be committed/frozen before any forbidden target, candidate, teacher, runtime, or evaluation read defined by the preregistration.
- Do not use later metrics to repair, rank, filter, or resample an earlier target-blind selection.
- Keep train/freeze and fresh evaluation separated when the protocol requires it.
- Do not add diagnostic reads to a pre-selection stage merely because they are not used in the final score; reading forbidden information is itself a contract violation.

## Determinism and identity

- Preserve exact seeds, hashes, ordering, de-duplication, color/phase mapping, and artifact identity where the active protocol freezes them.
- When serializing a frozen candidate, verify that the evaluation/runtime loader uses that exact artifact rather than reconstructing or refitting it.
- Never silently substitute a newer checkpoint, regenerated dataset, or convenient baseline.

## Verdict semantics

- Distinguish `technical failure`, `support insufficient/inconclusive`, and `scientific negative result` explicitly.
- `n=0`, missing/undersized cells, unreadable artifacts, failed sanity baselines, or incomplete gates must fail closed; never report them as neutral evidence.
- Preserve exact terminal verdict tokens already recorded in results documents.
- A favorable proxy/readout is not an Elo/runtime promotion decision unless the preregistered runtime comparison actually establishes it.
- Never promote or bake a candidate automatically.

## Tests for science-sensitive code

Prefer contract tests that prove the scientific invariant, not only the happy-path computation. Where relevant, test:

- forbidden reads remain zero before the allowed stage;
- deterministic replay gives identical selection/artifact hashes;
- baseline sanity is non-empty and behaves as expected;
- undersized/missing cells abort or return an explicit inconclusive state;
- parser writer/reader keys and sample counts round-trip exactly;
- candidate/baseline identity and feature ordering are asserted rather than inferred.

When reviewing a change, flag even small constants/defaults/order changes if they can alter the experiment's causal question.
