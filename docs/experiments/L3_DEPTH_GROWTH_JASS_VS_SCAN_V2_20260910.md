# L3 diagnostic depth-growth Jass vs Scan V2

Date: 2026-09-10. Status: **preregistered, DIAGNOSTIC_ONLY**.

## Question

On the frozen DEEP512 roots from the 2026-08-29 Scan-ceiling benchmark (cohort SHA256 `478abc0fe2fe1fcd8c2157f532ba796745c645ff4f03dac8fd21c2ff851f137e`), compare Jass and Scan under the same requested node budgets `{5000,50000,200000}` using each engine's already-frozen node semantics. Measure completed nominal depth, raw nodes-by-depth trajectory, throughput and canonical root-move agreement. This is an orientation diagnostic only: SEARCH, DECISION/EVAL, COST, SCALING and LOCALIZED are descriptive labels, never causal gates.

No q200/WDL/confirmation target is read. No fresh cohort, alpha, fit, game, model selection, promotion or tuning is authorized. Results cannot change any frozen ED4 threshold.

## Immutable code and engines

Jass code for this protocol is pinned to `513b15f5216e913deaf1c8d6850635999fae03ea`. Runtime queueing must pin the eventual merged implementation SHA separately and publish it; scientific inputs below must not drift.

Scan remains unmodified Scan 3.1 from mirror `rhalbersma/scan`, source commit `7aae17e7b7bfc47744601afb1ee7655e18983ce5`, tree `023eace16a90ec543b6b6174c79cfc42488a356e`, binary SHA256 `96b80c6aec1592f856a78ad7617ca6224b26be926800a6e37ede3b26f4e9cfa1`, eval SHA256 `0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba`, ini SHA256 `dc201a7debaf98bb869fb3d6b641adb219df71b0ea22004b2d9b6f51cdb69538`. Book off, one thread, `bb-size=0`, `tt_size=24`, `new-game` before each root.

CURRICULUM must be authenticated by the complete SHA256 already sealed by the Scan-ceiling benchmark; the implementation must resolve and publish the full hash before rehearsal and fail closed on mismatch. No abbreviated hash is accepted at runtime.

Build two Jass binaries from the same implementation SHA and common Release flags (`JASS_ENDGAME_FEATURES=ON`, `JASS_KING_MOBILITY=ON`, `JASS_SCAN_PARITY=ON`, `JASS_TEMPO_STAGE=ON`):

- `JASS_PARITY`: no `JASS_TIME_BREAKDOWN`; only cross-engine observables.
- `JASS_PROFILE`: same configuration plus `JASS_TIME_BREAKDOWN=ON`; only intra-Jass counters/breakdown.

On the 32-root rehearsal, PARITY and PROFILE must have identical canonical best move, observed nodes and completed nominal depth at equal node budgets. Time may differ. Any other divergence is technical failure.

## Blocking node-budget precondition

Jass must use the existing Scan-ceiling exact-node implementation directly, specifically the `scan_ceiling_jass_ladder`/`run_fresh_search(..., budget, ...)` path whose frozen contract constructs a fresh Engine per root/budget and reports `node_limit_mode=exact`, `requested_node_caps_exactly_configured=true`, and node-stopped rows equal requested. No HUB `go nodes`, movetime emulation or fixed-depth substitution is allowed.

Per row publish `nodes_requested`, `nodes_observed`, and `node_semantics`:

- Jass: `exact_cap; node-stopped rows equal N; complete MAX_PLY rows may end below N`.
- Scan: `exact requested N; last complete info is a progressive snapshot bounded by the next 16-node poll, not total consumed`.

Thus the experiment compares equal **requested** node budgets under frozen engine-specific observation semantics, not literal equality of observed counters.

## Per-root output

`per_root.tsv` contains `root_id phase stm pieces branching forced_capture_at_root max_capture_len budget_kind budget nodes_requested nodes_observed node_semantics engine completed_nominal_depth seldepth wall_ms nps bestmove_canonical score_cp terminal_flag qnodes eval_calls tt_hit_rate cutoffs first_move_cutoffs pvs_researches moves_searched`.

`bestmove_canonical` is from+to+exact captured-square set. `score_cp` is descriptive only and is never subtracted across engines. Internal counters are NA for Scan and JASS_PARITY.

Completed nominal depths are engine-reported iterative-deepening depths; they are not assumed to be identical algorithmic units across engines.

## Nodes-by-depth symmetry

Cross-engine `nodes_by_depth` and `depth_growth_ratio(d)=nodes(d)/nodes(d-1)` are valid only if both engines expose completed iterations from **one continuous iterative-deepening search per root**, with reset/new-game only before the root. Scan may use successive `info` lines from one `go analyze`. Jass must expose equivalent completed-iteration snapshots from the same exact-cap search without restarting at each depth.

If this Jass snapshot contract cannot be implemented without changing search semantics, cross-engine `nodes_by_depth`, `depth_growth_ratio`, SCALING orientation and `nodes_to_depth_jass/nodes_to_depth_scan` are disabled before rehearsal; the manifest records `cross_engine_depth_curve_available=false`. The node-budget depth/throughput/root-move diagnostic remains valid. Separate fresh depth-N searches must never be compared to Scan's in-search snapshots as one curve.

An optional `ebf_fit` may be descriptive only; no orientation depends on it.

## Bootstrap

Paired phase-stratified root bootstrap, 100000 replicates, seed `2026091002`. Unit is `root_id`; all engines, budgets and depth observations for a sampled root remain together. P0-P3 quotas remain fixed.

## Sizing

Rehearsal: 32 predetermined roots, 8 per phase, seed `2026091001`, including PARITY/PROFILE sanity.

FULL: 512 roots, 128/phase, node budgets `{5k,50k,200k}`, fixed-depth diagnostics `{9,12}` only where semantically valid.

LITE: 256 predetermined roots, 64/phase, same node budgets, fixed-depth diagnostic `{9}` only where semantically valid.

Mechanical selection: projected 512-root wall `<=2400s` => FULL; otherwise LITE. No third adaptation. Limits: <=45 min, <=16 CPU, >=3 GiB free.

## Orientations

SEARCH: Scan has a coherently better requested-nodes -> completed-nominal-depth trajectory across budgets/strata and raw throughput alone does not explain it.

DECISION/EVAL: node/depth trajectories are similar but canonical root moves diverge materially; this does not identify evaluation as sole cause.

COST: primarily an intra-Jass orientation; Jass/Scan NPS alone cannot attribute evaluation cost.

SCALING: only available when the symmetric continuous-search nodes-by-depth contract above is established; Jass node growth worsens more with depth across multiple strata.

LOCALIZED: contrasts concentrate in preregistered strata (phase, pieces, branching, forced capture, max capture length).

No automatic scientific verdict. JFC may record a descriptive orientation in `L3_CURRENT.md`; it authorizes no tuning or combination of levers.

## Outputs and quarantine

Required outputs: `per_root.tsv`, `aggregates.json`, `RESULTS.md`, `manifest.json`; additionally `nodes_by_depth.json` only when the symmetric curve contract is established. Terminal `DEPTH_GROWTH_JASS_VS_SCAN_V2_COMPLETE` on complete technical execution, otherwise `DEPTH_GROWTH_JASS_VS_SCAN_V2_TECHNICAL_FAILURE`.

`DIAGNOSTIC_ONLY=true`. DEEP512 is already consumed. This job runs in parallel with ED4 and cannot influence ED4 confirmation thresholds, selection or alpha.
