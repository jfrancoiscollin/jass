import re
import unittest
from jobs.tools import ed4_producer_classification as c


def row(job, attempt='a', code='c'*40, state='completed', exit_code=0,
        classification='unknown', required=None):
    return {'job_id': job, 'attempt_id': attempt, 'code_sha': code,
            'result_state': state, 'exit_code': exit_code,
            'classification': classification, 'required_paths': list(required or []),
            'classification_evidence': {}}


def report_with(*rows, missing=None):
    return {'sources': list(rows), 'missing_paths': list(missing or []),
            'unknown_or_unclassified_producers': [r['job_id'] for r in rows
                                                  if r['classification'] == 'unknown'],
            'verdict': c.INSUFFICIENT}


def meta(*items):
    return {'files': [{'path': path, 'sha256': sha} for path, sha in items]}


class ProducerClassification(unittest.TestCase):
    def test_explicit_superset_relation_wins(self):
        job = 'cpx62-1842-l3-decision-math-b3-fresh-audit-subset-seal-v1'
        report = report_with(row(job))
        out = c.apply(report, {(job, 'a'): meta(('artefacts/parents.jnnw', 'b'*64))})
        self.assertEqual(out['sources'][0]['classification'], 'covered_by_authenticated_superset')
        self.assertEqual(out['unknown_or_unclassified_producers'], [])

    def test_build_and_diagnostic_name_false_positives_are_non_position(self):
        for path in (
            'b2-full-teacher/build/CMakeFiles/egdb_intl.dir/root/egdb_intl/Huffman/x.cpp.o',
            'artefacts/SELFTEST__LAST__adaptive_sibling_b2_teacher_merge_verify_selftest_PASS',
            'documentary-worktree/docs/archives/CORPUS_30M_MANIFEST.md'):
            with self.subTest(path=path):
                job = 'cpx62-1802-synthetic-v1'
                report = report_with(row(job))
                out = c.apply(report, {(job, 'a'): meta((path, 'b'*64))})
                self.assertEqual(out['sources'][0]['classification'], 'non_position_producer')

    def test_position_payload_path_screen_is_closed(self):
        for path in ('x/parents.jnnw', 'x/current.jsm.gz', 'x/openings.fen',
                     'x/root-identities.tsv', 'x/parent-ids.txt', 'x/c-dataset.jsonl'):
            with self.subTest(path=path):
                self.assertTrue(c.is_position_payload_path(path))
        for path in ('x/source.json', 'x/cohort.json', 'x/parent-stats.jsonl',
                     'x/build/CMakeFiles/root/foo.o', 'x/docs/position.md'):
            with self.subTest(path=path):
                self.assertFalse(c.is_position_payload_path(path))

    def test_byte_identical_payload_hashes_are_covered_by_one_exact_source(self):
        exact = row('exact-source', classification='included_exact', required=[
            {'path': 'artefacts/parents.jnnw', 'present': True, 'sha256': 'a'*64},
            {'path': 'artefacts/parents.tsv', 'present': True, 'sha256': 'b'*64},
        ])
        copy = row('copy-source')
        report = report_with(exact, copy)
        out = c.apply(report, {('copy-source', 'a'): meta(
            ('work/parents.jnnw', 'a'*64), ('work/parent-identities.tsv', 'b'*64))})
        copy_out = next(x for x in out['sources'] if x['job_id'] == 'copy-source')
        self.assertEqual(copy_out['classification'], 'covered_by_authenticated_superset')
        self.assertEqual(copy_out['classification_evidence']['covering_source'], 'exact-source')
        self.assertEqual(copy_out['classification_evidence']['covered_payload_sha256'], ['a'*64, 'b'*64])

    def test_unmatched_payload_hash_stays_unknown(self):
        exact = row('exact-source', classification='included_exact', required=[
            {'path': 'artefacts/parents.jnnw', 'present': True, 'sha256': 'a'*64}])
        other = row('other-source')
        out = c.apply(report_with(exact, other), {
            ('other-source', 'a'): meta(('work/parents.jnnw', 'b'*64))})
        self.assertEqual(out['unknown_or_unclassified_producers'], ['other-source'])
        self.assertEqual(out['sources'][1]['classification'], 'unknown')

    def test_authenticated_prelaunch_failure_is_non_position(self):
        job = 'cpx62-1820-l3-decision-math-b2-terminal-classified-failure-zero-placeholder-repair-v1'
        report = report_with(row(job, attempt=None, code=None, state='failed', exit_code=-1))
        out = c.apply(report, {})
        self.assertEqual(out['sources'][0]['classification'], 'non_position_producer')
        self.assertEqual(out['sources'][0]['classification_evidence']['basis'],
                         'frozen_status_proves_no_attempt_and_no_code_execution')

    def test_no_metadata_for_executed_job_stays_unknown(self):
        job = 'cpx62-1811-unclaimed-v1'
        out = c.apply(report_with(row(job, attempt='real')), {})
        self.assertEqual(out['unknown_or_unclassified_producers'], [job])
        self.assertEqual(out['unknown_producer_compact_evidence'][0]['basis'],
                         'no_authenticated_terminal_metadata')

    def test_missing_literal_path_keeps_insufficient(self):
        job = 'non-position'
        report = report_with(row(job), missing=[{'job_id': 'literal', 'path': 'x'}])
        out = c.apply(report, {(job, 'a'): meta(('artefacts/report.json', 'a'*64))})
        self.assertEqual(out['unknown_or_unclassified_producers'], [])
        self.assertTrue(out['verdict'].endswith('INSUFFICIENT_V1'))

    def test_v2_classification_protocol_is_bound(self):
        job = 'non-position'
        out = c.apply(report_with(row(job)), {(job, 'a'): meta(('artefacts/report.json', 'a'*64))})
        self.assertEqual(out['classification_protocol_path'], c.CLASSIFICATION_PROTOCOL)
        self.assertRegex(out['classification_protocol_sha256'], r'^[0-9a-f]{64}$')

    def test_invalid_upstream_verdict_is_not_repaired(self):
        report = report_with(row('bad')); report['verdict'] = 'invalid'
        with self.assertRaisesRegex(ValueError, 'classification_upstream_verdict'):
            c.apply(report, {})


if __name__ == '__main__':
    unittest.main()
