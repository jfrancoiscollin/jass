# ED3-P1 — one soft-preference value candidate, then a separate fresh confirmation

Date: 2026-09-08. Mandate: user "Go next step", following the authorized ED3
continuation and launch-process hardening. Prospective scientific change.

## Scope and immutable evidence

ED2-N1 1878 / 20260908T191343Z-d71679e9 ended correctly with
`ED2_N1_PARTIAL_ORDER_VALUE_NOT_SUPPORTED_V1`. Neither that result nor the original
failed ED2-P1 is rewritten. CURRICULUM remains champion.
ED3 TRAIN diagnostic 1880 / 20260908T203314Z-b074eeaf completed with
`ED3_TRAIN_PRESSURE_DIAGNOSTIC_COMPLETE_V1`; its evidence is exploratory only.
The ED3-P0 scale rule was frozen before that diagnostic: weighted median positive
TRAIN gap divided by log(3). Its result on the frozen TRAIN is approximately
66.44746354375913; this is recomputed by the rule, not fitted or selected.

**This stage implements actual candidate learning and native artifact sealing.**
It does not implement or claim a held-out evaluation, runtime Gate0, Elo or
compounding result. The prior audit receipt cannot admit this different pipeline.
The future confirmation must have its own preregistration and full-path rehearsal.
No confirmation data are generated or scored by P1.

## Single scientific contrast

Same WDL_CONTROL starting bytes as ED2, same 240 existing MG/EG extras, frozen
pattern table and header, same original coordinate system, same historical WDL
replay, same ridge and solver. The only intended statistical treatment change is
hard retained preferences -> graduated retained preferences.

BASE SHA256: e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0.
HARD control: ED2-N1 PARTIAL, SHA256
3db65fe6dcc3dc828a7467ac27a43c4904c33d5791b484a2b2f19efcef70570e.
HARD is not refit. Neither is substituted for CURRICULUM.

Production uses all 512 existing TRAIN parents, 64 per phase/STM cell, 4976
children, 17622 retained nonterminal pairs, and the same 8192 replay rows. The
source seal is 31f763049fef50544bd1cbb240eeb4f51670728ae0697a77e982186df007152c.
Every label file, source file and replay selection/byte hash is verified using the
existing completed-run manifest/inventory/checksum fetcher. The source prefixes
are literal pinned identities in ed3_label_pressure.py. This is not a reuse of
old TEST targets. Neither ED2 TEST200k nor the old WDL holdout metrics are fetched.
Transporting the existing full Context30 array is permitted; only the sealed
TRAIN replay indices are dereferenced. No new teacher or Jass search occurs.

## Objective and numerical contract

For a retained pair a>b let g=Q50k(a)-Q50k(b)>0, mass=1/(512*retained_pairs(parent)),
and d be the new evaluator's parent-POV margin. Define

    tau = weighted_median_positive_train_gap / log(3)
    p = sigmoid(g/tau)
    L_pair = sum_pairs mass * [p*softplus(-d) + (1-p)*softplus(d)]
    L = L_pair + mean_replay(softplus(z)-y*z) + 0.0005*||beta||^2.

The full TRAIN parent-weighted median defines tau for both rehearsal and
production. At the median gap, p=0.75. This is a preference target, NOT a WDL
probability or certified teacher confidence. No clipping, temperature sweep,
margin threshold, feature addition, label-volume matching or checkpoint choice.
Parents with zero retained pairs contribute zero, not resampled weight.

Use float64 trust-exact and analytic Hessian, zero beta, maxiter=500, gtol=1e-6,
initial_trust_radius=1, max_trust_radius=1000, eta=0.15, exactly as ED2-N1. Cache
identical derivative calls only. Require solver success, finite output, and
L2 norm of the original-coordinate gradient <=1e-6. Publish the objective-gap
upper bound ||gradient||^2/(2*0.001). The numeric solve is capped at 300 seconds.
Failure is NUMERICAL/TECHNICAL, not a scientific rejection. No fallback or retry
with changed settings is allowed within this version. A solver report is written
before convergence refusal when finite values exist; original-phase/type/source
failure evidence is written in the same job.

