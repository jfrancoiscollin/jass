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

The failed 1834 history is preserved. The corrected execution is requeued under a new job identity on the merged #815 code SHA.
