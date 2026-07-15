# Jass control plane

This directory seeds the private `jass-control` repository used by
`infra/runner_v3.py`.

Layout:

- `queue/pending/`: reviewed job scripts waiting to be claimed;
- `queue/running/`: scripts atomically claimed by a runner;
- `queue/done/`: immutable executed scripts;
- `status/`: lightweight JSON pointers to the external result store;
- `state/`: pause, kill and per-host routing flags.

A v3 job must use the environment provided by the runner:

```bash
cd "$JASS_CODE_DIR"
mkdir -p "$JASS_ARTEFACT_DIR"
# write outputs under $JASS_ARTEFACT_DIR
```

Hard-coded `/root/jass` and references to `main` are rejected by default.
Payload logs and artifacts never belong in this repository.
