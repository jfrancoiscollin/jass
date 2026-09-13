#!/usr/bin/env python3
"""Execute the required regression suite and reject empty or skipped suites."""
from __future__ import annotations
# Final CI retrigger after automatic incident-ledger update; gate semantics unchanged.
import argparse
import json
import os
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from jobs.tools.launch_runtime_v2 import EFFECTS, atomic_json


def _ids(rows):
    return [case.id() for case, *_ in rows]


def _publish_failure_evidence(result, count):
    """Expose only failing unittest identities through the existing V2 failure status.

    The launch gate already copies phase/error_type/frames from execution-evidence
    into attempt-diagnostic.json.  Writing this file only after a regression
    failure makes target-host failures diagnosable without relaxing the gate or
    reading any scientific payload.
    """
    root = os.environ.get('JASS_ARTEFACT_DIR')
    if not root:
        return
    artifact = Path(root)
    artifact.mkdir(parents=True, exist_ok=True)
    frames = []
    for kind, rows in (('unittest-failure', result.failures),
                       ('unittest-error', result.errors),
                       ('unittest-skip', result.skipped)):
        for case, *_ in rows:
            frames.append({'file': kind, 'function': case.id(), 'line': 0})
    atomic_json(artifact/'execution-evidence.json', dict(
        schema='jass.execution_evidence.v2', state='failed',
        mode=os.environ.get('LAUNCH_MODE'),
        phase='launch-regressions-empty' if count == 0 else 'launch-regressions',
        completed_phases=[], actual_side_effects={k: 0 for k in EFFECTS},
        error_type='RegressionSuiteFailed', frames=frames[:64]))


def run(names, out):
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    count = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    good = count > 0 and result.wasSuccessful() and not result.skipped
    atomic_json(out, dict(schema='jass.launch_regressions.v2', suites=names,
                         tests=result.testsRun, failures=len(result.failures),
                         errors=len(result.errors), skipped=len(result.skipped),
                         failure_tests=_ids(result.failures),
                         error_tests=_ids(result.errors),
                         skipped_tests=_ids(result.skipped),
                         passed=bool(good)))
    if not good:
        _publish_failure_evidence(result, count)
    return 0 if good else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    return run(json.loads(a.profile.read_text())['regressions'], a.out)


if __name__ == '__main__':
    raise SystemExit(main())
