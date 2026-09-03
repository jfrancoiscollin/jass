# AGENTS.md — Jass Codex automatic routing policy

These instructions apply to the entire repository. They are designed so the user does **not** have to choose a model manually.

## 1. Active truth and precedence

Before any non-trivial change, establish the active project truth. Use this precedence:

1. The user's explicit instructions for the current task.
2. The experiment-specific preregistration / terminal result for the work being touched.
3. `docs/L3_CURRENT.md`.
4. `docs/L3_PURE_PLAN.md` when still applicable.
5. `docs/PROJECT_RESULTS.md`.
6. `CLAUDE.md` for permanent operational/runtime guardrails.
7. `.github/copilot-instructions.md` and the relevant `.github/instructions/*.instructions.md`.
8. The implementation and tests closest to the change.

`docs/archives/**` is historical evidence, not active specification. Never rewrite frozen history to make a new result look consistent.

If sources conflict, do not silently choose the convenient interpretation. Preserve terminal/frozen facts and escalate the conflict to the reasoning route below.

## 2. Automatic model routing — mandatory

Project Codex configuration defines two named roles:

- `fast` = `gpt-5.3-codex-spark`, for bounded tactical execution.
- `scientist` = `gpt-5.6-sol` with deep reasoning, for science/causality/architecture.

The root/orchestrator defaults to `gpt-5.6-sol`. Do not ask the user which model to use.

For every substantive request, classify the work **before editing**.

### FAST_TECHNICAL → delegate to the `fast` role

Use the `fast` role for bounded work where intended behavior is already fixed, including:

- inspecting logs, status files, CI output, job artifacts, or a known failing test;
- locating a technical root cause;
- small/local shell, Python, C++, config, parser, runner, harness, or CI fixes;
- adding diagnostics or instrumentation that does not change experimental meaning;
- implementing an already-decided change;
- mechanical documentation edits that do not reinterpret scientific results;
- running existing targeted tests or deterministic smoke/contract checks;
- repairing/requeueing an **unchanged** experiment only when the current task already authorizes remote execution and all launch guardrails are satisfied.

Give the fast agent the smallest causally narrow task that can complete the request plus the relevant invariants and required validation. The root/orchestrator must not edit the same files concurrently while the fast agent is working. Review its evidence, diff, and tests before accepting the result.

### DEEP_SCIENTIFIC → Sol owns the reasoning

Keep the work on the Sol root or delegate it to the `scientist` role when the task involves any of:

- interpreting a scientific result, terminal verdict, transfer claim, Elo/runtime evidence, or causal conclusion;
- preregistration, protocol, experiment design, control selection, or information barriers;
- candidate/baseline identity, feature set/order, training data/splits, seeds, budgets, labels, loss, epochs, sample sizes, gates, thresholds, confidence rules, or verdict mapping;
- model search, tuning/retuning, promotion/bake/champion decisions;
- multiple plausible causal explanations or conflicting evidence;
- architecture changes with broad semantic impact;
- a large or cross-cutting refactor where preserving experimental semantics is non-trivial;
- a second failed attempt at the same technical fix;
- any request from the fast agent to cross a science boundary.

### MIXED tasks → Sol decides, Spark executes, Sol reviews

For mixed work:

1. Sol establishes facts, invariants, and the exact allowed change.
2. Delegate the bounded implementation/diagnostic step to the `fast` role.
3. Spark edits and validates.
4. Sol reviews the diff/results against the scientific contract.
5. Repeat only with a newly bounded technical step.

### Escalation from Spark

If a fast task discovers that it requires a scientific decision, causal interpretation, protocol change, broad semantic refactor, or cannot cleanly separate technical from scientific causes, stop the risky part. The fast agent must return `SOL_ESCALATION_REQUIRED` with evidence. Continue on Sol; do not let Spark guess.

### Availability fallback

If the `fast` role or Spark model is unavailable, at capacity, not entitled for the account, or rejected by the installed Codex client:

