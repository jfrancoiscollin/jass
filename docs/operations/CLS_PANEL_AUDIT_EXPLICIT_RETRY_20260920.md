# CLS panel historical audit — explicitly authorized technical retry

Date: 2026-09-20. Operational continuation of PR #1052; no new scientific protocol.

## Authority and scope

After the report of the 2070 integer-JSON/string-TSV reader defect and the explicit statement that no retry had been launched, JFC answered **"Va y"**. This authorizes one reviewed technical retry of the same historical audit. It is not an automatic retry and does not authorize readiness games, LOCAL/WDL main matches, a HIER replay, training, G0 redecision, promotion or bake.

The source defect is confined to `G0_MISSING_INVENTORY`: canonical uint32 JSON numbers and decimal strings are losslessly normalized before exact ordered comparison. No identity, order, count, missing receipt, category, candidate, root, scientific parameter or original result is changed. The corrected core blob is `2aae455d2b6cb7c8d31fbef5c56dfe1e18f5cb87`.

## Accounting without a larger campaign envelope

Failed source: `cpx62-2070-l3-cls-g0-panel-historical-audit-v1`, attempt `20260920T180309Z-744c004c`, code `744c004cabff817b29e5bb7df3a6162d7048a38e`, status blob `156018dddee8b63d17b51165f8b244da12dace26`. Preserve FAILED/exit 2 and all its archives.

The observed runner interval is 18:03:13–18:09:39 UTC (386 seconds); including the attempt timestamp at 18:03:09 and the final done commit at 18:09:43 gives 394 seconds. Conservatively debit **400 seconds** of the original audit envelope. This includes publication overhead rather than treating it as free. It is wall-time accounting, not a measurement of CPU-seconds.

The one retry receives at most **500 stage seconds**, **30 seconds termination grace**, and the canonical **1100-second dispatcher limit** (500 + 600). Thus the debited audit work plus retry stage allowance is 400 + 500 = 900 seconds, and debited elapsed time plus the retry dispatch allowance is 400 + 1100 = 1500 seconds. These retain the original panel's 9900-second stage and 12300-second dispatch accounting envelopes when the untouched later stages are included. Termination/publication overhead is covered by the dispatch reserve; the outer publisher remains subject to its existing runner controls and its observed time must still be recorded, never reported as automatically bounded by a stage timer.

This is a stricter residual resource admission, not a time estimate or a promise of success. If it is insufficient, stop and record the technical/resource result: no further retry, cap increase, dropped data, resumed partial-success claim or downstream match under this authorization.

## Admission and evidence

Use a new job/attempt, the reviewed and merged #1052 code, and the updated exact Launch-V2 profile including `jobs.tests.test_cls_g0_panel_inventory_types`. Run the full zero-search audit in rehearsal mode; do not reuse the failed 2070 receipt. All five existing phases, output requirements, source/model pins and zero scientific-effect ceilings remain identical. Only the corrected code/profile identities and the residual time allowance differ from the original dispatch.

Before queue merge: fresh pending/running check, no duplicate retry, canonical dispatch and newline-sensitive spec/admission hashes, relevant CI and the five dispatcher tests. Native/R2 validation is established only by the actual new attempt, not by CI or this note.

## Review checkpoint

The PR's automated incident-register update added TI-086 at head `55f4703e7e8fb93fad61d5b01d20b74d66bdceab`; its bot-triggered workflows report `action_required`, not successful execution. This reviewed operational commit requests fresh CI on the current PR without weakening workflows, repository protection, test requirements or any audit check. Do not merge until the required current-head checks have actually succeeded.

TI-086 retains its stable dedupe key `job:cpx62-2070-l3-cls-g0-panel-historical-audit-v1:root-id-json-tsv-types`. It remains MITIGATED pending real-host terminal proof. A green retry must be recorded with its exact job/attempt/code, receipt, complete raw-audit and G0 coverage before closure; a failure is not a scientific negative.

CURRICULUM remains champion. All historical G0 FAILs and the 2069 result remain unchanged.
