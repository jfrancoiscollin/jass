import unittest
from jobs.tools import ed4_producer_classification as c


def row(job, attempt='a'):
    return {'job_id': job, 'attempt_id': attempt, 'classification': 'unknown',
            'classification_evidence': {}}


def report_for(job, attempt='a', missing=None):
    return {'sources': [row(job, attempt)],
            'missing_paths': list(missing or []),
            'unknown_or_unclassified_producers': [job],
            'verdict': c.INSUFFICIENT}


class ProducerClassification(unittest.TestCase):
    def test_explicit_superset_relation_wins_even_with_structural_paths(self):
        job = 'cpx62-1842-l3-decision-math-b3-fresh-audit-subset-seal-v1'
        out = c.apply(report_for(job), {(job, 'a'): {'files': [{'path': 'artefacts/parents.jnnw'}]}})
        self.assertEqual(out['sources'][0]['classification'], 'covered_by_authenticated_superset')
        self.assertEqual(out['unknown_or_unclassified_producers'], [])
        self.assertEqual(out['unknown_producer_evidence'], [])
        self.assertEqual(out['unknown_producer_compact_evidence'], [])

    def test_inventory_without_structural_descriptor_is_non_position(self):
        job = 'cpx62-1802-synthetic-readout-v1'
        metadata = {(job, 'a'): {'files': [
            {'path': 'artefacts/scientific-summary.json'}, {'path': 'artefacts/metrics.json'},
            {'path': 'manifest.json'}]}}
        out = c.apply(report_for(job), metadata)
        self.assertEqual(out['sources'][0]['classification'], 'non_position_producer')

    def test_structural_descriptor_publishes_small_kind_projection(self):
        job = 'cpx62-1810-unmapped-v1'
        paths = ['artefacts/cohort-01.json', 'artefacts/parents.jnnw',
                 'artefacts/children.jnnw', 'artefacts/siblings.tsv']
        metadata = {(job, 'a'): {'files': [{'path': p} for p in paths]}}
        out = c.apply(report_for(job), metadata)
        self.assertEqual(out['unknown_producer_evidence'][0]['structural_descriptor_paths'], sorted(paths))
        compact = out['unknown_producer_compact_evidence'][0]
        self.assertEqual(compact['structural_descriptor_count'], 4)
        self.assertEqual(compact['structural_kind_counts'], {
            'child': 1, 'cohort': 1, 'jnnw': 2, 'parent': 1, 'sibling': 1})
        self.assertEqual(len(compact['example_structural_paths']), 3)

    def test_no_terminal_metadata_stays_unknown(self):
        job = 'cpx62-1811-unclaimed-v1'
        out = c.apply(report_for(job, None), {})
        compact = out['unknown_producer_compact_evidence'][0]
        self.assertEqual(compact['structural_kind_counts'], {})
        self.assertEqual(compact['example_structural_paths'], [])

    def test_missing_literal_path_keeps_insufficient_after_all_classified(self):
        job = 'cpx62-1802-synthetic-readout-v1'
        report = report_for(job, missing=[{'job_id': 'literal', 'path': 'work/current.jsm'}])
        out = c.apply(report, {(job, 'a'): {'files': [{'path': 'artefacts/report.json'}]}})
        self.assertEqual(out['unknown_or_unclassified_producers'], [])
        self.assertTrue(out['verdict'].endswith('INSUFFICIENT_V1'))

    def test_invalid_upstream_verdict_is_not_repaired(self):
        job = 'cpx62-1812-invalid-v1'; report = report_for(job); report['verdict'] = 'invalid'
        with self.assertRaisesRegex(ValueError, 'classification_upstream_verdict'):
            c.apply(report, {})

    def test_tokens_are_conservative(self):
        meta = {'files': [{'path': p} for p in [
            'x/current.jnnw', 'x/current.jsm', 'x/parents.tsv', 'x/root-pool.json',
            'x/source-selection-publication.json', 'x/openings.txt']]}
        self.assertEqual(len(c.structural_paths(meta)), 6)


if __name__ == '__main__':
    unittest.main()
