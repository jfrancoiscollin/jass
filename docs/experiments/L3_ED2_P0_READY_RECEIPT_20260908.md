# ED2-P0 terminal receipt — 2026-09-08

Read-only record of the terminal control-plane publication. This document does
not modify the source cohort, labels, protocol, cost thresholds or prior history.

## Authenticated published identity

- Job: `cpx62-1875-l3-ed2-data-teacher-preflight-v1`.
- Attempt: `20260908T171140Z-bc30d685`.
- Code: `bc30d6858c4d590625f8831c4995f055816b95c2`.
- Published state: `completed`, exit `0`.
- Started: `2026-09-08T17:11:45Z`.
- Terminal publication: `2026-09-08T18:10:26Z`.
- Verdict: `ED2_DATA_AND_TEACHER_PREFLIGHT_READY_V1`.
- Source: `jfrancoiscollin/jass-control:status/cpx62-1875-l3-ed2-data-teacher-preflight-v1.json`.
- Terminal status blob: `58be06659039bd97e94556c999fa74fdc549d9ba`.
- Result prefix: `r2:jass-data/runs/cpx62-1875-l3-ed2-data-teacher-preflight-v1/20260908T171140Z-bc30d685`.

The interval above includes orchestration/publication and must not be reported
as pure teacher computation time. The earlier initial-running status is
superseded by this terminal receipt; no kill or duplicate P0 requeue was used.

## Frozen source and measured cost

TRAIN contains 512 parents (64 in each phase/STM cell), TEST 256 (32 per cell),
and calibration 16 (two per cell). There are 4,976 TRAIN children, 2,434 TEST
children and 146 calibration children. All 784 parent endpoints are unique.
Benchmark overlap and between-parent canonical parent/child-footprint overlap
are both zero under the P0 checks.

Source seal SHA256:
`31f763049fef50544bd1cbb240eeb4f51670728ae0697a77e982186df007152c`.

The completed calibration made 51 Scan calls, requesting 4,335,000 nodes.
The reserved full TRAIN/TEST grid requests 760,480,000 Scan nodes before
zero-cost terminal exclusions. The P0 projection is 668.8057645063964 seconds,
with eight workers and safety factor two; it passed the frozen 2,700-second
spending gate. This is a measured projection, not an ETA guarantee.

TRAIN labels, TEST labels, fits, Jass searches and games remain zero at P0.
Its `fit_authorized=false` remains unchanged: P0 itself was preparation only.
The subsequent paired fit is separately authorized by the user's continuation
and the preregistration in Jass #872.

## Continuation and incident boundary

Jass #872 implements POINT versus PARTIAL and #873 adds narrow scratch cleanup.
Control PR #573 queues `cpx62-1876-l3-ed2-paired-value-fit-v1` on frozen code
`27c30b3f5b4bc4ee971bb4acfcf0a423e124f7da`. The stage must reauthenticate the
completed P0 receipt, exact source files and measured spending limits before
any new labels or fit. TEST200k remains forbidden until both candidates are
sealed. No Elo, self-play, promotion or bake is authorized.

TI-021's missing-terminal observability blocker is resolved by this receipt.
The source-level exposure of full `work/src` and `work/build` to whole-run
publication is mitigated for future ED2 jobs by #873. Its causal contribution
to P0's elapsed time is not established without host/stage evidence.
Proof that the new cleanup ran correctly on CPX62 remains pending; do not close
that part of TI-021 on the strength of this unmodified P0 run alone.
