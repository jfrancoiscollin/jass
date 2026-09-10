from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from jobs.tools import ed4_c0c_exclusion_union_v2 as v2
from jobs.tools import ed4_c0c_exclusion_union as v1
from jobs.tools import ed4_c0c_exclusion_union_v2_stage as stage

ROOT = Path(__file__).resolve().parents[2]


class C0CV2Tests(unittest.TestCase):
    def _payload(self, target=b'abcde', tail=b'x' * 32):
        header = b'JNNW' + struct.pack('<I', 0)
        record = struct.pack('<QQQQB', 1, 2, 4, 8, 0) + target
        return header + record * 3023 + tail

    def _desc(self):
        return dict(path=v2.SALVAGE_PATH, kind='jnnw',
                    sha256=v2.SALVAGE_SHA256, size_bytes=v2.SALVAGE_SIZE)

    def _synthetic_parse(self, raw):
        # Substitute only the synthetic object's identity, never real R2 data.
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'synthetic.jnnw'
            path.write_bytes(raw)
            with mock.patch.object(v2, 'SALVAGE_SHA256', hashlib.sha256(raw).hexdigest()), \
                 mock.patch.object(v2, 'SALVAGE_SIZE', len(raw)):
                return v2._parse_exact_interrupted_jnnw(path)

    def test_shape_is_exact_3023_plus_32(self):
        self.assertEqual(len(self._payload()), 114914)
        self.assertEqual(divmod(114914 - 8, 38), (3023, 32))

    def test_frozen_exception_identity(self):
        self.assertEqual(v2.SALVAGE_JOB, 'cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1')
        self.assertEqual(v2.SALVAGE_ATTEMPT, '20260905T145718Z-d3657332')
        self.assertEqual(v2.SALVAGE_PATH, 'b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-1.jnnw')
        self.assertEqual(v2.SALVAGE_SHA256, '730ee719a651e371c782afd1c1f29a4a95a2c81b2bfdf7f9748aab4d6d7cd576')
        self.assertEqual((v2.SALVAGE_SIZE, v2.SALVAGE_COMPLETE_RECORDS,
                          v2.SALVAGE_PARTIAL_TAIL_BYTES, v2.REC), (114914, 3023, 32, 38))

    def test_exact_salvage_recovers_only_complete_records(self):
        ids, rows, meta = self._synthetic_parse(self._payload())
        self.assertEqual(rows, 3023)
        self.assertEqual(meta['complete_records_recovered'], 3023)
        self.assertEqual(meta['partial_tail_bytes_discarded'], 32)
        self.assertEqual(meta['declared_count'], 0)
        self.assertEqual(len(ids), 1)  # Record count is not unique-position count.

    def test_only_33_structural_bytes_reach_decoder(self):
        real_decoder = v1.canonical_from_position_bytes
        with mock.patch.object(v1, 'canonical_from_position_bytes', wraps=real_decoder) as decoder:
            self._synthetic_parse(self._payload())
        self.assertEqual(decoder.call_count, 3023)
        expected = struct.pack('<QQQQB', 1, 2, 4, 8, 0)
        self.assertTrue(all(call.args == (expected,) for call in decoder.call_args_list))

    def test_target_and_partial_tail_values_do_not_change_identities(self):
        first = self._synthetic_parse(self._payload())
        second = self._synthetic_parse(self._payload(target=b'\xff' * 5, tail=b'\x00' * 32))
        self.assertEqual(first, second)

    def test_actual_payload_hash_and_size_are_checked(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'not-the-frozen-object.jnnw'
            for raw in (self._payload(), self._payload()[:-1]):
                with self.subTest(size=len(raw)):
                    path.write_bytes(raw)
                    with self.assertRaisesRegex(v1.C0CError, 'v2_salvage_object_identity'):
                        v2._parse_exact_interrupted_jnnw(path)

    def test_header_count_and_shape_guards_remain_closed(self):
        raw = self._payload()
        cases = [
            (b'BAD!' + raw[4:], 'v2_salvage_header'),
            (raw[:4] + struct.pack('<I', 3023) + raw[8:], 'v2_salvage_expected_zero_placeholder'),
            (raw[:-1], 'v2_salvage_shape_mismatch'),
            (raw + b'x', 'v2_salvage_shape_mismatch'),
            (raw[:-38], 'v2_salvage_shape_mismatch'),
        ]
        for value, token in cases:
            with self.subTest(token=token, size=len(value)):
                with self.assertRaisesRegex(v1.C0CError, token):
                    self._synthetic_parse(value)

    def test_v1_remains_fail_closed_on_same_shape(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'x.jnnw'
            path.write_bytes(self._payload())
            with self.assertRaisesRegex(v1.C0CError, 'jnnw_trailing_bytes'):
                v1.parse_jnnw(path)

    def test_every_identity_field_is_required_before_salvage(self):
        cases = [('job', 'other-job'), ('attempt', 'other-attempt'),
                 ('path', 'other.jnnw'), ('sha256', 'a' * 64),
                 ('size_bytes', 114913), ('kind', 'jnnw_gzip')]
        for key, value in cases:
            with self.subTest(key=key):
                desc = self._desc()
                job, attempt = v2.SALVAGE_JOB, v2.SALVAGE_ATTEMPT
                if key == 'job':
                    job = value
                elif key == 'attempt':
                    attempt = value
                else:
                    desc[key] = value
                with mock.patch.object(v2, '_parse_exact_interrupted_jnnw') as salvage, \
                     mock.patch.object(v1, 'parse_candidate', side_effect=v1.C0CError('strict-v1')) as strict:
                    with self.assertRaisesRegex(v1.C0CError, 'strict-v1'):
                        v2._parse_candidate_v2(Path('/unused'), desc, job, attempt)
                    salvage.assert_not_called()
                    strict.assert_called_once_with(Path('/unused'), desc['kind'])

    def test_non_exact_malformed_candidate_reaches_real_v1_guard(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'other.jnnw'
            path.write_bytes(self._payload())
            desc = dict(path='other.jnnw', kind='jnnw',
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size_bytes=114914)
            with self.assertRaisesRegex(v1.C0CError, 'jnnw_trailing_bytes'):
                v2._parse_candidate_v2(path, desc, 'other-job', 'other-attempt')

    def test_missing_exact_recovery_cannot_publish_ready_union(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(v1, 'fetch_parent', return_value=({}, {})):
            artifact = Path(td) / 'artifact'
            with self.assertRaisesRegex(v1.C0CError, 'v2_exact_salvage_count'):
                v2.build_union_v2(Path(td) / 'work', artifact)
            self.assertFalse((artifact / 'ed4-c0c-structural-exclusion-manifest.json').exists())

    def test_direct_stage_entrypoint_without_pythonpath(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'jobs/tools/ed4_c0c_exclusion_union_v2_stage.py')],
            cwd=ROOT, env={'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('ModuleNotFoundError', result.stderr)
        self.assertIn('JASS_ARTEFACT_DIR', result.stderr)

    def test_registered_profile_keeps_science_disabled(self):
        profile = json.loads((ROOT / 'jobs/launch_profiles/ed4-c0c-exclusion-union-v2.json').read_text())
        self.assertEqual(profile['required_phases'], stage.PHASES)
        self.assertEqual(profile['stage'], 'ed4-c0c-exclusion-union-v2')
        self.assertIn('jobs.tests.test_ed4_c0c_exclusion_union_v2', profile['regressions'])
        self.assertIn('jobs.tests.test_launch_gate_pipeline_v2', profile['regressions'])
        for mode in ('rehearsal', 'production'):
            self.assertTrue(all(value == 0 for value in profile[mode + '_max_effects'].values()))


if __name__ == '__main__':
    unittest.main()
