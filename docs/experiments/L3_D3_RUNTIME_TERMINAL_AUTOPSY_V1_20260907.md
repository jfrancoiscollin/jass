# L3 D3 Runtime Terminal Autopsy V1 — 2026-09-07

## Status

Diagnostic-only post-terminal autopsy after the repaired immutable equal-node run terminated:

- job: `cpx62-1857-l3-decision-math-d3-runtime-equal-node-prereg-recovery-requeue-v1`
- attempt: `20260907T155344Z-fcdcd217`
- code: `fcdcd217cccb9d94aa7351b453dad725f3d816b1`
- verdict: `D3_RUNTIME_EQUAL_NODE_NOT_ESTABLISHED_V1`
- primary: 1500 games, D3 score 0.463, Elo -25.7573
- harness: 200 games, exact control/control score 0.5

This autopsy cannot reopen D3, authorize equal-time, retune D3, change the 632D feature map, fit/refit/search a model, invoke a teacher, play a game, promote, or bake.

## Frozen question

Why did a D3 adapter that improved held-out selected-action prediction offline lose strength when used only for runtime move ordering at an equal exact node budget?

The autopsy distinguishes only descriptive failure shapes already observable in the sealed 1857 game records:

1. **search-efficiency degradation** — at nearly identical exact-node consumption, D3 completes less depth than control;
2. **runtime-compute amplification** — D3 ordering consumes substantially more wall time per search even though wall time is not the equal-node scoring resource;
3. **broad vs localized failure** — weakness is shared across D3 colors and opening piece-count phases rather than isolated to one orientation/cohort;
4. **outcome coupling** — pair-level D3 score covaries descriptively with D3-minus-control depth, node/search, eval/search or wall/search deltas.

These are diagnostic labels only. No threshold may select a D3 hyperparameter or rescue configuration.

## Immutable inputs

Only sealed artefacts from the successful 1857 attempt may be read:

- `scientific-summary.json`;
- `d3-equal-node-pool-provenance.json`;
- all eight `shards/sXX/primary-games.jsonl` files;
- all eight `shards/sXX/harness-games.jsonl` files.

The source identity must authenticate exactly to the job/attempt/code above and state `completed`.

Forbidden:

- any engine/search invocation;
- any new game or replay;
- qscore or `SearchDecisionTrace`;
- job 1843/full-ladder targets;
- teacher/model search;
- fit/refit/tuning;
- equal-time results;
- promotion/bake.

## Frozen diagnostics

### A. Source reconstruction

Reconstruct exactly 750 primary opening pairs / 1500 games and 100 harness opening pairs / 200 games. Verify:

- all pair schemas and modes;
- no duplicate opening index inside a mode;
- node budget 20000 and max plies 160 on every pair;
- primary W/D/L, score and integer candidate/control telemetry totals agree with the sealed terminal summary;
- harness aggregate arm-A score is exactly 0.5.

Any mismatch is technical/provenance invalidity; it is not scientific evidence.

### B. Per-game telemetry deltas

For every primary game publish D3 minus control for:

- completed depth per search;
- nodes per search;
- eval calls per search;
- wall milliseconds per search;
- wall-time ratio D3/control;
- D3 feature calls per search.

Also retain D3 score/WDL, color, plies, termination reason and opening piece-count phase (`P0 >=30`, `P1 20..29`).

Publish count, mean, median, p05/p25/p75/p95 for every numeric diagnostic.

### C. Frozen group views

Publish the same descriptive telemetry summaries and D3 score for:

- D3 W/D/L;
- D3 color white/black;
- opening phase P0/P1;
- terminal reason.

No subgroup is a model-selection gate.

### D. Pair-level associations

For each of the 750 color-swapped primary pairs, compute pair score and the mean of the two game-level telemetry deltas. Publish Spearman rho between pair score and each telemetry delta.

No p-value, multiple-testing claim or causal gate is attached to these correlations.

### E. Descriptive classification

The autopsy emits booleans only from signs/identity facts:

- `equal_node_depth_efficiency_degraded`: primary score < 0.5 and mean depth delta < 0;
- `runtime_cost_amplified`: mean wall-time ratio > 1;
- `failure_broad_across_color`: both white and black D3 scores < 0.5;
- `failure_broad_across_opening_phase`: every represented P0/P1 phase has D3 score < 0.5;
- `depth_delta_tracks_pair_score_positive`: Spearman rho(pair score, depth delta) > 0.

Classification order:

- if depth efficiency is degraded and failure is broad across both color and phase: `BROAD_EQUAL_NODE_SEARCH_EFFICIENCY_DEGRADATION`;
- else if depth efficiency is degraded: `EQUAL_NODE_SEARCH_EFFICIENCY_DEGRADATION`;
- else: `EQUAL_NODE_FAILURE_WITHOUT_MEAN_DEPTH_DEGRADATION`.

This classification may motivate only a separate preregistration whose target is search utility. It cannot alter D3.

## Required terminal publication

Completion label: `D3_RUNTIME_TERMINAL_AUTOPSY_COMPLETE_V1`.

Required counters:

- fits = 0
- model_searches = 0
- teacher_searches = 0
- strength_games = 0
- searches = 0
- promotions = 0
- bakes = 0
- equal_time_authorized = false

Next stage is `D4_SEARCH_UTILITY_PREREGISTRATION_ONLY`.
