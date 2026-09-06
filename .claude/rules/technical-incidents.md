# Automatic technical-incident register

When a failure is classified as TECHNICAL, update the central incident ledger during the same repair task without waiting for the user to ask.

Canonical source: `docs/operations/TECHNICAL_INCIDENTS_V1.json`.
Generated view: `docs/operations/TECHNICAL_INCIDENT_REGISTER_V1_20260906.md`.
Tool: `python jobs/tools/technical_incident_register.py`.

For PR repairs, add exactly one `JASS_TECHNICAL_INCIDENT` JSON block to the PR body as documented in `.github/instructions/technical-incidents.instructions.md`; CI will auto-feed the ledger/register. Reuse the same `dedupe_key` for later mitigation/closure updates. Keep status MITIGATED until terminal runtime proof exists; only then mark CLOSED.

If the incident is found/fixed in `jass-control` only, create/update the companion record in Jass before considering the task complete. Do not change frozen scientific parameters while repairing or documenting technical incidents.
