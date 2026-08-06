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
