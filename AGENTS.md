# AGENTS.md — Jass Codex cost-aware automatic routing policy

These instructions apply to the entire repository. The user should **not** have to choose a model manually. Optimize for the cheapest model that can safely finish each bounded step, while preserving Jass scientific integrity.

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

If sources conflict, preserve terminal/frozen facts and escalate the unresolved decision to the appropriate reasoning tier below.

## 2. Automatic cost-aware model routing — mandatory

Project Codex configuration defines four roles:

- `monitor` = **GPT-5.6 Luna / low**, read-only observation and simple factual lookup.
- `fast` = **GPT-5.6 Luna / medium**, bounded mechanical execution.
- `dev` = **GPT-5.6 Terra / medium**, normal implementation and non-trivial technical debugging.
- `scientist` = **GPT-5.6 Sol / high**, deep science, causality, protocol, and broad semantic architecture.

The root/orchestrator defaults to **GPT-5.6 Terra / low**. Its first responsibility is routing, not doing every task itself. Do not ask the user which model to use.

Choose the **lowest sufficient tier before substantive work**. Escalate only when evidence shows the lower tier is insufficient. After a deep decision is fixed, immediately hand mechanical work back down to Terra or Luna.

### TIER 0 — OBSERVE → `monitor` (Luna low)

Use `monitor` for read-only, bounded work such as:

- job status, queue, attempt, CI, PR, commit, or artifact lookup;
- reading a small known log/status/result and reporting the relevant facts;
- checking whether a process/job is pending/running/completed/failed;
- locating a known file, symbol, marker, SHA, verdict, or exact string;
- compact factual summaries where no causal/scientific interpretation is required.

`monitor` must not edit, launch compute, mutate `jass-control`, or interpret scientific meaning.

### TIER 1 — MECHANICAL → `fast` (Luna medium)

Use `fast` when intended behavior is already fixed and the task is causally narrow, including:

- fixing a typo, CLI flag, path, shell wrapper, config key, import, schema wiring, or deterministic launcher bug;
- small/local shell, Python, C++, runner, harness, CI, parser, or packaging edits;
- adding narrow diagnostics/instrumentation with no semantic change;
- implementing an already-decided small change;
- deterministic technical requeue of an unchanged experiment when execution is already authorized;
- targeted tests/smokes for a bounded repair.

Luna must make the smallest correct diff and must not reinterpret the science.

### TIER 2 — ENGINEERING → `dev` (Terra medium)

Use `dev` for work that is clearly technical but exceeds a Luna-sized task, including:

- multi-file implementation;
- normal C++/Python feature implementation under an already-fixed contract;
- non-trivial debugging with more than one plausible technical hypothesis;
- build/link/runtime problems requiring meaningful code understanding;
- test design beyond a tiny regression test;
- localized refactors where semantics must be proven across several components;
- review/correction of a Luna handoff that failed once or exposed broader technical scope.

A first failed Luna repair normally escalates to Terra, **not Sol**.

### TIER 3 — DEEP SCIENCE → `scientist` (Sol high)

Use Sol only when the task genuinely needs expensive reasoning, including:

- interpreting a scientific result, terminal verdict, transfer claim, Elo/runtime evidence, or causal conclusion;
- preregistration, protocol, experiment design, controls, or information barriers;
- candidate/baseline identity, feature set/order, training data/splits, seeds, budgets, labels, objective, epochs, sample sizes, gates, thresholds, confidence rules, or verdict mapping;
- model search, tuning/retuning, promotion/bake/champion decisions;
- conflicting scientific evidence or multiple plausible causal explanations;
- broad architecture changes whose semantics cannot be locally proven;
- a technical failure that cannot be separated from a scientific boundary.

Do **not** use Sol merely because a technical issue is annoying, repetitive, or has consumed time. Escalate to Sol because the reasoning class requires it.

## 3. Escalation and descent protocol

The normal path is:

`monitor (Luna low) → fast (Luna medium) → dev (Terra medium) → scientist (Sol high)`

Skip tiers only when the task is obviously in a higher class from the start.

Escalation rules:

1. `monitor` discovers an edit is needed → `fast`.
2. `fast` cannot complete one bounded repair, or the fix is broader than expected → `dev`.
3. `dev` discovers a scientific/protocol/causal decision is required → `scientist`.
4. `scientist` fixes the decision/invariants only; implementation returns to `dev` or `fast` whenever possible.

For mixed work:

1. Terra root establishes the immediate facts and cheapest safe route.
2. A lower-tier worker performs the bounded step.
3. Terra root reviews evidence/diff/tests.
4. Sol is invoked only for the unresolved deep decision.
5. Once resolved, execution descends again.

