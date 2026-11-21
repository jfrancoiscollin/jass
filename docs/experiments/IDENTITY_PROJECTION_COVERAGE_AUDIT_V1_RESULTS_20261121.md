# Identity-projection recoverability — audit result

Date: 2026-11-21  
Preregistration: [frozen audit protocol](IDENTITY_PROJECTION_COVERAGE_AUDIT_V1_PREREG_20261121.md)  
Freeze SHA256: `d3f029674d0251b951e80c58b66aab78b17f0ab37c3bb84ac6d7732b6a7ff57e`  
Terminal: **`IDENTITY_PROJECTION_COVERAGE_NOT_ESTABLISHED_V1`**

## Scope and method

This read-only audit checked only versioned preregistration, result/readback receipts, and source-level provenance metadata for the fixed sources in the preregistration. It did not open any artifact payload, case/position list, model, database, or R2 object. No targets, labels, scores, or metrics were read; no job, compute, seed selection, or alpha use occurred. ED4/ED5 W/S targets remain abandoned and unread. The spent alpha 0.0125 and all consumed cohorts remain unchanged.

## Coverage findings

| Frozen source family | Versioned proof found | Missing coverage |
|---|---|---|
| CLS 1651 (`20260829T133348Z-28e12fba`, code `28e12fba0ead14def244ffc442b15937f65edc0e`) | `CLS_G0_REJECTION_PANEL_V1_20260920.json:22` pins the 2,000-parent cohort digest. B2 names this as one of its 40 sources. | Canonical parent list is outside the repository; the digest cannot reproduce the identities or their intersection. |
| CLS 2066 (`20260920T082643Z-426b9b4b`) | Contract pins `calibration-games.json` in `CLS_G0_REJECTION_PANEL_V1_20260920.json:23`. | No versioned identity projection for its trajectories/opening groups. |
| CLS 2067 (`20260920T090324Z-553f4511`) | Contract pins `stage-games.json.gz` in `CLS_G0_REJECTION_PANEL_V1_20260920.json:24`. | No versioned identity projection for its trajectories/opening groups. |
| CLS 2068 (`20260920T092427Z-0304fc16`) | Contract pins `stage-games.json.gz` in `CLS_G0_REJECTION_PANEL_V1_20260920.json:25`. | No versioned identity projection for its trajectories/opening groups. |
| CLS 2069 (`20260920T094538Z-0304fc16`) | Readback 2072 pins `historical-2069-position-identities.json`, SHA256 `3d1e63cfe1fa0b7b22d1da8c5ce8bc1592edba2751674e721714ed69196d20e8` (`CLS_PANEL_AUDIT_2072_READBACK_20260921.json:87`). Source stage derives played-position identities from `g.fens` (`jobs/tools/cls_g0_panel_audit_stage.py:294`). | Projection is an external artifact, not versioned. Its declared footprint is played positions only; it does not supply opening-group identities or the complete legal-child catalogue. |
| CLS 2075/2076 (`20260921T090819Z-e00900ff`, `20260921T100434Z-e00900ff`) | Joint readback pins a shared `opening-freeze.json` digest beginning `e36ce24d` and shared selection digest beginning `b5a728c5` (`CLS_PANEL_JOINT_2075_2076_READBACK_20260921.json`). | Full canonical opening lists and trajectory fingerprints remain outside versioned metadata. Equal selection hashes do not reconstruct group identities. |
| ED3 confirmation/transfer (1883/1884/1885/1886; plus source attempts 1875/1878/1882) | 1884 readback pins cohort seal `f1ce4d2d…8b8b`, exclusion digest `d6a3266f…a0c2`, and guard-plan digest `b973c7f8…db68`. Versioned transfer records identify consumed sources and receipts. | The source lists and canonical opening/group mapping remain in artifacts. 1885/1886 reuse TRAIN/1884/guard; their receipts provide hashes/counts, not the complete union needed here. |
| ED4 k=1 (D1937/W1959/S1949) | Source metadata pins attempts `20260913T073800Z-9673030c`, `20260914T065838Z-4a610fc0`, `20260913T220903Z-665ed70f` and position digests in `jobs/tools/ed5_fresh_dws_disjointness_stage.py:19-44`; 1970 authenticates its cohort report. | Identity lists are external. Position digests and local group IDs do not establish the canonical cross-run opening-group union. |
| ED5 k=2 (D1990/W1988/S1984; control 1995) | Source metadata pins `20260915T155218Z-f746408f`, `20260915T130012Z-da8aa733`, `20260915T084337Z-9e8eb2a3`; the 1997 readback authenticates its report. Control 1995 compares a bounded set of canonical positions. | The control covers ED2 P0, ED3 1884 decision and ED4 D/W/S only; it does not cover all frozen histories or provide canonical cross-run opening-group identities. W/S remain unread. |
| Historical B2 1773 / B3 1835 | B2 attests a 223,317-key plateau+side-to-move union over its frozen 40-source subset, including 1651; B3 adds 4,000 B2 fresh parents. | Both manifests are external and position-only. Their frozen source scope does not include later ED4/ED5/CLS cohorts or cross-run opening groups. |

## Decision

The required complete union cannot be reconstructed from the permitted versioned records. Hashes attest the identity of projections but do not expose their members; limited projections omit required identity types. Every missing intersection remains **unknown**, not zero.

The preregistered terminal is **`IDENTITY_PROJECTION_COVERAGE_NOT_ESTABLISHED_V1`**. Exact missing evidence:

1. Versioned, authenticated canonical identity-only projections for the CLS and ED3/ED4/ED5 exclusions, including complete root/child/trajectory coverage.
2. Canonical opening/group identities and mappings for all WDL and panel sources, so cross-run disjointness can be computed rather than inferred from run-local IDs or digests.
3. A reproducible union manifest covering all frozen exclusions and sufficient proof to recalculate intersections without reading case payloads.

This is not a scientific negative result or an impossibility claim for future source generation. The existing D/W/S generators appear technically capable of producing fresh cohorts once a complete exclusion union and canonical group scheme exist; those conditions are not met now. No new cohort, candidate, or CPX run is authorized by this audit. CURRICULUM remains champion; no bake, promotion, or scale-up.