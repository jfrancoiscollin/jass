# ED4-FRESH — prospective confirmation generated after candidate seal V1

Date: 2026-09-12. Status: preregistration before any fresh target generation or target read.

## 0. Purpose

Replace the historical-exclusion reconstruction as the critical path to the ED4 verdict with three new confirmation populations generated only after the ED4 candidate was frozen. The completed C0A/C0B/C0C work remains an audit artifact; it is not discarded, but unresolved historical aliases no longer gate ED4-FRESH because no historical holdout is used for confirmation.

Frozen candidate: `ED4_CHOICE.pjtw`, SHA256 `2e856652efdd1d2758a949a5d4a29557fa31f4a64d55505ae6dc41482b641f5b`, sealed by production job `cpx62-1888-l3-ed4-choice-value-fit-production-v1` / attempt `20260909T143020Z-93e2fd1f`.

Champion/control BASE remains the frozen BASE specified by the parent campaign. HARD remains the mandatory secondary control where already required; SOFT remains descriptive. No fit, retuning, checkpoint selection, candidate-byte change, threshold change, alpha reset, promotion or bake is authorized.

ED4 remains attempt `k=1` under `L3_EVAL_SEARCH_CANDIDATE_CAMPAIGN_V1_20260909.md`; the existing family-wise alpha accounting and three confirmation blocks remain unchanged.

## 1. Freshness by construction

All three confirmation sources are created after this preregistration and after the ED4 candidate seal. The source-generation code, seeds, population sizes, phase/STM quotas, teacher/search budgets, target-read barriers and evaluation gates are frozen before generation.

A source stage must publish and authenticate a cohort seal containing canonical position/opening/game identities and source hashes before any target/teacher/outcome value is read. Generation and target production are separate stages. Failure before the seal consumes no confirmation target. Once a confirmation target is read, that cohort is consumed permanently.

No row from CURRENT_2M, TRAIN512, replay8192, ED2/ED3 TEST, confirmation 1884, DEEP512 or any historical confirmation corpus may be used as an ED4-FRESH confirmation row. Historical artifacts may be used only as frozen binaries/models or metadata needed to authenticate the already-sealed candidate/controls.

## 2. Three independent confirmation blocks

### D — fresh decision confirmation

Population: 512 newly generated parent positions, 64 in each of the 8 predefined phase x STM cells. Each parent must have 2..16 legal root moves, >=9 pieces, and arise from an independently restarted random legal trajectory of 8..160 plies. No parent or child may be selected using model or teacher values.

Frozen source seed: `202609120401`.

For each legal child, obtain a fresh reference teacher score at 200000 Scan nodes using the same pinned Scan identity and terminal/tie/POV semantics as the parent campaign. Seal source identities before any Scan call.

Primary gates are exactly those of the parent campaign: candidate must reduce parent-weighted regret versus BASE and HARD with positive lower bounds, not reduce top-hit below the best mandatory control, and satisfy `harmed <= improved`. Bootstrap remains phase/STM-stratified by parent. No new metric or threshold is introduced after target read.

### W — fresh WDL confirmation

Generate a new outcome corpus after this preregistration; do not sample CURRENT_2M. The generation recipe must be frozen in its own child protocol before the first game and must use fixed engine/model identities, opening/source rule, time/node budget, adjudication and game seed. Outcomes are not visible to any fit or selection stage.

Frozen WDL master seed: `202609120402`.
Target evaluation population: 8192 sealed positions drawn by a score-free rule from newly generated games, with opening/game-group IDs retained for clustered inference and at least 32 independent game/opening groups. Exact game count is determined prospectively by the child sizing protocol before generation; it may only increase by a predeclared mechanical completion rule if 8192 eligible sealed positions are not produced, never in response to candidate metrics.

Mandatory gates remain candidate-minus-BASE upper bound `<= 0.002` for both logloss and Brier, with the group/cluster unit frozen before target read.

### S — fresh search-transfer confirmation

Population: 512 newly generated root positions, 64 in each phase x STM cell, produced independently from block D and W.

Frozen source seed: `202609120403`.

Seal all root identities before teacher/search scoring. Candidate and BASE are then plugged into the same Jass executable with identical bytes/configuration outside evaluator, same cache/thread settings and same frozen node budget. A pinned reference teacher is generated only after the root seal. The mandatory parent-campaign search-transfer gate is unchanged: lower bound of candidate-minus-BASE root-choice regret gain > 0, exact BASE/BASE sanity, and no nodes/configuration invariant divergence. HARD secondary; SOFT descriptive.

## 3. Independence and contamination checks

The D/W/S seeds are distinct and their generators must publish disjoint canonical identity sets. Cross-block duplicate canonical identities are a technical failure before target read and force regeneration from a prospectively declared reserve seed, never deletion after seeing target values.

Reserve seeds are frozen now solely for technical duplicate/support recovery: D `202609120411`, W `202609120412`, S `202609120413`. A reserve may be used only if the primary source fails before any target read for that block and only for a predeclared technical reason (identity collision, insufficient support, corrupt generation or timeout). It cannot be selected based on candidate performance.

Temporal freshness is not used as the sole proof: each source must also publish code SHA, generator identity, exact seed, quotas, canonical identity digest, and creation timestamp after the ED4 seal.

## 4. Execution order

1. Implement/CI the fresh source generators and target barriers with fixtures only.
2. Generate and seal D, W and S source populations. These source-generation jobs may run independently and read zero confirmation targets.
3. Authenticate seals and cross-block disjointness.
4. Only then run the three confirmation target/evaluation blocks under the existing ED4 alpha budget.
5. All three green -> `CAMPAIGN_REAL_CANDIDATE_GATE_GREEN_V1`, followed by `PREREGISTER_SCALE_UP_REVIEW`; no automatic promotion.
6. Any scientific gate failure -> `CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1` and consume that cohort.
7. Mechanical/source failure before target read -> repair/repeat the same frozen contract or use the corresponding reserve seed when its explicit condition applies.

## 5. Historical C0C disposition

Jobs through 1933 remain authoritative audit evidence. The three unresolved descriptors reported by 1933 are aliases of the same historical JNNW bytes (same SHA/size/projection). They remain unresolved for historical provenance and must not be silently reclassified. ED4-FRESH does not need to resolve them because none of those historical rows or derived holdouts are confirmation inputs.

This is a source change, not a scientific relaxation: the candidate, gates, alpha, controls and thresholds are unchanged; only the confirmation populations are newly generated after candidate freeze.