# Mini-Jass PatternEval reconstruction program

Status: M24-P through M21-P completed. M17-P2R confirmed the generation-8
response, M18-P decomposed its static development response, and M21-P rejected
generation-history mixing for strength at equal unique volume. Contextual
supervision was then rejected by disjoint C1/C2 pools; its train-only C3
diagnostic found a calibration gap but no authority to reopen that decision.
M15-P precisely excluded its preregistered practical recovery target. M15-C
then confirmed a smaller direct conditional-target signal while missing its
old practical threshold. M15-C2 confirmed the interior alpha-0.30 dose on both
static response and paired strength. M15-C2R independently replicated all four
alpha-0.30 axes and retained that dose. M15-C3 then rejected its naive convex
composition with M16-P `LAMBDA_50`: two of four primary axes failed. M15-C4 is
preregistered and implemented to test a separate collapsible residual path; it
is not queued by this code PR.

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

The independent `cpx62-1220` readout verified the source manifest, inventory
and checksums and passed all 160 arena audits. Every arena used 128 distinct
development starts and pair-level confidence; its scores covered 30 distinct
values from 0.48633 to 0.56836. The paired primary `G8 - G1` was +0.02463
(Student 95% CI +0.02220 to +0.02706), positive for all 20/20 seeds. Mean
advances were 6.55/8 and no seed had zero advances. The readout hash is
`829a92835da8a00f2d4e34d4316baf60187cbfed52445a9beb7df8ac8a90bfbe`.

### 5. M17-P2R — fresh-seed confirmatory replication

M17-P2R freezes the M17-P2 model, training, ladder, repaired arena and all
scientific boundaries. It changes only the cohort to 20 fresh paired seeds
(`264001` through `264020`), disjoint from M17-P and M17-P2. The confirmatory
endpoint and decision rule are frozen before execution: paired development
zero-regret `G8 - G1` must have a Student 95% lower bound strictly above zero
and a mean of at least +0.01. If the ladder averages fewer than one deployed
advance, the result is inconclusive regardless of the endpoint. Secondary
rungs and arena diagnostics remain descriptive. Frozen test stays sealed and
the cell is never promotable.

M17-P2R completed on `cpx62-1221`. Paired development zero-regret `G8 - G1`
was +0.03917 (Student 95% CI +0.03776 to +0.04058), positive for all 20/20
fresh seeds and above the +0.01 practical gate. The ladder averaged 6.4
advances and no seed was blocked. Result hash:
`c868949d2f1027889e6e76fd081e763aedcac7840f6105e1f18175e5c66685ea`.

### 6. M18-P — state, label and optimizer-path decomposition

M18-P generates one repaired eight-generation M17-P2 pack per fresh seed and
then trains every scientific arm from the same zero-initialized PatternEval.
It never regenerates data per arm. Seven paired arms separate three channels:

- `MIX_EXACT - G1_WIDE_EXACT` isolates late-generation state distribution at
  equal row volume under deterministic exact train labels;
- `MIX_OUTCOME - G1_WIDE_OUTCOME` asks whether that distribution remains useful
  with honest self-play outcomes;
- exact-minus-outcome contrasts quantify label noise within each distribution;
- `MIX_SEQUENTIAL_OUTCOME - MIX_OUTCOME` compares eight optimizer cycles with
  one monolithic fit using the exact same sample-draw multiset;
- G1-wide-minus-G1-only and G8-minus-G1 controls report unique-row volume and
  recency without confusing either with the primary distribution contrast.

The exact-label arms are diagnostic boundary crossings restricted to train
states and are never promotable. Generation and sample selection stay
oracle-blind. The primary response remains development `zero_regret_rate` from
one-ply value search; frozen test remains sealed. A mechanism requires a paired
Student 95% lower bound above zero and a mean gain of at least +0.01 across 20
fresh seeds (`265001` through `265020`). A state-distribution attribution
requires both the exact-label and honest-outcome distribution contrasts to
pass; otherwise M18-P reports the label interaction rather than overclaiming.

### 7. M21-P — generation composition strength

