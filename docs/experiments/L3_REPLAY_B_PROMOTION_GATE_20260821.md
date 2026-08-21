# L3 — REPLAY25 B versus CURRICULUM promotion gate

Date: 2026-08-21  
Tracking: issue #548

## Objective

Test whether the immutable exploratory DOE arm **B — REPLAY25 + CURRICULUM prior** should enter human succession review against the current general champion **CURRICULUM**.

This gate does not refit either model and cannot promote automatically.

## Immutable models

### Candidate B

- source job: `cpx62-1449-l3-exploratory-replay-four-arm-doe-v1`;
- attempt: `20260820T224246Z-7b22be6f`;
- artifact: `artefacts/B.pjtw.gz`;
- target: native JNNW WDL;
- data recipe: all D2 train plus whole-opening D1 replay;
- effective loss mass: 75% NEW / 25% OLD;
- prior: CURRICULUM;
- required certificates: successful optimizer convergence and zero exact-extras residual in MG and EG.

### Current champion

- label: `CURRICULUM`;
- source job: `cpx62-1341-jass-megacorpus-arm-d-fit-v1`;
- attempt: `20260814T191555Z-18c38a33`;
- artifact: `artefacts/D-c-prior-then-current.pjtw.gz`;
- decompressed SHA-256: `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

Both models are reused byte-for-byte. Candidate and baseline hashes must be different.

## Fresh force evidence

The gate generates two new pools using deterministic seeds:

- pool 1: `2026082201`;
- pool 2: `2026082202`.

Each pool contains 3,000 unique openings and is played with paired colours. Both pools must be mutually disjoint and have zero overlap with 21 explicit historical exclusions, including:

- both CTX3 1419 pools;
- both corrected CTX3 1428 pools;
- both replay-DOE 1451 pools.

## Search views and budget

- primary: native, 0.1 second per move;
- diagnostic: Q00, fixed depth 9;
- 6,000 games per pool and per view;
- 24,000 games total;
- 12 shards / 12-way parallel topology;
- 200,000 paired opening-cluster bootstrap replicates.

Locked seeds:

| evidence | native | Q00 |
|---|---:|---:|
| pool 1 gate | 2026082203 | 2026082204 |
| pool 2 gate | 2026082205 | 2026082206 |
| combined readout | 2026082207 | 2026082208 |

Q00 cannot override native.

## Native decision rule

The promotion gate passes only if every condition is true:

1. B scores above 50% on each fresh native pool separately;
2. the two native pool effects are compatible at 95%;
3. the combined native CI95 lower bound is above 50%;
4. the combined paired-bootstrap probability `P(score > 50%)` is at least 97.5%.

Possible terminal classifications:

- `JASS_REPLAY25_B_VS_CURRICULUM_PROMOTION_GATE_PASSED`;
- `JASS_REPLAY25_B_VS_CURRICULUM_PROMOTION_GATE_REJECTED`;
- `JASS_REPLAY25_B_VS_CURRICULUM_PROMOTION_NOT_ESTABLISHED`.

A PASS creates `PROMOTION_REVIEW_RECOMMENDED__TRUE`. It does **not** create an automatic promotion. CURRICULUM remains champion until an explicit human/documentary succession decision.

## Guards

- refits: 0;
- new self-play: 0;
- frozen cohort reads: 0;
- automatic continuation: forbidden;
- automatic promotion: forbidden;
- no seed, threshold, pool or search-parameter adjustment after force evidence begins.
