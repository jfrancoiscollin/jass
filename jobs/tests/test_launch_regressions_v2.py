from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from jobs.tools import launch_regressions_v2 as r


class Case:
    def __init__(self, name): self.name=name
    def id(self): return self.name


class Result:
    failures=[(Case('suite.Case.test_fail'),'trace')]
    errors=[(Case('suite.Case.test_error'),'trace')]
    skipped=[(Case('suite.Case.test_skip'),'reason')]


class LaunchRegressionEvidenceTests(unittest.TestCase):
    def test_failed_test_ids_are_published_without_trace_or_secret(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {
            'JASS_ARTEFACT_DIR':td, 'LAUNCH_MODE':'rehearsal'}, clear=False):
            r._publish_failure_evidence(Result(),3)
            value=json.loads((Path(td)/'execution-evidence.json').read_text())
        self.assertEqual(value['phase'],'launch-regressions')
        self.assertEqual(value['error_type'],'RegressionSuiteFailed')
        self.assertEqual([x['function'] for x in value['frames']], [
            'suite.Case.test_fail','suite.Case.test_error','suite.Case.test_skip'])
        self.assertTrue(all(x['line']==0 for x in value['frames']))
        self.assertNotIn('trace',json.dumps(value))
        self.assertTrue(all(v==0 for v in value['actual_side_effects'].values()))

    def test_empty_suite_phase_is_distinct(self):
        empty=type('Empty',(),{'failures':[],'errors':[],'skipped':[]})()
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {
            'JASS_ARTEFACT_DIR':td, 'LAUNCH_MODE':'rehearsal'}, clear=False):
            r._publish_failure_evidence(empty,0)
            value=json.loads((Path(td)/'execution-evidence.json').read_text())
        self.assertEqual(value['phase'],'launch-regressions-empty')
        self.assertEqual(value['frames'],[])


if __name__=='__main__': unittest.main()
