# Historical identity-projection recoverability audit — preregistration

Freeze timestamp: **2026-11-21 18:50 UTC**  
Freeze SHA256: `d3f029674d0251b951e80c58b66aab78b17f0ab37c3bb84ac6d7732b6a7ff57e`  
Status: frozen before audit; metadata-only.

## Question

Can existing versioned records prove the complete canonical identity/exclusion union needed for a future eval/search campaign, including case/position identities and opening/group identities, without reopening old scientific payloads or accessing R2?

This is only a recoverability audit. It does not evaluate candidates, read targets/labels/scores/metrics/model contents/cases, generate or select seeds/cohorts, allocate or spend alpha, or authorize compute. ED4/ED5 W/S targets remain abandoned and unread. Preserve spent alpha 0.0125 and every consumed cohort.

## Fixed scope

Inspect versioned preregistrations, result/readback receipts, and source-level provenance metadata for:

- CLS selection/trajectory sources 1651 and 2066–2069;
- published CLS selections/readbacks 2075–2076;
- ED3 confirmation/transfer sources named in the frozen documents, including 1883/1884/1885/1886 where listed;
- ED4 k=1 and ED5 k=2 source identities as declared in their frozen documents, without opening abandoned W/S targets;
- historical identity projections/unions B2 job 1773 and B3 job 1835 only as coverage-limited artifacts.

Do not widen source scope or follow artifact paths into R2. If a record points outside version-controlled metadata, mark the projection unavailable.

## Per-source ledger fields

For each fixed source, record only:

- immutable job/attempt/code and the versioned receipt/path;
- whether an identity-only projection is present and its declared hash/schema (do not inspect case payloads);
- declared completeness of roots, legal children/trajectories, openings/groups, and required canonical transform;
- publication/authentication evidence and whether the projection is reproducible from permitted versioned sources;
- gaps or contradictions.

Historical B2/B3 unions count only for the exact source subset their preregistrations declare. Matching opening IDs or selection hashes alone do not prove cross-run group disjointness.

## Terminal mapping

Return `IDENTITY_PROJECTION_COVERAGE_RECOVERABLE__NEW_FREEZE_REQUIRED` only if every required exclusion source has an authenticated, complete, versioned canonical projection covering the necessary identity types and its union can be reproduced without payload access. This is metadata feasibility only; it does not authorize future data generation.

Otherwise return `IDENTITY_PROJECTION_COVERAGE_NOT_ESTABLISHED_V1`, list exact missing projection/identity kinds, and stop. Do not infer zero overlap from absence. Do not retry, select seeds, or substitute sources within this audit.
