# L3 CLS — HIER-L2 next-candidate contract V1

Date: 2026-09-18. Status: **prospective preregistration before any candidate fit, runtime measurement or strength game under this contract**.

## 1. Upstream terminal state

This contract starts only after the already-authenticated CLS diagnosis and the complete CLS-L objective block.

The diagnostic anchor is fixed to:

- bottleneck job `cpx62-2015-l3-cls-bottleneck-classification-production-v1`;
- terminal `CLS_DIAGNOSIS_COMPLETE_V1`;
- classification `mixed`;
- supported axes exactly `SEARCH` and `DECISION-EVAL`;
- immutable CURRICULUM anchor SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

The first CLS-L learning-objective attempt is also terminal:

- recovery job `cpx62-2041-l3-cls-l-valid-arms-recovery-2038-v1` sealed technically valid LOCAL and WDL bytes while MIXED remained `TECHNICAL_FAILED` at the already-frozen L-BFGS `max_iterations=2000`; MIXED is not retuned or retried;
- LOCAL SHA256 `197998003db3d221d38e81577cfa381e8227d67705efc1c86b87205ddebbe450` reached authenticated G0 job `cpx62-2047-l3-cls-g0-local-runtime-rehearsal-v4` and terminated `CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1` because 56 candidate roots lacked the mandatory same-search Exact/full-root `nodes_to_d*` receipt;
- WDL SHA256 `eabe71068dbc6aeb519a61c730d18586e75c8b72308ecd340de08fe2e18deed6` reached authenticated G0 job `cpx62-2049-l3-cls-g0-wdl-runtime-rehearsal-v2` and independently terminated `CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1` because 56 candidate roots lacked the mandatory same-search Exact/full-root `nodes_to_d*` receipt;
- both G0 failures used the frozen FULL-512 cohort/order, 200k budget, parent-defined `d*`, no surrogate, and the immutable CURRICULUM parent/anchor;
- neither arm opened a strength cohort; zero strength games, confirmatory alpha, promotion and bake were authorized.

Therefore the exact LOCAL and WDL bytes are terminal and MUST NOT be retried, recalibrated, refit around the G0 result, or advanced to CLS-S / CLS-E. The failed MIXED arm likewise MUST NOT be rescued by increasing the optimizer iteration cap or changing lambda, L2, corpus, architecture or target recipe.

## 2. Why HIER-L2 is the next independent lever

The master CLS plan named historical `hier-l2` and `CONTEXT_30` candidates for reconsideration only if diagnosis showed evaluation remained actionable. That condition was fixed before the current G0 results and is satisfied by the terminal `DECISION-EVAL` support.

This contract chooses **one new factor only**: hierarchical shrinkage. The choice is not an adaptation to which roots failed LOCAL/WDL and no G0 measurement from those candidates selects a dose, corpus, target, root or search parameter.

The historical HIER preregistration fixed the causal idea that the hierarchical penalty is either absent or equal in strength to the ordinary ridge, with no opportunistic dose sweep. The current production CURRICULUM recipe has `l2=1e-5`; therefore this new contract prospectively fixes exactly:

- CONTROL: `hier_l2 = 0`;
- HIER: `hier_l2 = 1e-5`;
- ordinary `l2 = 1e-5` in both arms.

There is no second HIER dose and no post-result HIER tuning.

## 3. Exact parent and production-recipe anchor

Direct parent and permanent drift sentinel are both the existing production CURRICULUM bytes:

