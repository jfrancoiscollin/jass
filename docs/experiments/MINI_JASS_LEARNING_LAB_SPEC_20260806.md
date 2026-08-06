# Mini-Jass Learning Lab — specification

> Date: 2026-08-06  
> Status: implementation proposal  
> Target branch: `develop`

## 1. Purpose

Build a deliberately tiny, fully observable draughts-learning laboratory before scaling ideas to international draughts on 10×10.

The objective is not to create a strong miniature engine. The objective is to make every part of the learning loop measurable and falsifiable:

- game-state coverage;
- exact position values;
- target quality;
- policy quality;
- value calibration;
- exploration effects;
- replay effects;
- search versus network contribution;
- generation-to-generation improvement;
- compute efficiency.

The laboratory must reproduce the conceptual Jass loop while remaining small enough to run locally and, for the first level, small enough to solve exactly.

## 2. Why a dedicated Mini-Jass instead of extending `othello/`

The existing `othello/` POC is useful for validating pattern lookup and training infrastructure on a documented domain. It is intentionally standalone and focuses on pattern evaluation.

Mini-Jass answers a different question: does the complete self-play learning loop learn the correct draughts knowledge, and why?

It should therefore preserve the important semantics of draughts:

- diagonal movement;
- mandatory capture;
- multi-capture sequences;
- promotion;
- side-to-move perspective;
- terminal win/loss/draw outcomes.

Keeping these semantics makes results more transferable to 10×10 Jass than Othello, Tic-Tac-Toe, or Connect Four.

## 3. Scale ladder

### L0 — exact toy graph

A tiny deterministic game graph, generated in code, with known minimax values.

Purpose:

- validate generic trainer, replay, target sign, promotion gate, metrics, and reproducibility;
- catch pipeline bugs before any board-game complexity.

This level is optional if L1 implementation remains simple enough.

### L1 — Mini-Jass 5×5

L1 uses the following normative rules. Rows are numbered from Black's home rank to White's home rank, columns from left to right, and playable squares use this fixed row-major mapping:

```text
       column
       0  1  2  3  4
row 0  0  .  1  .  2   Black home rank
row 1  .  3  .  4  .
row 2  5  .  6  .  7
row 3  .  8  .  9  .
row 4 10  . 11  . 12   White home rank
```

- playable square `n` is bit `n` in every bitboard;
- the initial state has Black men on `{0, 2}`, White men on `{10, 12}`, no kings, White to move, and `reversible_plies = 0`;
- White men move one diagonal step toward decreasing row numbers; Black men move toward increasing row numbers;
- men capture one adjacent opposing piece by jumping to the empty square immediately beyond it, both forward and backward;
- kings move one diagonal step and capture by the same short jump in both directions; there are no flying kings at L1;
- if any capture is available to the side to move, every quiet move is illegal;
- a capture move is the complete ordered jump sequence and must continue until the moving piece has no further capture;
- when several continuations exist, every complete continuation is legal; L1 has no maximum-capture or majority-capture priority;
- a captured piece is removed immediately after its jump and cannot be captured again in the same sequence;
- a man remains a man throughout a capture sequence and is promoted only after the complete move, provided its final square is on the opponent's home rank;
- at the start of a turn, a side with no piece or no legal move loses;
- a capture or any move by a man sets `reversible_plies` to zero; a non-capturing king move increments it by one;
- after a move, loss by absence of piece or legal move is checked first; otherwise the position is a draw when `reversible_plies` reaches the configured limit, fixed to 20 for the L1 oracle;
- repetition is not a separate terminal rule at L1. Repeated board positions remain distinguishable through `reversible_plies`, so the game state is Markovian and all king cycles terminate at the reversible-ply limit.

The 5×5 board is the smallest square board on which short-jump multi-captures can occur: for example, the path `(0,0)→(2,2)→(4,4)` captures pieces on `(1,1)` and `(3,3)`. A 4×4 board cannot exercise this rule because every legal jump can only be followed by the reverse jump over the piece just removed. The short-king and no-repetition simplifications keep the state graph finite, the rules state-local, and the move generator auditable. Flying kings, majority capture, or repetition may be introduced later as isolated rule changes; a path-dependent repetition rule must augment the state and solver key with sufficient history.

### L2 — Mini-Jass 6×6

