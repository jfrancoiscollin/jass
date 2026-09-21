# CLS LOCAL 2075 — authenticated technical completion

The fixed LOCAL admission `cpx62-2075-l3-cls-g0-panel-local-main-v1` /
`20260921T090819Z-e00900ff` completed on CPX62 with exit code 0. The technical
readback authenticates the run and its publication envelope; it deliberately
does not parse or report any score, interval, scientific verdict, or outcome
from LOCAL.

## Technical facts

The run started at 09:08:24 UTC and reached its published terminal at 09:57:00 UTC. Its outer elapsed
time was 2,916 seconds and the stage duration was 2,774.983341 seconds. It
completed with 576 strength games and 59,804 new Jass searches. Scan searches,
self-play games, fits, bakes, promotions, and test-target reads were all zero.
The launch regression suite passed all 49 tests. The stage used four game
workers on a 16-CPU CPX62 host; these are separate counts.

The operational tracking status is `LOCAL_TECHNICAL_COMPLETE_WDL_RELEASE_PENDING`;
this label is not a newly emitted or reinterpreted scientific verdict.
This means the sealed LOCAL technical dependency is complete and WDL 2076 may
be released under its prebound admission. It does not establish a joint result
or change any scientific verdict. WDL remains pending its own authenticated
technical and final joint readback.

Following that technical-only check, control PR #784 released the byte-identical presealed
WDL dispatch. WDL 2076 started at `2026-09-21T10:04:38Z`, attempt
`20260921T100434Z-e00900ff`. The compact proof below preserves the pre-release snapshot;
the current operational state is `LOCAL_TECHNICAL_COMPLETE_WDL_RUNNING`.

## Identities and hashes

The full verified source proof copied from the local verification path has
SHA256
`1cafa1c74e18cf7d488218825c5394cf0a560148347c542e8dbb0defed4ba503`.
The compact companion readback is
[`CLS_PANEL_LOCAL_2075_TECHNICAL_READBACK_20260921.json`](CLS_PANEL_LOCAL_2075_TECHNICAL_READBACK_20260921.json);
its own SHA256 is
`aa1ed9ae70928946d15e03ce051b4d3c6a93eaeb3b5e030e8533d333c6fb059c`, distinct
from the full-source proof hash.

The companion retains all published artifact hashes, the stage receipt identity,
the prebound LOCAL admission, the activation hash, the immutable code SHA, the
opening freeze hash, the launch receipt hash, and the WDL release instruction.
No scientific parameter, candidate, baseline, sample, budget, threshold,
information barrier, or verdict mapping changed.
