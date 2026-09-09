import unittest
from jobs.tools import ed4_producer_classification as c


def row(job, attempt='a'):
    return {'job_id': job, 'attempt_id': attempt, 'classification': 'unknown',
            'classification_evidence': {}}


class ProducerClassification(unittest.TestCase):
    def test_explicit_superset_relation_wins_even_with_structural_paths(self):
        job = 'cpx62-1842-l3-decision-math-b3-fresh-audit-subset-seal-v1'
        report = {'sources': [row(job)], 'missing_paths': [],
                  'unknown_or_unclassified_producers': [job]}
        metadata = {(job, 'a'): {'files': [{'path': 'artefacts/parents.jnnw'}]}}
        out = c.apply(report, metadata)
        self.assertEqual(out['sources'][0]['classification'], 'covered_by_authenticated_superset')
        self.assertEqual(out['unknown_or_unclassified_producers'], [])
        self.assertTrue(out['verdict'].endswith('READY_V1'))

    def test_inventory_without_structural_descriptor_is_non_position(self):
        job = 'cpx62-1802-synthetic-readout-v1'
        report = {'sources': [row(job)], 'missing_paths': [],
                  'unknown_or_unclassified_producers': [job]}
        metadata = {(job, 'a'): {'files': [
            {'path': 'artefacts/scientific-summary.json'},
            {'path': 'artefacts/metrics.json'},
            {'path': 'manifest.json'}]}}
        out = c.apply(report, metadata)
        self.assertEqual(out['sources'][0]['classification'], 'non_position_producer')
        self.assertEqual(out['unknown_or_unclassified_producers'], [])

    def test_structural_descriptor_without_proof_stays_unknown(self):
        job = 'cpx62-1810-unmapped-v1'
        report = {'sources': [row(job)], 'missing_paths': [],
                  'unknown_or_unclassified_producers': [job]}
        metadata = {(job, 'a'): {'files': [{'path': 'artefacts/cohort.json'}]}}
        out = c.apply(report, metadata)
        self.assertEqual(out['sources'][0]['classification'], 'unknown')
        self.assertEqual(out['unknown_or_unclassified_producers'], [job])
        self.assertTrue(out['verdict'].endswith('INSUFFICIENT_V1'))

    def test_no_terminal_metadata_stays_unknown(self):
        job = 'cpx62-1811-unclaimed-v1'
        report = {'sources': [row(job, None)], 'missing_paths': [],
                  'unknown_or_unclassified_producers': [job]}
        out = c.apply(report, {})
        self.assertEqual(out['unknown_or_unclassified_producers'], [job])

    def test_missing_literal_path_keeps_insufficient_after_all_classified(self):
        job = 'cpx62-1802-synthetic-readout-v1'
        report = {'sources': [row(job)],
                  'missing_paths': [{'job_id': 'literal', 'path': 'work/current.jsm'}],
                  'unknown_or_unclassified_producers': [job]}
        metadata = {(job, 'a'): {'files': [{'path': 'artefacts/report.json'}]}}
        out = c.apply(report, metadata)
        self.assertEqual(out['unknown_or_unclassified_producers'], [])
        self.assertTrue(out['verdict'].endswith('INSUFFICIENT_V1'))

    def test_tokens_are_conservative(self):
        meta = {'files': [{'path': p} for p in [
            'x/current.jnnw', 'x/current.jsm', 'x/parents.tsv', 'x/root-pool.json',
            'x/source-selection-publication.json', 'x/openings.txt']]}
        self.assertEqual(len(c.structural_paths(meta)), 6)


if __name__ == '__main__':
    unittest.main()
