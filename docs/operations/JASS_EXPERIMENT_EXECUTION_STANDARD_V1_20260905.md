# Jass experiment execution standard v1

Date: 2026-09-05  
Status: operational architecture standard; no scientific parameter changes.

## 1. Principle

B2 exposed a repeated engineering failure mode: components were tested separately, but the full chain was not rehearsed on the same runner environment before confirmatory execution. Producer/consumer schema drift, runner path assumptions, CLI drift, publisher artifact ownership and generated-wrapper defects were therefore discovered sequentially on CPX.

The new hard rule is:

> **NO REHEARSAL -> NO FREEZE -> NO FRESH DATA**

A new confirmatory/fresh campaign must not consume fresh data until its complete planned execution path has a successful synthetic/miniature rehearsal.

The already-frozen B2 campaign is grandfathered and finishes without scientific changes. B3 and later new science must use this standard.

## 2. Ownership boundary

### `jass`

Jass owns reusable executable behavior:

- `jass.stage_spec.v1` schema and validation rules;
- the generic stage runner;
- input/output authentication;
- runtime/resource validation;
- process execution and timeout handling;
- producer/consumer contract tests;
- publisher contracts;
- `jass.stage_receipt.v1`;
- synthetic and target-host rehearsal entrypoints.

Jass does **not** own the immutable per-run spec that pins the same Jass commit, because such a document would create a self-referential SHA problem.

### `jass-control`

`jass-control` owns run-specific immutable stage specs and thin dispatch:

1. select the host;
2. pin the exact Jass SHA;
3. store/pin the run-specific stage spec containing that same Jass SHA;
4. invoke the generic Jass stage runner;
5. transport status/receipt.

New control scripts must not patch previous jobs, inject Python, reinterpret schemas or implement scientific compatibility logic.

## 3. Stage spec v1

Every new stage is defined by one immutable JSON object:

`schema = jass.stage_spec.v1`

The schema implementation lives at:

`jobs/specs/stage_spec_v1.schema.json`

Run-specific spec instances normally live in `jass-control/specs/` and pin:

- campaign/stage identity;
- exact Jass commit SHA;
- argv command, with no shell evaluation;
- working directory;
- authenticated inputs;
- required outputs;
- host/nproc/clean-worktree requirements;
- timeouts;
- artifact-directory ownership contract;
- explicit environment inheritance;
- declared scientific side effects;
- required exit code and next stage.

Supported path scopes are `repo`, `result`, and `artifact`.

Command placeholders are limited to:

- `{repo}`
- `{result_dir}`
- `{artifact_dir}`
- `{stage_spec}`

Unknown placeholders fail closed.

## 4. Generic runner

The runner is:

`jobs/tools/run_experiment_stage.py`

It performs:

1. stage-spec validation;
2. repository HEAD authentication and optional clean-worktree check;
3. host/nproc authentication;
4. artifact-directory precondition validation;
5. declared input authentication;
6. sanitized environment construction;
7. one shell-free argv execution;
8. process-group timeout handling;
9. declared output validation;
10. `stage-receipt.json` publication in the result directory.

The runner never pre-populates `JASS_ARTEFACT_DIR`. A publisher may therefore safely require that directory to contain only the outer runner's `runner-launch.json` before publication.

Runner-owned result files are:

- `stage.stdout.log`
- `stage.stderr.log`
- `stage-receipt.json`

The runner supplies these reserved provenance variables to the child stage when the outer runner provided them:

- `JASS_JOB_ID`
- `JASS_ATTEMPT_ID`

They are runner-owned; a stage spec cannot override or request arbitrary `JASS_*` environment variables.

## 5. Stage receipt v1

Every invocation produces:

`schema = jass.stage_receipt.v1`

It records:

- spec SHA256;
- campaign/stage/code SHA;
- start/end/duration;
- state;
- failure class and failure stage;
- exit code and timeout flag;
- whether the declared input set was authenticated, including an empty set;
- output authentication;
- runtime host facts;
- artifact-directory precondition;
- exact argv/cwd;
- stdout/stderr descriptors;
- declared scientific side effects;
- next stage only on success.

