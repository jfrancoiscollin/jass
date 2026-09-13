# ED4-FRESH W — pre-target sizing rehearsal V1

Date: 2026-09-13. Status: **prospective before any W source production or W target read**.

Parent protocols: `L3_ED4_FRESH_CONFIRMATION_V1_20260912.md` and `L3_ED4_FRESH_W_S_CHILD_PROTOCOL_V1_20260913.md`.

## Purpose

Freeze a small deterministic metadata-only rehearsal that measures records per independent `game_id` / `opening_id` so a later child preregistration can fix the exact W production group count before production. This rehearsal is not a confirmation cohort and cannot spend ED4 alpha or evaluate ED4_CHOICE, BASE, HARD or SOFT.

## Frozen sizing recipe

- master seed: `202609120402` (the already preregistered W primary seed);
- requested emitted records: `4096`;
- generator: exact pinned Jass commit used by the launch spec;
- evaluator used only to play the candidate-independent games: frozen CURRICULUM from job `cpx62-1341-jass-megacorpus-arm-d-fit-v1` / attempt `20260814T191555Z-18c38a33`, model SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`;
- `--gen-data-wdl 4096`, eval-depth `4`, play-depth `8`, max plies `260`;
- `--wdl-zero-score`, `--random-open-plies 8`, `--split-selfplay-rngs`, `--pair-openings`, `--drop-plycap`, JSM2 sidecar;
- no epsilon exploration, no adjudication, no tablebase relabel, no candidate/control evaluation;
- build uses the existing 8cf pattern geometry and production feature flags.

The sizing stage may inspect JSM2 structural fields needed for counts (`game_id`, `opening_id`, `seeded`, `ply`, `game_plies`, `last_eps_ply`, flags) but **must not parse `game_result`**. It must never inspect the JNNW WDL byte. Before any generated corpus bytes are published, it blindly overwrites every JNNW WDL byte with zero and every JSM2 `game_result` byte with zero. Raw generated files are scratch-only and are deleted before stage completion.

## Output and frozen follow-up rule

Publish only structural sizing statistics and zero-target evidence: record count, independent games/openings, records-per-game/opening distribution, exact recipe/model identities and hashes of the sanitized audit corpus. The sizing job reports the actual number of generated self-play games as an engineering side effect; `test_target_reads`, fits, searches, strength games, promotions, bakes and alpha remain zero.

The **production W game/group count is not chosen here**. After this rehearsal terminates, a separate child preregistration must deterministically derive and freeze that count from the sizing report, before W production starts. It may include a prospective safety margin for producing at least 8192 eligible sealed positions and at least 32 independent game/opening groups, but may not depend on ED4 candidate metrics or outcomes.

Terminal: `ED4_FRESH_W_SIZING_COMPLETE_V1` -> `FREEZE_W_PRODUCTION_GROUP_COUNT_FROM_SIZING_V1`. Any failure is technical and consumes no confirmation cohort.