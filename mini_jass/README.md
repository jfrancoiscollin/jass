# Mini-Jass

Mini-Jass is a standalone learning laboratory for exactly solvable 5×5 short-king draughts. It lives inside the Jass repository for source control only; it does not participate in the production Jass build or runtime.

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
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
```

The generated `build/` directory is local and ignored. These commands neither configure nor build production Jass.

## Foundation status

The foundation currently provides:

- the standalone CMake project;
- the normative 5×5 square mapping and initial state;
- state validation and the 180° colour-swapping symmetry;
- rule and isolation tests;
- a small `mini_jass_cli rules` command for inspecting the compiled rule constants.

The next implementation slice adds the production and independent reference move generators, complete-move encoding, exhaustive domain comparison, and reachable-state enumeration.