- 18 playable squares;
- six men per side, or a reduced configurable setup;
- international-draughts capture priority can be introduced;
- flying kings can be introduced;
- exact solving may be limited to selected material classes;
- all L1 experiment interfaces remain unchanged.

### L3 — Jass 10×10

Only mechanisms that survive L1 and L2 causal tests should be proposed for production-scale experiments.

## 4. Core design principles

1. **Correctness before strength** — exhaustive tests, deterministic seeds, simple algorithms.
2. **Exact oracle first** — compare learning against minimax truth, not only Elo.
3. **One variable per experiment** — all studies use paired seeds and fixed baselines.
4. **No production coupling** — build standalone; do not risk the Jass core.
5. **Transferable interfaces** — budgets, exploration, replay, and promotion concepts match Jass vocabulary.
6. **Full observability** — every run emits machine-readable config, metrics, checkpoints, and state-level errors.

## 5. Proposed repository structure

```text
mini_jass/
├── README.md
├── CMakeLists.txt
├── configs/
│   ├── l1_baseline.yaml
│   ├── l1_exact_supervised.yaml
│   └── l1_selfplay.yaml
├── src/
│   ├── board.hpp/.cpp
│   ├── movegen.hpp/.cpp
│   ├── rules.hpp/.cpp
│   ├── encode.hpp/.cpp
│   ├── solver.hpp/.cpp
│   ├── search.hpp/.cpp
│   ├── model.hpp/.cpp
│   ├── selfplay.hpp/.cpp
│   ├── replay.hpp/.cpp
│   ├── arena.hpp/.cpp
│   ├── metrics.hpp/.cpp
│   └── main.cpp
├── tools/
│   ├── train.py
│   ├── run_experiment.py
│   ├── compare_runs.py
│   ├── inspect_state.py
│   └── plot_learning.py
├── tests/
│   ├── test_board.cpp
│   ├── test_movegen.cpp
│   ├── test_movegen_reference.cpp
│   ├── test_capture_sequences.cpp
│   ├── test_promotion.cpp
│   ├── test_symmetry.cpp
│   ├── test_state_domain.cpp
│   ├── test_solver.cpp
│   ├── test_targets.py
│   ├── test_splits.py
│   └── test_reproducibility.py
└── artefacts/
    └── .gitkeep
```

`mini_jass/artefacts/` is ignored except for metadata examples. Large datasets and checkpoints must not be committed.

### Hard isolation contract

Isolation from production Jass is a merge-blocking requirement, not a convenience:

- every Mini-Jass source file, header, test, configuration, script, local build preset, generated manifest, and runtime artefact lives under `mini_jass/`;
- Mini-Jass implementation PRs must not modify the root `CMakeLists.txt`, `.github/`, `src/`, `tests/`, `tools/`, `jobs/`, `infra/`, `data/`, `artefacts/`, or any other production Jass path;
- the root Jass build must not call `add_subdirectory(mini_jass)` and Mini-Jass must not be built, tested, installed, or packaged by any existing Jass command;
- Mini-Jass configures independently with `cmake -S mini_jass -B mini_jass/build` and uses only targets prefixed `mini_jass_`, C++ symbols under namespace `mini_jass`, and environment variables prefixed `MINI_JASS_`;
- Mini-Jass must not include headers from, link targets or libraries from, import Python modules from, or invoke executables or scripts in the parent repository;
- Mini-Jass owns its dependencies and later Python environment under its subdirectory; it must not change root dependency manifests, compiler flags, caches, or generated files;
- default outputs are restricted to ignored paths under `mini_jass/build/` and `mini_jass/artefacts/`. An explicit external output directory is allowed only after rejecting the repository root and every production Jass subdirectory;
- implementation commits are checked with a path-scope guard that fails if any changed path is outside `mini_jass/`;
- a clean root Jass checkout and build remain byte-for-byte unaffected when Mini-Jass is absent, unconfigured, configured, built, tested, or removed.

The experiment specification may remain under `docs/experiments/`, but all implementation and generated content obeys the contract above. Any future integration with production Jass requires a separate design, branch, and explicit approval; it is outside this project's scope.

## 6. State representation

For L1, use a compact raw state:

```cpp
struct State {
    uint16_t white_men;
    uint16_t black_men;
    uint16_t white_kings;
    uint16_t black_kings;
    uint8_t side_to_move;
    uint8_t reversible_plies;
};
```

Bits 0 through 12 map to the thirteen playable squares; bits 13 through 15 are unused.

