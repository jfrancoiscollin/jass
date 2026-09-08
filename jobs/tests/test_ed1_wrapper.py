"""Exercise the actual ED1 Bash preflight; no network, labels or engine calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'jobs/templates/l3-ed1-partial-order-audit-v1.sh'
CODE = 'a' * 40


class ED1WrapperTests(unittest.TestCase):
    def run_wrapper(self, cpus=16, host='cpx62', dirty=False, code=CODE, go='1'):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            marker = root / 'fetch-reached'
            commands = {
                # Simulate GNU nproc's OpenMP override, not just a constant 16.
                'nproc': 'test "$#" -eq 0 || exit 91\nprintf "%s\\n" "${OMP_THREAD_LIMIT:-${OMP_NUM_THREADS:-' + str(cpus) + '}}"\n',
                'hostname': 'printf "%s\\n" "' + host + '"\n',
                'git': 'case "$1" in\nbranch) :;;\nstatus) ' + ('echo "?? dirty"' if dirty else ':') + ';;\nrev-parse) echo ' + CODE + ';;\n*) exit 92;;\nesac\n',
                # Stop at the first input-fetch call, before any source access.
                'python3': 'printf "%s %s %s\\n" "$OPENBLAS_NUM_THREADS" "$OMP_NUM_THREADS" "$MKL_NUM_THREADS" >"$FETCH_MARKER"\necho FETCH_SENTINEL >&2\nexit 73\n',
            }
            for name, body in commands.items():
                p = bin_dir / name
                p.write_text('#!/bin/bash\nset -eu\n' + body)
                p.chmod(0o755)
            venv = root / 'venv' / 'bin'
            venv.mkdir(parents=True)
            (venv / 'python').symlink_to(sys.executable)
            spec = root / 'spec.json'
            spec.write_text(json.dumps({'code_sha': code}))
            result, artifact = root / 'result', root / 'artifact'
            env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                       JASS_CODE_DIR=str(ROOT), JASS_RESULT_DIR=str(result),
                       JASS_ARTEFACT_DIR=str(artifact), JASS_STAGE_SPEC=str(spec),
                       JASS_JOB_ID='test-ed1-preflight', ED1_AUDIT_GO=go,
                       JASS_L3_NUMERIC_VENV=str(venv.parent), FETCH_MARKER=str(marker),
                       OMP_NUM_THREADS='1', OMP_THREAD_LIMIT='1')
            run = subprocess.run(['/bin/bash', str(SCRIPT)], env=env,
                                 capture_output=True, text=True, timeout=20)
            res = (artifact / 'RESULTS.txt').read_text()
            logs = artifact / 'execution-logs' / 'verified-a.log'
            self.assertEqual(res, (result / 'work' / 'RESULTS.txt').read_text())
            self.assertFalse((artifact / 'scientific-summary.json').exists())
            return run, res, marker.read_text() if marker.exists() else None, logs.read_text() if logs.exists() else None

    def test_openmp_cap_does_not_reduce_machine_cpu_probe(self):
        run, res, fetched, log = self.run_wrapper()
        self.assertEqual(run.returncode, 73, run.stdout + run.stderr)
        self.assertEqual(fetched, '1 1 1\n')
        self.assertIn('available_nproc=16', res)
        self.assertIn('phase=authenticate-existing-cohorts', res)
        self.assertIn('rc=73', res)
        self.assertIn('FETCH_SENTINEL', log)

    def test_wrong_cpu_support_is_not_bypassed(self):
        run, res, fetched, _ = self.run_wrapper(cpus=8)
        self.assertEqual(run.returncode, 1)
        self.assertIn('got=8 expected=16', res)
        self.assertIsNone(fetched)

    def test_wrong_host_fails_before_source_access(self):
        run, res, fetched, _ = self.run_wrapper(host='ccx33')
        self.assertEqual(run.returncode, 1)
        self.assertIn('host mismatch', res)
        self.assertIsNone(fetched)

    def test_dirty_worktree_fails_before_source_access(self):
        run, res, fetched, _ = self.run_wrapper(dirty=True)
        self.assertEqual(run.returncode, 1)
        self.assertIn('detached/clean', res)
        self.assertIsNone(fetched)

    def test_code_identity_remains_pinned(self):
        run, res, fetched, _ = self.run_wrapper(code='b' * 40)
        self.assertEqual(run.returncode, 1)
        self.assertIn('stage spec / HEAD mismatch', res)
        self.assertIsNone(fetched)

    def test_missing_go_fails_before_source_access(self):
        run, res, fetched, _ = self.run_wrapper(go='0')
        self.assertEqual(run.returncode, 1)
        self.assertIn('ED1 GO missing', res)
        self.assertIsNone(fetched)


if __name__ == '__main__':
    unittest.main()
