# Launch admission V2 — deployment evidence, 2026-09-08

User mandate: ED3 continuation and executable launch-process hardening.
This receipt records operational evidence, not a positive ED3 learning result.

## Integrated implementation and tests

- Jass #877 merged as `b074eeafa32a578108bf30e3b329c83e956b2b24`.
- Full-chain CI `34273484182`: PASS, 23 top-level tests, no skips.
  Actual v1 stage runner -> complete synthetic ED3 audit -> original publisher
  -> authenticated checksum-verifying fetch. The network transport alone is a
  local fake rclone. Missing terminal marker and changed spec are rejected.
- Native/Python/WASM build workflow `34273484205`: PASS.
- Initial rehearsal CI `34273087001` caught a canonical-spec vs raw-file-byte
  hash mismatch before any CPX launch. The fix preserves both identities; the
  integration regression proves their distinction through published artifacts.
- jass-control #576 merged as `96fe5b8668ab99f97c446a30cbadbc64d69c150f`.
  Shared dispatcher requires a pinned V2 admission, no ungated fallback.
- Control workflow `34274304113`: PASS. Five tests also passed locally against
  the exact pending wrapper/spec/admission, including rejection of missing or
  corrupt admission and wrong code/path. Queue CI checks canonical wrappers.

## Actual target-host execution

First full real-host rehearsal:

- job `cpx62-1879-l3-ed3-train-pressure-rehearsal-v1`;
- attempt `20260908T202244Z-b074eeaf`;
- code `b074eeafa32a578108bf30e3b329c83e956b2b24`;
- launch published at `2026-09-08T20:22:48Z`;
- status source: jass-control/status/cpx62-1879-l3-ed3-train-pressure-rehearsal-v1.json.

At the time this receipt was first written, only its launch/RUNNING record was
published. A launch record is not terminal or live-progress proof. The incident
remains MITIGATED until the successful published rehearsal is authenticated and
read back by a matching production admission. No repeated polling may be described
as a fresh process observation when the status has not changed.

## Non-negotiable scope boundaries

This job is the complete read-only ED3 TRAIN/replay diagnostic, with zero fit,
new Scan/Jass searches, TEST target reads, games or promotion/bake. It reuses
sealed source/model files; it does not generate any scientific confirmation set.
Its admission receipt CANNOT authorize the future soft-preference learner.
That learner still requires its own implementation/preregistration, representative
numerical and native-artifact tests, untouched evaluation data, complete miniature
execution and successful target-host publication/readback on its exact code.

Runtime enforcement covers the shared stage dispatcher. Existing bespoke historic
non-stage launchers are not implicitly migrated. GitHub branch-protection settings
were not changed. CI success does not replace actual target-host proof.

Later documentation commits do not alter this pinned attempt. A matching follow-up
must retain its exact rehearsed code/profile/normalized spec/runtime or rehearse
again. ED2-N1's negative terminal and CURRICULUM champion status remain unchanged.
