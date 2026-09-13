# ED4-FRESH — W/S child protocol V1

Date: 2026-09-13. Status: preregistration before any W or S target read.

## 1. Search-transfer source S

Parent protocol seed is `202609120403`, reserve `202609120413`.

The already sealed D source (job 1937) uses implementation sub-streams `202609120401`, `202609120402`, `202609120403`. Therefore using the same score-free generator with S primary seed `202609120403` would deterministically overlap the D reserved sub-stream. This is a pre-target technical identity-collision condition under §3 of `L3_ED4_FRESH_CONFIRMATION_V1_20260912.md`; no target has been read in D or S.

S therefore uses the preregistered reserve seed `202609120413`. This is not candidate-conditioned and does not alter population, quotas, search budget, controls, thresholds or alpha. The source recipe is identical to D: independently restarted random legal trajectories, 8..160 plies, >=9 pieces, 2..16 legal root moves, phase x STM balance. Production retains the 512 `decision` roots (64 in each phase x STM cell); calibration/reserved rows are source-only support and are never scored as S confirmation rows.

S-source terminal: `ED4_FRESH_S_SOURCE_SEALED_V1`. Target reads/searches/fits/games/alpha are all zero in the source stage.

## 2. WDL source W — sizing before production

Frozen master seed remains `202609120402`, reserve `202609120412`.

The existing `jass --gen-data-wdl` generator is record-count driven and writes WDL labels directly. It cannot be used as a confirmation source without a barrier. W therefore has two pre-target steps:

1. **Sizing rehearsal only**: generate a small deterministic corpus with JSM2 metadata to measure records per independent `game_id` / `opening_id`. The rehearsal may inspect only metadata and record counts; WDL bytes are never parsed and are zeroed before any artifact publication. This rehearsal consumes zero confirmation target and exists only to freeze an exact production game/group count.
2. **Production source**: after the game count is frozen in a follow-up child preregistration, replay a fixed seed/configuration, publish score-free positions (target bytes zeroed), JSM2 game/opening grouping, canonical identity digest and source hashes. At least 8192 eligible positions and >=32 independent game/opening groups are required. No candidate/control evaluation occurs.

The later W target stage deterministically replays the same frozen games after the source seal, authenticates that position/game identities match the seal, and only then reads the WDL outcome for the sealed 8192 positions. The candidate cannot influence game generation, position selection, group selection or completion.

No production W game count is chosen in this document; it will be fixed mechanically from the sizing rehearsal before W production, exactly as required by the parent preregistration.

## 3. Cross-block rule

Before any D/W/S target read, canonical identity sets for D, W and S must be authenticated pairwise disjoint. Any collision is a technical failure and can only use the already frozen reserve seed for the affected unconsumed block.