`CURRICULUM SHA256 = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

The authoritative source fit is:

- job `cpx62-1341-jass-megacorpus-arm-d-fit-v1`;
- attempt `20260814T191555Z-18c38a33`;
- code `18c38a33ae78c9c2e8e2df62fca266da28dacead`;
- artifact `artefacts/D-c-prior-then-current.pjtw.gz`;
- terminal state completed / exit 0.

The current candidate fit MUST reproduce that scientific recipe rather than silently substituting the later CLS-L recipe. In both CONTROL and HIER the following remain identical:

- raw TURNOVER source job `home-0977-l3-pure-turnover1to1-train-v1`, attempt `20260726T071254Z-336bb984`;
- raw JNNW SHA256 `9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d`;
- raw JSM SHA256 `acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682`;
- exact CURRENT_2M split from holdout modulus `10`, seed `577215`, 2,000,000 records, byte-matching the authenticated 1340 manifest;
- external target `CONTEXT_30_ALIGNED_alpha_0.30` from authenticated `cpx62-1340-jass-megacorpus-comparative-fit-v1` / `20260814T123246Z-2ce07222`;
- 8cf pattern geometry, exact fold, tempo-stage representation and 120 extras;
- lossless production pruning convention used by the 1341 recipe;
- exact authenticated MEGA_FULL_4M model C bytes from 1340 as `--prior-mean` for both arms;
- `prior_decay=0`;
- logistic loss;
- `l2=1e-5`;
- L-BFGS `max_iterations=2000`, `maxcor=20`, `gtol=1e-4`, chunk `20000`;
- identical train/holdout boundaries, feature bytes, deterministic coordinate order and PJTW serialization.

The only permitted fit difference is `hier_l2` as fixed above.

## 4. Mandatory reproduction proof before candidate admission

Current tooling must first prove that the CONTROL path still reproduces the historical production parent. This is a fail-closed comparability test, not a model-selection screen.

A production-shaped reproduction preflight shall:

1. authenticate all 1340/1341 source identities above and the exact historical CURRICULUM decompressed SHA256;
2. reconstruct the exact CURRENT_2M split and feature geometry under the historical recipe;
3. run CONTROL with `hier_l2=0` and all other parameters fixed;
4. require successful optimizer/convergence receipts under the frozen 2000-iteration / `gtol=1e-4` contract;
5. require the resulting decompressed CONTROL PJTW SHA256 to equal the immutable CURRICULUM SHA256 exactly.

If byte identity is not reproduced, the stage is **TECHNICAL** and stops. The only authorized response is bounded diagnosis and repair of the proven mechanical reproducibility defect. It does not authorize changing training data, target, L2, optimizer limits, feature geometry, fold, prior mean, serialization, or accepting a merely close CONTROL.

No HIER candidate bytes may be treated as admissible until this CONTROL reproduction is green.

## 5. HIER candidate fit and sealing

After the exact CONTROL reproduction is authenticated green, fit HIER from the same inputs and recipe with the sole change:

`--hier-l2 1e-5`.

The fit must:

- use the same projected/start state and the same source ordering as CONTROL;
- satisfy the same optimizer validity checks;
- seal the decompressed candidate SHA256 immediately;
- publish source authentication, optimizer/convergence receipt, coordinate identity, model manifest and execution evidence;
- report holdout/static readouts as descriptive only;
- perform no holdout-based selection, target sweep, lambda/dose sweep or adaptive retry.

An optimizer failure at the frozen limits is TECHNICAL for this candidate attempt and does not authorize retuning. A materially changed fit recipe requires a new prospective contract.

## 6. Frozen G0 dependency

A technically valid HIER candidate does not enter strength testing directly. It MUST pass the already-merged `L3_CLS_G0_RUNTIME_CATASTROPHE_CONTRACT_V1_20260916.md` unchanged.

The G0 evaluation therefore keeps exactly:

- direct parent = immutable CURRICULUM bytes;
- fixed anchor = the same immutable CURRICULUM bytes;
- exact FULL-512 root set and frozen order from depth/growth production;
- exact authenticated CURRICULUM 1M deep reference;
- 200,000 node budget;
- one thread, book off, TT 16 MiB freshly cleared per root/arm, same EGDB path/cache;
- identical search executable/configuration except evaluator bytes;
- passive SearchDecisionTrace trace-on/off parity requirement;
- parent-defined `d* = max(1, parent_completed_depth_at_200k - 1)`;
- same-search `nodes_to_d*` only from completed, Exact, all-actions-searched attempts;
- missing receipt in either arm = hard G0-C FAIL with **no surrogate**;
- phase-stratified 100,000-replicate bootstrap, seed `2026091605`, and every existing G0 threshold unchanged.

A HIER G0 FAIL is terminal for those exact bytes. No root filtering, threshold change, extra budget, surrogate, retry with altered bytes or candidate-specific search configuration is allowed.

A HIER G0 PASS authorizes only a separately preregistered CLS-S / fixed-time CLS-E stage. It does not authorize promotion or bake.

## 7. Launch discipline

Every executable stage under this contract uses Launch-V2 fail-closed admission and immutable job IDs.

Sequence:

1. implement a common HIER reproduction/fit specification and focused deterministic regressions;
2. run a production-shaped rehearsal of the exact CONTROL reproduction path;
3. only after authenticated green rehearsal, run production changing only `LAUNCH_MODE`;
4. only after exact CURRICULUM byte reproduction, run the HIER fit through the same common specification with only the prospectively fixed arm variable changing;
5. seal HIER bytes and run the unchanged G0 contract via its own required rehearsal/production discipline;
6. open no CLS-S / CLS-E strength job unless G0 PASS is authenticated.

Technical failures are auto-repaired only from exact bounded evidence. Scientific failures remain immutable and are never tuned around.

## 8. Explicit non-claims and forbidden actions

This preregistration does not claim that HIER is stronger, faster, or more faithful than CURRICULUM. It does not reopen LOCAL, WDL or MIXED. It authorizes no fresh strength cohort, alpha spending, promotion, bake, self-play reinjection or teacher regeneration by itself.

No automatic promotion, bake or scale-up is permitted anywhere in this contract.

Successful completion of this document's first executable stage means only that the historical parent recipe is reproducible under authenticated tooling and that the one-factor HIER candidate can be generated without confounding. External continuation still requires the frozen runtime/search and strength-at-time evidence from the master CLS campaign.
