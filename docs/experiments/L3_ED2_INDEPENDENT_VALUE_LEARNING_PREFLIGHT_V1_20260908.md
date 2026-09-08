# ED2 — Independent-data value-learning continuation / technical preflight V1

Date: 2026-09-08. Mandate: user's explicit "Ok go pour La suite" after ED1.
Status: **DATA SELECTION AND TEACHER COST PREFLIGHT ONLY IMPLEMENTED HERE.**
No paired fit is implemented or launched by this stage. A ready receipt permits
implementation/preregistration of the paired value fit, not a success claim.

## Immutable motivation and boundary

ED1 `cpx62-1874-l3-ed1-partial-order-audit-openmp-recovery-v1`, attempt
`20260908T161858Z-941faa2d`, code `941faa2df22c08b24cec45694d3277bd4407c0fc`,
ended 2026-09-08T16:24:13Z, exit 0, `ED1_PARTIAL_ORDER_LABEL_SIGNAL_V1`.
On A/B, contradiction rates fell from 0.0749235/0.0783555 to 0.0281145/0.0265373;
parent-average comparison coverage was 0.687316/0.684667. These are exploratory
benchmark diagnostics, not exact-truth, evaluation-improvement or Elo results.
ED1 labels, benchmark scores, and all BASE2000 positions remain training-prohibited.
D4c and J12 terminal negatives remain unchanged; CURRICULUM remains champion.

The learning hypothesis to test next is **partial-order supervision of the value
function**, not learned move ordering: holding architecture, initialization,
optimizer, fit budget and parent weighting constant, can avoiding unstable
teacher inequalities improve held-out decisions without damaging WDL calibration?

## Next paired-fit design (not yet executable)

Use one pair of fits: POINT (all strict Scan50k comparisons) and PARTIAL (only
comparisons with separated Scan5k/50k empirical ranges). Overlaps/touches abstain.
No threshold/temperature/feature sweep and no winner-dependent data selection.
No claim that abstention establishes exact search bounds.

Both start from the same sealed WDL_CONTROL artifact of job 1849. Planned
trainable representation: the existing 120 production extras with native MG/EG
phasing, 240 coefficients; pattern table, geometry, phase mapping and search stay
fixed. This is a value residual added to the frozen baseline, not the D2 pure
policy score. Its eventual serialized evaluator must be tested after quantization
and round-tripped against the native loader. No runtime-cost improvement is claimed
by this preflight. Numeric optimizer/regularization and WDL replay details must be
preregistered in the fit implementation **before any ED2 train teacher labels**.

POINT versus PARTIAL estimates the entire abstention recipe, including removing
labels, not a pure "quality at equal label volume" effect. Parent weights and fit
compute ceilings must match; labels are not independent observations. Report
coverage and corrected versus newly broken decisions. A positive candidate must
beat the frozen baseline too, not merely be less bad than POINT.

The untouched TEST uses Scan200k on **all** siblings, not a selected easy subset.
Primary endpoint is parent-level Scan regret improvement with phase/STM-stratified
paired bootstrap; top-hit, harmful flips and WDL non-inferiority are required
secondary gates. No validation split is needed for a fully frozen single recipe;
TEST cannot select a checkpoint or tune a parameter. Gates, statistical settings,
replay identities and exact fit recipe are reserved for the separate preregistration.
No fit is authorized by an ED2-P0 ready receipt alone. The current continuation
mandate permits preparing that preregistration without asking for another blanket go.
No Elo/self-play/promotion/bake is included.

## Frozen ED2-P0 data contract

New native generator: `jobs/tools/ed2_source.cpp`, pinned to the current Jass source.
No evaluator or search is called. Generate exactly:

| Role | Parents | Parents per phase x STM cell | Seed |
|---|---:|---:|---:|
| Calibration only | 16 | 2 | 202609081101 |
| TRAIN, reserved | 512 | 64 | 202609081102 |
| TEST, sealed | 256 | 32 | 202609081103 |

Eight cells: P0 30..40 pieces, P1 20..29, P2 12..19, P3 9..11; STM 0/1.
Each attempted trajectory restarts at the initial position. Draw one target ply
`8 + mt19937_64()%153`; at each step use `rng()%legal.size()` on native movegen.
Only one endpoint per trajectory is eligible; independent RNG seeds separate roles.
Accept the first structurally eligible endpoints per cell; maximum 2,000,000
attempts per role and a 240-second source cap. Parent has 2..16 legal moves.
No resampling based on scores, model output, teacher timeout, or results.

