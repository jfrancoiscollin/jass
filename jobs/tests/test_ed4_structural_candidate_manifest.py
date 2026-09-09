import unittest
from jobs.tools import ed4_structural_candidate_manifest as c


class StructuralCandidateManifestTests(unittest.TestCase):
    def test_parser_classes_are_path_only_and_conservative(self):
        cases = {
            'work/current.jnnw': 'jnnw',
            'artefacts/parents.jnnw.gz': 'jnnw_gzip',
            'x/positions.fen': 'fen',
            'x/positions.fen.gz': 'fen_gzip',
            'x/current.jsm': 'jsm',
            'x/current.jsm.gz': 'jsm_gzip',
            'x/parents.tsv': 'parents_tsv',
            'x/children.tsv': 'children_tsv',
            'x/siblings.tsv': 'siblings_tsv',
            'x/groups.tsv': 'groups_tsv',
            'x/d4-search-utility-roots.tsv': 'roots_tsv',
            'x/ordered-identities.txt': 'identity_text',
            'x/b3-fresh-exclusion-union.txt': 'identity_text',
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(c.candidate_kind(path), expected)
        for path in ('docs/POSITION_REVIEW.md', 'build/root/file.o', 'metrics.json',
                     'train-0.jsonl', 'MODEL.pjtw'):
            with self.subTest(path=path):
                self.assertIsNone(c.candidate_kind(path))

    def test_build_keeps_exact_hash_size_and_unknown_only(self):
        report = {'sources': [
            {'job_id': 'a', 'attempt_id': 'aa', 'classification': 'unknown'},
            {'job_id': 'b', 'attempt_id': 'bb', 'classification': 'non_position_producer'},
            {'job_id': 'c', 'attempt_id': 'cc', 'classification': 'structural_payload_unavailable'},
        ]}
        metadata = {
            ('a', 'aa'): {'files': [
                {'path': 'work/current.jnnw', 'size_bytes': 46, 'sha256': 'a'*64},
                {'path': 'docs/position.md', 'size_bytes': 12, 'sha256': 'b'*64},
                {'path': 'artefacts/parents.tsv', 'size_bytes': 10, 'sha256': 'c'*64},
            ]},
            ('b', 'bb'): {'files': [
                {'path': 'work/ignored.fen', 'size_bytes': 5, 'sha256': 'd'*64},
            ]},
            ('c', 'cc'): {'files': [
                {'path': 'artefacts/siblings.tsv', 'size_bytes': 7, 'sha256': 'e'*64},
            ]},
        }
        out = c.build(metadata, report, 'f'*40)
        self.assertEqual(out['candidate_jobs_count'], 2)
        self.assertEqual(out['candidate_files_count'], 3)
        self.assertEqual(out['candidate_declared_bytes_total'], 63)
        self.assertEqual(out['candidate_kind_counts'],
                         {'jnnw': 1, 'parents_tsv': 1, 'siblings_tsv': 1})
        self.assertEqual(out['jobs_without_parseable_position_candidate'], [])
        self.assertEqual(out['payload_downloads'], 0)
        self.assertEqual(out['target_reads'], 0)
        self.assertIs(out['confirmation_authorized'], False)

    def test_no_candidate_job_is_reported_not_reclassified(self):
        report = {'sources': [
            {'job_id': 'x', 'attempt_id': 'xx', 'classification': 'unknown'},
        ]}
        metadata = {('x', 'xx'): {'files': [
            {'path': 'artefacts/report.json', 'size_bytes': 3, 'sha256': 'a'*64},
        ]}}
        out = c.build(metadata, report, 'f'*40)
        self.assertEqual(out['candidate_files_count'], 0)
        self.assertEqual(out['jobs_without_parseable_position_candidate'], ['x'])
        self.assertEqual(out['candidate_jobs'][0]['classification_at_freeze'], 'unknown')

    def test_bad_descriptor_fails_closed(self):
        report = {'sources': [
            {'job_id': 'x', 'attempt_id': 'xx', 'classification': 'unknown'},
        ]}
        metadata = {('x', 'xx'): {'files': [
            {'path': 'work/current.jnnw', 'size_bytes': -1, 'sha256': 'bad'},
        ]}}
        with self.assertRaisesRegex(ValueError, 'candidate_descriptor_invalid'):
            c.build(metadata, report, 'f'*40)


if __name__ == '__main__':
    unittest.main()
