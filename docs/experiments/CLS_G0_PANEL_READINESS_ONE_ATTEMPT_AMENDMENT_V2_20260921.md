# CLS G0 panel readiness: one-attempt amendment V2

Date: 2026-09-21

Status: **AUTHORIZED PROSPECTIVE AMENDMENT — SEALED ACTIVATION REQUIRED**

## Decision

The renewed user authorization — “oh punaise oui j'autorise allez enchaine ... arrête de me demander” — authorizes preparation and, after the activation requirements below are sealed, execution of exactly one new technical-readiness admission.

This is a new admission, not a retry of `cpx62-2073-l3-cls-g0-panel-readiness-v1`. Attempt `20260921T070922Z-54e30b98` remains an immutable terminal failure. Its admission was consumed, its `automatic_retries: 0` rule remains in force, and none of its job, attempt, admission, plan, receipt, or result identities may be reused.

The new admission is limited to validating the mechanical test-harness correction for the pre-stage failure and adding the narrow control-gate rule needed to recognize this exact amendment. It authorizes reads of only the frozen model inputs already required by the 56-game readiness phase; it does not authorize any new or unfrozen model input, main-panel match, fit, bake, promotion, target read, or scientific-contract change.

## Prior attempt and consumed authority

- Job: `cpx62-2073-l3-cls-g0-panel-readiness-v1`
- Attempt: `20260921T070922Z-54e30b98`
- Code: `54e30b98ece4aa1efda8befd8f5e8f66e5279178`
- Result: exit 2 during launch regressions, before panel staging
- Scientific effects: 0 games, 0 new Jass searches, 0 Scan searches, 0 fits, 0 bakes, 0 promotions, 0 target reads
- Failure mechanism: the fixture intercepted only the literal `rclone` executable while the production reader correctly honored an inherited nondefault `RCLONE_BIN`; the test escaped its fake transport and the empty synthetic `_SUCCESS` marker was correctly rejected
- Historical-result source PR: `#1057`
- PR source commits: `f5ca290895c33300eae26ad0864d337bf3b1e601`, then `9b09ef6e6267ba60c5a410b1c4c3a2121098f11f`
- Results document at commit `9b09ef6e6267ba60c5a410b1c4c3a2121098f11f`: Git blob `5cd6632f194b7c13cf05331321980c32eb477bbe`; SHA-256 of Git-object file bytes `acc71625c974e4aaca7a56873c97d75e94faecb688a558d59144acb3abefcb17`
- Readback JSON at that commit: Git blob `f672ae18e66b82b7f9d7bd0bebd42e6bf6e2bc67`; SHA-256 of Git-object file bytes `f6ca519861e0b261f8ef7d424c6d0b4bc1005cb0edc1cf9d902cfb47197ca103`
- Publisher manifest SHA-256: `dca78e63970b57e02700f62dcf2fd540dcba287db14b2d25b0200c92ddebee03`
- Execution evidence SHA-256: `986a9975862460dcce3b4727fcf8e37e539868922d1f5c7ad4c3da25b2a20031`
- Regression report SHA-256: `0c1c9e5e01a523a277a5735389cde179dc5a93590cc8aefab1fe4fca70ea75b3`
- Runner-launch SHA-256: `da1253f519f32759560bcd8ca2e5f3abc0041f7ce4f07f7700ef1cc882eba5bf`
- Metadata SHA-256: `c2b75f05b82cae9659ffb114bf8157fe019be6d06132a2b0f12902ade7065b31`
- Exit-code-file SHA-256: `53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3`
- Terminal control commit: `7194f3c3f1ddcddc895c596aebb302b9da0c0431`
- Terminal status Git blob: `70ad8edbe46bb65bf7aca8d8967b21033f31ee90`

## Frozen scientific envelope

The new attempt must preserve the V1 panel contract and launch profile without modification:

- panel contract Git blob: `19e39b457e86d6131d028d26b1dc0e6bac881b06`
- launch profile raw Git-object bytes SHA-256: `4e1f9090e6f4dafdeac8d71e009ed1ca55730142781d5b428b5be2b843de3a47`
- original common-plan JSON SHA-256: `d48c2ac854707064fc8d7d0ba12db70b1e186fb333e91bc60452e7f0f3ea169b`
- readiness maximum: 56 games
- readiness maximum: 9,072 new Jass player searches
- readiness stage timeout: 1,800 seconds
- readiness dispatcher timeout: 2,400 seconds
- new Scan searches: 0
- fits, bakes, promotions, and target reads: 0
- main local/WDL matches: unauthorized