Required invariants:

- piece bitboards are disjoint;
- unused high bits are zero;
- each side has at most two pieces across men and kings;
- White men never persist on squares `{0, 1, 2}` and Black men never persist on `{10, 11, 12}` because promotion is applied before a complete move is stored;
- `side_to_move` is exactly White or Black;
- `reversible_plies` is in `[0, reversible_ply_limit]`, and terminal states are never expanded;
- terminal status is derived only from the complete state and the versioned L1 rules;
- serialization is stable and versioned.

The raw state is the authoritative solver node and its key contains every field above. Rule parameters, square mapping, and schema version are recorded in the solver manifest.

The initial L1 symmetry used for optional canonicalization is a 180° rotation combined with swapping White and Black pieces and swapping the side to move. The square permutation is `0↔12`, `1↔11`, `2↔10`, `3↔9`, `4↔8`, `5↔7`, with `6` fixed; `reversible_plies` is unchanged. The canonical key is the lexicographically smaller stable serialization of the raw state and this transformed state.

Ambiguous names such as `horizontal_reflection` are not accepted in the schema: every enabled symmetry has an explicit square permutation and colour/turn transformation. Further symmetries, such as left-right reflection, remain disabled until their own involution, legal-move equivariance, apply-move equivariance, and terminal-value tests pass. All metrics remain available on both raw and canonical states.

## 7. Exact solver and truth dataset

The L1 solver is the foundation of the project.

Implementation:

- enumerate reachable raw states from the normative initial state;
- include `side_to_move` and `reversible_plies` in every raw solver key;
- deduplicate by raw state first; enable symmetry-canonical storage only after the symmetry equivalence tests pass;
- construct the directed game graph;
- identify terminals;
- solve win/loss/draw by deterministic retrograde analysis;
- compute exact distance-to-conversion where meaningful;
- store optimal move set for every solved state.

The L1 rules make the graph finite without path-dependent terminal conditions: captures reduce material, man moves are directionally irreversible, and potentially cyclic quiet king moves strictly increase `reversible_plies`. No solver node may depend on traversal history.

Exact values are always from the side-to-move perspective: `+1` is a forced win, `0` a draw, and `-1` a forced loss. A no-piece or no-legal-move terminal has value `-1`; otherwise a reversible-limit terminal has value `0`; and every non-terminal uses `value(s) = max(-value(child))`. `optimal_moves` contains every move attaining that maximum. `dtw` is null for draws; for wins it is the shortest forced win against maximum resistance, and for losses the longest resistance against the opponent's shortest forced win.

Move generation has two implementations:

1. the production bitboard generator used by enumeration and search;
2. a deliberately slow coordinate-based reference generator with separate code paths and no shared direction or jump tables.

The two generators are compared on every structurally valid assignment of up to two pieces per side to the thirteen playable squares, for both sides to move and every man/king assignment. Out-of-domain higher-material states and malformed promotion-rank states are covered by rejection fixtures. Reachability enumeration is not itself the move-generation oracle: a missing production move could otherwise hide the successor that would expose the bug.

Output per state:

```json
{
  "raw_state_id": 123,
  "canonical_state_id": 87,
  "split": "development",
  "value": 1,
  "dtw": 7,
  "legal_moves": [4, 9],
  "optimal_moves": [9],
  "canonical_parent_count": 3
}
```

Required solver validations:

- production and reference generators return the same complete move set;
- every legal successor exists in the graph;
- terminal values match rules;
- the reversible counter has the specified reset/increment behavior on every transition;
- every transition satisfies `value(parent) >= -value(child)`, with equality exactly for the stored optimal moves;
- every winning state has at least one move to a losing successor;
- every losing state has only moves to winning successors;
- every remaining non-terminal state is a draw and draw classification is stable under traversal order;
- raw and canonical graphs have identical values and mapped optimal-move sets;
- solver output hash is deterministic.

## 8. Minimal model

Start with a deliberately small MLP in Python/PyTorch for iteration speed.

Input planes/features:

- 13 white-men bits;
- 13 black-men bits;
- 13 white-kings bits;
- 13 black-kings bits;
- side-to-move scalar;
- normalized reversible-ply count;
- optional legal-move mask for policy head only.

Baseline network:

```text
54 inputs
→ Linear(54, 32) + ReLU
→ Linear(32, 32) + ReLU
├── value head: Linear(32, 1) + tanh
└── policy head: Linear(32, ACTION_SPACE)
```