1. continue automatically on the Sol root/current capable model;
2. preserve the same narrow scope and validation requirements;
3. mention the fallback once in the final task summary;
4. do **not** ask the user to change model/settings.

If sub-agent tools are unavailable, preserve this routing policy semantically and continue safely with the current model rather than blocking the task. Never pretend delegation happened when it did not.

## 3. Spark execution contract

Every fast delegation must include enough context to work safely without re-deciding the science.

Spark must:

- prefer the smallest correct diff; no opportunistic refactor or cleanup;
- never modify scientific parameters to make a test/job/result pass;
- distinguish infrastructure/harness/runtime failure from scientific negative evidence;
- run the smallest relevant existing validation after any code/config/script change;
- explicitly run tests/checks rather than relying on Spark's lightweight default behavior;
- never claim a test passed unless it actually ran;
- never launch remote compute merely because code is ready;
- stop the risky part and return to Sol if a scientific decision becomes necessary.

Expected fast handoff fields:

- `FACTS`
- `ROOT_CAUSE`
- `CHANGES`
- `VALIDATION`
- `RESULT`
- `ESCALATION_NEEDED` (`yes/no`, with reason)

If Spark makes two unsuccessful attempts on the same failure, stop further patching and escalate to Sol with the evidence collected.

## 4. Scientific integrity — hard boundary

The routing system is an execution optimization, **not** permission to change the science.

Before modifying experiment definitions, jobs, tools, pattern code, datasets, model artifacts, or result documents, read `docs/L3_CURRENT.md`, the relevant preregistration/result document, and `.github/instructions/scientific-experiments.instructions.md`.

Never silently change:

- hypotheses or preregistered comparisons;
- candidate or baseline identity;
- features or feature order;
- data sources, splits, priorities, seeds, or deterministic selection;
- search/teacher budgets;
- labels, optimizer/loss, epochs, batches, stopping rules;
- sample sizes/cells/color or phase balance;
- gates, thresholds, confidence criteria, terminal verdict mapping;
- target-blindness or information-barrier rules;
- frozen hashes, artifacts, attempts, job IDs, terminal verdict strings, or historical results.

No new model search or retuning is allowed unless the current user task explicitly authorizes a new scientific experiment/version.

Never auto-promote or auto-bake a candidate. `CURRICULUM` remains champion unless an explicit authorized promotion decision changes that state.

`n=0`, undersized cells, missing artifacts, parser failures, broken sanity baselines, or incomplete gates fail closed; they are not neutral evidence.

## 5. Remote compute and control-plane safety

Automatic model routing does not grant compute authorization.

Before queueing CPX/CCX work, mutating `jass-control`, or launching costly workflows:

- obey the current task's explicit mandate;
- obey the active pre-launch sizing/runtime checks in `CLAUDE.md`;
- preserve the preregistered experiment exactly;
- do not bypass a required explicit go unless the current user's task explicitly supersedes that requirement.

A technical requeue is allowed only when the scientific experiment is unchanged and the current task authorizes execution.

## 6. Validation and completion

For modified files, use the repository's existing validation conventions:

- shell: syntax-check changed scripts and exercise the closest smoke/contract path;
- Python: compile/import-check and run closest tests;
- C++: use the existing build/test conventions; do not invent semantic compile flags;
- scientific tooling: test deterministic identity, read/write round-trips, fail-closed paths, and non-empty baselines when relevant.

The Sol/root agent is responsible for reviewing a Spark result before declaring completion on science-sensitive work.

At the end of the task, report:

- route used (`Spark`, `Sol`, or `Sol → Spark → Sol`);
- what changed;
- which scientific/runtime invariants were preserved;
- checks/tests actually run and their results;
- any unresolved risk deliberately left untouched.

Do not report a remote job as running, a candidate as promoted, or a scientific question as settled without repository evidence supporting that exact claim.