All frozen identities, seeds, exclusions, sources, opening recipe, phase templates, effect ceilings, and timeouts remain byte-for-byte equivalent to V1. Frozen file hashes must be computed from Git-object bytes, not platform-materialized working-tree bytes. Since attempt 2073 consumed no scientific effects, the cumulative ceiling across 2073 and this new admission remains 56 games and 9,072 new Jass searches.

## Mechanical and control change boundary

The permitted code delta is limited to the test/CI correction needed to exercise the already-frozen production behavior and the fail-closed control-gate exception defined below:

1. The regression fixture must accept the configured `RCLONE_BIN`, including an inherited nondefault absolute path, and intercept that exact executable.
2. Any unexpected subprocess must fail closed.
3. The raw-audit regression entry point must execute the exact ordered regression suite declared by the frozen launch profile, including `test_launch_gate_v2` and `test_launch_gate_pipeline_v2`.
4. The gate may recognize one reviewed exception record for the exact 2073 predecessor and exact new successor. It must implement the validation semantics below without changing any scientific input, effect ceiling, or phase behavior.

No launch-profile, stage, readiness, raw-audit, native-runtime, engine/model, or scientific-contract file may change. No other gate behavior may change.

## Exact prior-attempt exception semantics

The current gate scans the full Git history of every same-phase `*.admission.json` and rejects any prior claimed attempt with `PHASE_PREVIOUS_ATTEMPT_NO_RETRY`. A new job ID, code SHA, and common plan therefore do not suffice. The V2 implementation may add one explicit exception, recorded outside the 2073 admission, with all of these fail-closed rules:

1. The new admission must pin the exception-record path and SHA-256. The reviewed exception record must pin:
   - phase `readiness`;
   - predecessor job `cpx62-2073-l3-cls-g0-panel-readiness-v1`;
   - predecessor attempt `20260921T070922Z-54e30b98`;
   - predecessor code `54e30b98ece4aa1efda8befd8f5e8f66e5279178`;
   - full authenticated failure-publisher receipt, terminal-status, execution-evidence, regression-report, results, and readback hashes;
   - every predecessor effect counter, all equal to zero (all eight canonical counters, including `selfplay_games`);
   - the exact new job ID and new code SHA;
   - `max_successor_attempts: 1` and `automatic_retries: 0`;
   - this amendment's SHA-256.
2. The gate must enumerate the full same-phase history exactly as before. After excluding the current tuple, the distinct prior-attempt set must be exactly the pinned 2073 tuple. It must not hide, scope-filter, delete, or reinterpret history.
3. The authenticated 2073 terminal evidence must agree on the pinned job, attempt, code, terminal failure before panel staging, and zero effects. Any absent, abbreviated, inconsistent, nonterminal, or unauthenticated field rejects with `PHASE_PREVIOUS_ATTEMPT_NO_RETRY`.
4. The current job must equal the pinned successor job, differ from the 2073 job, use the newly sealed code and plan, and have no earlier distinct attempt in status history. Any other current or prior tuple rejects with `PHASE_PREVIOUS_ATTEMPT_NO_RETRY`.
5. Exactly one admission may reference the exception digest, and the exception may authorize exactly one successor attempt identity. A failure at any point consumes it, including a failure before games or staging.
6. The core materialized scientific spec must contain no exception field and must remain equivalent under the common-plan comparison below. The admission wrapper and separate control receipt must carry the exception path/digest and predecessor evidence digests; the result/readback must copy that wrapper provenance so the decision remains auditable without altering scientific fields.
7. Scientific accounting is cumulative, not reset: subtract authenticated predecessor effects from the V2 ceiling. For 2073 the authenticated charge is zero games and zero searches, leaving at most 56 games and 9,072 new Jass searches for the successor.

The gate must reject unknown prior attempts, additional same-phase histories, a second successor attempt, a reused job or attempt identity, mismatched evidence, or any request to generalize the exception.

## Common-plan compatibility

The original common plan cannot be reused because its `code_sha` is part of its identity. A new code commit therefore requires a new common-plan digest even though the scientific plan is unchanged.

Before activation, the reviewed control record must:

1. Authenticate the V1 common plan and consumed 2073 admission.
2. Build a new common plan using the new code SHA and exact frozen launch-profile bytes.
3. Prove unchanged Git blob identities for every production, profile, native, and scientific input other than the exact gate implementation reviewed under this amendment. At minimum, these 2073 blobs must match:
   - profile: `10e59a1670d32e71d437e0d155921cb131923c13`
   - stage: `668e0f35c84dd75884d8375a4abab13f92bc9503`
   - readiness: `1e904ac5ec3df5b1751bf26c9d65f062b17cfc4c`
   - raw audit: `2aae455d2b6cb7c8d31fbef5c56dfe1e18f5cb87`
   - experiment stage runner: `e892030965878e8acb685dac50d9f131d2a94712`
   - launch-regression runner: `c9fed2eb27a80138ec7415cbb8da6ac1e2688137`
4. Treat gate blob `9595a80fa8508597ac2b828cebe9546ba06d0274` as the immutable review baseline. Record the new gate blob and prove its semantic diff is limited to the exact fail-closed exception validation in this amendment.
5. Canonicalize the old and new common plans and core materialized readiness specs after removing only `code_sha` and fields derived exclusively from `code_sha`; the resulting canonical JSON must be byte-identical. Exception path/digest and predecessor evidence are wrapper/control provenance and are never inserted into or removed from the core scientific spec for this comparison.
6. Record the old/new digests, exact normalization field list, gate baseline/new-blob/diff proof, and equality result in the new control admission.

Any other difference is a scientific-contract change and blocks this amendment.

## Activation requirements

This draft becomes executable only after the reviewed source and control changes seal:

- merged PR `#1057`, whose source history ends at `9b09ef6e6267ba60c5a410b1c4c3a2121098f11f` after `f5ca290895c33300eae26ad0864d337bf3b1e601`, publishing the historical 2073 result and mechanical test fix;
- a distinct reviewed PR2 adding this amendment and its narrow gate exception;
- a final new source commit containing both reviewed changes and no unreviewed delta;
- a new unique readiness job ID;
- a reviewed, fully populated one-time prior-attempt exception record bound to that job and source commit;
- new common-plan, admission-record, and materialized-readiness-spec digests;
- full authenticated identities for all 2073 terminal evidence above;
- a clean-tree attestation;
- unchanged production/profile/native/scientific blob proof;
- the common-plan compatibility proof above;
- successful execution, in a Linux/CPX-equivalent environment with inherited nondefault `RCLONE_BIN`, of the exact six-module regression suite ordered by the frozen profile;
- proof that the fixture fails closed on every unexpected subprocess;
- focused tests showing the exception accepts only authenticated 2073 plus the first pinned successor attempt, while rejecting unknown predecessors, altered evidence, reused identities, a second successor attempt, and any non-readiness phase;
- Python compilation and launch-profile validation;
- one reviewed control admission explicitly naming this V2 amendment and the new job.

Until every item is sealed, no job may be queued or executed under this amendment.

## One-attempt execution and terminal mapping

The three V2 tokens below are operational control/wrapper/readback dispositions.
They do not replace the frozen stage terminal or create a scientific verdict;
`scientific_verdict` remains `null`.

The activated amendment permits one attempt under the new job ID. It permits no automatic retry and no reuse of any 2073 identity.

- Any preflight, regression, provenance, compatibility, staging, execution, publication, or readback failure stops as `CLS_G0_PANEL_READINESS_V2_TECHNICAL_FAILURE_BLOCKED`, even if zero games were played. No third attempt is authorized.
- Exceeding 56 games, 9,072 new Jass searches, or any zero-effect ceiling stops as `CLS_G0_PANEL_READINESS_V2_CONTRACT_BREACH`.
- Authenticated readiness completion permits publication/readback of readiness only and stops as `CLS_G0_PANEL_READINESS_V2_COMPLETE_MAIN_NOT_AUTHORIZED`.

Success does not authorize the 576-game local panel, the 576-game WDL panel, promotion, or any other main phase. Those remain behind a separate explicit admission.

## Engineering and control handoff

Engineering must finalize only the bounded fixture, regression-discovery, and exact gate-exception changes; produce a clean immutable source commit; and supply the exact validation receipts. Control must allocate fresh job/admission/plan/spec/exception identities, authenticate the full 2073 terminal evidence, prove frozen-input equivalence, and record the one-attempt/no-retry terminal map before queueing. The dispatcher must reject missing fields, an unpinned or generalized exception, unknown history, any reused 2073 identity, any second successor attempt, any changed frozen blob, any normalized-plan difference, or any main-phase request.