For the normative 5×5 topology, action vocabulary v1 contains 72 paths: 32 quiet paths, 20 one-jump paths, and 20 two-jump paths. The baseline above therefore has 5,225 trainable parameters and must remain below a hard 5,500-parameter ceiling. A linear model and an 8-hidden-unit model must also be supported as capacity controls.

The in-memory move stores the origin plus one or two ordered landing squares; no L1 move can have more than two jumps because a side has at most two opposing pieces. Quiet moves and one-jump captures have one landing, while two-jump captures have two.

The policy action ID is the index of this complete path in an immutable, lexicographically sorted vocabulary of paths that are legal in at least one structurally valid L1 state. The production and reference generators must produce the same vocabulary. Its exact size, ordered contents, schema version, and hash are stored in the rule and solver manifests and shared unchanged by C++ and Python. The model build reports its exact parameter count and fails the baseline configuration if the vocabulary differs from 72 actions or the model exceeds 5,500 parameters.

## 9. Three learning modes

### Mode A — exact supervised

Create one immutable split manifest over canonical-state equivalence classes. Within each exact W/L/D and material-class stratum, assign classes deterministically by stable hash to 70% train, 15% development, and 15% frozen test. Every raw state in one canonical class belongs to the same split.

Train only on the train split using exact value and optimal-policy targets. Use development metrics for configuration and stopping; read the frozen test split only for a preregistered milestone or final comparison. The split seed, algorithm, solver hash, resulting state counts, and manifest hash are recorded in `split_manifest.json`.

A separate diagnostic named `all-state-fit` may train on every solved state to test representation and model expressivity. It reports memorization error only and must not be presented as unseen-state performance or used for candidate promotion.

For Modes B and C, the split controls access to exact oracle labels, not which positions self-play may visit. Outcome- or search-target training may therefore include a development or frozen-test position without exposing its oracle value. Reports must separately label each state by oracle cohort and by actual training-sample count; `unseen` means zero samples consumed by the trainer, not merely membership in an oracle cohort.

Purpose:

- verify representation and model capacity;
- establish the best achievable approximation error;
- separate model limitations from self-play limitations.

### Mode B — outcome-only self-play

Targets:

- value = final WDL outcome;
- policy = selected self-play move or visit distribution;
- no solver information used for training.

The solver is used only for evaluation.

Purpose:

- observe whether the self-play loop discovers correct knowledge;
- measure target noise and blind spots.

### Mode C — search-improved self-play

Targets:

- value and/or policy produced by bounded search;
- configurable node budget;
- optional terminal bootstrap;
- no exact oracle leakage.

Purpose:

- reproduce the production Jass principle at tiny scale;
- decompose gains from search and network learning.

## 10. Search and budget controls

Implement a simple negamax alpha-beta first. MCTS may be added only after the alpha-beta laboratory is stable.

Every search call records:

- node budget requested;
- nodes consumed;
- depth reached;
- branching factor;
- terminal hits;
- leaf model evaluations;
- selected move;
- root score and root move scores.

Supported budget policies:

- fixed depth;
- fixed nodes;
- uniformly sampled node budget;
- log-uniform sampled node budget;
- curriculum by generation;
- position-complexity-conditioned budget;
- mixed-budget batch with a reproducible seed.

Initial budget ladder:

```text
1, 2, 4, 8, 16, 32, 64, 128, 256 nodes
```

## 11. Replay and exploration controls

Replay controls:

- buffer disabled;
- FIFO capacity;
- uniform sampling;
- recency-weighted sampling;
- hard-position sampling by oracle error, diagnostic only;
- generation mixture ratios;
- duplicate-state rate reporting.

Exploration controls:

- greedy;
- epsilon-greedy;
- top-K uniform;
- top-K softmax;
- temperature schedule;
- root score noise, disabled by default;
- deterministic paired-seed mode.

Top-K experiments must report whether diversity comes from genuinely new states or merely different visits to already-covered states.

Modes B and C must never use exact oracle values, oracle errors, test-split membership, or optimal moves for target construction, sampling, replay weighting, exploration, or training early stopping. Oracle information is restricted to development-set evaluation and the explicit promotion gate below. Oracle-hard sampling runs are labelled diagnostic and are excluded from clean self-play claims.

## 12. Required metrics

### Oracle metrics