Workers must return explicit escalation markers when leaving scope:

- `TIER_ESCALATION_REQUIRED`
- `TERRA_ESCALATION_REQUIRED`
- `SOL_ESCALATION_REQUIRED`

Never let a cheaper tier guess across a science boundary, and never let an expensive tier continue doing routine mechanics after the deep decision is settled.

## 4. Quota/token hygiene — mandatory

The routing policy exists to reduce Codex quota burn as well as latency.

- Prefer **one delegated worker at a time**. Do not spawn parallel agents for the same question unless independent parallelism is genuinely needed.
- Do not ask multiple models to independently solve the same routine task “for confidence”. Review with the Terra root first.
- Give workers the **smallest causally complete context**: exact files, attempts, invariants, error excerpt, and expected validation. Do not paste entire long histories when a few identifiers suffice.
- Prefer targeted file reads/searches over repository-wide exploration.
- Prefer exact log/error excerpts over full logs unless the failure location is unknown.
- Reuse already-established SHAs, frozen facts, and successful upstream receipts; do not rediscover them every turn.
- Keep reasoning and response verbosity low for monitoring/mechanical work.
- Do not use Sol for status polling, Git operations, routine PR work, deterministic requeues, simple wrappers, documentation mechanics, or known-contract test failures.
- Do not keep Sol alive as an implementation worker after it has produced a bounded engineering contract.
- Do not repeatedly retry the same Luna hypothesis. One failed bounded Luna repair is a signal to move to Terra.

## 5. Availability fallback

Model/sub-agent availability can vary by Codex client/version.

If `monitor` or `fast` cannot spawn with Luna (including a client allow-list/capability mismatch):

1. retry the same bounded task with `dev` / Terra;
2. preserve the same scope and validation contract;
3. do **not** jump directly to Sol;
4. mention the fallback once in the final task summary.

If the `dev` role is unavailable, continue on the Terra root/current capable model with the same bounded scope.

If Sol is required but unavailable, continue only if the current capable model can preserve the scientific boundary; otherwise report the capability blocker rather than silently weakening the reasoning requirement.

If sub-agent tools are unavailable entirely, preserve this tiering semantically with the current model and keep the same escalation discipline. Never pretend delegation happened when it did not.

## 6. Worker execution contracts

Every delegation must include enough context to work safely without re-deciding upstream facts.

All implementation workers must:

- prefer the smallest correct diff; no opportunistic refactor/cleanup;
- never modify scientific parameters to make a test/job/result pass;
- distinguish infrastructure/harness/runtime failure from scientific negative evidence;
- run the smallest relevant existing validation after code/config/script changes;
- never claim a test passed unless it actually ran;
- never launch remote compute merely because code is ready;
- stop the risky part and escalate if a scientific decision becomes necessary.

Expected technical handoff fields:

- `FACTS`
- `ROOT_CAUSE`
- `CHANGES`
- `VALIDATION`
- `RESULT`
- `NEXT_TIER` or `ESCALATION_NEEDED`

## 7. Scientific integrity — hard boundary

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

## 8. Remote compute and control-plane safety

Automatic model routing does not grant compute authorization.

Before queueing CPX/CCX work, mutating `jass-control`, or launching costly workflows:

- obey the current task's explicit mandate;
- obey the active pre-launch sizing/runtime checks in `CLAUDE.md`;
- preserve the preregistered experiment exactly;
- do not bypass a required explicit go unless the current user's task explicitly supersedes that requirement.

A technical requeue is allowed only when the scientific experiment is unchanged and the current task authorizes execution.

## 9. Validation and completion

For modified files, use the repository's existing validation conventions:

- shell: syntax-check changed scripts and exercise the closest smoke/contract path;
- Python: compile/import-check and run closest tests;
- C++: use existing build/test conventions; do not invent semantic compile flags;
- scientific tooling: test deterministic identity, read/write round-trips, fail-closed paths, and non-empty baselines when relevant.

The Terra root/orchestrator is responsible for reviewing lower-tier results. Sol reviews only when the task crosses a science/causal boundary.

At the end of a task, report:

- route used (for example `Luna`, `Luna → Terra`, `Terra`, or `Terra → Sol → Luna`);
- what changed;
- which scientific/runtime invariants were preserved;
- checks/tests actually run and their results;
- any unresolved risk deliberately left untouched.

Do not report a remote job as running, a candidate as promoted, or a scientific question as settled without repository evidence supporting that exact claim.
