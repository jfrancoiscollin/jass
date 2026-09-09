# ED4-C0A host identity overconstraint — 1889

Date: 2026-09-09. Classification: **TECHNICAL**.

Rehearsal 1889 reached `authenticate-envelopes` and then failed before any scientific verdict. The metadata collector compared the historical control-status `host` value with the authenticated outer result-manifest `host` as if host were part of the frozen source identity.

The C0A source identity contract freezes job, attempt, code SHA, result state and exit code together with authenticated descriptors. Host is useful authenticated evidence, but is not a scientific/source identity discriminator. Repair PR #889 therefore removes only host from the equality tuple while keeping job/attempt/code/state/exit fail-closed and adds a dedicated host-drift regression.

No source, allowlist, candidate, target, fit, threshold, alpha allocation, search budget, gate or verdict semantics changed. The incident remains MITIGATED until the same-contract target-host rerun 1890 proves the repair.
