# Mini-Jass

Mini-Jass is a standalone learning laboratory for exactly solvable 5x5 short-king draughts. It lives inside the Jass repository for source control only; it does not participate in the production Jass build or runtime.

## Isolation

- Configure from this directory only.
- Do not add this directory to the repository-root CMake project.
- Do not include, link, import, or invoke production Jass code.
- Keep source, tests, dependencies, build files, and outputs under `mini_jass/`.
- Prefix CMake targets with `mini_jass_`, C++ symbols with namespace `mini_jass`, and environment variables with `MINI_JASS_`.

See [ISOLATION.md](ISOLATION.md) for the merge-blocking contract.

## Build and test

From `mini_jass/`:

```text
cmake -S . -B build
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

The generated `build/` directory is local and ignored. These commands neither configure nor build production Jass.

For M3 Python tools, create the isolated environment under `mini_jass/` and install the declared dependencies:

```text
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=python .venv/bin/python -m pytest tests/python
```

On Windows, use `.venv\\Scripts\\python.exe`. A CPU-only PyTorch wheel may be selected from the official PyTorch CPU index when GPU packages are not wanted.

## M1 game core

The game core provides:

- the normative 5x5 mapping, initial state, validation, and 180-degree colour symmetry;
- immutable IDs for the 72 complete move paths;
- independent production and reference move generators;
- mandatory and multi-capture handling, promotion, reversible-ply draws, and terminal rules;
- exhaustive comparison over all 104,794 structural states and 258,632 legal moves;
- deterministic enumeration of 263,829 reachable states and 645,620 transitions.

The frozen v1 action-vocabulary hash is `11242579555617580249`. The frozen v1 raw-graph hash is `3347327730907747976`.

## M2 exact oracle

The exact oracle provides:

- deterministic retrograde W/L/D values from the side-to-move perspective;
- exact distance-to-win for wins and losses, with null DTW for draws;
- every value-optimal action for every non-terminal state;
- an independently solved canonical graph using 180-degree rotation plus colour/turn swap;
- exhaustive raw/canonical value, DTW, transition, and optimal-action equivalence checks;
- a byte-stable solver manifest in `artefacts/solver_manifest.v1.json`.

The raw graph contains 153,947 wins, 37,161 draws, and 72,721 losses. The canonical graph contains 218,305 states and 540,072 transitions. The initial position is a forced loss in 14 plies, and the maximum decisive DTW is 25.

The frozen v1 canonical-graph hash is `3712505811235282327`, the solver hash is `10671205679107391448`, and the manifest hash is `16484585856267539683`.

Use `mini_jass_cli rules`, `mini_jass_cli actions`, `mini_jass_cli enumerate`, or `mini_jass_cli solve` to inspect the compiled contracts.

## M3 exact-supervised baseline

M3 adds:

- stable JSONL export of every solved raw state, legal action, child, exact value, DTW, and optimal-action set;
- an immutable 70/15/15 split over canonical classes, stratified by exact value and material;
- a PyTorch MLP with 54 inputs, two 32-unit hidden layers, value and 72-action policy heads;
- exact-supervised and separately labelled `all-state-fit` training modes;
- deterministic seeds, checkpoints, JSONL epoch metrics, oracle calibration, regret, and Markdown reports;
- linear, hidden-8, hidden-32, and hidden-64 capacity controls.

The baseline contains exactly 5,225 trainable parameters and remains below the 5,500-parameter ceiling. The frozen split contains 184,602 raw train states, 39,539 development states, and 39,688 frozen-test states; its manifest hash is `9e4021da3331bc6ed4976f0ef9baa3c8721a4458c092420749588fbe84e35524`.

The exact-supervised development gate passes with 74.60% value-sign accuracy, 94.57% optimal top-1 accuracy, and 86.99% optimal-set probability mass. The frozen test, read only after model selection, records 75.10%, 94.61%, and 87.14% respectively. The 20-epoch all-state-fit diagnostic passes its capacity gate with 80.42% value-sign accuracy and 96.10% optimal top-1 accuracy. Frozen metadata and the deliberately retained failed 12-epoch diagnostic are recorded in `artefacts/m3_baseline.v1.json`.

Typical workflow after building `mini_jass_cli`:

```text
PYTHONPATH=python .venv/bin/python tools/export_oracle.py --executable build/mini_jass_cli --output artefacts/oracle.v1.jsonl
PYTHONPATH=python .venv/bin/python tools/create_split.py --oracle artefacts/oracle.v1.jsonl --output artefacts/split_manifest.v1.json
PYTHONPATH=python .venv/bin/python tools/train.py --config configs/l1_exact_supervised.yaml --oracle artefacts/oracle.v1.jsonl --run-dir artefacts/runs/exact-v1
```

The 93 MB oracle export, checkpoints, run metrics, and reports remain ignored under `mini_jass/artefacts/`. Only compact versioned manifests are committed.

## M4 deterministic self-play loop

M4 adds a complete, isolated learning loop:

- outcome-only self-play with final WDL targets and search-improved self-play with visit-policy targets;
- deterministic negamax alpha-beta search with strict node budgets, depth, branching, terminal, leaf-evaluation, selected-move, root-score, and per-action telemetry;
- fixed, uniform, log-uniform, curriculum, complexity, and mixed budget policies;
- greedy, epsilon-greedy, top-k uniform, and top-k softmax exploration;
- bounded FIFO replay with uniform, recency, and generation-mix sampling;
- replay-only value/policy training, paired candidate-versus-parent arenas, development-only oracle gates, and reproducibility-blocked promotion;
- resolved configuration, seeds, environment, rule/solver/split manifests, JSONL metrics, coverage, arena, checkpoints, summary, and reproducibility outputs.

The rule-only `GameGraph` deliberately has no exact values, DTW, or optimal-action fields. Those labels are available only inside the development promotion gate. The frozen test cohort is never read by M4 generation, training, arena, or promotion.

The frozen smoke baseline runs two generations and repeats the entire seeded execution. All six deterministic artefact hashes match, so the M4 reproducibility gate passes. Its compact record is `artefacts/m4_baseline.v1.json`. Both smoke candidates were correctly rejected rather than promoted because they failed the development and arena thresholds.

Run either learning mode after exporting the M3 oracle:

```text
PYTHONPATH=python .venv/bin/python tools/run_selfplay.py --config configs/l1_search_selfplay.yaml --oracle artefacts/oracle.v1.jsonl --run-dir artefacts/runs/search-v1
PYTHONPATH=python .venv/bin/python tools/run_selfplay.py --config configs/l1_outcome_selfplay.yaml --oracle artefacts/oracle.v1.jsonl --run-dir artefacts/runs/outcome-v1
```

Each command independently replays the seeded run before returning success. Large replay, checkpoint, trace, and report files remain ignored below `mini_jass/artefacts/`; only the compact M4 baseline manifest is committed.

## M5 first causal experiment pack

M5 adds the preregistered E1–E4 pack:

- E1 combines outcome-only WDL/policy targets with fixed 16-node search, no replay, and a short exploration warm-up;
- E2 compares fixed-depth and fixed-node stopping rules at matched measured node consumption;
- E3 compares fixed 32, uniform 8/16/32/64, log-uniform 4–128, and curriculum 8→128 budgets;
- E4 compares greedy, epsilon-greedy, top-2 uniform, and top-3 softmax exploration;
- every arm uses five paired seeds and identical initial weights per seed;
- the report preserves failed arms, raw counts, paired differences, 95% confidence intervals, training-sample-count strata, zero-sample populations, oracle regret, and coverage;
- the protocol and executable contracts are hashed before all fixed candidates are evaluated on frozen test.

The first pack contains 11 arms and 55 successful runs. Actual consumed-node imbalance is 4.2% for E2, 22.5% for E3, and 15.5% for E4, below the preregistered 35% limit. Top-2 uniform more than doubles mean unique-state coverage versus greedy in this smoke pack, but E1 does not improve value-sign accuracy and slightly reduces optimal-move mass. The automatic recommendation is therefore `continue_L1`; direct L2 or Jass 10×10 transfer is not authorized. The compact evidence record is `artefacts/m5_experiment_pack.v1.json`.

Run the pack after exporting the M3/M4 oracle:

```text
PYTHONPATH=python .venv/bin/python tools/run_experiments.py --config configs/l1_first_experiment_pack.yaml --oracle artefacts/oracle.v1.jsonl --run-dir artefacts/runs/m5-pack-v1
```

The ignored run directory contains resolved per-arm configs, all candidate checkpoints, raw arm results, the comparison report, rule/solver/split/executable manifests, and the transfer recommendation. Only the compact M5 evidence manifest is committed.

## M6 L1 learning gate

M6 keeps the laboratory on L1 and adds the preregistered E5–E9 consolidation pack:

- deterministic restarts sampled only from non-terminal states in the immutable train cohort;
- optimizer-dose, outcome-versus-search target, greedy-versus-Top-2, and replay ablations;
- exact target-quality diagnostics materialized only after every candidate and the protocol hash are fixed;
- development metrics for the complete cohort and for states actually encountered during generation;
- a strict scientific gate that requires simultaneous value-sign and optimal-move-mass progress before L2.

The pack contains 11 arms and 55 successful paired-seed runs. Its execution gate passes: all arms are reported, initial weights are paired, train-only restarts are enforced, frozen-test access is delayed, and every experiment remains below the 35% consumed-node imbalance limit. Train-cohort restarts multiply mean coverage by 4.34, and the selected `strong_1024` dose improves development value-sign accuracy by 0.3620 with a 95% selection-score interval of `[0.3433, 0.3770]`. Two of five candidates satisfy both development and arena promotion checks.

The strict scientific gate nevertheless remains closed because mean development optimal-move mass changes by -0.0018. Search targets themselves carry 88.25% mean optimal mass, so the remaining problem is policy-target generalization rather than target availability. The automatic decision is `continue_L1_policy_gate`; neither L2 nor Jass 10×10 transfer is authorized. The compact evidence record is `artefacts/m6_learning_gate.v1.json`.

Run the frozen gate after exporting the M3/M4 oracle:

```text
PYTHONPATH=python .venv/bin/python tools/run_learning_gate.py --config configs/l1_learning_gate.yaml --oracle artefacts/oracle.v1.jsonl --run-dir artefacts/runs/m6-learning-gate-v1 --compact-output artefacts/m6_learning_gate.v1.json
```

The detailed run directory remains ignored. The compact M6 record hashes the protocol, result, M5 input, Python package, rule/action/graph/solver/split contracts, and every retained report artefact.

## M7 balanced policy-target gate

M7 repairs the policy-target mechanism identified by M6 while remaining entirely on L1:

- root actions receive balanced per-action search budgets, differing by at most one node;
- every legal root action is searched before a policy target is built;
- self-play behavior uses search scores and is therefore independent of the training-target encoding;
- E10 compares visit distribution, best-action one-hot, and score-softmax targets as a target-only causal contrast;
- all three arms use the same 16-node budget, 1,024 optimizer steps, train-cohort starts, and five paired seeds.

All 15 runs succeed. The execution gate records 100% root-action coverage, balanced allocations, paired initial weights, and delayed frozen-test access. `score_softmax` wins the preregistered joint development score: mean value-sign accuracy improves by 0.4033 and mean optimal-move mass by 0.0256. Its targets carry 92.14% optimal mass and a 92.56% optimal argmax rate; the joint score 95% interval is `[0.4208, 0.4369]`.

The M7 scientific gate therefore passes, but M7 deliberately authorizes neither L2 nor Jass 10×10 transfer. Its decision is `rerun_frozen_M6_gate_before_L2`: freeze `score_softmax`, then rerun the complete M6 L1 gate before any scale-up. Compact evidence is retained in `artefacts/m7_policy_target_gate.v1.json`.

Run the frozen M7 pack after exporting the oracle:

```text
PYTHONPATH=python .venv/bin/python tools/run_policy_gate.py --config configs/l1_policy_target_gate.yaml --oracle artefacts/oracle.v1.jsonl --run-dir artefacts/runs/m7-policy-target-v1 --compact-output artefacts/m7_policy_target_gate.v1.json
```

The detailed run directory remains ignored. The compact M7 record binds the M6 result, exact protocol, current Python package, immutable solver/split contracts, and retained report hashes.

## M8 frozen learning-gate replication

M8 freezes the M7-selected `score_softmax` target at temperature 0.25 and replays the complete E5–E9 L1 gate. Every search arm uses balanced root budgets and target-independent search-score behavior; the outcome-only E7 arm remains the sole causal control. The pack retains five paired seeds, train-only restarts, optimizer-dose, exploration, replay, arena, and delayed frozen-test contracts.

The first execution-only attempt exposed that E8's historical 39-game greedy calibration no longer matched Top-2 after balanced root allocation: mean node totals were 3,837.4 versus 9,986.0. No threshold or scientific parameter was changed. A new protocol hash and new seed family were preregistered using only these node counts, with 102 greedy games. The retained compact record includes this calibration provenance.

The final pack reports 55/55 successful runs. Every experiment is below the 35% consumed-node imbalance ceiling; E8 is at 7.84%. The selected `strong_1024` arm improves mean development value-sign accuracy by 0.3860 and optimal-move mass by 0.0189. Mean target exact-value rate is 86.29%, target optimal mass is 91.94%, and the joint-score 95% interval is `[0.3861, 0.4237]`.

Both execution and scientific gates pass. M8 authorizes an isolated L2 replication through `advance_to_L2_not_10x10`; direct Jass 10×10 transfer remains forbidden. Compact evidence is retained in `artefacts/m8_learning_gate_replication.v1.json`.

Run the frozen replication after exporting the oracle:

```text
PYTHONPATH=python .venv/bin/python tools/run_learning_gate.py --config configs/l1_frozen_learning_gate.yaml --oracle artefacts/oracle.v1.jsonl --run-dir artefacts/runs/m8-frozen-learning-gate-v2 --compact-output artefacts/m8_learning_gate_replication.v1.json
```
