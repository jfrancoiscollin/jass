"""Receipt refusal tests; actual native success is mandatory in the CI CLI step."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PreflightRefusal(unittest.TestCase):
    def test_missing_probe_has_no_solves_or_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'result'
            result = subprocess.run([sys.executable, '-m', 'jobs.tools.ed4_choice_preflight',
                                     '--out-dir', str(out), '--native-probe', str(Path(tmp)/'absent')],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            failure = json.loads((out/'failure.json').read_bytes())
            self.assertEqual(failure['progress']['synthetic_optimizer_invocations'], 0)
            self.assertIn('compiled_native_probe_required', failure['message'])
            self.assertFalse((out/'manifest.json').exists())
            self.assertFalse((out/'report.json').exists())


if __name__ == '__main__':
    unittest.main()
