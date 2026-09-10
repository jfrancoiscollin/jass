from __future__ import annotations
import gzip, os, struct, subprocess, sys, tempfile, unittest
from pathlib import Path
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
    def test_direct_stage_entrypoint_bootstraps_repo_imports_without_pythonpath(self):
        env = {'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'}
        completed = subprocess.run(
            [sys.executable, str(STAGE)], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )
        # No runner-owned stage environment is supplied. Reaching the expected
        # JASS_ARTEFACT_DIR lookup proves direct-path startup got past jobs.tools
        # imports under the same no-PYTHONPATH condition that broke 1898.
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn('ModuleNotFoundError', completed.stderr)
        self.assertIn('JASS_ARTEFACT_DIR', completed.stderr)
if __name__=='__main__': unittest.main()
