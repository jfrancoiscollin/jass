#!/usr/bin/env python3
"""Execute the required regression suite and reject empty or skipped suites."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from jobs.tools.launch_runtime_v2 import EFFECTS, atomic_json


def _ids(rows):
    return [case.id() for case, *_ in rows]


def _safe_stage_failure(detail):
    """Extract only bounded generic runner receipt fields from unittest text.

    The full assertion detail may contain paths, commands or exception text, so
    never publish it. This parser is deliberately narrow and only recognizes the
    stable repr fields emitted by ``run_experiment_stage.run_stage`` receipts.
    """
    text = detail or ''
    patterns = {
        'failure_class': r"'failure_class':\s*'([A-Z0-9_]{1,64})'",
        'failure_stage': r"'failure_stage':\s*'([A-Z0-9_]{1,64})'",
        'exit_code': r"'exit_code':\s*(None|[0-9]{1,3})",
        'timed_out': r"'timed_out':\s*(True|False)",
    }
    matches = {key: re.search(pattern, text) for key, pattern in patterns.items()}
    if not all(matches.values()):
        return None
    exit_token = matches['exit_code'].group(1)
    return {
        'failure_class': matches['failure_class'].group(1),
        'failure_stage': matches['failure_stage'].group(1),
        'exit_code': None if exit_token == 'None' else int(exit_token),
        'timed_out': matches['timed_out'].group(1) == 'True',
    }


def _failure_frame(kind, case, detail):
    """Return test identity plus the last source line, never traceback/message text."""
    matches = re.findall(r'File "([^"]+)", line (\d+)', detail or '')
    if matches:
        path, line = matches[-1]
        frame = {'file': Path(path).name, 'function': case.id(), 'line': int(line)}
    else:
        frame = {'file': kind, 'function': case.id(), 'line': 0}
    safe_stage = _safe_stage_failure(detail)
    if safe_stage is not None:
        frame['stage_failure'] = safe_stage
    return frame


def _publish_failure_evidence(result, count):
    """Expose only failing unittest identities/source lines in V2 failure status."""
    root = os.environ.get('JASS_ARTEFACT_DIR')
    if not root:
        return
    artifact = Path(root)
    artifact.mkdir(parents=True, exist_ok=True)
    frames = []
    for kind, rows in (('unittest-failure', result.failures),
                       ('unittest-error', result.errors),
                       ('unittest-skip', result.skipped)):
        for case, detail in rows:
            frames.append(_failure_frame(kind, case, detail))
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
