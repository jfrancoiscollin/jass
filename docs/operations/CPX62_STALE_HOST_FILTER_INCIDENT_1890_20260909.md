# CPX62 stale host-filter incident — 1890

Date: 2026-09-09. Classification: **TECHNICAL**.

After the same-contract C0A metadata rehearsal 1890 was queued, `cpx62` remained active but did not claim it. The control-plane inspection showed `state/host-filter/cpx62` still pinned to the retired job `cpx62-1886-l3-ed3-transfer-diagnostic-production-v1`. Because the runner routes pending work through this prefix, 1890 could not be claimed even though `state/host-active/cpx62` exempted the host from the global pause.

Control PR #589 changes only the host-filter prefix to `cpx62-1890-l3-ed4-source-inventory-rehearsal-v1`. It does not edit the already-reviewed 1890 script, stage spec, admission, Jass code SHA, frozen C0A source snapshot, scientific inputs, gates, resources, timeouts or verdict semantics.

The incident remains **MITIGATED** until 1890 is actually claimed and reaches a terminal publication. If 1890 completes, its status/result receipt is the closure proof. If it fails for another reason, this routing incident may still close once claim is proven, while the distinct downstream cause receives its own dedupe key.
