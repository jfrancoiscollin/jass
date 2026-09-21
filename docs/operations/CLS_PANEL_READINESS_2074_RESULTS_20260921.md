# CLS readiness 2074 — authenticated panel proof

The single authorized replacement attempt `cpx62-2074-l3-cls-g0-panel-readiness-authorized-v2` /
`20260921T083944Z-e00900ff` completed on CPX62 with exit code 0 and the authenticated terminal
`CLS_G0_PANEL_READINESS_V2_COMPLETE_MAIN_NOT_AUTHORIZED`. That readiness admission covered
only readiness; the scientific verdict remains `null`. The user's standing authorization is
recorded separately for the fixed main admissions below.

## Bounded result

The sealed readiness stage completed all phases (`authenticate`, `build`, `seal`, `execute`,
`validate`, `publish`) and produced 56 games from 28 pairs, including four deterministic pairs.
The run performed 5,635 new Jass searches, with zero scan searches, fits, bakes, promotions or
self-play games. With predecessor 2073, the cumulative readiness ceiling remains fixed at 56 games
and 9,072 searches; this attempt consumed all 56 games and 5,635 of those searches. No test-target
reads occurred.

The stage lasted 340.137217 seconds; the parallel timed-game block lasted 230.439671671018 s.
The six ordered launch modules ran 49 tests, all passing without skips. Runtime identity was
CPX62, x86_64, 16 CPUs and four game workers. The immutable code was
`e00900ff38e71afa88201871713d4765409c2ac4`: public repair PR #1057 merged at `cd61be73`,
public implementation PR #1058 at `d001d341`, and control admission PR #782 at `6b211977`.
Canonical start `2026-09-21T08:39:49Z` to published terminal `2026-09-21T08:48:22Z`
took 513 seconds (terminal control `8d4852d6ba9b386a2a17889ac02e65be94e2bbd2`).

The readiness projection remains within the frozen main-stage bound: **LOCAL 2,793.110803209336 s**
and **WDL 2,780.972960489006 s**, both below 3,000 s. This is a runtime/readiness projection,
not a gain, promotion, or main-match result.

## Authentication and boundary

The compact public readback is [`CLS_PANEL_READINESS_2074_READBACK_20260921.json`](CLS_PANEL_READINESS_2074_READBACK_20260921.json).
Its full source receipt, independently copied and rehashed locally, has SHA256
`28666787f54b9f0ff195ba3fbd9b96d166c43983300ae9080330caee814f5e43`.
The companion lists all published artifact hashes and the typed readiness identity, including
the opening seal, stage receipt, runtime identity and authenticated prior-attempt exception.

The proof closes the inherited `RCLONE_BIN` fixture incident TI-089: the repaired fixture and
exact launch suite passed under the authenticated readiness run. TI-088 remains `MITIGATED`; its
separate admission/control-plane lifecycle is not reclassified by this readiness result.

The next step is the [distinct fixed main admission](../experiments/CLS_G0_PANEL_FIXED_MAIN_ADMISSION_20260921.md)
under the already granted standing mandate, without another permission request. It uses the
same code/common-plan/readiness/opening identities, prebinds WDL to the LOCAL job and admission
hash, and preserves the no-LOCAL-outcome-peeking barrier. No scientific threshold, sample, budget,
candidate, baseline, or verdict mapping changed. CURRICULUM and the historical G0 FAILs remain
unchanged.
