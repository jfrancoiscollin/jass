# Contextual outcome supervision — WDL + deterministic state context

## Status

Design/preregistration for the rebuilt Mini-Jass laboratory using the **production-like Jass architecture**: folded pattern-bucket, value-only evaluation whose move choice comes from search. This proposal must not be implemented on the retired MLP/two-head architecture.

No production Jass change or direct 10x10 transfer is authorized by this document.

## Motivation

Terminal W/D/L is a correct statement about the game result, but it is a very low-bandwidth credit signal when copied unchanged onto every preceding state.

Example: a side that is materially and positionally disadvantaged may save a draw through a sequence of strong moves. A plain draw target assigns the same neutral terminal outcome to those states as to an equal, uneventful draw. Conversely, a side that starts from a strongly favourable situation and throws the win away also receives a draw target.

The proposal keeps terminal WDL semantically pure and adds **context-conditioned auxiliary supervision**. It must never redefine a draw into a win or a loss.

## Core separation

For each sampled state `s_t`:

1. `Z_t` — terminal outcome from the side-to-move POV, unchanged historical WDL target.
2. `C(s_t)` — deterministic context vector computed from the board only.
3. `DeltaC_t` — deterministic change in context caused by the selected move, reoriented to the mover POV.
4. `B(C(s_t))` — frozen deterministic baseline mapping context to an expected scalar outcome.
5. `Rctx_t = Z_t - B(C(s_t))` — contextual outcome residual / outcome surprise.

The main value evaluator continues to learn the ordinary WDL objective. Context is auxiliary supervision only.

## Deterministic context vector v1

The first implementation must keep dimensions separate; do not collapse them into one handcrafted score before measurement.

All components are normalized to approximately `[-1, +1]` from side-to-move POV and must satisfy the exact `rot180 + colour-swap` symmetry used by the rebuilt pattern evaluator.

Required v1 components:

- `material_man_delta`: own men minus opponent men, normalized by initial material.
- `material_king_delta`: own kings minus opponent kings, with a **separate field**, not a hardcoded conversion into men.
- `legal_move_delta`: normalized own mobility minus opponent mobility, using legal move generation.
- `capture_option_delta`: normalized number/quality of currently available capture continuations; must respect mandatory/max-capture rules.
- `promotion_pressure_delta`: deterministic distance-to-promotion pressure for men, orientation-aware.
- `blocked_man_delta`: own blocked men versus opponent blocked men.
- `advanced_man_delta`: deterministic advancement statistic, orientation-aware.
- `center_presence_delta`: occupancy of a preregistered central region, if and only if the geometry definition is exact and symmetry-safe.
- `terminal_flag`: exact terminal status encoded separately; context must never override it.

Optional components such as tempo, structural formations or king activity must be added only in later ablations after an exact definition and symmetry tests. Avoid smuggling expert intuition into v1 through opaque composite features.

## Context transition

For a legal move `a_t: s_t -> s_{t+1}`:

`DeltaC_t = C_mover(s_{t+1}) - C_mover(s_t)`

where both vectors are explicitly represented from the POV of the player who selected `a_t`. The implementation must not subtract two side-to-move vectors without correcting the POV flip.

This vector is descriptive. It is not itself a reward and is never used by self-play to select a move in the first experiment.

## Frozen scalar baseline B(C)

We need a scalar only to construct the residual `Rctx`. It must be transparent and deterministic.

V1 baseline:

`raw = sum_i w_i * C_i`

`B(C) = tanh(raw / tau)`

Initial weights are preregistered, simple and deliberately conservative. Material-related terms may dominate v1, but kings remain a separate coefficient. No coefficient may be fitted on confirmation/frozen-test outcomes.

The first scientific stage MUST include baseline calibration diagnostics against the exact Mini-Jass oracle. If the handcrafted baseline is badly ordered or anti-correlated with exact value, the residual arm is diagnostic-only and cannot be selected.

Later stages may fit `B(C)` on a train-only solved cohort, but that is a distinct experiment and must be compared with the deterministic v1 baseline.

## Targets

### Main target — unchanged

`value_target = Z_t`

Use the same WDL convention as the production-like trainer. Do not replace WDL with context-adjusted WDL.

### Auxiliary context target

Predict `C(s_t)` from the shared pattern representation.

Because production Jass is a value-only linear pattern evaluator, do **not** permanently attach a large neural head. For Mini-Jass experiments, auxiliary predictions should be implemented as either:

- additional small linear readouts from the same active folded pattern buckets, used only during training; or
- an equivalent multi-task linear objective whose auxiliary parameters can be discarded after training.

The deployed/evaluated candidate must still answer positions through the normal scalar value evaluator + search path.

### Auxiliary transition target

Predict `DeltaC_t` from the state/action-derived training record, or use it to weight an auxiliary consistency loss. This arm must remain separate from the context-state arm so we can identify whether absolute context or improvement along the trajectory carries signal.

### Contextual residual target

`Rctx_t = clip(Z_t - B(C(s_t)), -rmax, +rmax)`

This residual is an auxiliary target only. It expresses whether the eventual result was better or worse than the deterministic context baseline predicted.

Examples under `[-1,0,+1]` WDL:

