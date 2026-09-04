# JFI campaign terminal readout v1

Date: 2026-09-04  
Status: **TERMINAL SCIENTIFIC READOUT**  
Program: Jass-native Fit Identifiability / active learning (JFI)  
Frozen preregistration: `docs/experiments/L3_JASS_NATIVE_IDENTIFIABILITY_ACTIVE_LEARNING_V1_20260901.md`  
Path amendment: `docs/experiments/L3_JFI_PATH_AMENDMENT_V1_20260903.md`

This document records the terminal findings of the JFI-v1 campaign. It does **not** modify the preregistration retrospectively. The preregistration and amendment remain the immutable statements of the hypotheses, gates, seeds and stopping rules that existed before the corresponding results were read.

---

## 1. Executive conclusion

JFI-v1 did not establish that the preregistered Fisher/leverage ACTIVE selector improves Jass-native PatternEval learning at fixed data volume.

The terminal JFI-C verdict is:

```text
JFI_ACTIVE_INFORMATION_GAIN_NOT_ESTABLISHED
```

The important scientific result is stronger than a simple null result:

- the ACTIVE selector **did increase one preregistered information diagnostic** substantially;
- nevertheless ACTIVE **generalized significantly worse than matched UNIFORM** on the common DEV distribution;
- therefore, for this setup, increasing parameter-space information/coverage is **not sufficient** to improve predictive generalization.

The campaign also established two independent findings that materially change our understanding of the Jass learning problem:

1. optimizer initialization is not the main explanation of the historical basin effect once functional score equivalence is judged at tolerances consistent with the optimizer;
2. PatternEval is extremely under-identified under the current Jass corpus: most coordinates receive essentially no direct empirical support.

The practical research lesson is:

> Useful acquisition must optimize not only novelty/information, but information that is representative of and useful for the downstream distribution.

---

## 2. Terminal provenance

### JFI-A/B physical fits

```text
job    cpx62-1755-l3-jfi-factorial-l2-fit-v1
attempt 20260902T201244Z-6fa708d0
code   6fa708d0a293c8b39178d7202657a6875aa7cbed
```

All seven fitted checkpoints were persisted:

```text
A
B
C
D
L2_0
L2_1E6
L2_1E4
```

The original process exited with code 3 after the JFI-A scientific readout, but the seven models, optimizer receipts and readout JSONs survived. No fit compute was lost in this attempt.

### Path-dependence autopsy

```text
P1  cpx62-1759-l3-jfi-path-autopsy-p1-v1
P2  cpx62-1760-l3-jfi-path-autopsy-p2-v1
P3  cpx62-1761-l3-jfi-path-autopsy-p3-v1
```

Terminal autopsy verdict:

```text
JFI_PATH_DEPENDENCE_OBJECTIVE_TOLERANCE_ONLY
```

### JFI-A amendment readout

```text
job     cpx62-1762-l3-jfi-path-amendment-v1
attempt 20260903T175222Z-0b16c0fe
code    0b16c0fe7c24bb9d5ef4e206a6076b3bb2297220
```

Amended verdict:

```text
JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED
```

### JFI-B identifiability

```text
job     cpx62-1763-l3-jfi-identifiability-v1
attempt 20260903T184031Z-0b16c0fe
code    0b16c0fe7c24bb9d5ef4e206a6076b3bb2297220
```

### JFI-C Boundary B / candidate universe

```text
job     cpx62-1764-l3-jfi-boundary-b-v1
attempt 20260903T194826Z-0b16c0fe
code    0b16c0fe7c24bb9d5ef4e206a6076b3bb2297220
```

This froze the exact target-blind Jass-only candidate universe of 10,000,000 rows and carried forward the selected JFI-B lambda and Fisher information.

### JFI-C target-blind selection

```text
job     cpx62-1765-l3-jfi-active-select-v1
attempt 20260903T205130Z-0b16c0fe
code    0b16c0fe7c24bb9d5ef4e206a6076b3bb2297220
```

It published immutable, disjoint:

```text
ACTIVE_2M
UNIFORM_2M
```

