# L3 CTX4 uncertainty-band decision-channel screen — 2026-08-20

## Scientific question

CTX3 compressed the independently predictive 1417 contextual mapper into the scalar
PatternEval value and remained non-positive after the dense-extras symmetry defect was
fixed.  The corrected causal gate 1428/1430 therefore closes that scalar route.

CTX4 asks a narrower question before any implementation work: **does the same contextual
information contain directional move-choice information when it is kept separate from
the scalar value and allowed to act only where the existing CURRICULUM search is
uncertain?**

## Frozen evidence

The screen is read-only with respect to all learned assets.

- context mapper: `cpx62-1417-l3-context3-exact-tanh-mapper-screen-v1`,
  immutable attempt `20260819T072356Z-999091b3`;
- corrected CTX3 model provenance: `cpx62-1427-l3-context3-paired-patterneval-exact-extras-v2`,
  immutable attempt `20260819T224926Z-7fe6c654`;
- corrected scalar force evidence and fresh pools:
  `cpx62-1428-l3-context3-two-pool-force-exact-extras-v2`,
  immutable attempt `20260820T005123Z-17517b38`;
- scalar-route closure readout:
  `cpx62-1430-l3-context3-1428-readout-publish-v2`,
  immutable attempt `20260820T044422Z-17517b38`,
  classification `NONPOSITIVE_CLOSE_CTX3`;
- scalar baseline: the unchanged 1341 `CURRICULUM` PatternEval, raw SHA-256
  `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

No frozen cohort is read.

## Preregistered protocol

1. Deterministically sample **256 openings from each of the two already fresh,
   mutually-disjoint 1428 pools** with seed `2026082007`.
2. Enumerate every legal child from each sampled position.
3. Rank every child with the unchanged `CURRICULUM` scalar search under the certified
   Q00 search parameter vector at depth 9.  Define the scalar uncertainty band as a
   top1-minus-top2 margin **≤ 20 cp**.  This threshold is fixed before reading any CTX4
   directional result.
4. Independently compute the 1417 exact-tanh contextual prediction on each child using
   the production `--dump-conditional-context-v2` feature path and the 1417 final
   aligned mapper coefficients.  Child side-to-move WDL is negated to parent POV.
5. The **aligned CTX4 advice** may only choose between scalar top1 and scalar top2:
   it flips to top2 iff contextual WDL(top2) > contextual WDL(top1).  Otherwise it
   leaves scalar top1 unchanged.
6. The **shuffled control** uses the exact same contextual-delta marginal, cyclically
   permuted within each source pool with seed `2026082008`.  This preserves each
   pool's flip propensity exactly while breaking state/action alignment and has zero
   fixed points.
7. Judge scalar top1 and top2 at depth 12 with the unchanged `CURRICULUM` model.
   The primary paired outcome per uncertainty position is

   `deep_gain(aligned advice vs scalar top1) - deep_gain(shuffled advice vs scalar top1)`.

8. Bootstrap the paired mean with 100,000 replicates and seed `2026082009`.

## Pass gate

The read-only screen authorizes CTX4 implementation only if **all** guards hold:

- at least 48 uncertainty-band positions total;
- at least 16 uncertainty-band positions from each pool;
- at least 12 aligned advice flips;
- shuffled control has zero fixed points;
- the 95% bootstrap CI of aligned-minus-shuffled deep gain is strictly above 0 cp;
- among aligned flips, the 95% bootstrap CI of the depth-12 top2-minus-top1 judgement
  is strictly above 0 cp;
- the aligned-minus-shuffled point estimate is positive in both pools.

A failure is scientific, not technical; it does not trigger threshold tuning, a wider
band, a different mapper, or another screen on the same evidence.

## Scope

This job performs **zero PatternEval fits, zero self-play, zero strength games, zero
frozen reads and zero promotions**.  It does not modify `CURRICULUM`.  A PASS only
authorizes implementation of a separate conditional decision channel followed by a
new causal two-pool strength gate on fresh mutually-disjoint evidence.
