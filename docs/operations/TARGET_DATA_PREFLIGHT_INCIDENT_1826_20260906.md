# Incident 1826 — target-data contract mismatch hidden by coarse failure class

Job: `cpx62-1826-l3-decision-math-b2-statistical-completion-r2-capability-v2`

The R2 capability hardening worked: immutable 1815 data was fetched successfully. The recovery then stopped before statistics because the authenticated 1815 failure was not explained by the three permitted binding hashes.

The architectural defect was observability and sequencing: the first target-data producer/consumer parity exercise lived inside the full recovery stage, and the X readout groups several distinct invariants under `PROJECTION_BINDING_INVALID`.

Remediation:

1. add `adaptive_sibling_b2_recovery_admissibility_preflight.py`;
2. run the X consumer parent-by-parent on stored and freshly projected X receipts;
3. preserve the underlying X `ReadoutError` message and record identity;
4. emit bounded field-level receipt diffs;
5. require the target-data preflight before the full B2 bootstrap;
6. keep all scientific side effects at zero during preflight.

This incident does not modify or evaluate the frozen B2 policy, thresholds, bootstrap seed or scientific gates.
