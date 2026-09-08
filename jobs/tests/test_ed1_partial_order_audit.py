from __future__ import annotations
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'jobs/tools/ed1_partial_order_audit.py'
spec = importlib.util.spec_from_file_location('ed1', SCRIPT)
ed1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ed1)


class ED1Tests(unittest.TestCase):
    def test_interval_overlap_abstains_and_no_fixed_gap(self):
        q = {(0,5000):0., (0,50000):5., (1,5000):-2., (1,50000):4.,
             (2,5000):-10., (2,50000):-10.}
        p = ed1.lower_labels([0,1,2], q)
        self.assertEqual(p['point'], [[0,1],[0,2],[1,2]])
        self.assertEqual(p['retained'], [[0,2],[1,2]])
        # Exactly touching envelopes also abstain, independent of cp units.
        q[1,50000] = 0.
        self.assertNotIn([0,1], ed1.lower_labels([0,1,2], q)['retained'])

    def test_higher_and_unselected_score_fields_are_not_accessed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'scan.tsv'
            p.write_text('row_index\tbudget_nodes\tparent_score_centi\n'
                         '0\t5000\t2\n0\t50000\t3\n'
                         '0\t200000\tFORBIDDEN\n9\t5000\tFORBIDDEN\n')
            self.assertEqual(ed1.load_scores([p], {0}, ed1.LOW), {(0,5000):2.,(0,50000):3.})
            with self.assertRaises(ValueError):
                ed1.load_scores([p], {0}, (200000,))

    def test_missing_duplicate_nonfinite_coverage_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'s.tsv'
            head = 'row_index\tbudget_nodes\tparent_score_centi\n'
            for tail in ('0\t5000\t2\n',
                         '0\t5000\t2\n0\t5000\t2\n0\t50000\t3\n',
                         '0\t5000\tnan\n0\t50000\t3\n'):
                p.write_text(head+tail)
                with self.assertRaises(ValueError):
                    ed1.load_scores([p], {0}, ed1.LOW)

    def test_audit_tie_not_a_wrong_label(self):
        p = dict(parent_id=0, cohort='A', phase='P0', rows=[0,1], point=[[0,1]],
                 retained=[[0,1]], best50=[0])
        r = ed1.parent_result(p, {(0,200000):1., (1,200000):1.})
        self.assertEqual(r['point']['contradiction'], 0.)
        self.assertEqual(r['point']['tie'], 1.)
        self.assertFalse(r['top50_set_disjoint_from_200'])

    def test_no_retained_labels_is_insufficient_not_neutral_success(self):
        p = dict(parent_id=0, cohort='A', phase='P0', rows=[0,1], point=[[0,1]],
                 retained=[], best50=[0])
        r = ed1.parent_result(p, {(0,200000):0., (1,200000):1.})
        s = ed1.cohort_summary([r], 1)
        self.assertFalse(s['support_sufficient'])
        self.assertFalse(s['supported'])
        self.assertIsNone(s['retained_contradiction'])

    def test_full_producer_consumer_roundtrip_and_seal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            groups = root/'siblings.tsv'
            lines = ['parent_id\trow_index\tparent_fingerprint\tparent_phase\n']
            cohorts = {c: [] for c in ('A','B')}
            shards = [[] for _ in range(16)]
            for pid in range(2000):
                phase = 'P'+str(pid//500)
                j = pid%500
                if j<128: cohorts['A'].append(pid)
                elif j<256: cohorts['B'].append(pid)
                for a in range(3):
                    rid = 3*pid+a
                    lines.append(f'{pid}\t{rid}\tfp-{pid}\t{phase}\n')
                    values = {5000:(0,-2,-10),50000:(5,4,-10),200000:(3,6,-10)}
                    for n, vals in values.items():
                        shards[rid%16].append(f'{rid}\t{n}\t{vals[a]}\n')
            groups.write_text(''.join(lines))
            cp = {}
            for c, ids in cohorts.items():
                cp[c] = root/f'{c}.txt'
                cp[c].write_text(''.join(f'{x}\n' for x in ids))
            paths = []
            for i, rows in enumerate(shards):
                p = root/f's{i:02d}.tsv.gz'; paths.append(p)
                with gzip.open(p, 'wt') as f:
                    f.write('row_index\tbudget_nodes\tparent_score_centi\n'+''.join(rows))
            labels = root/'labels.json'
            with patch.object(ed1, 'ID_SHA', {c:ed1.sha(p) for c,p in cp.items()}):
                ed1.freeze(groups, cp, paths, labels)
            report = ed1.audit_labels(labels, paths, root/'report.json', root/'details.json')
            self.assertEqual(report['verdict'], 'ED1_PARTIAL_ORDER_LABEL_SIGNAL_V1')
            self.assertEqual(report['cohorts']['A']['retained_parents'], 512)
            self.assertEqual(report['cohorts']['A']['retained_contradiction'], 0.)
            self.assertAlmostEqual(report['cohorts']['A']['point_contradiction'], 1/3)
            self.assertFalse(report['fit_authorized'])
            self.assertFalse(report['causal_eval_improvement_established'])
            with self.assertRaises(FileExistsError):
                ed1.write_new(labels, {})
            labels.write_text('{}\n')
            with self.assertRaisesRegex(ValueError, 'seal mismatch'):
                ed1.audit_labels(labels, paths, root/'bad.json', root/'bad-details.json')

    def test_actual_direct_cli_and_bad_arguments(self):
        run = subprocess.run([sys.executable, str(SCRIPT), '--help'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        run = subprocess.run([sys.executable, str(SCRIPT), 'audit', '--labels','missing',
                              '--scan-score','missing', '--out','out','--details','details'],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn('sixteen', run.stderr)


if __name__ == '__main__':
    unittest.main()
