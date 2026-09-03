# Claude Code automatic model routing for Jass

These rules apply to Claude Code sessions in this repository. The user should not have to choose models manually.

## Default

The project setting starts the main conversation on `opus`. Treat the main Opus conversation as the orchestrator and final reviewer for science-sensitive work.

Before substantive work, classify the task.

## FAST_TECHNICAL -> `jass-fast`

Delegate proactively to `jass-fast` when the intended behavior is already fixed and the work is bounded and technical, including:

- log, job-state, CI, status, artifact, or failing-test inspection;
- localized root-cause diagnosis;
- small C++/Python/shell/config/parser/runner/harness/CI fixes;
- diagnostics or instrumentation that does not change experimental meaning;
- implementation of an already-decided change;
- targeted existing tests, smoke checks, syntax checks, and deterministic validation;
- mechanical documentation edits that do not reinterpret scientific results.

Give the subagent a narrow task, the relevant invariants, and the validation expected. Do not concurrently edit the same files while it works. Review its evidence and changes before declaring completion.

## DEEP_SCIENTIFIC -> Opus / `jass-scientist`

Keep reasoning on the main Opus conversation or delegate an isolated reasoning workstream to `jass-scientist` when the task involves:

- interpreting scientific results, terminal verdicts, transfer claims, FORCE, Elo/runtime evidence, or causal conclusions;
- preregistration, experiment design, protocol, controls, or information barriers;
- candidate/baseline identity, features/order, data/splits, seeds, budgets, labels, loss/training settings, sample sizes, gates, thresholds, confidence criteria, or verdict mapping;
- model search, tuning/retuning, promotion/bake/champion decisions;
- conflicting evidence or multiple plausible causal explanations;
- broad semantic architecture changes;
- a second failed attempt at the same technical repair;
- any `OPUS_ESCALATION_REQUIRED` returned by `jass-fast`.

## MIXED -> Opus -> Sonnet -> Opus

For mixed tasks:

1. Opus establishes facts, scientific invariants, and the exact allowed change.
2. Delegate the bounded mechanical implementation/diagnostic step to `jass-fast`.
3. Sonnet edits and validates.
4. Opus reviews the diff/results against the active contract.
5. Repeat only with another newly bounded technical step.

Do not ask the user which Claude model to use.

## Fallback

If `jass-fast`, Sonnet, or subagent delegation is unavailable, continue safely on the current Opus-capable conversation with the same narrow scope and validation requirements. Mention the fallback once in the final summary. Do not block the task merely because delegation is unavailable, and never pretend a delegation occurred when it did not.

Automatic model routing does not grant permission to launch remote compute or alter scientific contracts. All existing Jass launch, preregistration, fail-closed, and promotion guardrails in `CLAUDE.md` remain authoritative.
