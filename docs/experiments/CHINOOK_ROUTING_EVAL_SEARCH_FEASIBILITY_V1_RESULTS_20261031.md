# CHINOOK routing eval/search — metadata-only feasibility result

Date: 2026-10-31  
Audit freeze: [preregistration](CHINOOK_ROUTING_EVAL_SEARCH_FEASIBILITY_V1_PREREG_20261031.md)  
Freeze SHA256: `23d97c02ac715191e86c9ade1adf5c2f207d42bdb13c3437af167b8b761ac77`  
Terminal: **`CAMPAIGN_BLOCKED_BY_EVIDENCE_OR_RESOURCE_V1`**

## Scope

This was a metadata-only audit for whether the frozen CHINOOK_HYBRID runtime intervention could support a future, separately preregistered eval/search comparison with fresh decision-quality cases, an independent WDL guard, and equal search budget.

It did not test decision quality, calibration, force, or search; read no labels, scores, metrics, model contents, positions/cases, database, or R2 objects; launch no job; spend no alpha; and did not admit a new experiment. The existing ED3/ED4/ED5 cohorts and the 0.0125 alpha already spent remain untouched.

The audit freeze required four conditions to be proved using version-controlled preregistration, result, and identity/provenance metadata only. Missing identity receipts were to remain unknown, never treated as zero overlap.

## Findings

| Frozen condition | Result | Evidence |
|---|---|---|
| Complete canonical identity sets for all declared exclusions, with reproducible union and overlap check | **Not established** | `docs/experiments/CLS_G0_REJECTION_PANEL_V1_20260920.json` records a cohort digest for selection 1651, but for 2066–2068 gives job/attempt/code/artifact identifiers, and for 2069 points to an artifact without publishing the full canonical identity set. Its exclusion list defines canonicalization but explicitly does not claim disjointness from all training data. `docs/operations/CLS_PANEL_AUDIT_2072_READBACK_20260921.json` references historical 2069 identities outside the versioned canonical set. `docs/operations/CLS_PANEL_JOINT_2075_2076_READBACK_20260921.json` records the shared selection hash and attempts, not canonical group sets. ED3/ED4/ED5 each define their own cohorts, but their records do not provide a single reproducible union and intersection audit across all required exclusions. |
| Independent, target-blind, disjoint decision source and WDL source | **Not established** | `docs/experiments/L3_CHINOOK_HYBRID_CAUSAL_STRENGTH_V1_20260921.md` defines the strength experiment and its opening policy, not D and W eval/search cohorts. `docs/operations/CLS_G0_V2_CASE_METADATA_INVENTORY_20260921.json` records `new_v2_roster_evidenced=false`, `new_v2_holdout_evidenced=false`, and an empty `eligible_new_cases_evidenced`. ED3's WDL guard is explicitly historical in `docs/experiments/L3_ED3_CONFIRMATION_V1_20260909.md`; it is not a fresh independent source for this audit. |
| Deterministic selection/generation without outcome-based selection | **Partially evidenced, insufficient** | The CLS metadata inventory describes a score-free mechanism, and CHINOOK V1 has fixed opening seeds. No new D/W recipe is specified that links canonical identity exclusions to separate target-blind sources. |
| Sufficient eligible identities and acquisition capacity for a later blind sizing/power analysis under a new alpha allocation | **Not established** | The CLS inventory leaves `finite_new_candidate_roster`, `untouched_score_blind_holdout`, `deep_reference_route`, and `prospective_case_count` null, and `eligible_new_cases_evidenced` empty. This audit made no alpha allocation and consumed none. |

No zero-overlap claim can be made: the complete canonical exclusion union is unavailable, and fresh D/W source identities are absent.

## Decision

The preregistered terminal is **`CAMPAIGN_BLOCKED_BY_EVIDENCE_OR_RESOURCE_V1`**. The missing evidence is:

1. Versioned canonical identity/group manifests for each required exclusion source, plus the algorithm and digest for their full union.
2. Independently generated D and W populations with frozen, target-blind selection recipes and canonical identity/group manifests proving pairwise disjointness from each other and from the full exclusion union.
3. A documented prospective acquisition route and enough eligible identities to permit a later blind sample-size calculation under a separately authorized, unspent alpha allocation.

This is a feasibility result about currently evidenced metadata. It is **not** a scientific negative result about CHINOOK_HYBRID, an impossibility claim about all future sources, or authorization for a V2, compute, training, or match. CHINOOK V1 remains a separate strength-safety rehearsal path; it cannot establish the requested eval/search-and-calibration improvement gate. CURRICULUM remains champion. No bake, promotion, or scale-up is admitted.

The V1 strength rehearsal's outstanding technical repair remains separate. A repair or rehearsal cannot satisfy this eval/search gate by itself.


## Publication CI note

The first CI for this documentation PR had a WASM compile failure in the existing source file `src/t3_f6.cpp`: `std::terminate()` lacked an explicit `<exception>` include. This was unrelated to the metadata audit and did not use any scientific artifacts. The minimal source fix was reviewed and merged separately as PR1089, commit `33f9a7eaae3f0bbcd82636ebb005df45d9fc62be`; its native, WASM, retirement-readiness, and incident-register checks all passed. This technical correction does not change the audit scope or terminal; the documentation PR must still pass checks on its updated head before merge.