M21-P reconstructed `MIX_OUTCOME - G1_WIDE_OUTCOME` with scalar PatternEval,
equal unique replay rows, an explicit shared batch schedule and paired
common-search arenas. It returned `FAIL`: the arena mean was `-0.0010742`, with
95% interval `[-0.0030960, +0.0009476]`. The frozen downstream rule therefore
selects the simpler equal-volume `G1_WIDE_OUTCOME` source.

### 8. M15-P — deployable value-target recovery

M15-P generates one selected `G1_WIDE_OUTCOME` replay per fresh paired seed and
fits outcome, root-search, 50/50 blend and exact-oracle targets on identical
rows and batch schedules. The sole primary is `BLEND_50 - OUTCOME` development
zero-regret. Search-only is mechanistic and cannot rescue the primary; exact
labels are a train-only diagnostic upper bound. See
[`PATTERN_M15P_VALUE_TARGET_SCREEN.md`](PATTERN_M15P_VALUE_TARGET_SCREEN.md).

M15-P completed on `cpx62-1237`. `BLEND_50 - OUTCOME` was `+0.0013216`
(Student 95% CI `[+0.0008605, +0.0017827]`), precisely below the frozen
practical target `+0.0061454`. The exact-label diagnostic retained a much
larger `+0.0122908` gap, while search-only targets were harmful. Result hash:
`443129d7b523b4c1ea94bd76c887a8defbeb1ce3f70c115dd85b81ab7869d645`.

### 9. M15-C — direct conditional-target injection

M15-C resolves a narrower question that C1/C2 did not test. It fits a
five-fold, complete-game-held-out conditional WDL estimate and injects it
directly into the scalar training target. The causal primary compares a 50/50
conditional blend with an equal-weight, within-fold permutation of the exact
same conditional predictions before also requiring improvement over raw
outcome. A global-mean blend remains a secondary shrinkage control. This
separates correct state-context alignment from target distribution effects. All
targets are oracle-blind, `frozen_test`
remains consumed and unread, and no arm is promotable. See
[`PATTERN_M15C_CONDITIONAL_TARGET_SCREEN.md`](PATTERN_M15C_CONDITIONAL_TARGET_SCREEN.md).

M15-C completed on `cpx62-1238`. The aligned conditional blend beat its
shuffled control by `+0.0160159` (95% CI `[+0.0145843, +0.0174476]`) and raw
outcome by `+0.0030931` (`[+0.0024638, +0.0037224]`), both positive on 20/20
seeds. It formally missed the old `+0.0039159` practical floor, so the frozen
status is `FAIL`, but the result confirms the conditional mechanism rather
than refuting it. Context-only training was harmful (`-0.0189698` versus
outcome), locating the useful regime inside the 0-to-50% interval.

### 9bis. M16-P — retained temporal signal

M16-P completed on `home-1321`. `LAMBDA_50 - OUTCOME` improved development
zero-regret by `+0.0015492` (Student 95% CI
`[+0.0009282, +0.0021702]`) and its descriptive paired arena by `+0.0056641`
(`[+0.0037216, +0.0076065]`). It recovered `10.25%` of the replicated exact
gap, below the preregistered 50% major-recovery target `+0.0075547`.

The experiment is retained as `POSITIVE`: the temporal mechanism is confirmed
but is not the dominant explanation of the target-noise gap. The immutable
source report keeps its original gate status and result hash; downstream work
retains `LAMBDA_50` as a composition candidate requiring fresh-seed strength
confirmation. It must not be described as an absence of temporal signal or
rerun identically.

### 10. M15-C2 — interior conditional-target dose

M15-C2 freezes alpha `0.30` as its sole confirmatory dose and surrounds it with
exploratory `0.20` and `0.40` arms. Every aligned dose has a within-fold,
marginal-matched shuffled control. The primary static gate has no positive
effect floor: both `CONTEXT_30 - SHUFFLED_CONTEXT_30` and
`CONTEXT_30 - OUTCOME` must have Student 95% lower bounds above zero. The
512-pair strength gate is reported separately and cannot rewrite the static
verdict. See
[`PATTERN_M15C2_CONDITIONAL_DOSE_SCREEN.md`](PATTERN_M15C2_CONDITIONAL_DOSE_SCREEN.md).