## Own complete target-host rehearsal

The common V2 profile is jobs/launch_profiles/ed3-soft-value-fit-v1.json.
CI must first execute derivatives, representative-scale convergence, complete
candidate producer/consumer fixtures, the real stage runner and original
publisher/checksum readback, and the actual compiled C++ native probe.
Mandatory launch regression suites must be nonempty, successful and unskipped.

The CPX rehearsal uses exactly the first 8 TRAIN parents in each of 8 cells (64
parents), with the full 8192-row replay. This exercises realistic production
features and correlations, the SAME objective construction, solver, quantizer,
native executable, artifact sealing and outer publisher. Pair normalizer is 64
for that miniature only; tau still comes from the fixed full TRAIN rule. Its
model is explicitly `development_only` and is never copied into production or
used as the scientific candidate. No parameter is chosen from this rehearsal.
Exactly one development invocation is allowed, distinct from the one scientific
production invocation; both are counted as fits by the launch effect ledger.

The production admission must authenticate the completed rehearsal from R2,
including successful marker, exact code/profile/normalized-spec/runtime, actual
candidate bytes and output hashes. A changed entrypoint, profile or scientific
configuration invalidates the proof. Only LAUNCH_MODE differs between the two
specifications; mode-dependent miniature volume is frozen here. Rehearsal success
is not a statistical validation of learning or generalization.

## Native artifact, preservation and terminal

Reuse the native evaluator probe archived by the exact completed CPX ED2-N1 run.
Authenticate both compressed and executable hashes against its cleanup receipt;
run on the same required cpx62 host/16-CPU profile. No source-tree copy or rebuild
is introduced in the remote run. Actual execution/parity is checked before fitting.

BASE native features/logits must match the authenticated TRAIN/replay dumps.
Zero-residual serialization must be byte-identical. Quantize the SOFT extras with
ties-to-even at scale 1000 into an ordinary PJTW v3. Preserve every header/pattern
byte. Reload the new file through the C++ evaluator on both TRAIN and replay;
verify feature identity and logits against the quantized residual (absolute
floating tolerance 1e-9), then reload in a second process and require exact feature,
logit and final native integer-score replay. BASE and HARD remain byte-identical.
No Python-only surrogate substitutes for native evaluation.

Publish SOFT.pjtw, candidate-seal.json (role, hashes, source/control identities),
train-contract.json, fit-report.json, solver-diagnostic.json, native-roundtrip.json,
execution-evidence.json and scientific-summary.json. Rehearsal terminal:
`ED3_SOFT_VALUE_REHEARSAL_COMPLETE_V1`. Production terminal:
`ED3_SOFT_VALUE_CANDIDATE_SEALED_V1`. Neither is a positive scientific verdict.
Production next_stage is PREREGISTER_DISJOINT_ED3_CONFIRMATION, not automatic play.
All old inputs/results stay unchanged; no model overwrite or promotion.

## Bounded budget and next scientific decision

CPX62 with 16 available CPUs; one-thread numerical libraries. Zero new Scan/Jass
searches, zero held-out target reads, zero games, zero promotion/bake. One fit per
invocation, 300s solver cap; 900s stage cap and 1500s outer admission/regression cap.
These are hard limits, not elapsed-time predictions. Inputs are existing small
selected artifacts, not a new full-repository/build publication. Original R2
transport and finalization still determine wall time outside computational work.

After a production candidate is sealed, preregister one comparison against BOTH
BASE and HARD on previously unused evaluation parents and a distinct historical
WDL guard with exclusion identities verified before targets. The old ED2 TEST and
old holdout cannot select a candidate, scale, threshold or checkpoint. The future
stage must define actual source identities, support/independence limitations,
reference budgets and gates BEFORE reading new targets; a new pipeline needs its
own rehearsal. No promise of fresh WDL/gameplay evidence from historical rows.
No soft-candidate tuning is authorized by this stage's TRAIN diagnostics.
