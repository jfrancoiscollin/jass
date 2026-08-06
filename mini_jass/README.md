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