- value mean absolute error versus exact value;
- value mean squared error on the scalar outcome `z ∈ {-1, 0, 1}`;
- value calibration by predicted-value bucket, reporting mean prediction, mean exact outcome, and count per bucket;
- exact value-sign accuracy;
- optimal-move top-1 accuracy;
- optimal-set probability mass;
- policy cross-entropy versus uniform optimal target;
- regret of selected move in exact game-theoretic value;
- error by distance to terminal;
- error by material class;
- error by state visit frequency.

Every oracle metric is labelled with its train, development, frozen-test, or all-state population. A multiclass Brier score is reported only if a later model exposes normalized W/D/L probabilities; the baseline scalar `tanh` head does not call its squared error a Brier score.

### Coverage metrics

- unique raw states visited;
- unique canonical states visited;
- percentage of reachable solved states visited;
- state-visit entropy;
- legal-action coverage;
- optimal-action coverage;
- oracle performance on states with zero consumed training samples, with the population count;
- duplicate rate in generated samples.

### Learning metrics

- train and validation loss;
- gradient norm;
- parameter norm;
- target disagreement for repeated states;
- replay age distribution;
- wall-clock and CPU time;
- positions generated per second;
- positions trained per second;
- oracle improvement per 1,000 generated positions;
- oracle improvement per CPU-second.

### Arena metrics

- candidate versus parent W/D/L;
- candidate versus random;
- candidate versus exact solver with restricted budget;
- transitive generation matrix;
- Elo shown only as a secondary metric.

Promotion must never depend on Elo alone at L1. The primary gate is oracle improvement.

## 13. Promotion policy

Default candidate promotion requires all of:

1. no regression in development-set exact value-sign accuracy beyond a preregistered tolerance;
2. improved development-set optimal-move probability mass;
3. improved or equal development-set error after stratifying states by actual training-sample count, including the zero-sample cohort when it is non-empty;
4. arena lower confidence bound above the configured threshold;
5. deterministic reproducibility check passes.

A candidate that wins the arena while becoming less correct against the oracle is marked `search/exploitation gain`, not a clean learning promotion.

The frozen test split is not consulted for generation-by-generation promotion. It is evaluated only after the candidate, thresholds, and report procedure are fixed, preventing repeated oracle-based selection from turning the test set into a development set.

## 14. First causal experiment matrix

Run the baseline using at least five paired seeds.

### E0 — pipeline sanity

- `all-state-fit` confirms that the representation and model can memorize the solved graph;
- split exact-supervised training measures generalization from train to development and frozen test;
- confirm the preregistered capacity target for value sign and optimal move prediction on each population;
- confirm target signs and side-to-move handling.

### E1 — self-play learns at all

- outcome-only self-play;
- fixed 16-node search;
- no replay;
- greedy after a short warm-up.

### E2 — fixed depth versus fixed nodes

- equalize measured node consumption as closely as possible;
- compare coverage, target quality, and oracle progress.

### E3 — variable node budget

Arms:

- fixed 32 nodes;
- uniform {8, 16, 32, 64};
- log-uniform 4–128;
- curriculum 8→128.

Primary outcome:

- frozen-test oracle error at equal total nodes, stratified by actual training-sample count and accompanied by the zero-sample population size.

### E4 — top-K exploration

Arms:

- greedy;
- epsilon-greedy;
- top-2 uniform;
- top-3 softmax.

Primary outcomes:

- solved-state coverage;
- unique optimal states reached;
- target quality;
- oracle regret.

### E5 — replay

Arms:

- none;
- FIFO 10k;
- 25% previous-generation replay;
- 50% previous-generation replay;
- oracle-hard sampling for diagnosis only.

### E6 — capacity

- linear;
- hidden 8;
- hidden 32;
- hidden 64.

Purpose: detect underfitting, memorization, and whether search hides model weakness.

## 15. Standard experiment protocol

Each run must emit:

```text
run_dir/
├── config.resolved.yaml
├── environment.json
├── seeds.json
├── rule_manifest.json
├── solver_manifest.json
├── split_manifest.json
├── metrics.jsonl
├── state_errors.parquet
├── coverage.json
├── arena.json
├── checkpoint_best.pt
├── checkpoint_final.pt
└── summary.md
```

Comparisons must:

