# Runner v3 migration: `develop` code, separate control plane, external results

This migration is intentionally staged. Do not delete or strip `main` until the
final cutover gates are green.

## Target invariants

1. Every job executes from a detached worktree pinned to one SHA of `develop`.
2. The runner never commits or pushes to the Jass code repository.
3. Queue, state and lightweight status live in a separate private Git repository.
4. Logs and artifacts live in an external object store; `_SUCCESS` or `_FAILED`
   is uploaded last, after checksum verification.
5. A failed upload does not re-run scientific work. The local spool is retained
   and retried on later ticks.
6. New jobs use `$JASS_CODE_DIR`, `$JASS_RESULT_DIR` and `$JASS_ARTEFACT_DIR`.
   Hard-coded `/root/jass` and `main` references are rejected.

## Components added by this PR

- `infra/runner_v3.py`: split code/control/result runner;
- `infra/jass-runner-v3.service` and `.timer`: dormant parallel systemd units;
- `infra/runner-v3.env.example`: non-secret configuration;
- `infra/secrets.env.example`: secret variable names only;
- `infra/control-plane-seed/`: seed content for `jass-control`;
- `infra/tests/test_runner_v3.py`: unit and filesystem end-to-end tests.

The existing `infra/runner.py` and active `jass-runner.service` are unchanged.

## Required manual prerequisites

Two items cannot be delivered through the Jass repository itself:

1. Create a private repository named `jass-control` and initialize it from
   `infra/control-plane-seed/`.
2. Put object-store credentials on each runner in
   `/etc/jass-runner/secrets.env` (`0600`). Never put credentials in a job or Git.

A separate deploy key is recommended for `jass-control`. GitHub deploy keys are
repository-scoped; use a distinct SSH key/host alias if the existing Jass deploy
key cannot access the control repository.

## Phase 1 — shadow smoke, no production cutover

Prepare two independent clones:

```bash
git clone --branch develop git@github.com:jfrancoiscollin/jass.git /srv/jass/code
git clone git@github.com:jfrancoiscollin/jass-control.git /srv/jass/control
install -d -m 0755 /var/lib/jass-runner
install -d -m 0700 /etc/jass-runner
install -m 0644 /srv/jass/code/infra/runner-v3.env.example /etc/jass-runner/runner-v3.env
install -m 0600 /srv/jass/code/infra/secrets.env.example /etc/jass-runner/secrets.env
```

Edit the two environment files, install `rclone`, then verify connectivity:

```bash
set -a
. /etc/jass-runner/runner-v3.env
. /etc/jass-runner/secrets.env
set +a
rclone lsd "$JASS_OBJSTORE_REMOTE"
```

Install the dormant v3 units without disabling the legacy runner:

```bash
install -m 0644 /srv/jass/code/infra/jass-runner-v3.service /etc/systemd/system/
install -m 0644 /srv/jass/code/infra/jass-runner-v3.timer /etc/systemd/system/
systemctl daemon-reload
```

Copy the smoke script to `jass-control/queue/pending/`, commit and push it. Run
one manual tick while the legacy timer is paused or idle:

```bash
systemctl start jass-runner-v3.service
journalctl -u jass-runner-v3.service -n 100 --no-pager
```

Expected result:

- script moves `pending -> running -> done`;
- `status/smoke-develop-object-store.json` ends in `completed`;
- the status contains `code_ref=develop`, a fixed `code_sha` and `result_uri`;
- the object prefix contains manifest, inventory, checksums, compressed log,
  artifacts and `_SUCCESS`;
- no commit appears on `jass/develop` or `jass/main` from the runner.

## Phase 2 — failure and recovery gates

Before production cutover, validate:

1. A deliberately failing job publishes `_FAILED` and a `failed` status.
2. Removing object-store access yields `upload_failed` without rerunning the job.
3. Restoring access lets the next tick publish the existing spool and changes the
   status to the original final state with `upload_recovered=true`.
4. A host-scoped kill flag terminates a long smoke cleanly.
5. Two consecutive successful jobs run from their recorded `develop` SHAs.

## Phase 3 — service cutover

Only with no legacy job in flight:

```bash
systemctl disable --now jass-runner.timer
systemctl enable --now jass-runner-v3.timer
systemctl list-timers 'jass-runner*'
```

Keep the legacy unit installed for rollback during the observation window.
Rollback is:

```bash
systemctl disable --now jass-runner-v3.timer
systemctl enable --now jass-runner.timer
```

## Phase 4 — tools consolidation

After the v3 service is the sole runner, move active root tools to `jobs/tools/`
and rewrite active references in one dedicated PR. Add CI guards rejecting
`tools/`, `origin/main`, `HEAD:main` and hard-coded `/root/jass` outside archives.
Historical queue scripts remain archived rather than mechanically reactivated.

## Phase 5 — retire `main`

Required gates:

- no active runner reads or writes `main`;
- queue/state/status are exclusively in `jass-control`;
- all new payloads are in the external store;
- historical results selected for retention are indexed/migrated;
- two successful production jobs, kill test and upload-recovery test are green;
- `develop` is the repository default branch.

Then tag the pre-cutover state, make `main` read-only for an observation period,
remove legacy queue/results/state from the code repository, and finally delete
`main`.
