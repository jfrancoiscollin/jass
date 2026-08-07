# Mini-Jass isolation contract

This contract is merge-blocking for every Mini-Jass implementation change.

## Filesystem boundary

All implementation files and default outputs belong under `mini_jass/`. A Mini-Jass implementation commit must not modify any path outside that directory.

Ignored runtime paths are limited to:

- `mini_jass/build/`;
- `mini_jass/artefacts/`;
- `mini_jass/.venv/`;
- `mini_jass/.venv_wsl/`;
- language-local caches under `mini_jass/`.

## Build boundary

Mini-Jass is configured with `mini_jass/CMakeLists.txt`. The repository-root `CMakeLists.txt` must not reference Mini-Jass, and no production Jass command may build, test, install, or package it.

Mini-Jass uses only:

- CMake targets prefixed `mini_jass_`;
- C++ symbols in namespace `mini_jass`;
- environment variables prefixed `MINI_JASS_`.

It does not inherit or mutate production Jass compiler flags, dependencies, caches, generated sources, runtime data, or artefacts.

## Code boundary

Mini-Jass does not include headers from, link libraries or targets from, import modules from, or invoke executables and scripts in the parent repository. Shared code requires a future explicit integration design and is forbidden by default.

## Enforcement

`mini_jass_isolation` fails when:

- the current worktree contains a changed path outside `mini_jass/`;
- the repository-root CMake project contains `add_subdirectory(mini_jass)`.

Review additionally rejects parent-directory includes/imports and unprefixed public targets, symbols, or environment variables.
