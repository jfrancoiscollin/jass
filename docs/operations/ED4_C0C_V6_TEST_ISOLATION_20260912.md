# ED4 C0C V6 test isolation — 2026-09-12

This technical repair closes an isolation defect in the V6 preflight regression
coverage. The test implicitly inherited a mutable configured runtime instead of
explicitly selecting the no-sizing case, allowing it to enter the builder and
its external I/O path.

The repaired test fixture patches the runtime limit to `None`, verifies the
exact `v6_runtime_sizing_pending` failure and that the builder is not called,
and guards the transport helpers so an accidental external read fails
immediately. Cleanup assertions also fail if an error handler swallows a
transport call. The production V6 runtime and its frozen scientific contract
are unchanged.

Validation covers the complete synthetic V6 suite and the five shared control
dispatcher tests on Linux. The new rehearsal remains pending until the repaired
preflight has completed its admission checks.
