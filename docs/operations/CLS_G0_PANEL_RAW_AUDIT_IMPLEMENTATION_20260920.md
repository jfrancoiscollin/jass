# CLS panel — independent raw audit implementation

Implements only section 4 of `CLS_G0_REJECTION_PANEL_V1_20260920.md` after JFC's
"Allez enchaîne" mandate. Preregistration #1050 is merged; its JSON and all
historical candidates, contracts, verdicts and statistical rules remain unchanged.

## Executable boundary

One bounded audit, 900-second stage / 1,500-second dispatcher ceilings, no new
match, training, evaluation, engine search, G0 probe, alpha, promotion or bake.
This implementation does not admit the 56-game readiness or either main contrast.
Those stages are not implemented here. It never imports `analyze_main` or calls
historical search/game helpers. Successful completion permits preparation of the
already-frozen readiness implementation, not automatic match execution.

## What is verified

Authenticate actual R2 inventories, checksums, successful tuples and pinned
receipts for 2069, 2041, 1341, 2047 and 2049. Check the pinned historical GitOps
status blobs as additional provenance, never as a substitute for raw archives.
Read 2069's compressed trajectories under 64 MiB compressed / 128 MiB expanded
limits. Recompute all 288 pair identities, colour scores, full exact captures,
request telemetry, warmup/scored separation, original alpha 0.05 Hoeffding
interval and cap censoring. The panel's future alpha 0.025 is NOT applied to 2069.

Replay every recorded move in one native HUB batch using only position/apply/fen;
never send go/eval/neteval. Compare every returned board+side with the archive.
Check each distinct final board using native perft(1), which enumerates legal
moves without engine search. Independently reconstruct 25-move and repetition
counters and terminal-before-cap ordering. No historical game is regenerated.
The native legality oracle is the unchanged historical Jass move generator,
not an independent implementation of international-draughts rules; the verifier
and statistical readout are independent of the match harness/analyzer.

Authenticate/decompress exact LOCAL/WDL/CURRICULUM bytes. Verify native source
subtrees and G0 build/probe code continuity, build with the recorded match CMake
options and require the rebuilt match binary identity. Publish the original
fixed-node/fixed-time configuration distinction. Historical per-game model
identity is grounded in authenticated loader/worker provenance; it is not inferred
from the moves alone. Read both complete G0 tables (1,024 input rows per model,
512 paired roots), classify actual depth failures versus attained-depth missing
Exact receipts and retain all 1,024 paired-root records without imputation or
G0 redecision.

## Fail closed and provenance

Any checksum, parsing, legal replay, source/binary, cadence, outcome or census
mismatch blocks readiness. Failure preserves bounded owned-log tails and the
old results. No automatic retry or tolerance change. Temporary files are outside
Git; only owned process groups are cleaned. StageEvidence records all five phases
and zero scientific effects; historical replay counts are reported separately.
The runner remains responsible for published status snapshots. No unattended
ChatGPT monitoring is claimed.

## Validation scope

Local synthetic tests cover exact capture identities, pair completeness, timing,
JSON/gzip bounds, source/model drift, no-clobber, no-search command construction,
subprocess timeout cleanup, original readout reconstruction and both G0 missing
receipt mechanisms. Synthetic trajectories and a mocked legality oracle are NOT
real archived-game or native/R2 proof. CI additionally runs the existing panel
contract tests and Launch-V2 suites through the registered profile. The first
actual CPX62 execution, successful publication and readback are still required.
