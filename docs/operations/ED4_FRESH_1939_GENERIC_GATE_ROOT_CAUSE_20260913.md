# ED4-FRESH 1939 — generic launch-gate root cause

Date: 2026-09-13. Classification: **TECHNICAL ONLY**.

The ED4-FRESH S-source rehearsal did not reach an ED4 scientific read or verdict. Its mandatory generic Launch V2 regression failed before the source stage.

The bounded target-host diagnostics localized the failure in three steps:

1. job 1943 identified `jobs.tests.test_launch_gate_pipeline_v2.ActualStageRoundtripTests.test_actual_stage_publication_fetch_and_fail_closed_marker`, assertion line 55;
2. job 1944 proved that the nested synthetic stage entered `EXECUTE`, did not time out, and exited with code 1;
3. zero-science probe 1945 reproduced the child process under the same sanitized target-host environment and proved an `ImportError` through `test_ed3_label_pressure.py` into `ed3_label_pressure.py:19`, the `scipy.special.expit` import.

The failing regression was an infrastructure test but reused an ED3 scientific fixture. That accidental dependency made generic launch admission depend on SciPy being importable in the deliberately sanitized child environment.

Jass #948 repaired the test by replacing the ED3 fixture with a hermetic zero-science fixture. The regression still exercises the real generic stage runner, StageEvidence phase/effect validation, nested regression execution, publication bytes, authenticated readback, stale-spec rejection, and fail-closed terminal marker handling. No ED4 seed, quota, candidate, target barrier, alpha, confirmation corpus, or scientific gate was changed or relaxed.

Target-host ED4-FRESH S-source rerun 1946 is the validation run for the repair. Until its terminal result is published, TI-050 remains mitigated pending target-host validation.
