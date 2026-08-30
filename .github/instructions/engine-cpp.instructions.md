---
applyTo: "src/**,tests/**,pattern_jass/src/**,pattern_jass/tests/**,pattern_jass/CMakeLists.txt,jobs/tools/search_semantics_preflight_project/**,docs/patches/**,jobs/patches/**,CMakeLists.txt,cmake/**"
---

# Engine C++ instructions

Changes under `src/` can alter move legality, search semantics, evaluation, timing, or experimental labels. Treat them as behavior-sensitive even when the diff looks like a refactor.

## Preserve semantics unless explicitly authorized

- Do not change move generation, capture rules, terminal handling, search/negamax sign conventions, quiescence behavior, bitbase precedence, evaluation perspective, color symmetry, or protocol behavior as incidental cleanup.
- Do not combine a scientific evaluation change with unrelated search/movegen optimizations in the same patch.
- A performance optimization must preserve observable semantics unless the task explicitly defines a new scientific variant.
- Keep deterministic behavior deterministic: avoid introducing iteration-order, threading, RNG, or initialization nondeterminism into experiment-critical paths.

## Candidate integration

- New experimental evaluators/candidates must remain explicitly selectable or feature-gated until a separate promotion decision authorizes production use.
- Do not replace `CURRICULUM` defaults automatically because a new artifact or evaluator exists.
- When loading frozen experimental artifacts, assert identity/shape/order where practical rather than silently accepting a compatible-looking file.
- Do not reconstruct, refit, normalize, or calibrate a frozen candidate inside runtime code unless the active protocol explicitly requires that exact transformation.

## Search/eval correctness

When touching search or evaluation code, check the relevant invariants explicitly:

- score perspective/sign at root, child, negamax, and leaf boundaries;
- terminal and tablebase precedence;
- quiescence entry/exit semantics;
- color-swap/symmetry expectations where applicable;
- time/deadline checks around expensive lazy initialization;
- fresh engine/search state assumptions used by teacher/evaluation tools.

Do not infer a search identity such as `search(depth=1) == max(-eval(child))` unless the actual production search semantics (including quiescence and terminal/TB handling) make that identity valid.

## Build and tests

- Follow the build/test conventions already exercised by `.github/workflows/build.yml` and existing CMake targets.
- Prefer targeted regression tests for the exact semantic boundary being changed, then run the broader relevant suite when feasible.
- Do not claim equivalence from compilation alone for a semantic engine change.
- If a change can affect experimental outputs, note that explicitly in the PR summary even when all tests pass.
