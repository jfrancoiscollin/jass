# ED3-P2 — disjoint native decision confirmation, BASE / HARD / SOFT

2026-09-09. Explicit mandate: **« Allez go enchaîne »** after completed candidate
1882. This is a NEW prospective confirmation, not ED2 retuning. Implement and
merge before the development rehearsal; admit production only after its own
completed, published and reread same-code V2 proof. No parameter changes from
rehearsal outcomes. No fit, self-play, Elo, promotion or automatic later stage.

## 1. Frozen candidate and two mandatory controls

- SOFT: 1882 / 20260908T220255Z-20a5e4eb, code
  20a5e4ebebedbf9340eafd3750506c1aed851506, completed exit 0;
  ED3_SOFT_VALUE_CANDIDATE_SEALED_V1.
  Model SHA256 d8a193de2017a6c156a46d89692245bdc1af00d29d056af3a41e7d6d4f5a486a;
  candidate seal 57709bdfad0063cdd1b815a8a8a22c9e713c2d963b7ff4d478b008fca2c5166b.
- HARD: ED2-N1 PARTIAL from 1878 / 20260908T191343Z-d71679e9;
  SHA256 3db65fe6dcc3dc828a7467ac27a43c4904c33d5791b484a2b2f19efcef70570e.
- BASE: WDL_CONTROL, 1849 / 20260906T222203Z-08fd187a;
  SHA256 e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0.

Authenticate successful outer manifests/inventories/checksums and these exact
bytes. Verify candidate role, recipe, associated evidence hashes and identical
PJTW header/pattern prefix. Do not refit HARD, BASE or SOFT, change tau, alter
240-coordinate extras, tune thresholds, blend models or substitute CURRICULUM.
This remains a comparison of frozen STATIC evaluators, not search strength.
CURRICULUM remains champion. ED2-N1 negative history stays unchanged.

## 2. New decision data, without a new source implementation

Reuse the exact score-free native generator produced by P0 1875 /
20260908T171140Z-bc30d685, authenticated file work/build/jass_ed2_source.
The original P0 wrapper retained that build in its published result. No source
patch or recompilation occurs on CPX. Failure to authenticate this literal file
blocks the stage; no guessed replacement binary or source-generation fallback.

The unchanged generator uses independently restarted random legal trajectories,
8..160 plies, at least 9 pieces, and 2..16 root moves. It excludes the whole
canonical parent/child footprint and has fixed four piece-count phases and STM
balance. Its fixed streams/seeds and two supported modes remain unchanged.
This reuses a tested source mechanism, not old selected endpoints.

Before generation, the exclusion set is the union of:
- authenticated P0 benchmark exclusions (BASE2000 parent/child identities);
- ALL P0 784 parents and 7556 children, including ED2 TRAIN/TEST/calibration;
- zero-target identities of the old 8192 replay and 8192 WDL guard selections;
- in production, ALL parent/child identities produced in the published ED3-P2
  rehearsal, including unscored calibration/reserved records.

REHEARSAL calls the source's smoke mode: 8 calibration, 16 development, 8
unused reserved parents. Use its train block as DEVELOPMENT16 (2/cell), never
as a training corpus. No confirmation population or targets are generated in
this rehearsal. PRODUCTION, after admission, calls original production mode:
16 calibration, 512 confirmation, 256 unused reserved parents. Its newly generated
train block is now CONFIRMATION512 (64/cell); the source's column name does NOT
mean these records can train a model. All original source files remain intact
and the mapping is explicit in cohort-seal.json. Numeric parent ids are local,
not cross-dataset identities. No resampling from model or teacher values.

Validate producer files with the existing source validator, including quotas,
canonical exclusions, child/parent alignments, zero-target records and unique
trajectory endpoints. Seal all source hashes before any new teacher call or
native candidate evaluation. Scan scores from old ED2 TEST are never fetched.
New canonical endpoints are disjoint from the enumerated sources, NOT a claim
of disjointness from every historical corpus or independent opening prefixes.
The fixed random streams still share opening prefixes; interpret bootstrap
intervals conditionally on this deliberately small generated population.

## 3. Separate historical WDL guard and its limits

Reuse byte-authenticated CURRENT_2M data/meta/Context30 array retained in the
successful N1 run: work/current.jnnw, work/current.jsm,
work/current-context30.npy. Validate data/meta hashes against N1's sealed
wdl-selection.json. Transport/hash verification of the array is allowed before
selection; INDEXING its target values is prohibited until the identity seal.

Only historical holdout indices [1800796,2000000) are eligible. Exclude complete
opening-id groups used in either old ED2 replay or old ED2 WDL guard; exclude
canonical identities from all old/new decision footprints and previously selected
records. No historical outcome is decoded by the selector.

REHEARSAL selects 256 development WDL rows using default_rng(202609090711),
permutation order without replacement. PRODUCTION selects 8192 guard rows using
default_rng(202609090712), and additionally excludes ALL opening groups and
identities in the authenticated rehearsal guard. At least 32 unique openings in
each; fixed sample sizes. Insufficient remaining support blocks the run without
extending the pool, changing seed, or reporting scientific neutrality. Publish
indices, opening IDs, identities and seal before target reads.

