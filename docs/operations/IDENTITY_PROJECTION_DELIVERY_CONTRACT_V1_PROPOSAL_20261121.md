# Historical identity-projection delivery contract — proposal

Status: **PROPOSAL ONLY**  
Version: `HISTORICAL_IDENTITY_PROJECTION_DELIVERY_V1`  
Context: [`IDENTITY_PROJECTION_COVERAGE_NOT_ESTABLISHED_V1`](../experiments/IDENTITY_PROJECTION_COVERAGE_AUDIT_V1_RESULTS_20261121.md)  
Audit preregistration: [`IDENTITY_PROJECTION_COVERAGE_AUDIT_V1_PREREG_20261121.md`](../experiments/IDENTITY_PROJECTION_COVERAGE_AUDIT_V1_PREREG_20261121.md)

## Purpose and boundary

This proposal defines the evidence a future authorized source custodian would need to deliver before a verifier could establish complete historical identity coverage. The preceding audit found that currently versioned receipts do not reconstruct the complete position and opening-group exclusion union.

This document does not assert that the missing projections exist or can be recovered. It does not identify a custodian, request or access an external artifact, open any payload, case, label, score, model, database, or R2 object, select a source/cohort/seed, define a scientific comparison, spend alpha, authorize a job, or authorize evaluation/search activation. Missing evidence remains `UNKNOWN`, never zero overlap. ED3/ED4/ED5 consumed cohorts and abandoned W/S targets remain unchanged; the spent alpha 0.0125 is preserved; `CURRICULUM` remains champion.

## Coverage scope

An implementation must consume a frozen, exhaustive source inventory derived from the published audit and its preregistration. Each inventory row identifies the immutable source job, attempt, producer code, readback/receipt, source role, and the identity classes required from that source. The initial inventory must include the source families already audited: CLS 1651 and 2066–2069, CLS 2075/2076, the declared ED3 confirmation/transfer sources, ED4 D/S/W provenance without opening abandoned W/S targets, ED5 D/S/W provenance without opening abandoned W/S targets, and the limited B2/B3 historical projections.

For every `source × identity_class` cell, the inventory records exactly one of:

- `REQUIRED`: a projection and exhaustive coverage proof are required;
- `NOT_APPLICABLE`: allowed only with a source-specific, independently verifiable justification;
- `UNKNOWN`: evidence does not establish applicability or coverage and the verifier must fail closed.

An absent or empty class is not inferred from a zero row count. It requires an authenticated exhaustive source inventory that proves the class has no members.

## Required artifact set

The producer delivery is a content-addressed bundle with four logical artifacts. JSON artifacts use UTF-8, canonical JSON serialization, and SHA-256 digests. Every digest covers the exact bytes delivered. The bundle preserves occurrences and source references; deduplicated unions are verifier outputs, not producer replacements for the source projections.

### 1. `scope.v1`

The scope manifest contains:

- contract version and audit/preregistration references;
- exhaustive inventory version and digest;
- one row per immutable source and required identity class;
- source job, attempt, code commit, receipt path/schema/digest, and declared universe;
- the `REQUIRED` / justified `NOT_APPLICABLE` / `UNKNOWN` status;
- the producer and authorized derivation path for each delivered projection.

Changing the source inventory, adding a source, dropping a source, or changing a required class creates a new contract version and a new review. It cannot be silently reconciled in place.

### 2. `identity-spec.v1`

One shared identity specification applies across all sources, roles, runs, and attempts. It must freeze before any projection is compared:

- ruleset and board-state fields included in identity;
- side-to-move representation;
- permitted symmetry transforms and their exact semantics;
- canonical serialization and encoding;
- digest algorithm and output format;
- versioned synthetic conformance vectors, including symmetry-equivalent and non-equivalent examples.

The same game state must produce the same cross-source identity regardless of role, run, cohort, producer, or local row number. Cohort-specific salts/namespaces are prohibited for the comparison key. Local identifiers remain as provenance references and are never treated as globally comparable identity keys. This proposal does not choose or change the canonicalization rule; that rule requires a separate technical/scientific review before use.

