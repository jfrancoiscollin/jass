---
applyTo: ".github/workflows/**,infra/**,jobs/**/*.sh,jobs/queue/**,jobs/state/**,jobs/paused/**,jobs/prepared/**,jobs/templates/**,jobs/lib/**"
---

# Runtime, runners, and CI instructions

These files can consume expensive compute or control long-running experiments. Reliability failures here can invalidate otherwise sound science.

## Do not launch by accident

- Editing a launcher/workflow is not permission to run it.
- Do not trigger `workflow_dispatch`, queue CPX/CCX work, or cause external compute as part of a normal code-review/fix task unless the task explicitly authorizes the launch.
- Keep expensive jobs opt-in and preserve existing permission boundaries.

## Sizing and machine facts

- Never infer CPU count from historical throughput. Read `nproc` on the actual target machine when a job runs.
- Do not transport throughput/rate assumptions across machines, model variants, search budgets, or materially different workloads.
- Runtime estimates must be based on a comparable measured rate plus explicit volume/build/fit/gate overhead.
- Prefer a light smoke/sizer before expensive runs when the active task authorizes remote compute.

## Cross-host native binary / ISA safety

- A native executable built on one host is **not portable by assumption** to HOME, CPX, CCX, or any other host. Before executing a foreign native binary, prove compatible architecture/ISA or fail closed.
- Treat exit `132` / `SIGILL` as a technical CPU/ISA incompatibility candidate, never as a scientific result. Record the failing stage and host facts before retrying.
- For cross-host technical diagnostics, prefer a target-host native rebuild from the pinned source SHA with the exact required CMake/build flags. Record source SHA, build flags, target host/CPU facts, and the resulting binary SHA.
- A target-host rebuild is **not byte-identical** to a frozen executable and must not silently replace a byte-frozen executable in a scientific strength contract. It is acceptable only when the preregistered contract permits it or when the run is explicitly technical/diagnostic and has no scientific decision authority.
- When comparing candidate/control cost on a host-native technical build, keep both arms on the same locally built executable and preserve all frozen model/search/runtime inputs. Do not transport absolute wall-clock measurements between hosts as if they were equivalent.
- Before long cross-host work, run both (1) a cheap loader/`hello` smoke and (2) a deterministic tiny invocation of the same hot work path, such as a shallow search on a fixed legal position with the intended runtime options. The second smoke must actually exercise the search/eval path that the long run will use, so host-specific instructions hidden from the loader path fail early.

## Parallel-job safety

- Every parallel generation/A-B shard needs a calibrated timeout so one stuck shard cannot freeze the whole job.
- When a monitor runs in the background, never use a bare `wait` that also waits for the monitor. Track worker PIDs explicitly and wait only for those workers before stopping/joining the monitor.
- Preserve partial-result semantics deliberately: know whether a generator writes incrementally or only at shard completion before adding kill/timeout logic.
- Progress for long jobs should remain observable rather than dark; preserve the repository's progress-reporting convention.

## Scratch, disk, and reporting

- Preserve the required disk-free guard and stale-scratch cleanup for remote jobs where the current runner contract expects them.
- Long-running detached jobs must write live `RESULTS`/`PROGRESS` sources in scratch outside the Git working tree when the runner's periodic hard reset could clobber tracked paths.
- Only materialize/commit final artifacts through the established runner helper/contract.
- Keep key terminal status/verdict information recoverable even if an intermediate result file is lost.

## Fail closed

- `n=0`, missing cells, undersized samples, broken parser output, or failed baseline sanity are errors/inconclusive states, never neutral results.
- A workflow should not continue into fit/gate/promotion logic after a required upstream integrity check failed unless the preregistered protocol explicitly defines that path.
- Make failure status visible and machine-readable.

## Shell and workflow validation

For changed shell/YAML runtime code:

- run shell syntax checks on changed scripts;
- preserve strict/error-aware shell behavior unless a documented command intentionally tolerates failure;
- validate referenced paths, environment variables, outputs, artifacts, and workflow dependencies;
- avoid broad permission increases, new long-lived credentials, or unpinned third-party actions without explicit need;
- add a cheap deterministic smoke/contract test for repaired orchestration bugs when practical.

Prefer the narrowest runtime fix that leaves the scientific contract unchanged.
