# Stage runner base environment incident — 1823

## Incident

Level-3 rehearsal jobs 1808 and 1823 reached the generic `jass.stage_spec.v1` runner but the inner rehearsal returned exit 4 during EXECUTE. The stage spec intentionally inherited no ambient variables.

## Root cause

`run_experiment_stage.py` constructed the child environment from an empty dictionary. With `environment.inherit=[]`, the stage received neither a usable `PATH` nor the durable `TMPDIR` created by runner-v3. The full-pipeline rehearsal invokes CMake and native build tools. CMake can itself be reached by absolute path/fallback lookup, but without a child `PATH` it cannot resolve the build program/compiler. Removing the runner-owned `TMPDIR` also violates the runner-v3 PrivateTmp durability contract.

## Repair

The generic stage runner now always supplies a deterministic system `PATH=os.defpath` and automatically preserves only the outer runner-owned `TMPDIR` when present. Explicit stage environment declarations remain additive/overriding for normal variables. JASS provenance remains runner-owned. Arbitrary ambient variables are still excluded.

## Regression

`test_sanitized_stage_keeps_system_path_and_runner_tmpdir` exercises `environment.inherit=[]`, requires the child to see the deterministic PATH and durable TMPDIR, and proves an unrelated ambient secret is not inherited.

This is infrastructure only. It changes no B2/B3 science, data, seeds, budgets, gates, model, search or promotion behavior.
