# Adding a Windows PC to the Jass fleet (WSL2 runner)

Turn a personal **Windows** PC into a Jass GitOps runner scoped to `home-` jobs,
so it joins the fleet alongside the cloud boxes (cpx62/ccx33). Once up, jobs are
scheduled by committing `jobs/queue/home-<id>.sh` from anywhere — the PC picks
them up within 5 minutes and commits results to `jobs/results/`.

> **Scope is mandatory.** A runner with no host filter picks *every* queued job —
> it would race cpx62/ccx33 for their jobs. We bootstrap this box with
> `JASS_HOST_FILTER=home-` so it only ever runs `home-*.sh`. This is wired
> race-free (systemd drop-in installed *before* the timer starts).

## 0. What this box can and cannot run
No shared filesystem between boxes. This runner can only run **self-contained**
jobs: builds, self-play data generation, training on data it generates or that is
committed to the repo. It **cannot** run jobs that need data living only on a
cloud box (e.g. the 0297 cumulative on cpx62) or the big sealed assets not
installed here (egdb bitbase, MTC db, the Scan binary) unless you stage them.

## 1. Install WSL2 + Ubuntu (PowerShell as Administrator)
```powershell
wsl --install -d Ubuntu
```
Reboot if prompted, then open **Ubuntu** from the Start menu and create the
Linux user when asked.

## 2. Enable systemd in WSL (the runner uses a systemd timer)
Inside Ubuntu:
```bash
printf '[boot]\nsystemd=true\n' | sudo tee /etc/wsl.conf
```
Then from **PowerShell**:
```powershell
wsl --shutdown
```
Reopen Ubuntu and confirm systemd is live:
```bash
systemctl is-system-running    # expect "running" or "degraded" (both fine)
```
If this errors, systemd is not active — check the `/etc/wsl.conf` step and that
your WSL is recent (`wsl --version`).

## 3. Bootstrap as a `home-` runner (one command)
```bash
sudo JASS_HOST_FILTER=home- bash -c "curl -sSL https://raw.githubusercontent.com/jfrancoiscollin/jass/main/infra/bootstrap.sh | bash"
```
This installs build deps, clones `/root/jass`, builds, generates an SSH deploy
key, writes the `home-` scope drop-in, and starts the 5-min timer.

## 4. One manual GitHub step (deploy key)
The script prints a public key + a URL. Open
<https://github.com/jfrancoiscollin/jass/settings/keys/new>, paste the key,
tick **Allow write access**, save. (Multiple deploy keys are fine; this is a 3rd
alongside the cloud boxes.) Then verify:
```bash
sudo ssh -T git@github.com         # expect "Hi jfrancoiscollin/jass! ..."
```

## 5. Verify it's live
```bash
systemctl status jass-runner.timer            # timer enabled
journalctl -fu jass-runner.service            # live tick logs
systemctl show jass-runner.service -p Environment | grep home-   # scope applied
```
A smoke job `home-0001-smoke.sh` is already queued — within ~5 min you should see
results land at `jobs/results/home-0001-smoke/` (output.log reports host + CPU).

## 6. Day-to-day
- **It only runs while the PC is on and WSL is running.** A `Persistent=true`
  timer fires one catch-up tick when WSL next starts. Keep an Ubuntu window open,
  or run `wsl` from a startup task, to keep it ticking.
- **Scheduling work for it (from anywhere):** commit `jobs/queue/home-<id>.sh`.
  Always source the pre-flight (`jobs/lib/preflight.sh`) and keep it
  self-contained (see §0).
- **Pause it:** `sudo systemctl stop jass-runner.timer`. Resume: `start`.
- **Update the clone:** the runner hard-resets to `origin/main` each tick, so it
  always runs the latest committed jobs.

## Troubleshooting
- *Runner grabs nothing:* confirm the scope — `systemctl show jass-runner.service
  -p Environment` must show `JASS_HOST_FILTER=home-`, and the job file must be
  named `home-*.sh`.
- *Push fails:* the deploy key isn't added with write access (step 4).
- *systemd missing:* WSL too old or `/etc/wsl.conf` not applied — redo step 2.
