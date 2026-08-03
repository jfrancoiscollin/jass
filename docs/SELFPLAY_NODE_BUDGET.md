# Experimental variable node-budget self-play

`--gen-data-wdl` normally searches every played move to a fixed depth. That
historical mode remains the default. The optional `nodes` mode varies the
amount of work per move or per game while keeping the allocation deterministic.

This is experimental infrastructure. It does not replace fixed-depth self-play,
change JNNW/JSM1, choose a production distribution, or schedule a campaign.

## Why nodes

A fixed depth gives every position the same nominal horizon even though game
trees differ greatly in width and tactical complexity. Varying the node budget
can diversify search errors and trajectories while making actual work directly
observable.

- Depth is deterministic but gives very different amounts of work to different
  positions.
- Wall time adapts work but is sensitive to the machine, scheduling and cache
  state, so it is not byte-reproducible.
- Nodes are deterministic on the supported single-threaded self-play path and
  represent search work more directly than time.

The same node budget can reach different completed depths in different
positions. Node counts also depend on the engine implementation: changing move
ordering, pruning, tablebases or the transposition-table policy may change the
trajectory even when the sampler produces the same budgets.

## CLI configuration

The repository's self-play configuration surface is the `--gen-data-wdl` CLI,
not YAML. Node mode must be selected explicitly; partially supplied budget
options are rejected rather than inferred.

Fixed budget, sampled per move (the fixed value naturally stays constant):

```bash
./build/jass --gen-data-wdl 1000 selfplay.jnnw 4 8 200 4242 \
  --wdl-zero-score \
  --search-limit nodes \
  --node-budget-fixed 80000 \
  --node-budget-sample-per move \
  --node-budget-log selfplay.node-budget.jsonl
```

Weighted budget sampled per move:

```bash
./build/jass --gen-data-wdl 5000 selfplay-variable.jnnw 4 8 200 4242 \
  --nnue nnue.bin --wdl-zero-score \
  --search-limit nodes \
  --node-budget-weighted 5000:10,20000:25,80000:35,300000:20,1200000:10 \
  --node-budget-sample-per move \
  --node-budget-log selfplay-variable.node-budget.jsonl
```

Use `--node-budget-sample-per game` to resolve one budget per game. The
`play_depth` positional value is retained for CLI compatibility but is not the
active limit in node mode; the engine uses `MAX_PLY` only as a safety ceiling.
`--play-depth-by-phase` and `--movetime` are rejected in node mode.

The policy applies to the primary **PLAY** search that selects each trajectory
move. The optional score-label search remains depth-controlled; terminal-WDL
pipelines should keep using `--wdl-zero-score` when that score is unused.

`--play-max-nodes` predates this feature. It remains a historical safety cap
combined with fixed depth and is deliberately distinct from
`--search-limit nodes`.

The initial implementation supports `fixed` and integer `weighted` policies.
Weights need not sum to 100. Every choice must contain at least 1,000 nodes,
every weight must be positive, and an overflowing cumulative weight is rejected.
Log-uniform sampling is intentionally deferred.

## Determinism

Sampler version 1 hashes a dedicated stream tag with:

- the effective global seed;
- `game_id`;
- `ply` and side to move for `sample_per=move`.

For `sample_per=game`, ply and side are omitted. The sampler is a pure function
and never reads or advances the opening, record-sampling, exploration, Top-K or
role RNG streams. Worker timing therefore cannot reorder budget draws. The
current `--gen-data-wdl` play search is single-threaded; reproducibility claims
do not extend to generic Lazy SMP searches.

If `--explore-topk` is enabled, ranking each candidate remains a separate
search and currently reuses the sampled cap per candidate. Those extra ranking
nodes are not part of the primary `nodes_used` field. Keep Top-K off for the
initial cost calibration, or account for that additional work explicitly.

## What `nodes_used` counts

`nodes_used` is the engine's existing authoritative per-call counter. It counts
entries into negamax and quiescence, including extensions, null-window probes
and re-searches. A transposition-table hit is still a visited search node. The
root driver itself and any Lazy SMP helper work are not counted. The self-play
node mode does not enable helpers.

The counter is checked locally at every node, without atomics or locks. A
budget-triggered search therefore reports `nodes_used == nodes_budget`; a search
may use less only if it finishes before the cap. Time and external-stop probes
remain throttled as before.

If a budget interrupts iterative deepening, the selected search move and score
come from the last complete iteration. `completed_depth` identifies that
iteration, `effective_depth` identifies the interrupted iteration, and
`aborted_iteration` is true. If even depth 1 cannot complete, the engine returns
a legal root fallback with `completed_depth=0`; it never exposes a partial root
result.

## JSONL provenance and telemetry

`--node-budget-log` is mandatory in node mode. Its first record is a manifest
containing the limit type, policy, granularity, min/max, choices, seed and
`sampler_version`. Every played move then records:

- `game_id`, `ply`, `side_to_move`;
- `search_limit_type`, `nodes_budget`, `nodes_used`;
- `effective_depth`, `completed_depth`, `aborted_iteration`, `stop_reason`;
- `search_time_ms`, `nps`, `search_best_move`, `move_selected`.

A `selfplay_game` record preserves result-level reproducibility. The final
summary contains total searches, mean and p10/p50/median/p90 budgets, bucket
counts, total/mean nodes, used/requested ratios, mean effective depth, mean
search time, aggregate NPS and interrupted-iteration count.

The JSONL sidecar is separate from JNNW/JSM1, so existing training readers and
historical datasets remain compatible. Fixed-depth runs do not create or emit
any of these new records.

## Reproduce a run

Run the same command twice, changing only output paths:

```bash
./build/jass --gen-data-wdl 100 repro-a.jnnw 4 8 80 4242 \
  --wdl-zero-score --random-open-plies 0 \
  --search-limit nodes \
  --node-budget-weighted 5000:10,20000:25,80000:35 \
  --node-budget-sample-per move \
  --node-budget-log repro-a.jsonl

./build/jass --gen-data-wdl 100 repro-b.jnnw 4 8 80 4242 \
  --wdl-zero-score --random-open-plies 0 \
  --search-limit nodes \
  --node-budget-weighted 5000:10,20000:25,80000:35 \
  --node-budget-sample-per move \
  --node-budget-log repro-b.jsonl

python3 tools/verify_node_budget_repro.py repro-a.jsonl repro-b.jsonl
cmp repro-a.jnnw repro-b.jnnw
```

The verifier compares game/ply, requested and used nodes, completed/effective
depths, search and selected moves, and game results. It intentionally excludes
wall-clock time and NPS.

## Smoke and calibration

The following uses the proposed experimental distribution and writes roughly
enough records for about 100 ordinary games. The actual game count is reported
by `selfplay_game` events because `--gen-data-wdl` targets records, not games.
Its requested arithmetic mean is 213,500 nodes per played move, so it must be
cost-calibrated on the target box before any remote launch.

```bash
./build/jass --gen-data-wdl 5000 smoke-variable.jnnw 4 8 200 20260803 \
  --nnue nnue.bin --wdl-zero-score --drop-plycap --split-selfplay-rngs \
  --search-limit nodes \
  --node-budget-weighted 5000:10,20000:25,80000:35,300000:20,1200000:10 \
  --node-budget-sample-per move \
  --node-budget-log smoke-variable.jsonl
```

Do not interpret quality before measuring wall time, positions/second, nodes per
game and effective depth against the fixed-depth baseline at comparable total
cost. Per repository policy, any remote job still requires measured target-box
throughput, a bounded ETA, the job safety checklist and explicit approval.
