from __future__ import annotations
import hashlib, json, os, tempfile, unittest
from pathlib import Path
from unittest import mock

from jobs.tools import ed4_c0c_exclusion_union as v1
from jobs.tools import ed4_c0c_full_format_diagnostic as subject
from jobs.tools import ed4_c0c_full_format_diagnostic_stage as stage

ROOT = Path(__file__).resolve().parents[2]


def descriptor(n: int, kind: str = 'fen', size: int = 12) -> dict:
    return {'path': f'artefacts/{n:04d}.{kind}', 'kind': kind,
            'sha256': hashlib.sha256(str(n).encode()).hexdigest(), 'size_bytes': size}


class FormatDiagnosticTests(unittest.TestCase):
    def setUp(self):
        for name in ('run_capture', 'download_verified'):
            patcher = mock.patch.object(subject.fetch_result_files.base, name,
                                        side_effect=AssertionError('real transport forbidden'))
            transport = patcher.start()
            self.addCleanup(patcher.stop)
            self.addCleanup(transport.assert_not_called)

    def test_error_code_never_keeps_input_text(self):
        self.assertEqual(subject._normalized_error(v1.C0CError('fen_empty: line 4: secret FEN')), 'fen_empty')
        with self.assertRaises(v1.C0CError):
            subject._normalized_error(v1.C0CError('bad error with text'))

    def test_comment_geometry_reports_no_content(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'x.fen'; path.write_text('# private comment\n\n # another\n', encoding='utf-8')
            geometry = subject._text_geometry(path, 'fen')
        self.assertEqual(geometry, {'utf8_valid': True, 'physical_lines': 3, 'blank_lines': 1,
                                    'comment_lines': 2, 'payload_lines_after_v1_comment_stripping': 0})

    def test_known_parser_error_is_a_row_but_unexpected_propagates(self):
        d = descriptor(1)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'a'; path.write_text('# comment\n', encoding='utf-8')
            row = subject._diagnose_one(path, d, 'job', 'attempt', {}, {}, None)
            self.assertEqual(row['outcome'], 'fen_empty')
            with mock.patch.object(v1, 'parse_candidate', side_effect=ValueError('unexpected')):
                with self.assertRaises(ValueError):
                    subject._diagnose_one(path, d, 'job', 'attempt', {}, {}, None)

    def test_full_726_fixture_is_sorted_and_has_no_raw_payload(self):
        candidates = [descriptor(i) for i in range(726)]
        for candidate in candidates[:6]:
            candidate['size_bytes'] = 0; candidate['sha256'] = v1.EMPTY_SHA256
        allow = {( 'job', 'attempt', d['path']): {'sha256': d['sha256'], 'size_bytes': d['size_bytes'],
                 'partial_tail_bytes_from_size': 1 if i < 216 else 0,
                 'complete_records_from_size': 1} for i, d in enumerate(candidates[6:237])}
        c0a = {'sources': [{'job_id': 'job', 'attempt_id': 'attempt', 'result_state': 'completed'}]}
        c0b = {'candidate_jobs': [{'job_id': 'job', 'attempt_id': 'attempt', 'candidate_files': candidates}]}
        def fetch_files(**kwargs):
            kwargs['out_dir'].mkdir(parents=True, exist_ok=True)
            files=[]
            for remote, local in kwargs['selections']:
                (kwargs['out_dir'] / local).write_text('W:W1,K2:B3,K4\n', encoding='utf-8')
                d=next(x for x in candidates if x['path']==remote)
                files.append({'path':remote,'sha256':d['sha256'],'size_bytes':d['size_bytes']})
            return {'job_id':'job', 'attempt_id':'attempt', 'result_state':'completed', 'files': files}
        def classify(path, desc, job, attempt, allow_rows, *_args):
            frozen = allow_rows.get((job, attempt, desc['path']))
            outcome = ('v5-partial-recovery-pass' if frozen and frozen['partial_tail_bytes_from_size'] else
                       'v6-aligned-recovery-pass' if frozen else 'strict-v1-pass')
            return subject._row(desc, job, attempt, outcome, 1)
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(subject.v6, '_load_1927', return_value=({}, {}, {})), \
             mock.patch.object(subject.v6, 'validate_1927', return_value=(allow, {'v5': [], 'aligned': []}, {'allowlist_canonical_sha256':'a'*64, 'aligned_subset_canonical_sha256':'b'*64})), \
             mock.patch.object(subject.v1, 'fetch_parent', return_value=(c0a, c0b)), \
             mock.patch.object(subject.v1, '_authenticate_candidate_descriptors', return_value=(list(enumerate(candidates[6:], 6)), [{'path': x['path']} for x in candidates[:6]])) ,\
             mock.patch.object(subject.fetch_result_files, 'fetch_files', side_effect=fetch_files), \
             mock.patch.object(subject, '_diagnose_one', side_effect=classify):
            result = subject.build_diagnostic(Path(td)/'work', Path(td)/'art')
            published = (Path(td)/'art'/'ed4-c0c-full-format-diagnostic.json').read_text(encoding='utf-8')
        self.assertEqual(result['descriptor_count'], 726)
        self.assertEqual(result['recovery_descriptor_count'], 231)
        self.assertEqual(result['failure_row_count'], 0)
        self.assertEqual(sum(r['outcome']=='v5-partial-recovery-pass' for r in result['rows']), 216)
        self.assertEqual(sum(r['outcome']=='v6-aligned-recovery-pass' for r in result['rows']), 15)
        self.assertNotIn('W:W1', published)
        self.assertEqual(result['rows'], sorted(result['rows'], key=lambda r:(r['job_id'], r['attempt_id'], r['path'])))

    def test_duplicate_and_deadline_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)/'work'; art = Path(td)/'art'
            d=descriptor(1)
            with mock.patch.object(subject.v6, '_load_1927', return_value=({}, {}, {})), \
                 mock.patch.object(subject.v6, 'validate_1927', return_value=({}, {}, {})), \
                 mock.patch.object(subject.v1, 'fetch_parent', return_value=({'sources': [{'job_id':'j','attempt_id':'a','result_state':'completed'}]}, {'candidate_jobs': [{'job_id':'j','attempt_id':'a','candidate_files':[d,d]}]})), \
                 mock.patch.object(subject, 'EXPECTED_RECOVERY_ROWS', 0), mock.patch.object(subject, 'EXPECTED_DESCRIPTORS', 2):
                with self.assertRaisesRegex(v1.C0CError, 'duplicate_descriptor'):
                    subject.build_diagnostic(work, art)
        with self.assertRaisesRegex(v1.C0CError, 'format_diagnostic_deadline_exceeded'):
            subject._deadline(0.0, 'test')

    def test_multiple_known_errors_continue_deterministically(self):
        candidates=[descriptor(0), descriptor(1), descriptor(2)]
        for d in candidates: d['path'] = d['path'].replace('.fen', '.fen')
        c0a={'sources':[{'job_id':'job','attempt_id':'attempt','result_state':'completed'}]}
        c0b={'candidate_jobs':[{'job_id':'job','attempt_id':'attempt','candidate_files':candidates}]}
        payloads={candidates[0]['path']:'# a\n', candidates[1]['path']:'# b\n', candidates[2]['path']:'W:W1,K2:B3,K4\n'}
        def auth(**_kwargs): return list(enumerate(candidates)), []
        def fetch(**kwargs):
            kwargs['out_dir'].mkdir(parents=True, exist_ok=True); files=[]
            for remote, local in kwargs['selections']:
                (kwargs['out_dir']/local).write_text(payloads[remote], encoding='utf-8')
                d=next(x for x in candidates if x['path']==remote); files.append({'path':remote,'sha256':d['sha256'],'size_bytes':d['size_bytes']})
            return {'job_id':'job','attempt_id':'attempt','result_state':'completed','files':files}
        def run(td, suffix):
            with mock.patch.object(subject.v6, '_load_1927', return_value=({}, {}, {})), \
                 mock.patch.object(subject.v6, 'validate_1927', return_value=({}, {}, {})), \
                 mock.patch.object(subject.v1, 'fetch_parent', return_value=(c0a,c0b)), \
                 mock.patch.object(subject.v1, '_authenticate_candidate_descriptors', side_effect=auth), \
                 mock.patch.object(subject.fetch_result_files, 'fetch_files', side_effect=fetch), \
                 mock.patch.object(subject, 'EXPECTED_RECOVERY_ROWS', 0), mock.patch.object(subject, 'EXPECTED_ZERO_DESCRIPTORS', 0), mock.patch.object(subject, 'EXPECTED_DESCRIPTORS', 3):
                return subject.build_diagnostic(Path(td)/('w'+suffix),Path(td)/('a'+suffix))
        with tempfile.TemporaryDirectory() as td:
            first=run(td,'1'); second=run(td,'2')
        self.assertEqual([r['outcome'] for r in first['rows']], ['fen_empty','fen_empty','strict-v1-pass'])
        self.assertEqual(first['failure_rows_sha256'], second['failure_rows_sha256'])

    def test_fetch_identity_drift_and_descriptor_set_fail_before_parse(self):
        d=descriptor(0); c0a={'sources':[{'job_id':'job','attempt_id':'attempt','result_state':'completed'}]}; c0b={'candidate_jobs':[{'job_id':'job','attempt_id':'attempt','candidate_files':[d]}]}
        with tempfile.TemporaryDirectory() as td, mock.patch.object(subject.v6, '_load_1927', return_value=({}, {}, {})), \
             mock.patch.object(subject.v6, 'validate_1927', return_value=({}, {}, {})), mock.patch.object(subject.v1, 'fetch_parent', return_value=(c0a,c0b)), \
             mock.patch.object(subject.v1, '_authenticate_candidate_descriptors', return_value=([(0,d)], [])), \
             mock.patch.object(subject.fetch_result_files, 'fetch_files', return_value={'job_id':'wrong','attempt_id':'attempt','result_state':'completed','files':[]}), \
             mock.patch.object(subject, 'EXPECTED_RECOVERY_ROWS', 0), mock.patch.object(subject, 'EXPECTED_ZERO_DESCRIPTORS', 0), mock.patch.object(subject, 'EXPECTED_DESCRIPTORS', 1):
            with self.assertRaisesRegex(v1.C0CError, 'fetch_identity'):
                subject.build_diagnostic(Path(td)/'w', Path(td)/'a')
        for files in ([], [{'path':'artefacts/extra.fen','sha256':'a'*64,'size_bytes':1}]):
            with tempfile.TemporaryDirectory() as td, mock.patch.object(subject.v6, '_load_1927', return_value=({}, {}, {})), \
                 mock.patch.object(subject.v6, 'validate_1927', return_value=({}, {}, {})), mock.patch.object(subject.v1, 'fetch_parent', return_value=(c0a,c0b)), \
                 mock.patch.object(subject.v1, '_authenticate_candidate_descriptors', return_value=([(0,d)], [])), \
                 mock.patch.object(subject.fetch_result_files, 'fetch_files', return_value={'job_id':'job','attempt_id':'attempt','result_state':'completed','files':files}), \
                 mock.patch.object(subject, 'EXPECTED_RECOVERY_ROWS', 0), mock.patch.object(subject, 'EXPECTED_ZERO_DESCRIPTORS', 0), mock.patch.object(subject, 'EXPECTED_DESCRIPTORS', 1):
                with self.assertRaisesRegex(v1.C0CError, 'fetch_descriptor_set'):
                    subject.build_diagnostic(Path(td)/'w', Path(td)/'a')

    def test_stage_runtime_guard_does_not_run_builder(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(stage, 'RUNTIME_MAX_SECONDS', None), \
             mock.patch.object(stage, 'build_diagnostic', side_effect=AssertionError('must not build')) as build, \
             mock.patch.dict(os.environ, {'JASS_ARTEFACT_DIR':str(Path(td)/'a'), 'JASS_RESULT_DIR':str(Path(td)/'r'), 'LAUNCH_MODE':'rehearsal'}):
            self.assertEqual(stage.main(), 2)
        build.assert_not_called()

    def test_stage_rejects_production_before_builder(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(stage, 'build_diagnostic') as build, \
             mock.patch.dict(os.environ, {'JASS_ARTEFACT_DIR':str(Path(td)/'a'), 'JASS_RESULT_DIR':str(Path(td)/'r'), 'LAUNCH_MODE':'production'}):
            self.assertEqual(stage.main(), 2)
        build.assert_not_called()

    def test_profile_includes_launch_and_v6_guards(self):
        profile = json.loads((ROOT/'jobs/launch_profiles/ed4-c0c-full-format-diagnostic-v1.json').read_text())
        self.assertTrue({'jobs.tests.test_launch_gate_v2','jobs.tests.test_launch_gate_pipeline_v2',
                         'jobs.tests.test_ed4_c0c_exclusion_union_v6',
                         'jobs.tests.test_ed4_c0c_full_format_diagnostic'}.issubset(profile['regressions']))

if __name__ == '__main__': unittest.main()
