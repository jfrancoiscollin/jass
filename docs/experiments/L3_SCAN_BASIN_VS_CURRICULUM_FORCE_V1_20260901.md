# L3 Scan-basin vs CURRICULUM force — SB2 v1

Date: 2026-09-01

Status: **PREREGISTRATION ONLY**. Merge is not a strength GO.

## 0. Scientific question

SB1 established that, holding CURRENT_2M, archived Context30 target, PatternEval architecture, exact-fold/tempo-stage, optimizer and L2 fixed, the `SCAN_BASIN` refit is causally stronger than the otherwise identical `SELF_BASIN` refit.

The next question is narrower and decisive for production relevance:

> Does the already-frozen `SCAN_BASIN` candidate beat the byte-identical production `CURRICULUM` champion under the production search contract?

No new fit, retuning, architecture change, feature change, self-play, PL8, F6, D/D1/Rich-D or search-semantic change is permitted in SB2.

## 1. Immutable upstream

### 1.1 Production champion

```text
CURRICULUM SHA256 = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
```

The exact production artifact and runtime contract are unchanged.

### 1.2 Frozen SCAN_BASIN candidate

Source fit:

```text
job    = cpx62-1724-l3-sb1-scan-basin-fit-v1
attempt= 20260831T204024Z-e05fb469
artifact = artefacts/SCAN_BASIN.pjtw.gz
```

The exact raw model SHA MUST be read from and match the immutable model certificate published by the successful SB1 force job:

```text
job    = cpx62-1743-l3-sb1-scan-basin-force-pool1-recovery-v10
attempt= 20260901T173344Z-e05fb469
code   = e05fb4691bfe4877f7139c69be603c0d659f1ade
verdict= SB1_SCAN_BASIN_ESTABLISHED
```

No refit, reserialization with changed semantics, shrink, blend or calibration is allowed.

### 1.3 Jass code

Strength uses the pinned production-capable Jass code:

```text
e05fb4691bfe4877f7139c69be603c0d659f1ade
```

A technical rebuild on CPX62 is allowed, but both sides of every game MUST use the same executable bytes. Runtime executable SHA is published before strength.

## 2. One-factor causal contrast

Exactly one scientific treatment:

```text
B = frozen SCAN_BASIN
A = byte-identical CURRICULUM
```

Everything else is identical within each game/view:

- same executable;
- same production search parameters;
- threads = 1;
- book = OFF;
- production EGDB contract;
- same TT/cache policy;
- same opening and reversed-colour pairing;
- same scheduling/sharding policy;
- no runtime Scan engine, teacher, micro-search or external evaluator.

No `SELF_BASIN` is used in SB2 except as historical motivation.

## 3. Fresh-opening construction

Both pools are generated target-blind before any candidate-vs-champion result is read.

Use the same deterministic opening-generation family already validated in SB1:

```text
candidate_count = 30000
generator_depth = 8
generator_maxplies = 32
random_open_plies = 20
selected_openings = 3000
exact board+STM uniqueness = required
paired reversed sides = required
```

Every selected state MUST be exactly disjoint from every published force pool available at selection time, including the full SB1 Pool1 opening set from job 1743. PL8 is not read or consumed.

### Pool 1 seeds

```text
opening seed   = 2026110201
bootstrap seed = 2026110202
```

### Pool 2 seeds

Pool 2 is generated **only if authorized by the Pool 1 decision rule** and is exactly disjoint from Pool 1 plus every older force pool.

```text
opening seed   = 2026110211
bootstrap seed = 2026110212
```

### Chained bootstrap

```text
samples = 200000
seed    = 2026110299
```

These seeds are frozen before any SB2 strength result.

## 4. Strength views

Each pool uses the same 3000 openings for both views.

### Primary

```text
native fixed movetime = 0.1 s/move
3000 openings x reversed colours = 6000 games
```

This is the sole strength-decision view.

### Diagnostic

```text
Q00 depth = 9
3000 openings x reversed colours = 6000 games
```

