# Stage object-store capability incident 1825 — 2026-09-06

## Incident

`cpx62-1825-l3-decision-math-b2-statistical-completion-recovery-v1` failed before any scientific statistic was evaluated. The outer `runner_v3` correctly forwarded the documented rclone configuration variables into the job environment, but the stage specification declared `environment.inherit=[]`. The strict stage runner therefore removed those credentials before invoking the recovery tool. `rclone` fell back to `/root/.config/rclone/rclone.conf` and could not resolve the `r2` remote.

No B2 scientific evidence was produced by this failure: no new teacher search, fit, strength game, promotion or bake, and no bootstrap/statistical verdict.

## Contract

Object-store access is an explicit stage capability, not ambient authority. A stage that reads or writes the configured Cloudflare R2 remote must declare the exact runner-provided variables it needs in `environment.inherit`:

- `RCLONE_CONFIG_R2_TYPE`
- `RCLONE_CONFIG_R2_PROVIDER`
- `RCLONE_CONFIG_R2_ENDPOINT`
- `RCLONE_CONFIG_R2_ACCESS_KEY_ID`
- `RCLONE_CONFIG_R2_SECRET_ACCESS_KEY`

The stage runner must continue to drop unrelated ambient variables and secrets. Stages without this explicit inheritance must not receive R2 credentials.

## Regression policy

The dedicated stage-runner contract test verifies both directions: declared R2 variables are forwarded unchanged, while undeclared R2 credentials and unrelated secrets are absent. Future remote/capability changes must extend this contract before production use.

This is infrastructure-only. It changes no B2 data, policy (`M5=100`, `M50=60`, `minimum_survivors=2`), seed, bootstrap replication count, threshold, gate or scientific implementation.
