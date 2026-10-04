# L3 — R1 adjudicated relabel — review amendment v1

> Date: 9 September 2026
> Status: normative amendment to `L3_R1_ADJUDICATED_RELABEL_V1_20260909.md` for PR #888. If this document conflicts with the original preregistration, this amendment controls.
> Scope: tooling/preregistration only. No remote job, fit, game, promotion or change of champion is authorized by merge.

## 1. Program status relative to ED4

R1 is **PREREGISTERED_PARALLEL_NOT_ACTIVE** while the prospective ED4/C0A campaign is active. This PR MUST NOT replace the active frontier in `L3_CURRENT.md` or `PROJECT_RESULTS.md`. R1 can be activated only by a distinct JFC GO after ED4 reaches a terminal or JFC explicitly changes program priority.

For this reason PR #888 no longer modifies `docs/L3_CURRENT.md` or `docs/PROJECT_RESULTS.md`.

## 2. Single-factor scope; R2 mechanism removed

R1 changes exactly one scientific factor: the training target. The `--prior-precision-file` implementation and its tests belong to R2 and are removed from PR #888. R1 uses the existing byte-identical training recipe only:

```text
--exact-fold --tempo-stage
--prior-mean <CURRICULUM> --prior-decay 0
--l2 1e-5 --lbfgs-gtol 1e-4 --lbfgs-maxcor 20
```

Any per-coordinate prior precision remains a separate future preregistration and separate SHA.

## 3. Arm C is diagnostic only

The confirmatory family contains one primary contrast only: **B vs A**.

- A = reconstructed `context30` control.
- B = `y_R1 = 0.5 * p_term + 0.5 * p_adj`, primary confirmatory arm.
- C = `y_ADJ`, diagnostic arm only.

C MUST NOT unlock G3, force testing, bake or promotion under R1, regardless of its G2 result. Its pairwise/top-hit values may be published descriptively with confidence intervals, but they are non-decisional. This removes the sequential B-then-C multiplicity path from the original §4.3.

The only confirmatory G2 rule is therefore:

```text
R1_OFFLINE_DECISION_SUPPORTED     <=> lower 95% CI of pairwise(B)-pairwise(A) > 0
                                     AND top-hit(B)-top-hit(A) >= 0
R1_OFFLINE_DECISION_NOT_SUPPORTED otherwise
```

If B is NOT_SUPPORTED, R1 stops without strength games. A positive C diagnostic may motivate a separately preregistered future experiment, never a substitution inside R1.

## 4. Correct command name and phase coverage

In original §4.1, `--adjudicate-relabel` is a typo. The required micro-probe command is the implemented **`jass --deep-relabel`** path with the exact R1 flags (`depth 14`, EGDB, Q00 search params, draw band 50, `--clear-tt`, `--source-tags-out`).

In original §4.2, phase reporting is **P0–P4**, not P0–P3. The five bins are opening, midgame, late-mid, endgame and deep-eg, matching `phase_index_of` and the target-builder constants.

## 5. Consequences for terminal interpretation

The original §6 table is amended as follows:

- B G2 NOT_SUPPORTED -> `R1_OFFLINE_DECISION_NOT_SUPPORTED`; stop R1, zero strength games. C remains descriptive only.
- B G2 SUPPORTED + G3 NOT_ESTABLISHED -> static decision gain without demonstrated force transfer; read-only autopsy only.
- B G2 SUPPORTED + G3 ESTABLISHED -> R1 target is a strength-supported lever; bake still requires separate explicit authorization.

No R2/R3 activation follows automatically from any R1 result.
