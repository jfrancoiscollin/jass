# Jass Chinook — pause handoff V1

Date: **23 September 2026**  
Status: **PROJECT_PAUSED / CHINOOK_CAUSAL_STRENGTH_NOT_YET_ESTABLISHED**

## Restart point in one sentence

Resume **at the technical repair and exact rerun of the 2081 CHINOOK_HYBRID strength rehearsal**. Do not restart singleton mining, do not retune the gate, and do not jump directly to the 576-game main.

## Completed Chinook evidence

### 2079 — singleton error mining complete

Job: `cpx62-2079-l3-chinook-error-mining-v1`  
Attempt: `20260921T173557Z-b97224af`  
Terminal: `CHINOOK_ERROR_MINING_COMPLETE_V1`

The diagnostic consumed the frozen 512-root Scan reference. The frozen gross-error tail was nominally the top 64 roots, tie-inclusive at **41 centi-Scan**, yielding **65 roots** and a baseline gross-error rate of **0.126953125**.

The strongest singleton motifs included:

- `white_men=5`: support 27, 11 gross errors, rate 0.407407, lift 3.2091;
- `black_men=5`: support 32, 13 gross errors, rate 0.40625, lift 3.2;
- `legal_moves=5-8`: support 87, 31 gross errors, rate 0.356322, lift 2.8067.

This result is `EXPLORATORY_CONSUMED_DATA` only. It authorizes no feature, promotion or causal claim.

### 2080 — fixed interaction audit complete

Job: `cpx62-2080-l3-chinook-interaction-audit-v1`  
Attempt: `20260921T194709Z-c60dfd5a`  
Terminal: `CHINOOK_INTERACTION_AUDIT_COMPLETE_V1`

The strongest of the preregistered fixed interactions was:

`P2_CORE = phase P2 AND legal_moves 5-8 AND side-to-move behind`

with support **29**, **13** gross errors, gross-error rate **0.4482758621**, and lift **3.531034483** over the same baseline. Other strong fixed interactions were `CORE` (lift 3.1236), `MOBILITY_BEHIND` (2.9681) and `PHASE_MOBILITY` (2.9407).

This audit is also descriptive consumed-data analysis only; `scientific_verdict=null`.

## Frozen runtime candidate

The causal runtime candidate was implemented in commit:

`7a3a13679274079055262241c3829f4d1077d1d7`

The evaluator is:

- **CURRICULUM outside the gate**;
- **HIER inside the gate**;
- gate = total pieces **9-19**, legal moves **5-8**, side-to-move strictly behind in weighted material (man=1, king=3).

Frozen models:

- CURRICULUM SHA256: `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`
- HIER SHA256: `95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628`

No blend weight, centipawn bonus, threshold tuning or learned amplitude is part of this candidate.

## Exact point where execution stopped

Job: `cpx62-2081-l3-chinook-hybrid-strength-rehearsal-v1`  
Attempt: `20260921T200839Z-7a3a1367`  
Exit: **2**  
Classification: **TECHNICAL**  
Failure: `STAGE_FAILED:EXECUTE` / `ValueError`  
Last phase: **`build-runtime`**

The recorded stack is:

1. `chinook_hybrid_strength.py:151 main`
2. `cls_g0_strength_calibration.py:157 build`
3. `cls_g0_strength_calibration.py:109 command`
4. `cls_g0_strength_calibration.py:49 need`

The attempt failed before the paired strength stage. Therefore:

- **no scientific Chinook strength verdict exists**;
- the rehearsal readiness terminal was not reached;
- the 288-pair / 576-game main was **not admitted**;
- CHINOOK_HYBRID is neither validated nor rejected by played strength;
- CURRICULUM remains champion.

The root technical reason behind the failing `need()` was not resolved before the project pause. Do not reinterpret this technical failure as negative scientific evidence.

## Exact restart sequence

1. Diagnose and repair only the technical `build-runtime` failure from 2081. Preserve the preregistered science byte-for-byte in meaning: models, gate, seeds, cadence, openings policy, sample sizes and verdict rules.
2. Rerun the exact representative rehearsal: 8 representative openings, self-contrasts only (`CURRICULUM/CURRICULUM` and `CHINOOK_HYBRID/CHINOOK_HYBRID`), no cross-model scientific conclusion.
3. Require the published rehearsal terminal `CHINOOK_HYBRID_STRENGTH_REHEARSAL_READY_V1`, `production_ready=true`, and the normal Launch V2 published round-trip before admitting the main.
4. Only then run the frozen main: **288 colour-reversed pairs / 576 games**, `CHINOOK_HYBRID vs CURRICULUM`, 100 ms/move nominal, one thread, no book, pool seed `2026092121`, order seed `2026092122`.
5. Interpret the preregistered fixed-N paired Hoeffding result. **No automatic promotion, bake or retuning.**

## Pause / restore assets

The verified pause capsule is:

`r2:jass-data/pause/jass-20260922`

The latest pre-purge verification measured approximately **1,442,285,057 bytes / 3,349 objects** in the capsule. It includes the preserved results for 2079, 2080 and the failed 2081 attempt, plus the frozen champion lineage and reference assets required for restart.

Bulk `runs/` and `historical/` are disposable cleanup namespaces and must not be treated as the restart source. The pause capsule plus Git history are the canonical restart basis.

## Invariants at pause

- CURRICULUM remains champion.
- No Chinook strength claim exists yet.
- No automatic promotion or bake.
- No gate retuning from the consumed 2079/2080 data.
- No replay of 2079/2080 as if they were fresh confirmation.
- The next scientific question remains exactly: **does the frozen CHINOOK_HYBRID causal intervention avoid a substantial strength loss versus CURRICULUM under the preregistered main?**
