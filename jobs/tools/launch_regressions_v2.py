#!/usr/bin/env python3
"""Execute the required regression suite and reject empty or skipped suites."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from jobs.tools.launch_runtime_v2 import atomic_json


def run(names, out):
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    count = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    good = count > 0 and result.wasSuccessful() and not result.skipped
    atomic_json(out, dict(schema='jass.launch_regressions.v2', suites=names,
                         tests=result.testsRun, failures=len(result.failures),
                         errors=len(result.errors), skipped=len(result.skipped),
                         passed=bool(good)))
    return 0 if good else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    return run(json.loads(a.profile.read_text())['regressions'], a.out)


if __name__ == '__main__':
    raise SystemExit(main())
