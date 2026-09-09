# ED4-P0 — choice-set value objective and synthetic numerical preflight V1

Date: 2026-09-09. Prospective freeze before any synthetic calculation. ED4 does
not reopen ED3. ED1 supported PARTIAL labels on two exposed cohorts; ED2/ED3 did
not establish alignment of the all-pairs objective with choice. ED3-T1 cannot
identify a cause across its different TRAIN and Q200k estimands.

After commit, only implementation and synthetic preflight are authorized. No
archived read, real fit/model/candidate, engine work or remote job; fixture PJTW
bytes are permitted.

## Single future intervention

Only ordinal loss changes. Architecture, BASE bytes, PJTW pattern/header, 120
extras/240 MG-EG coordinates and order, TRAIN512, replay8192, both loss
coefficients 1, and ridge `0.0005*||beta||^2` remain unchanged.
BASE, HARD and SOFT stay frozen controls with SHA256 respectively
`e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0`,
`3db65fe6dcc3dc828a7467ac27a43c4904c33d5791b484a2b2f19efcef70570e`,
and `d8a193de2017a6c156a46d89692245bdc1af00d29d056af3a41e7d6d4f5a486a`.
The TRAIN source seal remains
`31f763049fef50544bd1cbb240eeb4f51670728ae0697a77e982186df007152c`.
P0 records these as metadata without fetching them.

For parent `p`, let `V_p` be its nonterminal children and retain the exact
PARTIAL directed edge `a -> b` iff
`min(Q5k(a),Q50k(a)) > max(Q5k(b),Q50k(b))`. Let `A_p` be the children in
`V_p` with no incoming retained edge (the arrow enters the inferior child): the
maximal, not-known-inferior choice set. For black-POV native logit `z0`, frozen
feature row `x`, and parent sign `s_p=+1` for parent STM 1 and `-1` for STM 0,
define `u_i(beta)=s_p*(z0_i+x_i beta)` and

```
ell_p(beta) = logsumexp_{i in V_p} u_i(beta)
              - logsumexp_{a in A_p} u_a(beta)
L(beta) = (1/512) sum_p ell_p(beta)
          + mean_replay[softplus(z)-y*z]
          + 0.0005*||beta||^2.
```

This maximizes softmax mass on the admissible set without prescribing an ordering within it.
`V_p` empty or `A_p=V_p` contributes zero while remaining in denominator 512.
Nonempty `V_p` with empty `A_p` fails closed. Terminals never enter this term.

No temperature, margin, clipping, alternative target distribution, WDL change,
edge filtering, sweep or checkpoint choice.

## Non-convex numerical contract for a future candidate

For `|A_p|>1`, the Hessian is covariance over `V_p` minus covariance over `A_p`
and can be indefinite; ridge does not ensure global convexity. No global optimum,
uniqueness, strong-convexity gap bound or ED2 global certificate is claimed.

A later separately authorized real fit uses float64 analytic value, gradient and
Hessian; zero beta; SciPy `trust-exact`; maxiter 500, gtol `1e-6`, initial trust
radius 1, maximum radius 1000, eta 0.15; one invocation and a 300-second cap.
No restart, fallback or changed initialization. Numerical acceptance
requires solver success, finite state, `||gradient||_2 <= 1e-6`, symmetric
Hessian, minimum Hessian eigenvalue `>= -1e-8`, and
`L(beta_final) <= L(0)+1e-12`. This establishes only an approximate second-order
stationary point on that trajectory. Failure permits no V1 parameter change.

If later authorized, quantize once at scale 1000, ties-to-even, into PJTW v3,
preserving header/pattern bytes. Reload natively twice; require exact features
and integer scores, logit reconstruction within `1e-9`, finite objective and
`L(beta_quantized) <= L(0)+1e-12`. A sealed artifact is not a success or promotion.

## P0 synthetic preflight