- context baseline `-0.55`, terminal draw `0` -> residual `+0.55`;
- context baseline `+0.70`, terminal draw `0` -> residual `-0.70`;
- context baseline `-0.20`, terminal win `+1` -> residual `+1.20` before clipping.

## Loss family

Baseline:

`L0 = L_wdl`

Context arm:

`L = L_wdl + beta * L_context`

Transition arm:

`L = L_wdl + gamma * L_delta_context`

Residual arm:

`L = L_wdl + eta * L_residual`

Full arm:

`L = L_wdl + beta * L_context + gamma * L_delta_context + eta * L_residual`

Weights must be preregistered and screened on development only. Confirmation is read once after the candidate recipe is frozen.

## Scientific sequence

### C0 — invariants and oracle characterization

Before training:

- prove every context feature is deterministic;
- prove colour/rotation POV symmetry;
- prove terminal states are handled exactly;
- measure correlation/ordering of each context component with exact oracle value;
- measure `DeltaC` against exact one-ply oracle value change;
- measure residual distribution by W/D/L and by context strata;
- report redundancy/correlation between context dimensions.

This stage selects no model. Its purpose is to catch bad handcrafted rules before they influence training.

### C1 — isolated auxiliary ablation

Use the rebuilt production-like architecture and a frozen self-play dataset/trajectory pack so targets cannot change behaviour.

Paired arms:

1. `WDL_ONLY`.
2. `WDL_PLUS_CONTEXT`.
3. `WDL_PLUS_DELTA_CONTEXT`.
4. `WDL_PLUS_RESIDUAL`.
5. `WDL_PLUS_FULL_CONTEXT`.
6. `ORACLE_VALUE` diagnostic upper bound, never promotable.

Same active pattern representation, initialization family, replay records, sample counts and optimizer updates across non-oracle arms.

Primary endpoint: common-search paired arena strength.

Secondary endpoints: exact value ordering/sign/regret under oracle, WDL calibration, and performance stratified by material/mobility/context disadvantage.

The contextual hypothesis is especially supported if disadvantaged-state strata improve without degrading neutral/favourable strata.

### C2 — credit assignment localization

If C1 passes, test where the gain comes from:

- absolute context only;
- transition/delta only;
- residual only;
- context + residual;
- full combination.

Also test whether auxiliary readouts can be discarded after training with no loss in arena strength. This is required for production parity.

### C3 — baseline sophistication

Only after deterministic v1 is validated:

- deterministic hand baseline;
- train-only calibrated linear/logistic baseline `B(C)`;
- optional context-conditional WDL baseline `P(W,D,L | C)` trained only on train solved states.

The oracle can evaluate these baselines but cannot provide targets to the deployable arm.

## Reward-shaping boundary

Do not feed `DeltaC`, `Rctx` or any handcrafted context score back into self-play action selection in C0-C3. Doing so would change the policy and confound supervision with behaviour.

A later, separately preregistered experiment may test potential-based shaping. If done, the shaping term must have the potential-difference form and must be compared against an unshaped behaviour control. It is not part of this PR.

## Interaction with search

The rebuilt Mini-Jass architecture has no policy head; actions come from search over the scalar value evaluator. Therefore all final candidate comparisons must use the **same common arena search**. Auxiliary training heads/readouts cannot participate in move selection.

Report both static evaluator quality and search-amplified arena quality. A contextual objective that improves static metrics but loses in common-search arena is rejected.

## Required implementation objects

Suggested isolated modules under `mini_jass/python/mini_jass_lab/`:

- `context.py`: deterministic feature extraction and POV/symmetry helpers.
- `context_targets.py`: `DeltaC`, baseline `B`, residual construction.
- `context_train.py`: auxiliary linear readouts / multi-task loss without changing production-like inference.

Suggested experiment tooling:

- `mini_jass/configs/contextual_outcome_supervision.yaml`;
- `mini_jass/tools/run_contextual_outcome_supervision.py`;
- focused tests for context invariants, leakage and training isolation;
- CPX wrapper only after the architecture-rebuild baseline is frozen.

## Fail-closed requirements

- no oracle read in self-play generation, target construction for deployable arms, sample selection, loss weighting or promotion;
- exact same replay sample IDs across C1 paired arms;
- exact same WDL targets across C1 non-oracle arms;
- context targets derived only from the board/move record;
- context feature definitions hashed into the result contract;
- baseline coefficients/tau hashed into the result contract;
- common arena starts/search/seeds across arms;
- 20 seeds minimum by default, increased by preregistered power analysis;
- compact summary under GitOps inline limit with phase timings;
- no post-hoc winner advances without fresh-seed replication.

## Interpretation

A PASS would not mean that WDL was wrong. It would mean that WDL alone is an insufficiently dense supervision signal for the production-like representation, and deterministic context provides useful credit assignment while preserving the terminal game objective.

A FAIL would be equally useful: it would reject the hypothesis that handcrafted material/mobility/position context is the missing supervision channel, preventing us from embedding subjective heuristics into Jass without evidence.

## Boundaries

- `promotable: false`
- `production_jass_changes_authorized: false`
- `direct_10x10_transfer_authorized: false`
- implementation must wait for the rebuilt production-like Mini-Jass baseline/ceiling to be frozen enough that the comparison is interpretable.
