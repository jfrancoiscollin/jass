# CLS readiness 2073 — technical failure before any game

The unique authorized attempt `cpx62-2073-l3-cls-g0-panel-readiness-v1` /
`20260921T070922Z-54e30b98` failed with exit **2** during launch regressions,
before entering the panel stage. Source SHA:
`54e30b98ece4aa1efda8befd8f5e8f66e5279178`.
**Zero native games and zero searches were started.** No opening seal, stage
receipt or successful readiness proof was produced. The scientific verdict
remains `null`; this is a technical failure, not evidence about model strength.

## Authenticated failure evidence

The R2 `_FAILED` marker, manifest identity, inventory and checksums were verified
with the existing `fetch_result_files.py --expected-state failed` reader. Six
selected files were downloaded and their hashes and sizes verified again locally:
execution evidence, runner launch record, regression report, outer manifest,
metadata and exit code. No environment file was read or copied.

- Publisher manifest SHA256:
  `dca78e63970b57e02700f62dcf2fd540dcba287db14b2d25b0200c92ddebee03`.
- Failure execution evidence SHA256:
  `986a9975862460dcce3b4727fcf8e37e539868922d1f5c7ad4c3da25b2a20031`.
- Regression report SHA256:
  `0c1c9e5e01a523a277a5735389cde179dc5a93590cc8aefab1fe4fca70ea75b3`.
- Terminal control commit:
  `7194f3c3f1ddcddc895c596aebb302b9da0c0431`; status blob:
  `70ad8edbe46bb65bf7aca8d8967b21033f31ee90`.
- [Persisted readback](CLS_PANEL_READINESS_2073_READBACK_20260921.json), SHA256:
  `2627d8ef1e477584032dff12205083386db25d09a85ab7a3cd4c24a38e13da46`.

Started at **09:09:27 Europe/Paris** on 21 September 2026. The publisher manifest
ended at **09:14:28** (301 seconds); the terminal GitOps status followed at
**09:14:32** (305 seconds from start). These durations include the runner's
finalization interval, not native play. The regression log reports **42 tests
in 3.603 seconds**, one error, no failures or skips. All eight recorded effect
counters are zero and no panel phase completed.

## Cause and bounded correction

`test_gate_core_transport_and_corrupt_payload_refusal` used a fake subprocess
transport matching only the literal executable `rclone`. The real reader accepts
`RCLONE_BIN`; the CPX62 runner configuration sets it to `/usr/bin/rclone`.
That command escaped the fixture and reached the host. The synthetic `_SUCCESS`
read returned empty bytes, which the real reader correctly rejected. An inherited
nondefault executable reproduces the fixture bypass locally.

The fixture now owns `RCLONE_BIN=fixture-rclone`, checks the synthetic R2 prefix,
and rejects every unexpected subprocess instead of falling through to the host.
The real envelope parser, identity checks, checksum verification and tampered
payload refusal remain exercised. Existing panel CI now loads the **exact ordered
six-module launch suite** from the profile, including the two V2 prerequisites
previously absent from that CI job. No workflow, production code, launch profile,
generic V2 behavior or frozen scientific contract is changed.

Validation: **51 focused local tests passed**, Python compilation succeeded, and
**81 launch profiles** validated. Linux CI for the exact launch suite is pending.
The original source had passed 99 panel tests and full-chain/native/WASM CI before
admission; those successes did not cover this inherited executable setting.
The defect and guardrail are recorded as **TI-089**; **TI-088** remains mitigated
without a successful real readiness proof. The amendment's existing mojibake
was restored to UTF-8 without changing its scientific clauses.

## Admission boundary

Source PR [#1056](https://github.com/jfrancoiscollin/jass/pull/1056), dispatcher
PR [#780](https://github.com/jfrancoiscollin/jass-control/pull/780) and unique
readiness admission [#781](https://github.com/jfrancoiscollin/jass-control/pull/781)
are merged. Their authorization was exercised by 2073. The frozen V1 contract
allows no automatic retry; zero games consumed does not reset that rule or permit
a new source SHA to reuse the failed admission. No replacement job is queued.

The panel is blocked without a joint verdict. LOCAL/CURRICULUM and WDL/CURRICULUM
remain unlaunched and unadmitted. Any proposed new attempt requires a separately
reviewed amendment and explicit authorization. Frozen model/native identities,
seeds, exclusions, budgets, thresholds, historical G0 FAILs, audit 2072 and the
CURRICULUM champion remain unchanged. No training, promotion or bake occurred.
