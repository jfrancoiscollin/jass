# L3 F6 transfer — E1 terminal results

Date: 2026-08-31

Status: **TERMINAL PASS — `E1_COST_ATTRIBUTED`**

This document closes E1 of the preregistered F6 transfer program. It is a read-only record of the completed E1 compute and its terminal readout. It does not authorize E2 full compute, E3, any fit/tune/refit/calibration, D1, ablation, bake, promotion, Pool2 v4, or any strength games.

## 1. Terminal provenance

E1 full:

```text
job     = cpx62-1708-l3-t3-f6-e1-full-v1
attempt = 20260831T054226Z-47258018
code    = 47258018c1438e3220fcebeff8c371cbe9f2b5fc
exit    = 0
verdict = E1_COST_ATTRIBUTED
```

Read-only terminal publication:

```text
job     = cpx62-1709-l3-t3-f6-e1-terminal-readout-v1
attempt = 20260831T061358Z-47258018
code    = 47258018c1438e3220fcebeff8c371cbe9f2b5fc
exit    = 0
state   = completed
```

The terminal readout publishes `E1_TERMINAL_READOUT_READY`, `E2_POST_E1_PREFLIGHT_REQUIRED__TRUE`, and `E2_POST_FACTS_JFC_GO_REQUIRED__TRUE`.

## 2. Exactness and support

```text
leaf_positions      = 4096
search_roots         = 128
roots_per_phase      = 32
depth                = 9
threads              = 1
cache_O1_primary     = OFF
feature_mismatches   = 0
score_mismatches     = 0
strength_games       = 0
fit_runs              = 0
```

E1 therefore remains a cost-attribution/search-support experiment only. No force result was generated.

## 3. Direct node ratio on CPX62

Terminal aggregate:

```text
CURRICULUM nodes = 1,649,795
T3-A nodes       = 3,338,212
nodes_ratio_E1   = 2.023410
CI95             = [1.793640 ; 2.278168]
bootstrap seed   = 2026100105
```

The direct preregistered E1 answer is that, on the consumed E1 support at depth 9 with O1 OFF, T3-A expands about **2.0234×** as many nodes as CURRICULUM. This is the node-ratio input for the preregistered E2 `delta_info` decomposition; it is not itself a strength estimate.

## 4. Rate and cost-family attribution

Terminal markers:

```text
CURRICULUM NPS x1e3 = 5,112,458,674
T3-A NPS x1e3       =    62,859,662
top cost family      = F3
top family share     = 480,335 ppm = 48.0335 %
```

The top family is F3 at about **48.03%** of the attributed cost. This is below the preregistered `>=60%` condition that would merely make a future separate ablation preregistrable. E1 therefore does not open or execute any ablation.

## 5. Scientific interpretation

E1 establishes two facts needed by the transfer program:

1. the runtime/search cost remains materially asymmetric, with a direct T3-A/CURRICULUM node ratio of `2.023410` on the E1 support; and
2. the measured cost is not dominated at the preregistered 60% threshold by a single attributed family.

E1 does **not** alter any frozen model bytes or authorize retuning, refitting, calibration, D1, F6 removal/approximation, production bake, promotion, or strength testing.

## 6. E2 boundary

E2 is the preregistered equal-nodes experiment:

```text
C1 = 1500 games, T3-A vs CURRICULUM, 20k / 20k nodes
C2 =  800 games, CURRICULUM-hi vs CURRICULUM-lo, 20k / 10k nodes
C3 =  400 games, byte-identical CURRICULUM vs CURRICULUM, 20k / 20k nodes
```

Before any of those 2700 strength games, the program requires a post-E1 **read-only/technical preflight** to publish fresh machine/build/O1-selftest/rate/sizing/timeout/ETA/disk/ISA/hot-path facts. Only after those facts are terminal may a distinct explicit `GO E2` authorize the preregistered full E2 run.

The first technical preflight attempt, `cpx62-1710-l3-t3-f6-e2-preflight-v1`, failed during isolated CMake configuration before build/selftest/sizing. This was a technical failure only: fresh E2 pool was not generated, strength games were `0`, fit runs were `0`, and no scientific decision occurred. The isolated harness configure-root defect was repaired without changing E2 science in Jass PR #739, merged as `1048281f94aca085666702b2b2a2d0c8621f7151`. A versioned technical preflight requeue is the next operational step.
