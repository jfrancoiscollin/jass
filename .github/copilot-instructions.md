# Jass — GitHub Copilot repository instructions

These instructions apply to every Copilot task, code review, and cloud-agent change in this repository.

## 1. Establish the active truth before editing

For any non-trivial change, read the relevant current project state before touching code.

Use this precedence:

1. The explicit task/issue/PR instructions for the current work.
2. `docs/L3_CURRENT.md` for the live L3 state and current scientific verdicts.
3. `docs/L3_PURE_PLAN.md` for the normative L3 plan when still applicable.
4. `docs/PROJECT_RESULTS.md` for acquired results and closed directions.
5. `CLAUDE.md` for permanent operational/runtime guardrails.
6. The implementation and tests closest to the code being changed.

Files under `docs/archives/` are historical evidence, not active specifications. Do not update them or resurrect archived decisions unless the task explicitly asks for historical work.

If two sources appear to conflict, do not silently choose the convenient one. Prefer the newer active source, preserve already-published terminal results, and call out the conflict in the PR/task summary.

## 2. Scientific integrity is a hard constraint

Jass is an experimental engine project. A technically valid patch can still be scientifically invalid.

- Never change scientific parameters as a side effect of a refactor, bug fix, cleanup, or CI repair.
- Treat feature sets, data sources/splits, seeds, sample sizes, search budgets, labels, loss definitions, training epochs, stopping rules, gate thresholds, candidate identity, and comparison baselines as scientific parameters unless clearly proven otherwise.
- Never retune after reading outcomes unless the task explicitly authorizes a new experiment/version.
- Never remove a negative result, reinterpret a technical failure as a scientific result, or reinterpret a scientific failure as a technical failure without evidence.
- Preserve preregistered target blindness and information barriers. Selection code must not read forbidden scores, labels, metrics, candidate outputs, or post-selection information.
- Frozen artifacts, recorded hashes, attempts, job IDs, seeds, and terminal verdict strings are immutable historical facts. New work must create a new version rather than rewriting history.
- `CURRICULUM` remains the production champion unless an explicit, separately authorized promotion decision says otherwise. Never auto-promote a candidate because tests or an evaluation look favorable.
- Fail closed when evidence is missing or structurally invalid. `n=0`, undersized cells, parser failures, missing artifacts, or broken baselines are not neutral outcomes.

If satisfying the requested implementation would require changing the science beyond the task mandate, stop that part of the change and explain exactly which scientific assumption would have to change.

## 3. Keep technical fixes causally narrow

When fixing a failure:

- Identify the smallest technical cause first.
- Prefer a patch that preserves the preregistered comparison, candidate, baseline, seeds, and thresholds.
- Do not opportunistically improve adjacent modeling/search behavior in the same patch.
- Add or strengthen a regression/contract test whenever practical.
- Keep unrelated formatting, renaming, and cleanup out of scientific PRs.

For reviews, explicitly flag any diff that can change experimental meaning even if it looks like a harmless constant, default, parser, ordering, filtering, or seed change.

## 4. Remote compute and experiment launching

A GitHub coding/review task does **not** imply permission to spend remote compute.

- Do not queue CPX/CCX jobs, trigger costly experimental workflows, mutate `jass-control`, or launch a new scientific campaign unless the current task explicitly authorizes it.
- Creating or repairing code that *could* launch a job is allowed; actually launching it requires the task mandate.
- Never add an automatic promotion path from CI or experiment output to production champion state.

## 5. Validation expectations

Run the smallest relevant validation before claiming a fix is complete.

- Shell: syntax-check changed shell scripts and preserve strict/error-aware behavior.
- Python: compile/import-check changed scripts and run the closest existing unit/contract tests.
- C++: use the repository's existing build/test conventions from `.github/workflows/build.yml`; avoid inventing a different toolchain or semantic compile flags.
- GitHub Actions: preserve existing permissions/security boundaries and validate YAML plus referenced scripts/paths.
- Scientific tooling: exercise a deterministic smoke/contract path that checks read/write formats and fail-closed behavior when one exists.

Do not claim tests passed unless they were actually run. If an environment limitation prevents a relevant test, state that explicitly.

## 6. Review priorities

When reviewing Jass PRs, prioritize in this order:

1. Scientific-contract violations or leakage.
2. Wrong candidate/baseline/artifact/seed identity.
3. Runtime hangs, silent truncation, `n=0`, partial-data or reporting bugs.
4. Search/eval/move-generation semantic regressions.
5. Reproducibility and determinism regressions.
6. Security/permissions/dependency risks.
7. Ordinary correctness, maintainability, and style.

Be specific: cite the affected file/line, explain the failure mode, and propose the narrowest safe correction.

## 7. Output discipline

At the end of a coding task, summarize:

- what changed;
- which scientific/runtime invariants were preserved;
- tests/checks actually run and their results;
- any unresolved risk or follow-up that was deliberately not included.

Never state or imply that a candidate is promoted, a scientific question is settled, or a remote experiment is running unless the repository evidence and explicit task mandate support that statement.