Q00 is diagnostic only. It cannot rescue a native failure and is not required for final support.

For both views publish W/D/L, B score, Elo, ordinary CI95 where available, paired-opening bootstrap CI95, bootstrap probability B>0.5, errors/skips, wall time and runtime diagnostics exposed by the existing force harness.

## 5. Pool 1 decision

After a healthy Pool 1:

- if native `SCAN_BASIN` point estimate `<= 0.5`:

```text
SB2_SCAN_BASIN_VS_CURRICULUM_NOT_SUPPORTED
```

and STOP;

- if native point estimate `> 0.5`, exactly one unchanged Pool 2 replication is authorized by the preregistration, subject to the separate post-facts execution authorization in section 8. No scientific field may change between pools.

Q00 never changes this decision.

## 6. Final two-pool decision

After a healthy Pool 2, compute a paired-opening chained bootstrap over Pool 1 + Pool 2 using exactly 200000 samples and seed `2026110299`.

Final verdict:

```text
SB2_SCAN_BASIN_VS_CURRICULUM_ESTABLISHED
```

iff ALL hold:

1. Pool 1 native B point estimate > 0.5;
2. Pool 2 native B point estimate > 0.5;
3. chained native paired-bootstrap CI95 lower bound > 0.5;
4. zero skipped/asymmetric/error games in both native pools;
5. frozen SCAN_BASIN raw bytes are identical across pools;
6. CURRICULUM raw SHA is exactly the production SHA above across pools;
7. same executable bytes are used on both sides of each pool;
8. no runtime external evaluator/search teacher is present.

If Pool 2 native point estimate `<= 0.5`:

```text
SB2_SCAN_BASIN_VS_CURRICULUM_NOT_SUPPORTED
```

If both native pool point estimates are `> 0.5` but chained CI95 lower bound `<= 0.5`:

```text
SB2_SCAN_BASIN_VS_CURRICULUM_INCONCLUSIVE
```

No third pool and no threshold change are allowed.

## 7. Interpretation

A positive SB2 would establish that weight-basin information is not merely useful relative to an identically refit Jass control: the frozen Scan-basin refit would also beat the current production champion under native wall-clock search.

A negative SB2 would mean the SB1 basin effect is real but insufficient to surpass the production CURRICULUM lineage; it would not invalidate SB1.

## 8. Authorization boundary

The current user instruction to continue may authorize preregistration, implementation, technical fixes and preflight, but **strength compute requires a distinct post-facts GO after the preflight facts below are published**.

Before any SB2 fresh opening generation or strength game, publish on the target CPX62 run:

- exact Jass code SHA and branch/ref;
- CPU, nproc, ISA/native flags;
- free disk and scratch path;
- exact rebuilt executable SHA;
- exact SCAN_BASIN raw SHA and immutable source authentication;
- exact CURRICULUM SHA authentication;
- consumed-root native 0.1s and Q00 d9 rate measurements only;
- projected Pool 1 wall/ETA using the chosen technical shard/parallelism/timeouts;
- chosen shard count, max parallelism, per-game timeout and whole-view timeout;
- confirmation that fresh openings generated = 0 and strength games = 0.

Then require the distinct explicit post-facts authorization:

```text
GO SB2 FORCE
```

No earlier or generic GO satisfies this boundary.

After valid `GO SB2 FORCE`, Pool 1 may run. If Pool 1 native point estimate is positive, Pool 2 may run automatically under the frozen preregistration without another scientific GO, because its exact seeds/protocol/decision rule are already frozen here. Technical failures may be repaired and requeued versionedly without changing science.

## 9. Hard stops

SB2 authorizes no fit/refit, no self-play, no PL8, no F6, no D/D1/Rich-D, no architecture/search tuning, no third pool, no bake and no promotion.

Even if `SB2_SCAN_BASIN_VS_CURRICULUM_ESTABLISHED`, promotion/bake requires a separate explicit user authorization and a separate immutable promotion receipt.
