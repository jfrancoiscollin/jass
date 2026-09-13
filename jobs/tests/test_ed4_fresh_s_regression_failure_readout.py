from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from jobs.tools import ed4_fresh_s_regression_failure_readout_stage as s


class FreshSRegressionFailureReadoutTests(unittest.TestCase):
    def report(self):
        return {
            'job_id': s.SOURCE_JOB,
            'attempt_id': s.SOURCE_ATTEMPT,
            'code_sha': s.SOURCE_CODE,
            'result_state': 'failed',
            'exit_code': 2,
            'files': [
                {'path':'launch-regressions.json','size_bytes':12,'sha256':'a'*64},
                {'path':'launch-regressions.log','size_bytes':34,'sha256':'b'*64},
            ],
        }

    def test_identity_and_fixed_allowlist(self):
        seen=[]
        def download(_rclone, remote, local, _sha, _size):
            seen.append(remote)
            Path(local).write_text('{}' if remote.endswith('.json') else 'log')
        with tempfile.TemporaryDirectory() as td, \
             patch.object(s.fetch_result_files,'inspect_result_inventory',return_value=self.report()), \
             patch.object(s.fetch_result_files.base,'download_verified',side_effect=download):
            out=Path(td)
            got=s.fetch_diagnostics(out)
            self.assertEqual(got['job_id'],s.SOURCE_JOB)
            self.assertEqual([x.rsplit('/',1)[-1] for x in seen],list(s.DIAGNOSTIC_PATHS))

    def test_missing_diagnostic_fails_closed(self):
        r=self.report(); r['files']=r['files'][:1]
        with tempfile.TemporaryDirectory() as td, \
             patch.object(s.fetch_result_files,'inspect_result_inventory',return_value=r), \
             self.assertRaises(RuntimeError):
            s.fetch_diagnostics(Path(td))

    def test_wrong_source_identity_fails_closed(self):
        r=self.report(); r['code_sha']='0'*40
        with tempfile.TemporaryDirectory() as td, \
             patch.object(s.fetch_result_files,'inspect_result_inventory',return_value=r), \
             self.assertRaises(RuntimeError):
            s.fetch_diagnostics(Path(td))


if __name__=='__main__': unittest.main()
