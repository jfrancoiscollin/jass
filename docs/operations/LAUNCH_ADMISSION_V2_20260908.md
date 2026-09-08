# Launch admission V2 — executable enforcement, 2026-09-08

Mandate: JFC requests ED3 and a more robust launch process after ED2.
This is TECHNICAL framework work. It does not rewrite frozen ED2 protocols,
attempts, scientific verdicts, model identities or champion status.

## What is enforced

The existing generic stage runner and v1 specs remain byte-identical.
`launch_gate_v2.py` wraps them, using a separate immutable admission document.
The shared control-plane dispatcher must require a pinned admission hash; it must
not silently fall back to the ungated core for new stage-spec jobs. No running
attempt is to be edited. Empty current queues permit cutover without exemptions.
Historic scripts/results in queue/done remain archival and cannot be blindly
requeued through the new dispatcher without a valid admission.

Two modes use the SAME registered command and the SAME spec except for
`environment.set.LAUNCH_MODE`: rehearsal or production. The normalized spec
hash retains code, all other environment entries, source descriptors, outputs,
resources, timeouts, declared effects and argv. Exact code SHA is mandatory:
a new commit, including documentation-only changes, invalidates the receipt;
production may instead keep executing the previously rehearsed immutable SHA.

A production admission must pin a different completed rehearsal job/attempt and
the SHA256 of its launch receipt. Before any production command, the gate uses
the existing `fetch_result_files` verifier to require `_SUCCESS`, outer manifest,
inventory and checksums, and to re-read the actual published stage receipt,
regression report, phase evidence and registered output files. Job/attempt/code/
host and every output hash must agree. A queued/running/failed/missing or merely
self-declared local receipt is insufficient. `FULL_PIPELINE_REHEARSAL_PASS` is
issued only AFTER that successful publication roundtrip, not by the rehearsal
itself before its outer publisher has completed.

The gate checks the host, available CPU count without OpenMP contamination,
interpreter binary, Python/package environment and platform. Both modes run the
profile's mandatory regression suites; empty or skipped suites fail. A profile
must include the generic admission and complete synthetic stage/publisher tests.
The profile is part of the code and independently hash-pinned in the admission.
Required completed phases and actual side-effect counters are checked after the
stage; rehearsal and production have separate explicit maxima.

This is an engineering safety mechanism, not a security sandbox against an
administrator who rewrites the dispatcher. Old bespoke non-stage runners are
not automatically migrated. New control jobs must use the canonical dispatcher;
new arbitrary shell/Python scripts are not authorized by this migration.

## Coverage is scoped, never transitive by wishful thinking

ED3-P0 is a read-only existing-TRAIN audit. Its real target-host rehearsal may
read the same historical inputs because it generates no fresh teacher data,
fits no model and reads no TEST targets. This small whole audit is its own
rehearsal workload. Its receipt cannot authorize an ED3 learner: a learner has
a different command/profile/spec and must implement a full synthetic/development
mode, numerical stress fixtures, native artifact roundtrip, fresh holdout barrier
and its own target-host/publisher proof BEFORE fresh confirmation.

When adding a future profile, register the relevant incident-derived tests,
including numerical/representative-data tests for every new solver. Unit tests
on an easy miniature are not a guarantee of numerical behavior at scale. A
failed optimizer must publish diagnostics, not be converted into a scientific
negative or silently given a looser stopping rule.

## First-failure diagnostics and progress

`StageEvidence` writes a bounded phase checkpoint and a compact running summary
when phases change. A caught failure records exception TYPE plus repository
source basename/function/line, never raw exception messages, environments,
credentials or target values. The gate publishes this information directly in
`attempt-diagnostic.json` and `scientific-summary.json`, which are already in
the runner's GitOps allowlist. Full stderr stays in the normal result store.
A missed/old runner tick remains an observability limitation; a stale running
marker must not be reported as a fresh process observation.

## Validation

Local: new pure-Python admission tests plus the full synthetic ED3 analyzer
producer/consumer chain. Full-repository CI additionally executes the actual v1
stage runner, the complete synthetic ED3 entrypoint, the original result-store
publisher and the original checksum-verifying fetcher, with only network
transport replaced by a local fake rclone. Target-host rehearsal separately uses
actual R2. Missing terminal marker and changed spec are negative tests.

A receipt cannot prove that every bug is impossible. Its purpose is to make
missing, stale, skipped or partial validation reject launch automatically.
