# B3 exclusion fetch-receipt JSON incident — 1834

Date: 2026-09-06

Classification: **TECHNICAL**

Affected job: `cpx62-1834-l3-decision-math-b3-fresh-exclusion-prep-v1`, attempt `20260906T132605Z-e2762791`.

The stage failed with exit code 2 before producing the exclusion union. No fresh B3 parent, teacher search, fit, strength game, promotion or bake occurred.

## Root cause

`adaptive_sibling_b3_exclusion_prepare.py` authenticated its upstream inputs with `fetch_result_files.py`, then attempted to parse the fetch report with `read_canonical_json()`.

That assumption is invalid: `fetch_result_files.py --report` deliberately writes semantic JSON using `json.dumps(..., indent=2, sort_keys=True)`. The report is authenticated JSON, but it is not the compact canonical serialization used by frozen scientific receipts. The consumer therefore rejected a mechanically valid fetch report before reading the authenticated payloads.

## Durable invariant

Serialization requirements are ownership-specific:

- frozen scientific receipts that declare canonical bytes must continue to be read fail-closed as canonical JSON;
- generic `fetch_result_files.py` reports must be parsed as semantic JSON objects and validated by their authenticated fields, not by compact-byte equality;
- a consumer must not strengthen an upstream serialization contract implicitly.

## Correction / rerun

Jass PR #815 added `adaptive_sibling_b3_fresh_exclusion.py`, whose fetch boundary parses the generic fetch report semantically and then validates `state`, `result_state`, `exit_code`, `job_id`, `attempt_id`, `code_sha` and `prefix` explicitly. The scientific inputs and exclusion semantics remain unchanged.

The failed 1834 history is preserved. The corrected execution ran as `cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1`, attempt `20260906T134208Z-c553a572`, and completed with exit code 0.

Terminal proof:

- verdict: `B3_FRESH_EXCLUSION_PREPARATION_COMPLETE`;
- historical identities: 223,317;
- B2 confirmation identities: 4,000;
- cross-component overlap: 0;
- combined identities: 227,317;
- union SHA256: `b553939e8ded3ab31d121e40b2be9cfa1012168bf01835f692b59a60815d9ecb`;
- manifest SHA256: `f734de99761b7a3ee7ddb107de3d678fa29eb7e39a11708b6a8c8bbbe700cc0c`;
- fresh B3 parents, teacher searches, fits, strength games, promotions and bakes: 0.

The serialization-boundary correction is therefore runtime-proven and this incident is closed.
