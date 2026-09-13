# CPX control plane v1

## Goal

Provide a small operational API on CPX hosts so runner diagnosis and recovery do not depend on a scientific queue job being claimed first.

This is intentionally **not** a remote shell. The API has a fixed allow-list of operations:

- `GET /health` — unauthenticated liveness only;
- `GET /v1/status` — authenticated runner + transient Jass job state;
- `GET /v1/logs?unit=...&lines=N` — authenticated journal tail for the runner or a validated `jass-job-<20 hex>.service` unit;
- `POST /v1/runner/restart` — restart the runner oneshot;
- `POST /v1/job/kill` — TERM one validated Jass transient job unit;
- `POST /v1/server/reboot` — disabled by default and requires both `JASS_CONTROL_ALLOW_REBOOT=1` and `X-Jass-Confirm: REBOOT`.

There is no generic command, shell, path-read, file-write, package-management or arbitrary systemd-unit endpoint.

## Network boundary

The service binds to `127.0.0.1:8765` by default. Do **not** change it to `0.0.0.0` on an Internet-facing host. Remote access must be provided by a separate authenticated transport such as a private tunnel / mTLS gateway. The eventual ChatGPT connector should talk to that transport, not directly to an open root HTTP port.

## Authentication

All `/v1/*` endpoints require:

```
Authorization: Bearer <token>
```

The installer generates a random token at `/etc/jass-control-plane/token` with mode `0600`. The token must never be committed to Git, published in runner status, uploaded to R2, or printed in CI logs.

## Install

On the host, from the checked-out Jass code tree:

```bash
sudo JASS_CODE_DIR=/srv/jass/code bash infra/install_cpx_control_plane.sh
```

The installer compiles/tests the API, installs and enables `jass-control-plane.service`, and checks `/health`. It deliberately does not print the token.

## Example local checks

```bash
curl -s http://127.0.0.1:8765/health
TOKEN="$(sudo cat /etc/jass-control-plane/token)"
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/v1/status
curl -s -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:8765/v1/logs?lines=100'
```

## Audit

Mutating actions and failed authentication attempts append JSON lines to `/var/lib/jass-control-plane/audit.jsonl`. Secrets and authorization headers are not recorded.

## Connector boundary

This server layer alone does not add a new network capability to ChatGPT. A small custom connector/plugin still has to expose the allow-listed API operations to ChatGPT through an authenticated remote transport. Keeping the server and connector separate makes the privileged host surface independently testable and keeps the connector from becoming a general SSH substitute.
