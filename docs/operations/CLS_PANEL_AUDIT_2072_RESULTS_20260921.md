# CLS panel audit 2072 — authenticated publication

Job `cpx62-2072-l3-cls-g0-panel-historical-audit-publication-retry-v3`, attempt `20260921T053109Z-20a09597`, code `20a09597c6ccdf48829e16287e6ae3efd78d3805` completed on CPX62 with the
authenticated terminal `CLS_G0_PANEL_HISTORICAL_RAW_AUDIT_COMPLETE_V1`. The readback verdict is
`FULL_PIPELINE_REHEARSAL_PASS`; the stage took `54.488958` seconds. The outer
window was `2026-09-21T07:31:13+02:00` to `2026-09-21T07:37:42+02:00` (Europe/Paris), measured at
`389.0` seconds. Original UTC timestamps remain in the companion record.

The publication covers 576 historical games and 1,024 G0 roots. All five
phases completed, all recorded effects are zero, `scientific_verdict` remains
`null`, no match was admitted, and LOCAL/WDL/HIER remain `FAIL`. The frozen
CURRICULUM champion and all model, source, budget, identity, and panel rules
remain unchanged. This audit admission includes no downstream match. Next stage:
`IMPLEMENT_FROZEN_PANEL_READINESS_NO_AUTOMATIC_MATCH`.

The authenticated launch receipt SHA256 is `c490e576800d91d239e191effe52c4bfe4dae3e47d4c4ec1eb7b488af1b0857f`. The terminal
control commit is `1e64c15132d349e618a1e70fcb51faa427a04081` and the terminal status blob is
`1083803748927680f87bd39d185172e3caf43fde`. Attempt timestamp to terminal control commit took
`393` seconds. The launch regression receipt reports
`85` tests, passed, with zero
failures, errors, or skips. Accounting reserves prior 400 + 400 stage seconds
and 400 + 400 dispatcher seconds, plus the new 100-second stage and 700-second
dispatcher limits; these are separate from measured durations.

Raw input readback SHA256: `52780b8b3404c8645f0c8851af95c6bd51b84fd58177296d737b59e345df4b25`.
Persisted companion readback: [`CLS_PANEL_AUDIT_2072_READBACK_20260921.json`](CLS_PANEL_AUDIT_2072_READBACK_20260921.json), SHA256 `a23e9c8e267039531db4b41013bbb1dc322b616b64324297b648a9d7f1751f07`.