before any Context30 target read.

### JFI-C fits and terminal publisher

```text
fit job     cpx62-1767-l3-jfi-active-fit-v1
fit attempt 20260903T215056Z-0b16c0fe
code        0b16c0fe7c24bb9d5ef4e206a6076b3bb2297220

terminal job     cpx62-1768-l3-jfi-active-terminal-publish-v1
terminal attempt 20260904T022956Z-0b16c0fe
code             0b16c0fe7c24bb9d5ef4e206a6076b3bb2297220
```

Terminal publisher exit code: `0`.

---

## 3. Finding A — the optimizer-path STOP was a tolerance artifact, not a material score difference

The original JFI-A readout stopped on same-center path dependence because the cross-endpoint objective difference exceeded the frozen `1e-6` compatibility threshold.

The autopsy showed that the actual score differences were tiny relative to the preregistered materiality bounds.

Approximate observed contrasts:

```text
A vs B, same CURRICULUM center:
  score RMS  ~= 0.0207 cp
  score max  ~= 0.202 cp

C vs D, same ZERO center:
  score RMS  ~= 0.0222 cp
  score max  ~= 0.281 cp
```

Original materiality limits:

```text
score RMS <= 0.5 cp
score max <= 2.0 cp
```

The objective differences were of order a few `1e-6`, while each endpoint independently satisfied the frozen optimizer convergence requirement (`success=true`, `status=0`, gradient infinity norm <= `gtol=1e-4`).

The terminal autopsy therefore established:

```text
JFI_PATH_DEPENDENCE_OBJECTIVE_TOLERANCE_ONLY
```

The amendment made cross-endpoint objective difference descriptive rather than a standalone path-independence gate, while retaining the original score materiality thresholds and individual optimizer convergence requirements.

### Interpretation

For the convex logistic + positive-L2 problem used here, the campaign provides no evidence that a practically meaningful local-minimum/path instability explains the historical Jass basin behavior.

The prior/ridge center and data identifiability remain the more plausible mechanisms.

### Methodological lesson

A numerical equivalence gate must be calibrated to the actual optimizer stopping criterion. Requiring objective equality substantially tighter than implied by `gtol` can manufacture a false scientific STOP even when serialized score functions are effectively indistinguishable.

---

## 4. Finding B — zero-centered L2 selection

The frozen one-standard-error JFI-B rule selected:

```text
lambda = 1e-5
```

This lambda remained frozen through JFI-C. No downstream selector or fit changed it.

The `l2=0` arm remained diagnostic-only as preregistered.

---

## 5. Finding C — PatternEval is massively under-identified by the current Jass corpus

JFI-B measured identifiability over:

```text
coordinates = 8,503,296
effective_df = 23,687.41324462831
selected_l2 = 1e-5
```

Coordinate-class fractions:

```text
UNSEEN          = 0.9700640786819605   (~97.0064%)
PRIOR_DOMINATED = 0.022686026688945087 (~2.2686%)
MIXED           = 0.007134409998193642 (~0.7134%)
DATA_DOMINATED  = 0.00011548463090077071 (~0.01155%)
```

Data-to-ridge gradient ratio:

```text
92.00535860413655
```

### Interpretation

The striking result is not that ridge globally dominates every fitted direction. Rather, the exact coordinate design is extremely sparse: roughly 97% of PatternEval coordinates are never directly activated by the consumed training corpus, and only a tiny fraction classify as strongly data-dominated under the frozen JFI-B rule.

This means that a very large fraction of the nominal PatternEval parameter space is not empirically identified by the current corpus.

### What this helps explain

This finding is consistent with several long-running Jass observations:

- repeated fits can converge to broadly similar functional behavior;
- iterative self-play generations have struggled to compound learning strongly;
- corpus coverage matters disproportionately;
- many coordinates remain decided by regularization/default behavior because the data never constrain them;
- adding more rows is not automatically equivalent to adding more useful independent information.

This does **not** prove that every unseen coordinate matters for strength. Many may correspond to extremely rare or low-value states. The central issue is therefore not merely maximizing the number of activated coordinates, but identifying which additional information is useful.

