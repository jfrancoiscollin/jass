---
applyTo: "**"
---

# Automatic technical-incident capitalisation

The user must never have to remind an agent to update the central technical incident register.

Whenever a failure, aborted job, broken preflight, CI/runtime defect, contract mismatch, publication problem, control-plane problem, or similar defect is investigated:

1. classify it explicitly as `TECHNICAL` or `SCIENTIFIC` before changing behavior;
2. if it is `TECHNICAL`, register it automatically as part of the same repair workflow;
3. do not wait for a separate user request to update the register;
4. do not reclassify a scientific negative result as a technical incident merely to make it disappear.

## Canonical mechanism

The canonical source is:

`docs/operations/TECHNICAL_INCIDENTS_V1.json`

The human-readable table in:

`docs/operations/TECHNICAL_INCIDENT_REGISTER_V1_20260906.md`

is generated. Never edit its generated table manually.

For a local/direct repair, use:

`python jobs/tools/technical_incident_register.py record ...`

For a PR-based repair, include exactly one machine-readable block in the PR body:

```text
<!-- JASS_TECHNICAL_INCIDENT
{"dedupe_key":"job:<stable-job-or-incident-key>","context":"<job / context>","symptom":"<observed failure>","root_cause":"<exact understood cause>","invariant":"<durable contract / guard>","evidence":"<tests, PRs, attempts, receipts>","status":"MITIGATED — <terminal proof pending>"}
JASS_TECHNICAL_INCIDENT -->
```

The `technical-incident-register` GitHub Action consumes that block and commits the ledger/register update back to same-repository PR branches automatically.

Use a stable `dedupe_key`. A later PR or update for the same incident must reuse the same key so the existing TI entry is updated rather than duplicated.

## Lifecycle

- New understood technical defect: record it immediately, normally `OPEN` or `MITIGATED — <proof pending>`.
- Code fix merged but runtime proof pending: keep `MITIGATED`.
- Terminal rerun / explicit proof establishes the guard: update the same incident to `CLOSED` and append the proof to `evidence`.
- If the root cause changes materially, update the existing record before deciding whether a distinct incident is justified.

`CLOSED` requires evidence, not optimism.

## Cross-repository control-plane failures

If the repair occurs only in `jass-control`, it still belongs in this central Jass register when it is a project technical incident. The agent handling the repair must create/update the companion Jass incident record (or companion documentation PR) during the same task. Do not end the task with a known technical incident left only in `jass-control` status/history.

## Science boundary

Incident auto-capitalisation may add documentation, tests, guards, compatibility code, or deterministic technical requeues. It does not authorize changing frozen hypotheses, cohorts, seeds, search budgets, thresholds, models, verdict mappings, promotion state, or any other scientific parameter.
