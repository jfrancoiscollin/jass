# Jass experiment execution standard v1

Date: 2026-09-05  
Status: operational architecture standard; no scientific parameter changes.

## 1. Problem statement

Recent B2 execution exposed a repeated pattern: scientific code and orchestration contracts were individually tested, but the complete chain was not rehearsed on the same runner environment before fresh confirmatory execution. As a result, producer/consumer schema mismatches, runner path assumptions, CLI drift, publisher artifact-directory ownership, and generated-wrapper defects were discovered sequentially on CPX.

This standard changes that boundary.

> **NO REHEARSAL -> NO FREEZE -> NO FRESH DATA**

A new confirmatory or fresh scientific campaign must not consume fresh data until the exact execution path has a successful synthetic/miniature end-to-end rehearsal.

The current frozen B2 campaign is grandfathered and must finish without changing its science. B3 and later new stages must use this standard.

## 2. Ownership boundary

### `jass`

`jass` owns executable behavior:

- stage specifications and schemas;
- input/output authentication;
- runtime/resource validation;
- process execution and timeout handling;
- producer/consumer contract tests;
- publisher contracts;
- machine-readable stage receipts;
- synthetic and CPX rehearsal entrypoints.

### `jass-control`

`jass-control` should become a thin dispatcher:

1. select the host;
2. pin the Jass SHA;
3. pin/pass the stage spec;
4. invoke `jobs/tools/run_experiment_stage.py`;
5. transport the resulting status/receipt.

New control scripts should not patch previous job scripts, inject Python, reinterpret schemas, or implement scientific compatibility logic.

## 3. Stage spec v1

Every new stage is defined by one immutable JSON document using:

`schema = jass.stage_spec.v1`

The machine-readable schema is:

`jobs/specs/stage_spec_v1.schema.json`

The stage spec pins:

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

Command placeholders are deliberately limited to:

- `{repo}`
- `{result_dir}`
- `{artifact_dir}`
- `{stage_spec}`

Unknown placeholders fail closed.

## 4. Generic runner

The generic runner is:

`jobs/tools/run_experiment_stage.py`

It performs this sequence:

1. validate the stage spec;
2. authenticate repository HEAD and optional clean worktree;
3. authenticate host/nproc;
4. require `JASS_ARTEFACT_DIR` to be empty or contain only `runner-launch.json`;
5. authenticate all declared inputs;
6. build a sanitized environment;
7. execute one argv vector with no shell;
8. enforce a process-group timeout;
9. validate all declared outputs;
10. publish `stage-receipt.json` in the result directory.

The runner never pre-populates `JASS_ARTEFACT_DIR`. This prevents the class of failure where an orchestration receipt contaminates a publisher-owned artifact directory.

The runner always owns these files under the result directory:

- `stage.stdout.log`
- `stage.stderr.log`
- `stage-receipt.json`

## 5. Stage receipt v1

Every invocation produces:

`schema = jass.stage_receipt.v1`

The receipt records:

- spec SHA256;
- campaign/stage/code SHA;
- start/end/duration;
- state;
- failure class and failure stage;
- stage exit code and timeout flag;
- input/output authentication results;
- runtime host facts;
- artifact-directory precondition;
- exact argv/cwd;
- stdout/stderr descriptors;
- declared scientific side effects;
- next stage only on success.

A first failure must therefore be diagnosable from the original job. A second diagnostic job must not be required merely to discover where the first job failed.

## 6. Producer -> consumer contracts

For every boundary `A -> B`, CI must exercise B against bytes actually produced by A.

Examples include:

- source publisher -> preread;
- teacher -> merge;
- merge -> publisher;
- publisher -> allocation;
- allocation -> projection;
- projection -> readout;
- readout -> terminal statistics;
- terminal readout -> terminal publisher.

Independent unit tests of A and B are insufficient when a shared serialized contract exists.

Schema changes require a new schema version or an explicit backward-compatible contract test. Runtime shims in `jass-control` are not an acceptable long-term compatibility mechanism.

## 7. Full-pipeline rehearsal gate

Before a new fresh campaign may freeze:

### Level 1: CI synthetic rehearsal

Run the complete planned stage chain on deterministic fixtures.

### Level 2: target-host smoke

Run the same entrypoints on the real target host with:

- real runner;
- real filesystem paths;
- real R2 fetch/publish path where applicable;
- real native build/EGDB path where applicable;
- miniature data volume.

### Level 3: terminal rehearsal

The rehearsal must reach the same final publisher used by the full campaign.

Only then may the campaign publish:

`FULL_PIPELINE_REHEARSAL_PASS`

and authorize the scientific freeze/fresh boundary.

## 8. Retry policy

A failed stage is not immediately converted into another ad-hoc wrapper.

Before retry:

1. use the original `stage-receipt.json` to identify the failure stage;
2. reproduce the failure with the smallest fixture;
3. add a regression/contract test;
4. fix the root cause in `jass` when the defect is in Jass;
5. rerun the relevant rehearsal;
6. then requeue the unchanged science.

After two technical failures on the same logical stage, stop campaign retries and treat the problem as an infrastructure/framework defect.

The target is at most one technical retry per stage.

## 9. New-job prohibitions

For new campaigns using this standard, do not introduce:

- `sed` patches of previous job scripts;
- inline Python in control-plane shell wrappers;
- runtime dependencies on `queue/done/<old-job>.sh`;
- control-root discovery from staged `BASH_SOURCE`;
- implicit working-directory assumptions;
- ad-hoc R2 transport where the standard fetch contract exists;
- writes to the artifact directory before its publisher;
- schema repair logic in `jass-control`.

## 10. Definition of Ready for fresh data

All items must be true:

- scientific preregistration complete;
- implementation merged;
- stage specs versioned;
- producer/consumer contract tests green;
- synthetic full-pipeline rehearsal green;
- target-host full-path smoke green;
- artifact ownership green;
- terminal publisher green;
- code/spec hashes published.

Only then can fresh data be consumed.

## 11. Rollout

### A. Finish current B2

Do not change frozen B2 science. Technical repairs remain versioned and science-neutral.

### B. Harden before B3

Implement and merge:

1. stage spec v1;
2. generic runner;
3. stage receipt v1;
4. dedicated CI;
5. generic control-plane launcher;
6. B2 miniature replay through the new framework.

### C. B3 boundary

B3 is the first new scientific stage that must not start until the B2 miniature full-pipeline replay is green under this framework.

C/D/E/F and future campaigns inherit the same rule.

## 12. Reliability targets

- 100% of new stages have a stage spec;
- 100% of serialized interfaces have a producer/consumer contract test;
- 100% of fresh campaigns have an end-to-end rehearsal;
- zero generated `sed` repair chains;
- zero inline Python in new control jobs;
- zero dependency on historical `queue/done` scripts;
- zero extra diagnostic job needed to identify the first failure stage;
- >95% target first-pass success rate for full stages.

CPX should execute science, not progressively compile our understanding of orchestration.
