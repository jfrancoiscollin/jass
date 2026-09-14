# ED4-FRESH W — production source freeze V1

Date: 2026-09-14. Status: **prospective before W source production or any W outcome/target read**.

Parents: `L3_ED4_FRESH_CONFIRMATION_V1_20260912.md`, `L3_ED4_FRESH_W_S_CHILD_PROTOCOL_V1_20260913.md`, and `L3_ED4_FRESH_W_SIZING_REHEARSAL_V1_20260913.md`.

## Authenticated sizing input

This child freeze uses only the structural, target-blind result of `cpx62-1948-l3-ed4-fresh-w-sizing-rehearsal-v2`, attempt `20260913T220257Z-7782dc2b`, code `7782dc2b5fa79e02711d5c898cb91ee6bf7b691a`.

The sizing report contains 4096 emitted records, 118 represented games and 65 represented openings. Structural records/game: min 13, p10 23, median 31, p90 51. Structural records/opening: min 24, p10 37, median 64, p90 90. `game_result` and JNNW WDL were not parsed; candidate/control evaluation, target reads, fits and alpha were zero.

## Mechanical production group freeze

`--pair-openings` permits at most two represented games per represented opening. Therefore the sizing prefix contains exactly `118 - 65 = 53` openings with both paired games represented.

To give every retained opening equal weight without outcome-conditioned completion:

1. Per-game row quota is the largest power of two not exceeding the observed sizing minimum records/game: `q = 8` (largest power of two <= 13).
2. Every retained opening contributes exactly two games x 8 score-free rows = 16 positions.
3. The exact production confirmation population is 8192 positions, therefore the frozen cluster count is `8192 / 16 = 512` opening groups and 1024 paired game groups.
4. Cluster unit for later W inference is frozen as `opening_id`; each cluster contributes exactly 16 sealed rows.

Eligibility is structural only: an opening is eligible iff exactly two represented game IDs exist and each represented game has at least 8 emitted rows. Openings are considered in first-appearance order; the first 512 eligible openings are retained. Within each paired game, the first 8 emitted rows are retained. No score, WDL, game result, candidate output or control output participates.

## Raw-generation sizing and predeclared completion rule

The represented-pair rate measured by sizing is `53/65`. The mechanically estimated number of represented openings needed to obtain 512 eligible pairs is therefore `ceil(512 * 65 / 53) = 628`.

The initial record budget is the next 4096-record boundary above `628 * median_records_per_opening = 628 * 64 = 40192`, hence **40960 raw records**.

If and only if fewer than 512 structurally eligible paired openings exist, repeat the same deterministic seed/configuration from scratch with record budgets increased by exactly 4096: `45056`, `49152`, `53248`, then `57344`. The maximum is the next 4096 boundary above `628 * p90_records_per_opening = 56520`, namely **57344**. No budget step may depend on outcomes or candidate metrics. If 512 eligible paired openings are still unavailable at 57344, terminate `ED4_FRESH_W_SOURCE_INSUFFICIENT_V1`; no confirmation target is consumed.

The master seed remains `202609120402`; reserve `202609120412` is untouched unless the parent protocol's pre-target technical reserve condition is separately proven.

## Frozen generator recipe

The generator and frozen CURRICULUM player are the same as sizing:

- CURRICULUM source: `cpx62-1341-jass-megacorpus-arm-d-fit-v1` / `20260814T191555Z-18c38a33`, model SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`;
- `--gen-data-wdl`, eval depth 4, play depth 8, max plies 260;
- `--wdl-zero-score --random-open-plies 8 --split-selfplay-rngs --pair-openings --drop-plycap`;
- JSM2 sidecar; no epsilon exploration, adjudication or TB relabel;
- 8cf pattern geometry and production feature flags.

Raw JNNW/JSM2 files live only in private scratch. JNNW WDL bytes are blindly zeroed before any scientific artifact is created. JSM2 `game_result` bytes are never decoded and are blindly zeroed before any scientific artifact is created. Only the 8192 selected score-free rows and their zeroed structural metadata are sealed.

## Required source seal

Production must publish:

- exactly 8192 score-free JNNW positions;
- exactly 512 opening clusters and 1024 represented games, 8 rows/game;
- an aligned zero-result JSM2 sidecar and TSV grouping map;
- canonical position identity digest and unique-count evidence;
- exact source/model/code/seed/recipe identities and file hashes;
- `target_reads=0`, `candidate_reads=0`, `control_evaluations=0`, `fits=0`, `alpha_spent=0`, `confirmation_target_consumed=false`.

Production terminal: `ED4_FRESH_W_SOURCE_SEALED_V1` -> `AUTHENTICATE_D_W_S_DISJOINTNESS_BEFORE_TARGET_READ`.

No W target replay, candidate/control evaluation or alpha spend is authorized until D/W/S canonical identity sets are authenticated pairwise disjoint.
