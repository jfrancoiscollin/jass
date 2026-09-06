# B2 legacy support JSON compatibility after 1829

Date: 2026-09-06

## Incident

Full frozen B2 statistical-completion job
`cpx62-1829-l3-decision-math-b2-statistical-completion-exact-zero-compat-v2`,
attempt `20260906T103258Z-6f85af21`, stopped technically before production
statistics with:

```text
failure_stage = RECOVERY
ReadoutError: terminal input authentication failed: non-canonical JSON: .../terminal-bundle/verified-historical.json
```

The attempt produced no scientific verdict and reported zero fresh data reads,
new teacher searches, fits, strength games, promotions and bakes.

## Root cause

The immutable historical-support JSON was produced before the current B2 terminal
contract required compact sorted-key canonical JSON. Its bytes are valid JSON and
are part of the frozen support evidence, but the current terminal authenticator
rejects the legacy whitespace/key-layout serialization before evaluating its
support semantics.

This is a serialization compatibility defect at the historical-evidence boundary.
It is not a B2 data, teacher, allocation, policy, support-gate, bootstrap,
statistical or verdict failure.

## Normative repair boundary

The recovery must not rewrite or canonicalize frozen support evidence. Instead a
process-local compatibility adapter may accept non-canonical formatting only for
these three immutable support artefact basenames:

- `verified-historical.json`
- `source-manifest.json`
- `legacy-terminal-summary.json`

The adapter must:

1. first invoke the exact frozen canonical parser;
2. activate only when that parser fails specifically for non-canonical JSON and
   the basename is in the closed allowlist above;
3. parse strict JSON with duplicate-key and non-finite-value rejection preserved;
4. require an object root;
5. return the original raw bytes unchanged so descriptor SHA256/size identity is
   preserved;
6. leave every other JSON input on the exact frozen canonical contract.

The exact-zero-cost compatibility, immutable 4,000-parent cohort/8x500 cells,
teacher observations, policy 100/60/2, all support/scientific gates, bootstrap
R=200000 and seed=2026110717, and terminal verdict mapping remain unchanged.

## Regression

`test_adaptive_sibling_b2_legacy_support_json_compat.py` proves that:

- an allowlisted pretty-serialized legacy object is accepted without one byte of
  rewrite;
- a non-allowlisted pretty JSON remains rejected;
- duplicate keys remain rejected;
- canonical support JSON still traverses the original parser;
- the v3 recovery entrypoint executes by path without relying on `PYTHONPATH`.

No new data, teacher, model, fit, strength evaluation, promotion or bake is
introduced. B3 remains unauthorized and must not be started automatically.