M15-C2 completed on `cpx62-1240`. The alpha-0.30 target beat its shuffled
control by `+0.0088027` (95% CI `[+0.0080939, +0.0095115]`) and OUTCOME by
`+0.0048164` (`[+0.0042114, +0.0054214]`) in development zero-regret, positive
on all 20 seeds. Both paired strength contrasts were also positive:
`+0.0011719` versus shuffled (`[+0.0003383, +0.0020054]`) and `+0.0011475`
versus OUTCOME (`[+0.0004087, +0.0018862]`). Result hash:
`2f839078622bc8c5393fc16a46060ef20a47d0c3545b95caedcad1ae0f927b0d`.

### 11. M15-C2R — independent dose replication

M15-C2R freezes 20 fresh seeds, alpha `0.30` as the sole primary replication
and alpha `0.40` as a secondary dose that cannot rescue it. Alpha 30 must
replicate all four static/strength attribution and operational intervals above
zero. Alpha 40 replaces it only if its own four controls pass and direct paired
`CONTEXT_40 - CONTEXT_30` intervals are positive for both zero-regret and
strength. There is no decision effect floor. See
[`PATTERN_M15C2R_CONDITIONAL_DOSE_REPLICATION.md`](PATTERN_M15C2R_CONDITIONAL_DOSE_REPLICATION.md).

M15-C2R completed on `cpx62-1242`. Alpha 30 passed all four fresh-seed static
and strength intervals and remains retained. Alpha 40 beat 30 in static
response (`+0.0015064`, 95% CI `[+0.0011496, +0.0018632]`) but not in direct
strength (`+0.0000977`, `[-0.0004192, +0.0006145]`). Result hash:
`d240e5c006b9e7463221bbae4e639d80dbc8773840c2310b64ed9df1bd45ae25`.

### 12. M15-C3 — conditional-temporal composition

M15-C3 freezes alpha `0.30`, temporal `LAMBDA_50`, 24 fresh seeds and six
paired arms. It compares `0.70*OUTCOME + 0.30*context` with
`0.70*LAMBDA_50 + 0.30*context`, using the same aligned and within-fold
shuffled conditional predictions under both bases.

The primary requires positive static and strength intervals both for
`COMPOSED_30 - CONTEXT_30` and for
`COMPOSED_30 - SHUFFLED_COMPOSED_30`. Singleton confirmations and the
difference-in-differences interaction cannot rescue it. Even after a primary
pass, composition replaces the incumbent only if it also beats `LAMBDA_50`
and `OUTCOME` directly in static response and strength. See
[`PATTERN_M15C3_CONDITIONAL_TEMPORAL_COMPOSITION.md`](PATTERN_M15C3_CONDITIONAL_TEMPORAL_COMPOSITION.md).

M15-C3 completed on `cpx62-1244` with two of four primary axes passing. Static
temporal increment and strength conditional attribution were significantly
negative, so `CONTEXT_30` remains retained and that convex formula is closed.

### 13. M15-C4 — separate conditional residual path

M15-C4 holds the final additive target fixed while comparing a direct 2,048-step
fit with a 1,024-step temporal base plus a 1,024-step conditional residual. The
residual base is frozen, the aligned arm is controlled by a within-fold shuffled
residual, and the two linear tables collapse before evaluation into one standard
`PatternEval` with zero extra inference parameters. Four static/strength axes
must pass; descriptive direct and singleton arms cannot rescue them. See
[`PATTERN_M15C4_CONDITIONAL_RESIDUAL_PATH.md`](PATTERN_M15C4_CONDITIONAL_RESIDUAL_PATH.md).

M15-C4 completed on `cpx62-1250`: the separate residual path failed while the
conditional static signal survived. `CONTEXT_30` remains the retained recipe.

### 14. M15-C5 — conditional on-policy feedback

M15-C5 follows `OUTCOME` and retained `CONTEXT_30` through two paired
generations. G1 is a strictly shared-replay comparison; G2 lets each arm
generate its own replay. A third G2 continuation starts from the context G1
model but consumes the outcome replay, isolating the distribution-feedback
term. The primary requires positive static and strength intervals for the
on-policy G2 contrast, with no effect floor. See
[`PATTERN_M15C5_CONDITIONAL_FEEDBACK.md`](PATTERN_M15C5_CONDITIONAL_FEEDBACK.md).

