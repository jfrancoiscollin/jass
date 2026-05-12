# Bootstrap CCX63 — runbook (~10 min)

Quick guide to bring a fresh Hetzner CCX63 (48 vCPU, 192 GB) into
the GitOps rotation as the production data-gen runner.

## 0. Prereqs

- A Hetzner Cloud account
- The current CCX 16GB box (jass-runner@ubuntu-16gb-hel1-2) is still
  reachable but its GitOps timer will be disabled before this box
  joins (via job `0008-stop-runner-on-this-host`)

## 1. Provision the box (Hetzner Cloud Console, ~3 min)

- Image: **Ubuntu 24.04**
- Type: **CCX63** (48 vCPU AMD EPYC dedicated, 192 GB RAM)
- Location: any (Helsinki / Falkenstein / Nuremberg — pick the
  closest to you for ssh latency; doesn't matter for the job)
- SSH key: paste your public key OR set a root password and use it
- Name: e.g. `jass-bigbox`
- Click "Create & Buy now"

Hetzner sends an email with the IP. Note it.

## 2. Bootstrap (one SSH session, ~5 min)

```powershell
ssh root@<CCX63-IP>
# (accept the host key, type the password if you used one)

curl -sSL https://raw.githubusercontent.com/jfrancoiscollin/jass/main/infra/bootstrap.sh | bash
```

`bootstrap.sh` will:
- install build deps + python3
- clone /root/jass at main
- build the jass binary (Release)
- generate a dedicated SSH deploy key for git push
- install + enable the systemd timer

At the end it prints a public key. **Copy the line.**

## 3. Add the deploy key on GitHub (~1 min)

Open: <https://github.com/jfrancoiscollin/jass/settings/keys/new>

- **Title:** `jass-runner@jass-bigbox` (or whatever Hetzner named the box)
- **Key:** paste the line from step 2
- ✅ tick **Allow write access**
- click **Add key**

## 4. Verify (~30 s)

Back in the SSH session:

```bash
ssh -T git@github.com
# expect: "Hi jfrancoiscollin/jass! You've successfully authenticated..."

systemctl status jass-runner.timer --no-pager
# expect: Active: active (waiting)

systemctl list-timers jass-runner.timer
# expect: Trigger: <some time in the next 5 min>

journalctl -fu jass-runner.service
# wait for the next tick — expect to see git fetch + pick_next_job +
# (since the queue is empty for this box at that point) silent return
# Ctrl+C to exit
```

If anything fails here, ping Claude — there's likely a deploy-key
or DNS issue.

## 5. Hand the IP back to Claude

Paste the IP and a "ready" in chat. Claude will then:

1. Merge `0008-stop-runner-on-this-host` → CCX23 disables its timer
   in ~10-15 min
2. Wait until CCX23 confirmed silent
3. Merge `0009-rate-test-bigbox` → ~30 min smoke validates the
   per-CPU rate at 48-shard scale
4. If smoke is OK (records/sec/CPU within 0.45-0.65), merge
   `0010-gen-data-depth20-10M-bigbox` → 4-5 days, 10M records

You'll see all of this in `git log origin/main` plus a
`progress.json` heartbeat every 5 min in
`jobs/results/0010-.../progress.json` so you can watch it grow.

## 6. After the 10M run finishes

- 48 × ~7.9 MB shard files committed under
  `jobs/results/0010-.../artefacts/`
- Final `output.log` has the full rate summary
- Optional: `git pull` locally and merge the shards into one file
  with the inline python from `jobs/queue/0007-rate-test-depth20-v3.sh`

## 7. Decommission

Once happy with the data:

```bash
# On CCX63 itself, OR via Hetzner Cloud Console "Delete server"
shutdown -h now   # then delete in the console to stop billing
```

CCX23 (the small box) can be deleted at any time — its runner is
already disabled at this point.