P0 has no source/artifact input option. It uses exactly one formula-generated
fixture with NumPy `default_rng(910)`, 24 parents x 4 siblings = 96 TRAIN rows,
192 replay rows and 240 coordinates; no sweep. Generate 288x120 binary raw
features, mask columns 0..99 independently with probability .05, multiply
columns 100..119 by `[1,20,60,150,2]` repeated four times, then set column 101
to twice column 100. Draw phase from `[0,.05,.2,.65,1]` and form the 240 MG/EG
columns. Draw TRAIN/replay base logits from standard normal and set replay
`y=expit(replay_logit+0.1*standard_normal)` in that exact RNG call order.

Parent `p` has STM `p mod 2` and equal synthetic Q5/Q50 vectors by `p mod 4`:
0 uses `[1,0,0,0]`; 1 uses `[2,2,1,0]`; 2 uses `[0,0,0,0]`; 3 marks all rows
terminal. Form every strict edge from these scores, including transitive pairs.
Thus the admissible sets are respectively `{0}`, `{0,1}`, all four, and empty.
The synthetic parent normalizer is 24; a separate exact assertion fixes the real normalizer at
512. Solve this nonsymmetric problem twice from zero through the future path.
Require byte-identical reports, solver success and all criteria above. Quantize
the identical fitted beta without another solve; its objective on this same
problem must be no worse than beta zero.

An analytic rejection fixture has one active parent with `V={0,1,2}`,
`A={0,1}`, first-coordinate features `[-10,+10,0]`, 511 all-terminal parents and
zero-feature replay. At beta zero its gradient is zero but its full first-axis
curvature, including ridge, is `-100/(3*512)+0.001 < 0`; the second-order gate
must reject this symmetric saddle even if the solver reports success.

Additional exact assertions cover `A=V` zero loss/gradient/Hessian; all-terminal
`V` empty; rejection of nonempty `V` with empty `A`; retained-edge direction;
and stable logits `[-1000,0,+1000]`. At
`beta=linspace(-0.001,0.001,240)`, check coordinates
`[0,49,100,104,120,220,239]` by central differences with step `1e-7`: gradient
absolute error `<=1e-6`, Hessian `rtol<=1e-5` and `atol<=1e-5`, and analytic
Hessian asymmetry `<=1e-10`.

Exercise scale-1000 ties-to-even quantization and two-process, freshly built
`ed2_value_probe` reload on 16 committed literal score-free legal-format JNNW records
and a synthetic zero-weight normal-layout PJTW v3 with 120 extras. Require
a nonzero representable residual, exact feature/order preservation, `<=1e-9`
logit mapping and exact repeated integer scores. The synthetic model is marked
development-only and is never a candidate. No production BASE/model/data bytes
may be read. One CPU, one-thread numeric libraries, 60-second numeric/solve cap
and 300-second whole preflight cap; timeout or any failed check ends P0 without
retry or parameter change.

The implementation commit must freeze those records as 16 literal hex-encoded
38-byte payloads before any test. A deterministic fixture encoder may construct
them, but no engine generation, archived source or target value is permitted;
the compiled probe must accept their native layout. Any later semantic change to
objective, fixture or gate requires a prospective amendment before testing.

Missing compiled probe fails; numeric-only checks cannot emit the terminal.
Ordinary CI is authorized, no CPX/control queue. Publish fixture hashes, checks,
non-convex witness, two solve reports, native roundtrip and an effect ledger with
`synthetic_optimizer_invocations=2` per complete preflight receipt,
`real_fits=0`, and every real-data read,
real model/candidate, search, game, promotion and bake equal to zero. Terminal:
`ED4_CHOICE_SET_OBJECTIVE_PREFLIGHT_COMPLETE_V1`; classification
`SYNTHETIC_TECHNICAL_ONLY`; next `REVIEW_AND_PREREGISTER_ED4_CANDIDATE`;
`automatic_continuation=false`, `runtime_authorized=false`.

Each local/CI receipt counts its own two solves. Mocked failures add none.

P0 success shows only path coherence. Real fit needs separate GO; evaluation
needs a fresh target-blind contract before target reads. ED2/ED3/1884 provide
exclusions/context only, never tuning. `STOP_ED3` and `CURRICULUM` remain.