### 3. `projection.v1`

Each occurrence has a stable `source_occurrence_id`, source reference, identity class, canonical identity key, and any applicable links. The projection retains duplicate occurrences so coverage can be reconciled before deduplication.

Required link forms include:

- parent/root occurrence → source parent reference;
- legal child occurrence → parent occurrence and legal move reference;
- played position → game/trajectory reference and ply index;
- opening occurrence → canonical opening-root identity;
- game/trajectory → opening, pair, and group references where those relations exist;
- paired games → shared pair/group identity and both member references.

Group and opening identities must resolve across runs under a frozen common rule. Two different local group numbers, two local JSM2/JSSU1 identifiers, or distinct salted keys do not prove distinct groups. Unresolved aliases or memberships remain `UNKNOWN`.

Projection classes are explicitly typed as `parent`, `legal_child`, `played_position`, `opening_root`, or `group_membership`; a position projection cannot stand in for a group projection. The producer records the source-local reference and all parent/child, game/ply, pair, and group links needed to reconcile the declared universe.

### 4. `coverage-receipt.v1`

For each delivered projection, the receipt contains:

- source job/attempt/code and authenticated source-receipt digest;
- input-manifest digest and projection-tool version/commit;
- output path, byte length, record count, and SHA-256 digest;
- expected and observed counts by source, identity class, and link type;
- an authenticated exhaustive inventory or verifiable derivation that supplies the expected universe independently of the projection output;
- reconciliation evidence for every source reference and required link;
- explicit error/omission counts, all required to be zero for a complete cell.

Counts or a signed output hash alone do not prove completeness: a common extractor can omit the same records from both its projection and its self-reported count. Expected coverage must be tied to an independent authenticated source inventory, a complete pre-existing manifest, or a separately reviewable exhaustive derivation from an authorized producer. For legal children, reconcile the full legal-child catalog for every covered parent. For played positions and groups, reconcile every declared game, trajectory, opening, pair, and membership reference.

The receipt must not contain target outcomes, labels, scores, model values, or evaluation metrics. If the only way to produce a projection is to inspect a forbidden payload or abandoned target, mark the cell unavailable; do not access it under this proposal.

## Verifier contract

A future verifier, separately implemented and reviewed, consumes only the frozen scope, identity specification, projections, coverage receipts, and existing authorized versioned metadata. It emits a deterministic `verification.v1` report containing input digests, verifier version/commit, cell-by-cell status/reason, reconciled counts, and reproducible union digests.

The verifier must:

1. authenticate every source and artifact against the frozen inventory;
2. reject missing, changed, duplicate-conflicting, malformed, or unauthenticated records;
3. reconcile expected and observed occurrence/link coverage before deduplication;
4. resolve aliases using only the frozen cross-source identity rules;
5. calculate separate unions for canonical positions and canonical opening/groups;
6. report only coverage and overlap facts; do not select or rank candidate sources.

Any absent artifact, `UNKNOWN` cell, unjustified `NOT_APPLICABLE`, orphan reference, unresolved group alias, count mismatch, unverified expected universe, hash mismatch, or incomplete link causes `IDENTITY_COVERAGE_NOT_ESTABLISHED`. A fully reconciled inventory may support the narrower terminal `HISTORICAL_IDENTITY_UNION_RECONSTRUCTED`; that terminal establishes coverage of the declared inventory only, not scientific independence or campaign admission.

## What this does not establish

Even a successful historical-union reconstruction is not an experiment preregistration or an admission. Before any future recruitment, a separate reviewed protocol must freeze a candidate question, data roles, selection rules, budgets, gates, and information barriers. A later verifier must calculate historical–D, historical–W, D–W, and D–S intersections in every required identity space, including groups where applicable. This proposal preselects no source, seed, cohort size, or target.

Until an authorized custodian supplies projections meeting this contract, the published terminal `IDENTITY_PROJECTION_COVERAGE_NOT_ESTABLISHED_V1` remains in force. No old audit is reopened and no data access, recruitment, compute, alpha use, bake, promotion, or scale-up follows from this proposal.

