# Mini-Jass PatternEval reconstruction program

Status: M24-P and M14-P completed; M17-P v1 completed operationally but was
scientifically inconclusive because its arena gate was underpowered. M17-P2
is the preregistered repair and is not yet scientific evidence.

The wiring evidence is intentionally not a scientific reconstruction result.
It established that the architecture is executable and deterministic:

- 12 exact-supervised epochs reached development zero-regret 0.96294 and value
  sign 0.68419; the descriptive frozen-test zero-regret was 0.96390;
- the two-generation outcome-only smoke reproduced all 6/6 deterministic
  artefact hashes; generation 1 improved development selection score by
  0.02592, but neither generation was promoted;
- total CPX time was 52 s (11 s exact-supervised, 7 s self-play), so the M24-P
  dose ladder is comfortably sized.

## Question and invariant

The program reconstructs the Mini-Jass learning experiments with the same
architectural contract as production Jass:

1. a folded linear table evaluation (`PatternEval`, window 3);
2. exact side-aware rotation/colour folding;
3. one scalar value and no learned policy head;
4. actions supplied by search over child values.

The historical MLP evidence is not pooled with this program. It used a learned
policy head and often scored `optimal_probability_mass`; that field has no
meaning for a value-only evaluator. Every new artefact therefore has a new
schema and a `-P` milestone. The primary response is `zero_regret_rate` from
one-ply value search. Value sign accuracy remains secondary.

## Frozen reconstruction v1

The first pass changes the architecture, not every training factor at once.
It retains the laboratory MSE/AdamW optimizer, the M8 search/exploration dose,
the immutable L1 split, and the same rule/oracle hashes. `policy_weight` must
be zero because PatternEval has no policy parameters. The production
logistic/L-BFGS/ridge-to-parent recipe is a later, explicit fit-recipe factor;
mixing it into v1 would prevent attribution to architecture.

The common loop is `configs/l1_pattern_reconstruction_loop.yaml`. Training
samples are restricted to the train cohort. Development is the only selection
cohort. Except for the conditional M24-P ceiling read, frozen test remains
sealed.

## Ordered cells

### 1. M24-P — representational ceiling

`run_pattern_supervised_ceiling.py` fits exact solved values at doses 12, 48,
192 and 768 epochs. Saturation is decided on development. If the last step is
larger than 0.005, the cell returns `CEILING_NOT_SATURATED` and does not read
frozen test. If saturated, it reads frozen test only for the two largest-dose
models. This is an oracle-trained upper bound and is never promotable.

This cell answers whether later self-play curves are below a model ceiling.
Capacity-window and production-fit-recipe ladders remain conditional follow-up
factors, not silent additions to this first run.

### 2. M14-P — value-target noise

Twenty fresh paired seeds generate one replay each. The outcome and exact
oracle arms must have identical complete replay fingerprints. Both candidates
start from the same zero-initialized PatternEval state, see the same positions,
and use the same optimizer schedule. Only replay `value_target` differs after
the train-cohort mask. The primary contrast is the paired difference in
development zero-regret gain. Frozen test is not read. The oracle arm is never
promotable.

### 3. M17-P — generation composition

Twenty fresh seeds run one causal ladder to generation 8 and report rungs 1,
2, 4 and 8. Each rung scores the parent actually deployed after the promotion
decision, not a rejected candidate. A ladder with fewer than one mean advancing
generation is inconclusive. Frozen test is not read.

The first execution (`cpx62-1218`) advanced zero of 160 candidate generations.
This was not evidence that iteration fails: with 4 arena pairs (8 games), a
neutral candidate scoring 0.5 has a 95% lower bound of only 0.1535 against the
0.40 promotion threshold. Even a 0.625 score fails. The cell therefore mostly
measured an underpowered promotion gate.

### 4. M17-P2 — promotion-gate repair

M17-P2 preserves the model, training, development threshold, ladder and sealed
cohorts. It changes the arena control from 4 to 128 pairs (256 games), for which
a neutral 0.5 score has lower bound 0.41338 and can pass the unchanged 0.40
non-regression threshold. Because an arena from one fixed start merely
duplicates the same two deterministic games, the repaired control samples 128
distinct non-terminal development states without replacement. Candidate and
parent swap roles from each common start; action selection remains greedy.
Confidence uses each paired two-game block as one effective observation, never
the 256 correlated games. The runner recomputes the bound and fails closed if
the gate is underpowered or starts are not varied. Twenty fresh seeds are
disjoint from v1. Every generation
publishes the development improvement, arena counts/bound, both pass bits and
the resulting advance decision so that a second zero-advance result identifies
the blocking component instead of being opaque.

M17-P2 completed on `cpx62-1219` with 131/160 promotions and a monotone mean
development zero-regret gain from +0.08053 at G1 to +0.10516 at G8. This is a
selected discovery result, not its own replication. The preregistered readout
therefore treats paired `G8 - G1` zero-regret as primary, audits every arena
start/confidence contract, computes a Student 95% interval across the 20 seeds,
and sizes a fresh replication on a minimum practical gain of 0.01 rather than
only on the observed +0.02463.

## Conditional continuation

After M24-P/M14-P/M17-P:

- If M24-P is unsaturated, extend only its dose ladder.
- If M24-P is saturated but far from the oracle response, test pattern-window
  capacity before interpreting self-play failures.
- If M14-P supports target noise, reconstruct M15/M16 target mechanisms on the
  same immutable-replay/common-search contract.
- If M17-P advances and compounds, replicate with fresh seeds before extending
  the ladder; if it cannot advance, diagnose the promotion gate first.
- Only then reconstruct M18/M19 (iteration mechanics), M21/M23 (signal mixes),
  and the L2 level after PatternEval gains a separately validated L2 pattern
  geometry/action contract.
- Contextual supervision from draft PR #441 is a later factor. It must not be
  mixed into the baseline architecture reconstruction.

No result in this program authorizes a production Jass change or a direct
10x10 transfer.

## CPX entrypoint

One job is prepared per cell:

```text
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m24p
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m14p
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m17p
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m17p2
```

The entrypoint builds the C++ oracle, runs CTest and the full Python suite,
exports an L1 oracle, enforces host `cpx62`, retains the full audit result, and
publishes a bounded runner summary. No queue file is created by this branch.
