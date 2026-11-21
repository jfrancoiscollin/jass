# CHINOOK routing eval/search — feasibility audit preregistration

Freeze timestamp: **2026-10-18 13:53 UTC**  
Freeze SHA256: `23d97c02ac715191e86c9ade1adf5c2f2072d42bdb13c3437af167b8b761ac77`  
Status: frozen before the follow-on metadata audit; metadata-only.

## Question

Can the already-frozen CHINOOK_HYBRID routing intervention support a future, separately preregistered eval/search confirmation with a fresh decision-quality cohort, an independent WDL guard, and equal search budget, without reopening consumed cohorts or changing the V1 runtime-strength protocol?

This audit does not test whether the intervention improves decisions, calibration, force, or search. It does not admit V2, spend alpha, authorize training, model/data/case/DB/R2 access, or authorize compute. It cannot select seeds, openings, cases, checkpoints, or parameters from outcomes.

## Fixed scope and permitted evidence

Read only version-controlled preregistration, terminal-result, and identity/provenance metadata documents. Resolve identity unions for the declared exclusions: source attempts 1651, 2066–2069, 2075/2076, and ED3/ED4/ED5 sources named by their frozen records.

Do not read labels, scores, metrics, model contents, game positions/cases, or R2 objects. Record unavailable identity receipts as unknown, never as zero overlap.

## Required feasibility conditions

A future version is only designable if metadata proves all of:

1. Canonical, complete identities for every listed exclusion source, with a reproducible union and overlap check.
2. At least one independent, prospectively generatable source for decision-quality cases, and a separate independent WDL source; both must be target-blind, disjoint from the complete exclusion union and from each other at the canonical identity/group level.
3. Deterministic selection/generation that does not use score, label, seed ranking, checkpoint ranking, or outcomes.
4. Enough eligible identities and documented acquisition capacity to permit a later blind sample-size/power calculation under an unspent alpha allocation, without choosing N from observed effects. The audit itself does not assign or spend alpha.

## Terminal mapping

If every condition is proven from permitted metadata, return `METADATA_FEASIBILITY_ONLY__NEW_PREREG_REQUIRED`; this is not experiment authorization or a candidate gate. If any is unavailable, contradicted, or not auditable under the permitted scope, return `CAMPAIGN_BLOCKED_BY_EVIDENCE_OR_RESOURCE_V1` and list the exact missing evidence. No retries or substitute sources within this audit.
