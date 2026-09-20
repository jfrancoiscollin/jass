# CLS G0 strength study — separate resource admission V2

Date: 2026-09-20. Operational resource amendment under JFC's continuing
resumption mandate. No HIER/CURRICULUM outcome has been generated or read.
This does not change the scientific appendix
`CLS_G0_STRENGTH_VALIDATION_MAIN_V1_20260920.md`, any G0 result or champion.

## Observed resource block, preserved

Representative rehearsal `cpx62-2067-l3-cls-g0-strength-main-rehearsal-v1`,
attempt `20260920T090324Z-553f4511`, code
`553f45111c99ec1852b704bd976dcc1e6f146ce5`, completed with exit 0.
It played exactly 32 same-model games and 3,207 searches including warmups.
All scored-response clock checks passed; zero main-start overlaps; zero
cross-model games. The paired work block measured 153.23255123593844 s,
projecting 2,758.185922246892 s for 288 pairs, versus the 2,700 s planning
allowance. The difference is 58.185922246892 s, about 2.16% of the allowance.
This is a RESOURCE preparation block, not a HIER strength failure or broken
clock. Original terminal remains
`CLS_G0_STRENGTH_MAIN_PREPARATION_BLOCKED_V1`, production_ready=false.
Its launch receipt is
`bc5a4e6d74d41785c2f59001ba456787d592a27f25a52b806a89583bf71aad48`.
The original 2067 receipt must NOT admit production.

## New resource envelope, not threshold rescue

The projected paired-work allowance for the NEW explicitly registered profile
is 3,000 s (50 minutes), within the already fixed 3,600 s stage hard cap.
The dispatcher hard cap stays 4,200 s; workload maximum remains 576 games,
93,312 searches including warmups. No larger game/node workload or harder
resource timeout is authorized. This spends a slightly larger portion of the
existing hard-cap envelope; it is not permission to extend a completed test.
The ordinary V1 entrypoint/default remains 2,700 s and reproduces the original
resource rejection. No frozen document/status is edited in place.

New profile: `cls-g0-strength-main-resource-v2`.
New entrypoint: `jobs/tools/cls_g0_strength_main_resource_v2.py`.
It calls the common apparatus with explicit 3,000 s planning allowance and
pins the exact already sealed 2067 selection digest:
`0a9497f68387b1e0b65a36a9d0da538e9cfd7932167c0d2b0f664e15b81c53c1`.
No new seed, changed starts, score-based filtering or replacement is allowed.
The same eight representative starts are re-exercised solely because new
code/profile require their own Launch-V2 target-host rehearsal. All those
additional self-games/searches are counted; none enters main inference.

Unchanged scientific and runtime quantities: both model SHAs; all 288 main
openings and order; 8 representative starts; native source; 100 ms requested
movetime; 120 ms response ceiling; one depth-1 startpos warmup/player/game;
4 workers; colour pairing; 160-ply censoring; per-game60s/per-pair180s;
100-logistic-Elo loss margin; fixed N288; pair-level Hoeffding interval;
alpha0.05; no interim inference or extension; no promotion/bake/reinjection.

New rehearsal must independently pass all actual native/clock/overlap checks,
match the original selection SHA, satisfy the new planning allowance, and
publish all evidence. Only its authenticated same-code/profile/spec R2
roundtrip may admit production, changing only LAUNCH_MODE. A clock failure
still cannot be rescued by raising 120 ms. A new resource failure is recorded,
not solved by repeatedly rerunning until the measured rate happens to pass.

## Validation

23 focused local tests passed: existing18 plus5 resource-specific tests.
The whole-stage synthetic fixtures explicitly preserve the original 2067
resource rejection and exercise the separate 3,000 s admission. Native/R2
proof is not claimed by local tests. CI additionally executes the existing
calibration and Launch-V2 suites. The added selection pin fails closed.

Record this operational blockage in the technical-incident ledger with its
resource nature explicit. It does not convert any scientific FAIL into PASS.
CURRICULUM remains champion; the eventual main readout remains a coarse,
selected-candidate case study, never a promotion or G0 calibration claim.
