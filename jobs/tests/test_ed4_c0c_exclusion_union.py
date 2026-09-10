from __future__ import annotations
# Keep this module in the ED4 workflow so incident-register autofeed commits are
# followed by an ordinary branch commit that retriggers the required checks.
# Ordinary author commit below keeps required PR checks runnable after bot autofeed.
import gzip, hashlib, os, struct, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
from jobs.tools import ed4_c0c_exclusion_union as c0c
from jobs.tools.ed4_c0c_exclusion_union import parse_jnnw, parse_fen_file, parse_tsv, parse_candidate

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / 'jobs/tools/ed4_c0c_exclusion_union_stage.py'

class C0CParserTests(unittest.TestCase):
    def _record(self,target=b'abcde'):
        return struct.pack('<QQQQB',1,2,4,8,0)+target
    def test_jnnw_targets_are_not_semantic_input(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a.jnnw'; b=Path(td)/'b.jnnw'
            a.write_bytes(b'JNNW'+struct.pack('<I',1)+self._record(b'12345'))
            b.write_bytes(b'JNNW'+struct.pack('<I',1)+self._record(b'zzzzz'))
            ida,ra=parse_jnnw(a); idb,rb=parse_jnnw(b)
            self.assertEqual((ida,ra),(idb,rb)); self.assertEqual(ra,1)
    def test_gzip_jnnw(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jnnw.gz'
            with gzip.open(p,'wb') as f: f.write(b'JNNW'+struct.pack('<I',1)+self._record())
            ids,rows=parse_jnnw(p,True); self.assertEqual(rows,1); self.assertEqual(len(ids),1)
    def test_fen_and_tsv_converge(self):
        fen='W:W1,K2:B3,K4'
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); f=root/'x.fen'; t=root/'parents.tsv'
            f.write_text(fen+'\n'); t.write_text('fen\tother\n'+fen+'\tx\n')
            self.assertEqual(parse_fen_file(f)[0],parse_tsv(t)[0])
    def test_jsm_is_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jsm'; p.write_bytes(b'arbitrary')
            ids,rows,why=parse_candidate(p,'jsm')
            self.assertEqual(ids,set()); self.assertEqual(rows,0); self.assertIn('sidecar',why)
    def test_jnnw_rejects_trailing_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jnnw'; p.write_bytes(b'JNNW'+struct.pack('<I',1)+self._record()+b'x')
            with self.assertRaises(Exception): parse_jnnw(p)
    def test_parent_fetch_uses_runner_artefacts_namespace(self):
        sentinel = RuntimeError('stop-after-call-contract')
        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            c0c.fetch_result_files, 'fetch_files', side_effect=sentinel
        ) as fetch:
            with self.assertRaisesRegex(RuntimeError, 'stop-after-call-contract'):
                c0c.fetch_parent(Path(td))
        self.assertEqual(fetch.call_count, 1)
        kwargs = fetch.call_args.kwargs
        self.assertEqual(kwargs['prefix'], c0c.PARENT_PREFIX)
        self.assertEqual(kwargs['expected_state'], 'completed')
        self.assertEqual(kwargs['selections'], [
            ('artefacts/ed4-c0a-source-descriptor-inventory.json', 'c0a.json'),
            ('artefacts/ed4-c0b-structural-candidate-manifest.json', 'c0b.json'),
        ])
    def test_zero_size_candidate_is_authenticated_but_not_fetched_or_parsed(self):
        empty_sha = hashlib.sha256(b'').hexdigest()
        candidates = [
            {'path':'artefacts/empty.jnnw','kind':'jnnw','size_bytes':0,'sha256':empty_sha},
            {'path':'artefacts/live.jnnw','kind':'jnnw','size_bytes':46,'sha256':'a'*64},
        ]
        inventory = {
            'job_id':'job-1','attempt_id':'attempt-1',
            'files':[
                {'path':'artefacts/empty.jnnw','size_bytes':0,'sha256':empty_sha},
                {'path':'artefacts/live.jnnw','size_bytes':46,'sha256':'a'*64},
            ],
        }
        with mock.patch.object(c0c.fetch_result_files, 'inspect_result_inventory', return_value=inventory):
            nonempty, receipts = c0c._authenticate_candidate_descriptors(
                prefix='r2:x/job-1/attempt-1', state='completed', job_id='job-1',
                attempt='attempt-1', candidates=candidates,
            )
        self.assertEqual(nonempty, [(1, candidates[1])])
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]['path'], 'artefacts/empty.jnnw')
        self.assertEqual(receipts[0]['rows'], 0)
        self.assertEqual(receipts[0]['unique_identities'], 0)
        self.assertEqual(receipts[0]['semantics'], 'authenticated_zero_size_no_position_bytes')
    def test_zero_size_candidate_requires_empty_hash(self):
        candidates = [
            {'path':'artefacts/empty.jnnw','kind':'jnnw','size_bytes':0,'sha256':'a'*64},
        ]
        inventory = {
            'job_id':'job-1','attempt_id':'attempt-1',
            'files':[{'path':'artefacts/empty.jnnw','size_bytes':0,'sha256':'a'*64}],
        }
        with mock.patch.object(c0c.fetch_result_files, 'inspect_result_inventory', return_value=inventory):
            with self.assertRaisesRegex(c0c.C0CError, 'zero_size_hash_mismatch'):
                c0c._authenticate_candidate_descriptors(
                    prefix='r2:x/job-1/attempt-1', state='completed', job_id='job-1',
                    attempt='attempt-1', candidates=candidates,
                )
    def test_direct_stage_entrypoint_bootstraps_repo_imports_without_pythonpath(self):
        env = {'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'}
        completed = subprocess.run(
            [sys.executable, str(STAGE)], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn('ModuleNotFoundError', completed.stderr)
        self.assertIn('JASS_ARTEFACT_DIR', completed.stderr)
if __name__=='__main__': unittest.main()