---

## 6. Finding D — Fisher ACTIVE successfully increased effective information coverage

JFI-C was a clean fixed-volume causal comparison:

```text
candidate universe = 10,000,000 Jass-only rows
ACTIVE             = 2,000,000 rows
UNIFORM            = 2,000,000 rows
selection          = target-blind
ACTIVE/UNIFORM     = disjoint
lambda             = 1e-5
init               = ZERO for both
L2 center          = ZERO for both
Context30          = one common reconstruction after selection freeze
DEV                = common and byte-identical target tail
Scan reads          = 0
strength games      = 0
```

The selector did what it was designed to do on at least one preregistered information diagnostic:

```text
effective_df ACTIVE  = 28,661.593408773857
effective_df UNIFORM = 16,993.85716488905

ACTIVE > UNIFORM: true
```

Therefore:

```text
INFO_GATE_PASS = true
```

This is important: the negative JFI-C result cannot be dismissed as a selector implementation that failed to find high-information rows. The selector materially changed the information geometry in the predicted direction.

---

## 7. Finding E — greater information coverage did not improve generalization

Common DEV:

```text
rows            = 997,917
unique openings = 66,628
```

Primary terminal statistic:

```text
DeltaCE = CE_ACTIVE - CE_UNIFORM
        = +0.0015633702058855904

cluster-bootstrap CI95
  low  = +0.0013953909758329833
  high = +0.0017333078907936525
```

The entire confidence interval is above zero.

Therefore ACTIVE is not merely tied with UNIFORM or noisy around zero: under the frozen DEV metric, it is **significantly worse**.

```text
CE_GATE_PASS = false
```

Other information diagnostics:

```text
DATA_DOMINATED fraction ACTIVE
  = 0.00006585681599229287
  ~= 0.00659%

DATA_DOMINATED fraction UNIFORM
  = 0.00012465754455684007
  ~= 0.01247%

ACTIVE > UNIFORM: false
```

Posterior-variance proxy median:

```text
ACTIVE  = 100000
UNIFORM = 100000
ACTIVE < UNIFORM: false
```

Thus JFI-C passed one information sub-gate (effective df) but failed the required CE gate.

Terminal verdict:

```text
JFI_ACTIVE_INFORMATION_GAIN_NOT_ESTABLISHED
```

---

## 8. Finding F — the JFI-C result is not an optimizer-convergence failure

Both JFI-C fits converged under the same frozen optimizer contract.

```text
ACTIVE
  iterations        = 1411
  gradient_inf_norm = 9.520059964412843e-05

UNIFORM
  iterations        = 1547
  gradient_inf_norm = 7.308485446965693e-05
```

Both gradients are below:

```text
gtol = 1e-4
```

The negative CE result should therefore be interpreted scientifically, not as a failed or obviously under-converged ACTIVE arm.

---

## 9. What hypothesis is rejected

The following JFI-v1 hypothesis is rejected for the exact frozen setup tested:

> At fixed volume, selecting Jass-only rows using the preregistered target-blind diagonal-Fisher/leverage criterion will improve downstream Context30 DEV generalization relative to a matched UNIFORM sample.

It did not.

More strongly, the experiment showed:

> A selector can increase effective parameter-space coverage while simultaneously worsening predictive generalization.

This falsifies the simple identification:

```text
more Fisher information / more effective df
        ==
better evaluation
```

for this data/model/selector combination.

---

## 10. What is NOT rejected

The campaign does **not** establish any of the following broader claims:

- all active learning is useless for Jass;
- information-theoretic data acquisition is useless;
- the current PatternEval architecture cannot improve;
- UNIFORM is globally optimal;
- the JFI-C ACTIVE model is necessarily weaker in Elo;
- diversity is harmful in general;
- additional data cannot help.

No FORCE games were run for the JFI-C candidate, by design. Therefore the campaign makes no direct causal Elo claim about ACTIVE vs UNIFORM or ACTIVE vs CURRICULUM.

The terminal STOP occurred earlier because the preregistered predictive gate failed decisively.

---

