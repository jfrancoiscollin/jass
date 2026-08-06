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

### L1 — Mini-Jass 4×4

Recommended initial rules:

- 4×4 board;
- 8 playable dark squares;
- two men per side in the initial position;
- men move one diagonal step forward;
- captures are mandatory;
- multi-capture is mandatory until no continuation exists;
- promotion on the opponent back rank;
- kings move one diagonal step in both directions;
- kings capture by jumping one adjacent opponent piece;
- no flying kings at L1;
- win when the opponent has no piece or no legal move;
- draw after a configurable reversible-ply limit, initially 20 plies;
- deterministic repetition handling.

The simplification to short kings is intentional. It keeps the state graph small and the move generator auditable. Flying kings can be introduced later as an isolated rule change.

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
│   ├── test_capture_sequences.cpp
│   ├── test_promotion.cpp
│   ├── test_symmetry.cpp
│   ├── test_solver.cpp
│   ├── test_targets.py
│   └── test_reproducibility.py
└── artefacts/
    └── .gitkeep
```

`mini_jass/artefacts/` is ignored except for metadata examples. Large datasets and checkpoints must not be committed.

## 6. State representation

For L1, use a compact canonical state:

```cpp
struct State {
    uint8_t white_men;
    uint8_t black_men;
    uint8_t white_kings;
    uint8_t black_kings;
    uint8_t side_to_move;
    uint8_t reversible_plies;
};
```

Each bit maps to one of the eight playable squares.

Required invariants:

- piece bitboards are disjoint;
- unused high bits are zero;
- side to move is explicit;
- terminal and repetition metadata are explicit;
- serialization is stable and versioned.

Canonicalization should optionally use horizontal reflection. All metrics must be available both on raw states and canonical states so symmetry effects remain measurable.

## 7. Exact solver and truth dataset

The L1 solver is the foundation of the project.

Implementation:

- enumerate reachable states from the initial position;
- deduplicate by canonical state key;
- construct the directed game graph;
- identify terminals;
- solve win/loss/draw by retrograde analysis or memoized minimax with cycle handling;
- compute exact distance-to-conversion where meaningful;
- store optimal move set for every solved state.

Output per state:

```json
{
  "state_id": 123,
  "value": 1,
  "dtw": 7,
  "legal_moves": [4, 9],
  "optimal_moves": [9],
  "canonical_parent_count": 3
}
```

Required solver validations:

- every legal successor exists in the graph;
- terminal values match rules;
- negamax consistency holds on acyclic solved transitions;
- every winning state has at least one move to a losing successor;
- every losing state has only moves to winning successors;
- draw-state classification is stable under traversal order;
- solver output hash is deterministic.

## 8. Minimal model

Start with a deliberately small MLP in Python/PyTorch for iteration speed.

Input planes/features:

- 8 white-men bits;
- 8 black-men bits;
- 8 white-kings bits;
- 8 black-kings bits;
- side-to-move scalar;
- normalized reversible-ply count;
- optional legal-move mask for policy head only.

Baseline network:

```text
34 inputs
→ Linear(34, 32) + ReLU
→ Linear(32, 32) + ReLU
├── value head: Linear(32, 1) + tanh
└── policy head: Linear(32, ACTION_SPACE)
```

Target size should remain below roughly 5,000 trainable parameters. A linear model and an 8-hidden-unit model must also be supported as capacity controls.

The action encoding must be fixed-width and versioned. Multi-capture sequences are encoded as complete moves, not individual jumps.

## 9. Three learning modes

### Mode A — exact supervised

Train directly on all solved states using exact value and optimal-policy targets.

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
- hard-position sampling by oracle error;
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

## 12. Required metrics

### Oracle metrics

- value mean absolute error versus exact value;
- value Brier score / calibration by predicted bucket;
- exact value-sign accuracy;
- optimal-move top-1 accuracy;
- optimal-set probability mass;
- policy cross-entropy versus uniform optimal target;
- regret of selected move in exact game-theoretic value;
- error by distance to terminal;
- error by material class;
- error by state visit frequency.

### Coverage metrics

- unique raw states visited;
- unique canonical states visited;
- percentage of reachable solved states visited;
- state-visit entropy;
- legal-action coverage;
- optimal-action coverage;
- unseen-state oracle performance;
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

1. no regression in exact value-sign accuracy beyond tolerance;
2. improved optimal-move probability mass;
3. improved or equal unseen-state error;
4. arena lower confidence bound above the configured threshold;
5. deterministic reproducibility check passes.

A candidate that wins the arena while becoming less correct against the oracle is marked `search/exploitation gain`, not a clean learning promotion.

## 14. First causal experiment matrix

Run the baseline using at least five paired seeds.

### E0 — pipeline sanity

- exact-supervised training;
- confirm near-perfect value sign and optimal move prediction;
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

- unseen-state oracle error at equal total nodes.

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
├── solver_manifest.json
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
- distinguish training-set states from unseen solved states.

## 16. Implementation milestones

### M0 — specification and skeleton

- standalone `mini_jass/` build;
- CLI and config parser;
- deterministic run manifest;
- no integration with production jobs.

### M1 — correct game

- board, move generation, mandatory captures, multi-captures, promotion;
- exhaustive per-state invariants;
- hand-authored tactical fixtures.

Gate: zero move-generation discrepancy across exhaustive reachable-state tests.

### M2 — exact oracle

- complete reachable graph;
- exact W/L/D values and optimal moves;
- deterministic solver manifest and hash.

Gate: all solver invariants pass.

### M3 — exact-supervised baseline

- model and trainer;
- train/validation split by canonical state;
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
7. At what scale do mechanisms validated on 4×4 stop transferring?
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
- all reachable states from the initial L1 position enumerate deterministically;
- every generated move passes apply/undo or copy-apply invariants;
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
