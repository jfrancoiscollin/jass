from __future__ import annotations
import hashlib, struct, tempfile, unittest, os
from contextlib import ExitStack
from pathlib import Path
from unittest import mock
from jobs.tools import ed4_c0c_exclusion_union as v1
from jobs.tools import ed4_c0c_full_format_diagnostic_v2 as subject
from jobs.tools import ed4_c0c_full_format_diagnostic_v2_stage as stage
from jobs.tools.adaptive_sibling_b2_exclusions import ContractError

def desc(): return {'path':'artefacts/x.fen','kind':'fen','sha256':hashlib.sha256(b'x').hexdigest(),'size_bytes':1}

class V2LeafValidationTests(unittest.TestCase):
    def setUp(self):
        self.canaries=[]
        for name in ('run_capture','download_verified'):
            patcher=mock.patch.object(subject.fetch_result_files.base,name,side_effect=AssertionError('real transport forbidden')); guard=patcher.start(); self.canaries.append(guard); self.addCleanup(patcher.stop); self.addCleanup(guard.assert_not_called)
    def row(self, text):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.fen'; p.write_text(text,encoding='utf-8'); return subject._diagnose_one(p,desc(),'job','attempt',{}, {},None)
    def test_known_leaf_errors_are_normalized_without_payload(self):
        cases=[('W:W1:B1','fen_cross_colour_overlap'),('W:W51:B2','fen_square_out_of_range'),('W:W1,1:B2','fen_duplicate_square')]
        for text, code in cases:
            row=self.row(text); self.assertEqual(row['outcome'],code); self.assertNotIn(text,str(row))
        with mock.patch.object(v1,'parse_candidate',side_effect=ContractError('parent fingerprint STM is not 0 or 1')):
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'x'; p.write_text('x'); self.assertEqual(subject._diagnose_one(p,desc(),'j','a',{}, {},None)['outcome'],'position_stm_invalid')
    def test_unknown_contract_error_propagates(self):
        with mock.patch.object(v1,'parse_candidate',side_effect=ContractError('catalog schema mismatch')):
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'x'; p.write_text('x')
                with self.assertRaisesRegex(ContractError,'catalog schema mismatch'): subject._diagnose_one(p,desc(),'j','a',{}, {},None)
    def test_contract_error_outside_parse_scope_propagates(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(subject.v6,'_load_1927',return_value=({}, {}, {})), mock.patch.object(subject.v6,'validate_1927',return_value=({},{},{})), mock.patch.object(subject.v1,'fetch_parent',side_effect=ContractError('catalog schema mismatch')), mock.patch.object(subject,'EXPECTED_RECOVERY_ROWS',0):
            with self.assertRaisesRegex(ContractError,'catalog schema mismatch'): subject.build_diagnostic(Path(td)/'w',Path(td)/'a')
    def test_real_binary_position_leaf_errors_continue_as_rows(self):
        cases=[((1,2,4,8,2),'position_stm_invalid'),((1<<50,0,0,0,0),'position_bitboard_out_of_range'),((1,1,0,0,0),'position_overlapping_pieces')]
        with tempfile.TemporaryDirectory() as td:
            for index, (fields, code) in enumerate(cases):
                raw=b'JNNW'+struct.pack('<I',1)+struct.pack('<QQQQB',*fields)+b'xxxxx'; p=Path(td)/str(index); p.write_bytes(raw)
                d={'path':f'artefacts/{index}.jnnw','kind':'jnnw','sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)}
                self.assertEqual(subject._diagnose_one(p,d,'j','a',{}, {},None)['outcome'],code)
    def test_all_leaf_messages_are_finite(self):
        for message, code in [('bad parent fingerprint: private','position_fingerprint_syntax'),('FEN contains an empty square token','fen_empty_square_token'),('bad FEN square token: private','fen_square_token'),('bad FEN range: private','fen_range'),('FEN must contain one W piece field','fen_piece_field')]:
            self.assertEqual(subject._normalize_leaf_contract_error(ContractError(message)),code)
        with self.assertRaises(ContractError):
            subject._normalize_leaf_contract_error(ContractError('parent fingerprint STM is not 0 or 1 unexpected'))

class V2FullTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        record=struct.pack('<QQQQB',1,2,4,8,0)+b'\xff'*5; candidates=[]; payloads={}; allow={}
        for i in range(726):
            kind, raw='fen', b'W:W1,K2:B3,K4\n'
            if i<6: raw=b''
            elif i<237:
                kind='jnnw'; raw=b'JNNW'+struct.pack('<I',0)+record+(b'\xff' if i<222 else b'')
            elif i==237: raw=b'# comment\n'
            elif i==238: kind='jnnw'; raw=b'JNNW'+struct.pack('<I',1)+struct.pack('<QQQQB',1,2,4,8,7)+b'\xff'*5
            d={'path':f'artefacts/{i:04d}.{kind}','kind':kind,'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}; candidates.append(d); payloads[d['path']]=raw
            if 6<=i<237: allow[('job','attempt',d['path'])]={**d,'job_id':'job','attempt_id':'attempt','partial_tail_bytes_from_size':1 if i<222 else 0,'complete_records_from_size':1}
        def fetch(**kw):
            kw['out_dir'].mkdir(parents=True,exist_ok=True); files=[]
            for remote,local in kw['selections']:
                (kw['out_dir']/local).write_bytes(payloads[remote]); files.append(next(d for d in candidates if d['path']==remote))
            return {'job_id':'job','attempt_id':'attempt','result_state':'completed','files':files}
        cls.stack=ExitStack(); cls.addClassCleanup(cls.stack.close); cls.guards=[cls.stack.enter_context(mock.patch.object(subject.fetch_result_files.base,n,side_effect=AssertionError('network forbidden'))) for n in ('run_capture','download_verified')]
        cls.stack.enter_context(mock.patch.object(subject.v6,'_load_1927',return_value=({}, {}, {}))); cls.stack.enter_context(mock.patch.object(subject.v6,'validate_1927',return_value=(allow,{}, {'allowlist_canonical_sha256':'a'*64,'aligned_subset_canonical_sha256':'b'*64}))); cls.stack.enter_context(mock.patch.object(subject.v1,'fetch_parent',return_value=({'sources':[{'job_id':'job','attempt_id':'attempt','result_state':'completed'}]},{'candidate_jobs':[{'job_id':'job','attempt_id':'attempt','candidate_files':candidates}]}))); cls.stack.enter_context(mock.patch.object(subject.v1,'_authenticate_candidate_descriptors',return_value=(list(enumerate(candidates[6:],6)),candidates[:6]))); cls.stack.enter_context(mock.patch.object(subject.fetch_result_files,'fetch_files',side_effect=fetch))
        cls.tmp=tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.tmp.cleanup); cls.table=subject.build_diagnostic(Path(cls.tmp.name)/'w',Path(cls.tmp.name)/'a')
    @classmethod
    def tearDownClass(cls):
        for guard in cls.guards: guard.assert_not_called()
        cls.stack.close(); cls.tmp.cleanup()
    def test_full_726_continues_known_fen_and_position_errors(self):
        counts={};
        for row in self.table['rows']: counts[row['outcome']]=counts.get(row['outcome'],0)+1
        self.assertEqual(counts,{'zero-byte':6,'v5-partial-recovery-pass':216,'v6-aligned-recovery-pass':15,'fen_empty':1,'position_stm_invalid':1,'strict-v1-pass':487})
        self.assertNotIn('W:W1',str(self.table))
    def test_stage_rejects_production_and_deadline_without_builder(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(stage,'build_diagnostic') as build, mock.patch.dict(os.environ,{'JASS_ARTEFACT_DIR':str(Path(td)/'a'),'JASS_RESULT_DIR':str(Path(td)/'r'),'LAUNCH_MODE':'production'}): self.assertEqual(stage.main(),2)
        build.assert_not_called()
        with self.assertRaisesRegex(v1.C0CError,'deadline'): subject.base._deadline(0.0,'test')


if __name__=='__main__': unittest.main()
