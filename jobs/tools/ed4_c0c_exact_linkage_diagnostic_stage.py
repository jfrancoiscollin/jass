#!/usr/bin/env python3
"""Rehearsal-only execution of the prospectively pinned exact-linkage map."""
from __future__ import annotations
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.ed4_c0c_exact_linkage_diagnostic import OUTPUT_NAME, load_frozen_manifest, _need
from jobs.tools.ed4_c0c_exact_linkage_transport import SUMMARY_FIELDS, build_diagnostic
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

RUNTIME_MAX_SECONDS = 2100
OUTER_BUDGET_SECONDS = 2700

def main() -> int:
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    evidence = StageEvidence(artifact, os.environ["LAUNCH_MODE"])
    try:
        if os.environ["LAUNCH_MODE"] != "rehearsal":
            raise RuntimeError("exact_linkage_rehearsal_only")
        if RUNTIME_MAX_SECONDS != 2100 or OUTER_BUDGET_SECONDS != 2700:
            raise RuntimeError("exact_linkage_runtime_contract")
        deadline = time.monotonic()+RUNTIME_MAX_SECONDS
        evidence.begin('authenticate-frozen-21-row-manifest')
        # JASS_STAGE_SPEC is runner-owned. CONTROL_REPO_DIR is intentionally
        # absent from the sanitized stage environment.
        control = Path(os.environ['JASS_STAGE_SPEC']).resolve().parent.parent
        relative = Path(os.environ['EXACT_LINKAGE_MANIFEST_REL'])
        _need(not relative.is_absolute() and '..' not in relative.parts and relative.parts[0] == 'specs',
              'manifest_relative_path')
        path = control/relative
        _need(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(control),
              'manifest_path_containment')
        digest = os.environ['EXPECTED_EXACT_LINKAGE_MANIFEST_SHA256']
        manifest = load_frozen_manifest(str(path),digest)
        evidence.complete()
        def checkpoint(name,event):
            if event == 'begin': evidence.begin(name)
            elif event == 'complete': evidence.complete()
            else: raise RuntimeError('checkpoint_event')
        result = build_diagnostic(manifest,digest,Path(os.environ['JASS_RESULT_DIR'])/'exact-linkage-v1',
                                  artifact,deadline,checkpoint)
        atomic_json(artifact/'scientific-summary.json',{k:result[k] for k in SUMMARY_FIELDS})
        evidence.finish()
        return 0
    except Exception as exc:
        evidence.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.ed4.c0c_exact_linkage_diagnostic.failure.v1",
            "state": "failed", "output_name": OUTPUT_NAME,
            "classification": "TECHNICAL_STRUCTURAL_RECOVERY_INVESTIGATION_ONLY",
            "terminal":"ED4_C0C_V7_BLOCKED_BY_INCOMPLETE_STRUCTURAL_COVERAGE",
            "error_type": type(exc).__name__,
            "read_ledger":None, "read_ledger_measurement":"incomplete_failed_execution",
            "scientific_verdict": None, "confirmation_authorized": False,
            "automatic_continuation": False,
        })
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