- use identical initial weights where appropriate;
- use paired game seeds;
- use equal total node budgets, not merely equal game counts;
- report all arms, including failed runs;
- avoid changing more than one causal factor;
- include confidence intervals and raw counts;
- use the same immutable split manifest and distinguish train, development, frozen-test, and all-state metrics;
- select configurations and promotion decisions without consulting the frozen test split;
- record rule-schema, move-encoding, solver-graph, split-manifest, and executable hashes.

## 16. Implementation milestones

### M0 — specification and skeleton

- standalone `mini_jass/` build;
- CLI and config parser;
- deterministic run manifest;
- no integration with production jobs.

### M1 — correct game

- board, move generation, mandatory captures, multi-captures, promotion;
- independent bitboard and coordinate-based move generators;
- exhaustive cross-generator comparison over the complete valid L1 state domain;
- exhaustive per-state and transition invariants;
- hand-authored tactical fixtures.

Gate: zero move-generation discrepancy between independent implementations, including states that are valid but unreachable from the initial position.

### M2 — exact oracle

- complete reachable graph;
- exact W/L/D values and optimal moves;
- raw/canonical symmetry equivalence proof by exhaustive tests;
- deterministic solver manifest and hash.

Gate: all solver invariants pass.

### M3 — exact-supervised baseline

- model and trainer;
- immutable train/development/frozen-test split by canonical-state class;
- separate `all-state-fit` expressivity diagnostic;
- oracle dashboard.

Gate: model demonstrates sufficient capacity to learn the solved game.

### M4 — self-play loop

- generation, replay, search, training, arena, promotion;
- same resolved-config pattern for every run.

Gate: repeated seeded run produces identical artefact hashes where deterministic mode is enabled.

### M5 — first experiment pack

- E1 to E4;
- automatic comparison report;
- recommendation for L2 or Jass 10×10 transfer.

## 17. Non-goals for the first PRs

Do not initially add:

- distributed execution;
- R2 storage;
- CPX62 job templates;
- quantization;
- SIMD optimization;
- production NNUE format compatibility;
- MCTS;
- a graphical interface;
- 10×10 code reuse that complicates correctness;
- flying kings;
- international majority-capture tie-breaking.

These can be introduced only after the L1 oracle loop is stable.

## 18. Reuse from the current repository

Reuse concepts and lightweight utilities, not tightly coupled production code:

- deterministic seed conventions;
- JSONL metric emission;
- candidate/parent vocabulary;
- paired arena methodology;
- resolved configuration manifests;
- report-generation conventions;
- causal A/B discipline already used in L3 experiments.

Avoid copying the current production pipeline wholesale. Its complexity would defeat the purpose of the laboratory.

## 19. Expected answers from Mini-Jass

The project should make the following questions answerable with direct evidence:

1. Does variable node budget improve generalization at equal compute?
2. Does top-K create useful state coverage or only noisier targets?
3. When does replay stabilize learning, and when does it freeze old errors?
4. How much playing strength comes from search versus learned evaluation?
5. Can arena Elo improve while oracle accuracy worsens?
6. Which model capacity is enough for the game graph?
7. At what scale do mechanisms validated on 5×5 stop transferring?
8. Which production Jass parameters are actually causal rather than correlated?

## 20. Recommended first implementation PR

The first code PR should contain only:

- `mini_jass/` CMake skeleton;
- L1 board representation;
- move generator;
- complete-move encoding for multi-captures;
- terminal detection;
- exhaustive state enumerator;
- tests and a CLI command `mini_jass enumerate`.

It should not contain neural training yet.

Acceptance criteria:

- build and tests run locally without GPU;
- the rule manifest fixes square mapping, initial state, capture, promotion, terminal, and reversible-counter semantics;
- all reachable states from the initial L1 position enumerate deterministically;
- the production and independent reference move generators agree over the complete valid L1 state domain;
- every generated move passes apply/undo or copy-apply invariants;
- symmetry transformation commutes with move generation and move application;
- state count and graph hash are printed;
- a second run yields the same state count and graph hash;
- malformed and overlapping bitboards are rejected;
- CI runtime remains small.

## 21. Decision after L1

Proceed to L2 only if:

- solver truth is stable;
- exact-supervised mode proves the representation can express the game;
- self-play demonstrates measurable oracle progress;
- at least one causal mechanism produces a repeatable effect across paired seeds;
- the effect remains visible when compute is equalized.

Otherwise, keep the experiment at L1 and diagnose the learning loop. Scaling an unexplained result is explicitly considered a failure of the laboratory's purpose.