Before generation, authenticate the 2,000 benchmark parents AND every benchmark
child from `home-1651-l3-scan-ceiling-selection-v1`, attempt
`20260829T133348Z-28e12fba`, using `fetch_result_files.py`. Read board/STM only.
Canonical key = lexicographic minimum of fixed-width 13-hex-digit board fingerprint
(wm:wk:bm:bk:stm) and rotate180+colour-swap with STM inversion.
Reject a candidate if its parent OR any child collides canonically with any
benchmark identity or any already-selected parent's parent/child footprint.
This rejects cross-role sibling/transposition leakage before any teacher read.
Within-parent duplicate child boards remain in the same group, never independent.
The Python consumer independently checks these identities, exact quotas, seeds,
trajectory IDs, child ownership, STM inversion, row counts and zero target bytes.
This proves the specified exclusions, not disjointness from every historical Jass
corpus ever produced. Independent random trajectories can still share early moves.

Publish counted score-free parents/children JNNW, parent/group TSV, source report,
canonical exclusions, and SHA256 `ed2-source-seal.json` **before any calibration**.
Every JNNW target/score byte is zero. Data selection is frozen even if sizing fails.
The 16 calibration parents and their siblings are permanently forbidden for fitting
and scientific assessment, including any future ED2 fit extension.

## Frozen ED2-P0 teacher probe and spending limit

Authenticate the official unmodified Scan 3.1 runtime from
`home-1650-l3-scan-ceiling-preflight-v1`, attempt `20260829T132800Z-28e12fba`:
compiled binary, eval data, ini, build manifest. Verify executable SHA against the
manifest and source commit `7aae17e7b7bfc47744601afb1ee7655e18983ce5`.
Require cpx62, 16 available CPUs measured with OpenMP overrides removed ONLY from
the probe, x86_64 and POPCNT. Numeric library caps stay 1. Compile the native Jass
source on CPX itself; do not transport a -march=native Jass binary from another host.

Only after the data seal: choose the first nonterminal child of each calibration
parent, exactly 16 children; absent support fails closed. Reuse NodeScanEngine's
unaltered Hub contract: book OFF, threads 1, bb-size 0, fresh `new-game` per search,
`go analyze`, requested nodes exactly 5k/50k/200k. Repeat the first child at each
budget to prove deterministic score/move/depth/snapshot replay. Numeric scores
may be compared only within this technical replay, never published or used to
alter selection, label recipe or a scientific model.

Maximum **51 Scan searches, 4,335,000 requested nodes**, with a 30-second per-RPC
cap and 240-second entire probe cap. Stock Scan final node consumption is not
exposed: do not mislabel progressive snapshots as exact consumed totals.
Training teacher calls = 0; TEST teacher calls = 0; fits = 0; games = 0.

Planned later labeling volume (not executed): each TRAIN child at 5k and 50k;
each TEST child at 200k, with TEST targets hidden until both models are sealed.
The worst-case planned requested-node count is **1,269,760,000** (16 children per
parent). This is deliberately reported instead of calling the full run "free".
A measured sizing gate is necessary before committing that work.

Engineering projection = 2 x sum(planned rows per budget x maximum observed
calibration duration at that budget) / 8 workers + 600 seconds for setup/fit.
This is a conservative heuristic, **not a confidence interval or guarantee**;
it is measured on CPX, not extrapolated from HOME. Up to 2,700 seconds gives
`ED2_DATA_AND_TEACHER_PREFLIGHT_READY_V1`; otherwise
`ED2_COMPUTE_REVIEW_REQUIRED_V1`. Missing/corrupt data or tool failures are technical,
not scientific negatives. No N/seed/budget change to make sizing pass.
Full ED2-P0 stage cap 1,800 seconds. No automatic fit or other continuation.

## Tests and deliverables

Pure Python tests: counted-format/target-byte guards; canonical symmetry; malformed
boards; output immutability; exact quotas and budgets; calibration filtering that
cannot read training/test row values; missing support. Dedicated CI additionally
builds and executes the real native producer twice, validates both consumers,
proves byte-identical replay and benchmark exclusion handling, rejects overwrites
and rejects production launch without a benchmark exclusion population.
CI's fixed `smoke` mode uses 1/2/1 endpoints per cell and cannot pass production
seal validation; the remote wrapper always invokes `production`.

Deliverables: authenticated source receipts, frozen source files/seal, measured
teacher timing distribution, planned cost, `ed2-preflight.json`,
`scientific-summary.json`, phase/error logs. A ready preflight is not a positive
learning result. The paired learner, real labels and WDL gate remain to implement.

## Incident closure accompanying this continuation

TI-020 (`ed1-nproc-openmp-preflight-v1`) can be CLOSED: the pinned recovery 1874
passed its unchanged 16-CPU guard, completed exit 0, and published the label seal,
audit readout and terminal ED1 scientific summary. This records technical recovery,
not additional scientific evidence beyond the immutable ED1 result above.