This is a newly reserved and opening-disjoint subset of a HISTORICAL Context30
holdout, not newly played outcomes and NOT globally unexposed data: prior project
experiments have used this corpus/aggregate holdout. It is a calibration guard,
not independently fresh WDL/gameplay evidence. The fresh decision population is
the primary confirmation. This limitation cannot be removed by renaming a split.

## 4. Fixed Scan reference and bounded compute

Authenticate official Scan from 1650 / 20260829T132800Z-28e12fba, source commit
7aae17e7b7bfc47744601afb1ee7655e18983ce5, binary SHA256
96b80c6aec1592f856a78ad7617ca6224b26be926800a6e37ede3b26f4e9cfa1.
Same data/eval and ini; existing NodeScanEngine uses book OFF, bb-size 0,
threads 1, fresh new-game and go analyze. Every nonterminal sibling gets one
200000-node request; exact no-legal-reply terminals use unchanged +10000 parent
score and unchanged winning-child priority for all three models.

Before scoring development/confirmation, choose the first nonterminal child of
each separate calibration parent, score at 200k and repeat the first one. Verify
exact repeat signature; retain timing only, never calibration score values.
9 calls in rehearsal, 17 in production. Cost gate = max(60,
2*maximum_observed_per_row_seconds*largest_mod8_shard+60), must be <=1200 seconds.
Per RPC 30 seconds, 8 single-thread workers, fixed row_index modulo 8. No partial
harvest, replacing slow rows, early statistical stop or repeat selection.

Maximum production: 8192 reference calls + 17 calibration calls = 8209 calls,
1,641,800,000 REQUESTED Scan nodes. Development <=265 calls/53,000,000 requested
nodes (profile uses a conservative 273-call ceiling). Actual terminal rows cost
zero; record actual completed searches separately. Progressive node snapshots
are checked, not called exact final consumption. Prior ED2-N1 processed 2430
200k requests in 16.42 s; that is historical evidence, NOT a promised runtime.
Calibration on the current host is the binding batch spending check.

CPX62, 16 available CPUs, numeric libraries one thread, >=3GB free disk. Source
240s, native RPC 180s, stage 900s and launch admission 1500s hard caps. Timeouts
are not ETAs. Controller termination cleans detached worker process groups.
No entire repository/build copy; only authenticated binary reuse. No new Jass
search, optimizer invocation, self-play or strength game.

## 5. Native readout and frozen statistical gates

Reuse the exact CPX62 evaluator probe archived by N1, checking archive/executable
hashes. Evaluate every selected child and every selected guard row for all three
models, with matching features, quantized residual/native logit reconstruction
at absolute tolerance 1e-9, and repeated BASE integer scores identical. Check all
model hashes again after readout. Python surrogate scores cannot replace native
integer results. Ties use original sibling order; Scan top-hit includes exact ties.

Primary per-parent regret = max_sibling Q200k - Q200k(chosen native child).
Require BOTH paired improvements: BASE minus SOFT, HARD minus SOFT. Bootstrap
parents within the eight fixed phase/STM cells, 20000 draws, percentile two-sided
95% CI; seeds 202609090801 and 202609090802. Both lower endpoints strictly >0.
This conjunction is not selecting a favorable contrast. Publish all 512 parents,
mean regret/top-hit by arm, changed/improved/harmed/unchanged counts and both CIs.
An identity BASE-vs-BASE control must have n>0, exact zero delta/CI/changed choices.

Additional gates, unchanged tolerances from ED2:
- SOFT top-hit no lower than BASE AND HARD;
- versus BASE, strictly harmed parents <= strictly improved parents;
- historical guard logloss SOFT-BASE upper CI95 <=0.002, opening-cluster bootstrap
  20000 draws, seed 202609090804, ratio-of-sums/counts preserves row estimand;
- SOFT Brier <= BASE Brier+0.002; all counts/metrics finite and complete.

All pass: ED3_SOFT_CONFIRMATION_SUPPORTED_V1, next PREREGISTER_NATIVE_GATE0.
Otherwise: ED3_SOFT_CONFIRMATION_NOT_SUPPORTED_V1, next STOP_ED3. An imprecise CI
is not proof of zero effect; it does not authorize a larger or tuned rerun.
Missing/corrupt inputs, worker failure or native mismatch are execution failures;
insufficient support or spending gate is a blocked/inconclusive run. Neither is
converted into a scientific negative. No automatic later job or promotion.

## 6. Actual launch proof and no extrapolation from fit receipts

Own V2 profile: jobs/launch_profiles/ed3-confirmation-v1.json. The candidate-fit
receipt does NOT admit this evaluator. CI runs identity-only selection, target
barriers, complete fixture stage -> original publisher -> checksum-validating
readback (reject corruption/missing marker), and separately the same fixture with
actual compiled unchanged native source and evaluator, with no skip fallback.
CI fixtures do not pretend to be official Scan or authenticated production data.

Then run the whole CPX development path, including real source, real Scan, native
readout, clustered statistics and R2 publication. It produces no scientific
verdict. Production requires the completed same-code/profile/normalized-spec/
runtime development proof and rereads every registered output, including source
bytes. Only LAUNCH_MODE differs in the two specs; mode-specific populations above
are frozen. Production verifies identical model/binary identity evidence, excludes
all development data, then generates and seals its confirmation inputs. No use
of development metrics for recipe choices. Keep the exact rehearsed code SHA.