A first failure must be diagnosable from the original job. A separate diagnostic job must not be necessary merely to discover where it failed.

## 6. Producer -> consumer contracts

For every serialized boundary `A -> B`, CI must execute B against bytes actually produced by A.

Examples:

- source publisher -> preread;
- teacher -> merge;
- merge -> publisher;
- publisher -> allocation;
- allocation -> projection;
- projection -> readout;
- readout -> terminal statistics;
- terminal readout -> terminal publisher.

Independent unit tests of A and B are insufficient when they share a serialized contract.

Schema changes require a new version or an explicit compatibility contract test. Runtime compatibility shims in `jass-control` are not a long-term mechanism.

## 7. Full-pipeline rehearsal gate

Before a new fresh campaign may freeze:

### Level 1 — CI synthetic rehearsal

Run the complete planned chain on deterministic fixtures.

### Level 2 — target-host smoke

Run the same entrypoints on the real target host with:

- real runner;
- real filesystem paths;
- real R2 fetch/publish path where applicable;
- real native build/EGDB path where applicable;
- miniature data volume.

### Level 3 — terminal rehearsal

The rehearsal must reach the same final publisher used by the full campaign.

Only then may the campaign publish:

`FULL_PIPELINE_REHEARSAL_PASS`

and authorize its scientific freeze/fresh boundary.

## 8. Retry policy

A failed stage is not immediately converted into another ad-hoc wrapper.

Before retry:

1. read the original `stage-receipt.json`;
2. reproduce the failure with the smallest fixture;
3. add a regression/contract test;
4. fix the root cause in Jass when the defect is in Jass;
5. rerun the relevant rehearsal;
6. requeue the unchanged science only after that rehearsal is green.

After two technical failures on the same logical stage, stop campaign retries and classify the problem as infrastructure/framework work.

Target: at most one technical retry per stage.

## 9. New-job prohibitions

For new stage-spec campaigns, do not introduce:

- `sed` patches of previous job scripts;
- inline Python in control-plane shell wrappers;
- runtime dependencies on `queue/done/<old-job>.sh`;
- control-root discovery from staged `BASH_SOURCE`;
- implicit working-directory assumptions;
- ad-hoc R2 transport where a standard fetch contract exists;
- orchestration writes into the artifact directory before its publisher;
- producer/consumer schema repair logic in `jass-control`.

## 10. Definition of Ready for fresh data

All must be true:

- science preregistered;
- implementation merged;
- run-specific stage specs immutable and SHA-pinned;
- producer/consumer contract tests green;
- synthetic full-pipeline rehearsal green;
- target-host full-path smoke green;
- artifact ownership green;
- terminal publisher green;
- code/spec hashes published.

Only then may fresh data be consumed.

## 11. Rollout

### A. Finish current B2

Do not change frozen B2 science. Technical repairs remain versioned and science-neutral.

### B. Harden before B3

Required infrastructure:

1. stage spec v1;
2. generic runner;
3. stage receipt v1;
4. dedicated CI;
5. generic `jass-control` dispatcher;
6. B2 miniature replay through the new framework.

### C. B3 boundary

B3 is the first new scientific stage that must not start until the B2 miniature full-pipeline replay is green under this framework.

C/D/E/F and future campaigns inherit the same rule.

## 12. Reliability targets

- 100% of new stages have a stage spec;
- 100% of serialized interfaces have producer/consumer contract tests;
- 100% of fresh campaigns have end-to-end rehearsal;
- zero generated `sed` repair chains;
- zero inline Python in new control jobs;
- zero dependency on historical `queue/done` scripts;
- zero extra diagnostic job needed to identify the first failure stage;
- >95% target first-pass success rate for full stages.

CPX should execute science, not progressively compile our understanding of orchestration.
