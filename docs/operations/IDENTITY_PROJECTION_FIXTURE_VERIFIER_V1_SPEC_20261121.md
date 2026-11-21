# Synthetic identity-projection verifier — engineering scope

Status: **FROZEN FOR ONE SYNTHETIC ENGINEERING PASS**  
Version: `IDENTITY_PROJECTION_FIXTURE_VERIFIER_V1`  
Parent proposal: [`HISTORICAL_IDENTITY_PROJECTION_DELIVERY_V1`](IDENTITY_PROJECTION_DELIVERY_CONTRACT_V1_PROPOSAL_20261121.md)  
Scientific terminal remains: `IDENTITY_PROJECTION_COVERAGE_NOT_ESTABLISHED_V1`

## Question and stop condition

Can a standalone verifier reject two concrete false-positive patterns using synthetic identity tokens: (1) a projection and its own receipt omit the same occurrence and report zero omissions, and (2) different source-local group identifiers conceal one common canonical group?

This is one fixture-conformance engineering pass. Stop after the fixed fixture cases below are implemented and validated. It does not attempt to verify real historical identity coverage or a real producer receipt.

## Strict boundary

Inputs are synthetic byte strings held in memory and compared with a reference fixture fixed independently in the test harness. They contain fictitious ASCII tokens only; no FEN, game state, source artifact, R2 locator, case, label, score, model, database, or real identity is permitted. The verifier accepts no path, URL, database handle, environment-selected file, or caller-supplied trusted inventory. No job, compute, alpha, source/cohort/seed selection, data acquisition, recruitment, or evaluation is authorized.

The implementation must be a standalone module used only by its dedicated fixture tests. Do not connect it to the CLI, production, training, launch/control plane, existing search/evaluation, or campaign data generators. Do not alter any candidate, experiment, existing output, cohort, or target. CURRICULUM remains champion; alpha 0.0125 remains spent.

## Input and canonicalization rules

All five JSON objects have closed schemas and exact version tags. Reject unknown keys, missing required fields, duplicate JSON keys, unknown versions, invalid UTF-8, non-ASCII identity tokens, duplicate conflicting IDs, and non-canonical integer/count forms. Document bytes are UTF-8; document and projection digests use SHA-256 over exact input bytes. Object key order does not affect parsed semantics; output serialization is canonical UTF-8 JSON with sorted keys, compact separators, and no trailing newline.

The test harness, not the input bundle, pins the independent reference inventory, allowed source/partition/class tuples, expected occurrence IDs, expected links, allowed token aliases, and vector outcomes. A bundle cannot redefine its own reference, attestation authority, or completeness universe.

### `scope.fixture.v1`

Fields: `profile`, `reference_sha256`, `identity_spec_sha256`, `sources[]`. Each source has `id`, `partition` (`H`, `D`, `W`, or `S`), `attempt`, `producer_id`, `input_manifest_sha256`, and `cells[]`. Each cell has `class`, `requirement`, and `basis_ref`. The parsed scope must equal the independent fixture reference exactly. `UNKNOWN` rejects. `NOT_APPLICABLE` is accepted only where the fixture reference pins a justification; an empty required class cannot be inferred from a zero count.

### `identity-spec.fixture.v1`

Fields: `profile`, `position_aliases[]`, `group_aliases[]`, and `vectors[]`. Each alias binds a synthetic local token to a synthetic canonical key in one identity space. The independent reference fixes the allowed aliases. Vectors include both equivalent and distinct token pairs for positions and groups. Missing, conflicting, or unrecognized aliases reject. These tokens are not real identities and do not choose the production canonicalization rule.

### `projection.fixture.v1`

Fields: `source_id`, `identity_spec_sha256`, `occurrences[]`, and `links[]`. Each occurrence has `id`, `source_ref`, `class`, and `token`. Each link has `kind`, `from_ref`, `to_ref`, and `qualifier`. The fixture pins valid source references and link endpoints for parent–child/move, game–played-position/ply, game–opening, pair–game, and game–group relations. Occurrences and links must reconcile exactly with the independent reference before identity deduplication. Orphans, omissions, extras, duplicate conflicts, unsupported classes, and incomplete pairs reject.

Identity classes `parent`, `legal_child`, `played_position`, and `opening_root` contribute tokens to the position space; `group_membership` contributes to the group space. The fixture specifies token space for every occurrence. Links do not imply equality unless an explicit allowed alias in the identity spec says so.

### `coverage_receipt.fixture.v1`

Fields: `source_id`, `attempt`, `producer_id`, `input_manifest_sha256`, `reference_sha256`, `projection_sha256`, `projection_bytes`, `occurrence_counts`, `link_counts`, and `omissions`. Recompute exact-byte digest, byte size, occurrence/link counts, and omission count. Reconcile the full occurrence IDs and typed link records against the independent fixture reference, including same-count substitutions. A self-reported zero omission count cannot override a missing expected occurrence or link.

### `verification.fixture.v1`

Fields: `profile`, `verifier_version`, `input_sha256`, `status`, `errors[]`, `unions`, and `intersections`. Status is exactly `FIXTURE_CONFORMANT` or `FIXTURE_REJECTED`. Error codes and references are ordered deterministically. Rejected reports have `unions` and `intersections` set to null. A conforming report contains separate position/group unions and all six unordered partition pairs H/D/W/S in both spaces. Each set is sorted before canonical JSON serialization and SHA-256 hashing. Non-empty intersections are valid findings, not verifier errors.

## Fixed fixtures

The dedicated tests use only the independently pinned synthetic reference and cover:

1. a complete conforming bundle with some intentional position and group overlaps;
2. a parent–legal-child identity overlap between partitions;
3. one common opening group represented by different local aliases across partitions;
4. omission of an occurrence from both a projection and its receipt;
5. same-count substitution of an expected occurrence;
6. incomplete paired-game/group membership links;
7. malformed, duplicate-key, unknown-field, unknown-version, and hash-mismatch inputs;
8. permutation of occurrence order, preserving unions/intersections while changing the exact-byte input digest.

Only fixture outcomes are permitted: `FIXTURE_CONFORMANT` or `FIXTURE_REJECTED`. The synthetic fixtures may prove that the verifier catches these constructed errors; they cannot prove any historical coverage, absence of overlap, or scientific independence.

## Future work explicitly excluded

Real projection ingestion, producer attestation, historical-union reconstruction, source acquisition, group-equivalence semantics for actual data, D/W/S recruitment, any alpha or compute, and all experiment admission require separate authorization and review. The currently published scientific terminal remains unchanged until authorized complete source projections and an exhaustive independent reference inventory exist.