M15-C5 completed on `home-1256`: G1 replicated the conditional static and
strength gains, but G2 reversed development zero-regret (`-0.002349`, 95% CI
`[-0.003352, -0.001346]`) while retaining a tiny positive arena effect
(`+0.001668`, 95% CI `[+0.000437, +0.002899]`). The exact repeated-target
feedback recipe is closed; the static `CONTEXT_30` evidence remains retained.

### 15. M15-C6 — separate contextual decision channel

M15-C6 keeps `LAMBDA_50` as the sole search value and fits aligned and shuffled
conditional OOF predictions into separate linear `PatternEval` tables. Context
can only choose among root actions inside a temporal uncertainty band calibrated
on train replay. The decisive playing-strength contrasts are aligned minus
shuffled and aligned minus `LAMBDA_50`; both confidence intervals must be above
zero, and static diagnostics cannot rescue them. See
[`PATTERN_M15C6_CONTEXTUAL_DECISION_CHANNEL.md`](PATTERN_M15C6_CONTEXTUAL_DECISION_CHANNEL.md).

## Conditional continuation

The original conditional ordering has now resolved as follows:

- If M24-P is unsaturated, extend only its dose ladder.
- If M24-P is saturated but far from the oracle response, test pattern-window
  capacity before interpreting self-play failures.
- M14-P supported a target-noise effect and M15-P precisely excluded major
  recovery by the frozen root-search target. M15-C confirmed a smaller
  conditional signal. M16-P independently confirmed a small temporal signal;
  `LAMBDA_50` is retained for composition even though it missed the 50%
  major-recovery gate. M15-C2 confirmed the interior conditional dose;
  M15-C2R independently replicated it; M15-C3 closed its naive convex
  conditional-temporal formula; M15-C4 rejected a separate residual path.
  M15-C5 showed that the static conditional gain does not survive one on-policy
  feedback step. M15-C6 therefore changes the causal channel: temporal value and
  context stay separate until the root decision, with a shuffled context table
  as the causal control.
- If M17-P advances and compounds, replicate with fresh seeds before extending
  the ladder; if it cannot advance, diagnose the promotion gate first.
- M18-P and M21-P are complete. After M15-P/M16-P, reconstruct the remaining
  M19-P mechanics only where a live hypothesis remains; M21-P already closes
  an unguided M23-P mix-shape screen.
- The discarded-head C1/C2 mechanism remains closed. M15-C independently
  confirmed that direct conditional-target injection is a distinct live
  mechanism; M15-C2 confirmed its dose without reopening the auxiliary-head
  result, M15-C2R replicated that result, M15-C3 rejected the first composition
  formula, and M15-C4 rejected a training-only residual decomposition without
  reopening the discarded training-only head mechanism. M15-C5 closed repeated
  scalar conditional feedback. M15-C6 is deliberately different: it tests a
  second runtime decision channel, leaves the temporal search value unchanged,
  and is non-promotable even if its scientific gate passes.

M18-P cannot settle playing strength because its causal endpoint is static
development zero-regret. The historical M21 arena evidence cannot settle it
either because it used the retired MLP/policy-head architecture. M21-P therefore
reconstructs `MIX - G1_WIDE` with scalar PatternEval, equal unique replay rows,
an explicit shared batch schedule, and paired common-search arenas. See
[`PATTERN_M21P_SIGNAL_COMPOSITION.md`](PATTERN_M21P_SIGNAL_COMPOSITION.md).

No result in this program authorizes a production Jass change or a direct
10x10 transfer.

## CPX entrypoint

One job is prepared per cell:

```text
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m24p
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m14p
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m15p
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m15c
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m15c2
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m15c2r
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m15c3probe
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m15c3
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m15c4probe
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m15c4
mini_jass/jobs/run_pattern_conditional_feedback_home.sh probe
mini_jass/jobs/run_pattern_conditional_feedback_home.sh full
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m17p
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m17p2
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m17p2r
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m18p
mini_jass/jobs/run_pattern_reconstruction_cpx.sh m21p
```

The entrypoints build the C++ oracle, run CTest and the full Python suite,
exports an L1 oracle, enforces host `cpx62`, retains the full audit result, and
publishes a bounded runner summary. M15-C5 instead enforces HOME hostname
`User`, `nproc=16` and persistent-venv reuse. No queue file is created by this
branch.