## 11. Best current interpretation

The most plausible interpretation of JFI-C is a **usefulness/representativity mismatch**.

The diagonal leverage score preferentially seeks coordinates with little existing Fisher support. That is exactly how it increases effective df. But low-support directions can be rare, peripheral or weakly represented in the downstream DEV distribution.

A fixed 2M budget spent aggressively on such directions can therefore trade away repeated observations of common, important states in exchange for broad but low-utility coverage.

A concise model of the result is:

```text
ACTIVE learned more different directions,
but UNIFORM learned the downstream distribution better.
```

This is an interpretation supported by the joint pattern of results; it is not itself a separately randomized causal experiment.

---

## 12. Research implications for the next campaign

The next data-acquisition hypothesis should no longer optimize raw information gain alone.

A more promising conceptual objective is:

```text
useful acquisition
  = information gain
  x representativity / density
  x downstream relevance
```

Candidate directions for a **new preregistration**, not authorized by this readout, include:

1. **density- or representativity-weighted information selection** — penalize extremely rare leverage spikes;
2. **hybrid UNIFORM + ACTIVE acquisition** — preserve broad distributional coverage while reserving a controlled portion of the budget for under-identified regions;
3. **cross-fitted residual acquisition** — use predictions from a pilot trained on disjoint data to target states with reproducible downstream error, without leaking the evaluation target into row selection;
4. **expected loss-reduction criteria** — rank rows by expected impact on held-out predictive loss rather than parameter uncertainty alone;
5. **structured coverage constraints** — protect phase/material/opening/pattern-family density while seeking information inside each representative stratum;
6. **information per downstream mass** — prioritize under-identified coordinates only when they are activated by a non-negligible fraction of the target distribution.

Any concrete score, mixture ratio, pilot model, quota or new gate must be preregistered before reading new comparative outcomes. JFI-v1 must not be retrofitted post hoc.

---

## 13. Reusable scientific assets

The campaign leaves reusable frozen artifacts rather than only a terminal verdict.

From JFI-A/B:

- seven physical fit checkpoints;
- optimizer/convergence receipts;
- selected lambda `1e-5`;
- Fisher vector and per-coordinate identifiability diagnostics;
- path-autopsy evidence.

From JFI-C:

- immutable 10M candidate universe;
- immutable ACTIVE_2M and UNIFORM_2M row-ID manifests;
- common Context30 target reconstruction;
- `JFI_C_ACTIVE.pjtw.gz`;
- `JFI_C_UNIFORM.pjtw.gz`;
- ACTIVE and UNIFORM Fisher arrays;
- coordinate diagnostics for both arms;
- terminal paired DEV/bootstrap readout.

These assets can support read-only forensic analysis without repeating the expensive fits.

They must not be used to post-hoc tune the already-terminal JFI-v1 selector and then claim a preregistered JFI-v1 success.

---

## 14. Campaign-level verdict

### Established

```text
1. Functional optimizer path independence is established under the amended,
   optimizer-consistent gate.

2. Positive zero-centered lambda selected by the frozen JFI-B rule is 1e-5.

3. Current Jass data leave the overwhelming majority of PatternEval coordinates
   empirically unseen / weakly identified.

4. Target-blind Fisher/leverage ACTIVE selection can materially increase
   effective degrees of freedom at fixed volume.

5. That increase did not translate into better DEV prediction; it produced a
   statistically significant CE regression relative to matched UNIFORM.
```

### Not established

```text
1. JFI-v1 ACTIVE information gain as an evaluation improvement.
2. JFI-D JASS_NATIVE_ACTIVE_V1 candidate superiority.
3. Any FORCE/Elo improvement from JFI-C.
4. Any promotion case.
```

### Terminal action

```text
STOP AFTER JFI-C
NO JFI-D
NO JFI-E FORCE
NO PROMOTION
```

---

## 15. One-sentence takeaway

> JFI-v1 showed that Jass is severely information-starved in parameter space, but also that chasing the rarest under-identified directions with raw Fisher leverage is the wrong objective: **information must be aligned with the distribution and loss that ultimately matter.**
