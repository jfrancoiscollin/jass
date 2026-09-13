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
    failures=[(Case('suite.Case.test_fail'), 'Traceback\n  File "/secret/root/jobs/tests/test_x.py", line 57, in test_fail\nAssertionError: secret value')]
    errors=[(Case('suite.Case.test_error'), 'Traceback\n  File "/other/path/test_y.py", line 91, in test_error\nRuntimeError: private')]
    skipped=[(Case('suite.Case.test_skip'),'reason')]


class LaunchRegressionEvidenceTests(unittest.TestCase):
    def test_failed_test_ids_and_lines_are_published_without_trace_or_secret(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {
            'JASS_ARTEFACT_DIR':td, 'LAUNCH_MODE':'rehearsal'}, clear=False):
            r._publish_failure_evidence(Result(),3)
            value=json.loads((Path(td)/'execution-evidence.json').read_text())
        self.assertEqual(value['phase'],'launch-regressions')
        self.assertEqual(value['error_type'],'RegressionSuiteFailed')
        self.assertEqual([x['function'] for x in value['frames']], [
            'suite.Case.test_fail','suite.Case.test_error','suite.Case.test_skip'])
        self.assertEqual(value['frames'][0], {'file':'test_x.py','function':'suite.Case.test_fail','line':57})
        self.assertEqual(value['frames'][1], {'file':'test_y.py','function':'suite.Case.test_error','line':91})
        self.assertEqual(value['frames'][2]['line'],0)
        encoded=json.dumps(value)
        self.assertNotIn('/secret/root',encoded)
        self.assertNotIn('secret value',encoded)
        self.assertNotIn('private',encoded)
        self.assertTrue(all(v==0 for v in value['actual_side_effects'].values()))

    def test_runner_receipt_fields_are_bounded_and_error_text_is_not_published(self):
        detail=(
            'Traceback\n  File "/secret/root/jobs/tests/test_launch_gate_pipeline_v2.py", line 55, in test\n'
            "AssertionError: 2 != 0 : {'failure_class': 'STAGE_EXIT_CODE', "
            "'failure_stage': 'EXECUTE', 'error': 'secret /credential/path', "
            "'exit_code': 2, 'timed_out': False}"
        )
        frame=r._failure_frame('unittest-failure',Case('suite.Case.test_stage'),detail)
        self.assertEqual(frame, {
            'file':'test_launch_gate_pipeline_v2.py',
            'function':'suite.Case.test_stage',
            'line':55,
            'stage_failure':{
                'failure_class':'STAGE_EXIT_CODE',
                'failure_stage':'EXECUTE',
                'exit_code':2,
                'timed_out':False,
            },
        })
        encoded=json.dumps(frame)
        self.assertNotIn('credential',encoded)
        self.assertNotIn('/secret/root',encoded)
        self.assertNotIn('error',encoded)

    def test_empty_suite_phase_is_distinct(self):
        empty=type('Empty',(),{'failures':[],'errors':[],'skipped':[]})()
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {
            'JASS_ARTEFACT_DIR':td, 'LAUNCH_MODE':'rehearsal'}, clear=False):
            r._publish_failure_evidence(empty,0)
            value=json.loads((Path(td)/'execution-evidence.json').read_text())
        self.assertEqual(value['phase'],'launch-regressions-empty')
        self.assertEqual(value['frames'],[])


if __name__=='__main__': unittest.main()
