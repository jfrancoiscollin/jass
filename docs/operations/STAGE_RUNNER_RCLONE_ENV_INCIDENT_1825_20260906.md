# Stage runner Rclone environment incident — 1825

Date: 2026-09-06  
Classification: infrastructure / transport only; frozen B2 science unchanged.

## Incident

B2 statistical-completion recovery job `cpx62-1825-l3-decision-math-b2-statistical-completion-recovery-v1`, attempt `20260906T074458Z-d9d1de72`, terminated with exit code 2 during `RECOVERY` before any fresh scientific read or production bootstrap.

The recovery's first authenticated fetch of the immutable failed 1815 bundle invoked `jobs/tools/fetch_result_files.py`. Its child `rclone` reported that `/root/.config/rclone/rclone.conf` was absent and that remote `r2` had no configured section.

## Proven root cause

Runner-v3 already forwards only its allowlisted Rclone transport environment into the per-attempt `job.env`: `RCLONE_BIN`, `RCLONE_CONF_B64`, `RCLONE_CONFIG`, and native `RCLONE_CONFIG_*` variables. The outer runner also successfully published the failed 1825 result to the `r2:jass-data` result store, proving that object-store transport configuration existed at the runner boundary.

The generic `jass.stage_spec.v1` runner then rebuilt the inner stage environment from a sanitized base. After the earlier 1823 repair, that base preserved `PATH` and the runner-owned `TMPDIR`, but it did not preserve the runner's Rclone transport envelope. Because the 1825 stage spec correctly declared `environment.inherit=[]`, the inner recovery process lost all Rclone configuration and fell back to an unconfigured default file.

This is therefore an execution-framework environment propagation defect, not a missing 1815 object and not a B2 policy/data defect.

## Repair

The generic stage runner now preserves exactly the same runner-owned Rclone envelope already allowlisted by runner-v3:

- `RCLONE_BIN`
- `RCLONE_CONF_B64`
- `RCLONE_CONFIG`
- every native `RCLONE_CONFIG_*` variable

The sanitized environment contract otherwise remains unchanged. Arbitrary ambient variables are still excluded unless explicitly declared by the stage spec. Existing explicit `environment.inherit` / `environment.set`, durable `TMPDIR`, and runner-owned Jass provenance semantics are unchanged.

## Regression

`jobs/tests/test_run_experiment_stage_rclone_env.py` executes a stage with `environment.inherit=[]` and proves that the complete Rclone envelope reaches the child while an unrelated ambient secret does not.

## Scientific containment

The 1825 attempt reported:

- `fresh_data_reads = 0`
- `new_teacher_searches = 0`
- `fits = 0`
- `strength_games = 0`
- `promotions = 0`
- `bakes = 0`
- `scientific_verdict = null`

No production statistics or bootstrap were reached. No B2 policy, M5/M50/minimum-survivor setting, gate, seed, data, teacher, fit, strength result, promotion, bake, or terminal verdict is changed by this repair. This repair does not authorize a B2 rerun and does not authorize or start B3.
