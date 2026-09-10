# ED4 C0C 1905 — launch profile identity incident

Date: 2026-09-10. Classification: **TECHNICAL / LAUNCH-ADMISSION**.

Job `cpx62-1905-l3-ed4-c0c-1903-fetch-precondition-diagnostic-v1` was claimed on CPX62 and failed before stage execution with `PROFILE_IDENTITY`.

The admission pinned `04a34e561dd1e3737f9e4c0e021ce53ef48c1fc1e8560f59a5d52683905ec775`, which is the canonical JSON digest of `jobs/launch_profiles/ed4-c0c-fetch-precondition-diagnostic-v1.json`. `launch_gate_v2` instead requires the SHA256 of the actual profile file bytes. At immutable code `60a74cf8d294b47102d64dcc963f1574b5db364a`, that file SHA256 is `781d267b4009dff85196a3c83803b93f95b1c02b8588e36714bfad1e59436f55`.

This failure happened before the metadata-only diagnostic stage executed. It consumed no ED4 confirmation targets and changed no candidate bytes, exclusion universe, thresholds, alpha, model, fit, search, game or promotion state.

The control-plane mitigation is a new immutable V2-admitted diagnostic retry with the same code/spec/runtime/scientific contract and the correct profile-file SHA256. Runtime proof remains required before closure.

The central technical-incident register auto-feed assigned this defect `TI-042`.
