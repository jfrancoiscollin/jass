from __future__ import annotations
import hashlib, json, os, struct, tempfile, unittest
from pathlib import Path
from unittest import mock
from jobs.tools import ed4_c0c_exclusion_union as v1
from jobs.tools import ed4_c0c_exclusion_union_v5 as v5
from jobs.tools import ed4_c0c_exclusion_union_v6 as v6
from jobs.tools import ed4_c0c_exclusion_union_v6_stage as stage


def record(position=(1,2,4,8,0), target=b'abcde'):
    return struct.pack('<QQQQB', *position) + target


def row(n, aligned=False, target=b'abcde'):
    complete = 1944 if aligned and (n < 2 or n in (216, 217)) else 2160 if aligned else 1
    tail = 0 if aligned else (n % 37) + 1
    raw = b'JNNW' + struct.pack('<I', 0) + record(target=target) * complete + b'x' * tail
    return {'job_id': 'job-%03d' % n, 'attempt_id': 'attempt', 'path': 'artefacts/%03d.jnnw' % n, 'kind': 'jnnw', 'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw), 'reason': 'jnnw_trailing_bytes', 'state': 'invalid', 'declared_count': 0, 'complete_records_from_size': complete, 'partial_tail_bytes_from_size': tail, 'interrupted_writer_shape': not aligned}, raw


class V6ContractTests(unittest.TestCase):
    def setUp(self):
        for name in ('run_capture', 'download_verified'):
            patcher = mock.patch.object(
                v6.fetch_result_files.base, name,
                side_effect=AssertionError('V6 test attempted real transport'),
            )
            transport = patcher.start()
            self.addCleanup(patcher.stop)
            self.addCleanup(transport.assert_not_called)

    def inventory(self):
        pairs = [row(i) for i in range(216)] + [row(216 + i, True) for i in range(15)]
        rows = [x[0] for x in pairs]
        zeros = {'record_fields_decoded':0,'position_identity_reads':0,'target_fields_decoded':0,'target_reads':0,'score_reads':0,'wdl_reads':0,'qvalue_reads':0,'model_reads':0,'teacher_calls':0,'search_calls':0,'fits':0,'games':0,'alpha_spent':0}
        inv = {'schema':'jass.ed4.c0c_v4_full_malformed_inventory.v1','state': 'completed', 'malformed_count': 231, 'malformed': rows, **zeros}
        outside = [{k:r[k] for k in (*v6.CANONICAL_FIELDS, 'state', 'interrupted_writer_shape')} for r in rows if not r['interrupted_writer_shape']]
        readout = {'schema':'jass.ed4.c0c_v5_inventory_class_readout.v1','state':'completed','inventory_job_id':v5.INV_JOB,'malformed_count':231,'interrupted_writer_count':216,'outside_class_count':15,'outside_class':outside,'scientific_verdict':None,'confirmation_authorized':False,**zeros}
        _, full = v6._canonical_rows(rows); _, aligned = v6._canonical_rows([r for r in rows if not r['interrupted_writer_shape']])
        return inv, readout, pairs, full, aligned

    def _pipeline(self, pairs, inv, readout, full, aligned, omit=None, duplicate=False):
        bodies = {r['path']: raw for r, raw in pairs}
        jobs = []
        for r, _ in pairs:
            if r['path'] == omit: continue
            jobs.append({'job_id':r['job_id'],'attempt_id':r['attempt_id'],'candidate_files':[{'path':r['path'],'kind':r['kind'],'sha256':r['sha256'],'size_bytes':r['size_bytes']}]})
        if duplicate: jobs.append(dict(jobs[0]))
        c0a = {'sources':[{'job_id':j['job_id'],'attempt_id':j['attempt_id'],'result_state':'completed'} for j in jobs]}
        c0b = {'candidate_jobs':jobs}
        def auth(**kwargs):
            return list(enumerate(kwargs['candidates'])), []
        def fetch(**kwargs):
            report=[]
            for path, name in kwargs['selections']:
                raw=bodies[path]; (kwargs['out_dir']/name).parent.mkdir(parents=True,exist_ok=True); (kwargs['out_dir']/name).write_bytes(raw)
                r=next(x for x,_ in pairs if x['path']==path); report.append({'path':path,'sha256':r['sha256'],'size_bytes':r['size_bytes']})
            return {'files':report}
        return mock.patch.object(v6,'_load_1927',return_value=(inv,readout,{'inventory_sha256':v6.INV_SHA256,'inventory_size_bytes':v6.INV_SIZE,'readout_sha256':v6.READOUT_SHA256,'readout_size_bytes':v6.READOUT_SIZE})), mock.patch.object(v1,'fetch_parent',return_value=(c0a,c0b)), mock.patch.object(v1,'_authenticate_candidate_descriptors',side_effect=auth), mock.patch.object(v6.fetch_result_files,'fetch_files',side_effect=fetch), mock.patch.object(v6,'FULL_ALLOWLIST_CANONICAL_SHA256',full), mock.patch.object(v6,'ALIGNED_SUBSET_CANONICAL_SHA256',aligned)

    def test_1927_partition_digest_and_readout_equality(self):
        inv, readout, _, full, aligned = self.inventory()
        with mock.patch.object(v6, 'FULL_ALLOWLIST_CANONICAL_SHA256', full), mock.patch.object(v6, 'ALIGNED_SUBSET_CANONICAL_SHA256', aligned):
            allow, partitions, digests = v6.validate_1927(inv, readout)
        self.assertEqual(len(allow), 231); self.assertEqual(len(partitions['v5']),216); self.assertEqual(len(partitions['aligned']),15)
        self.assertEqual(sum(x['complete_records_from_size'] for x in partitions['aligned']),31968)
        self.assertEqual(digests['allowlist_canonical_sha256'],full)

    def test_authenticated_inventory_constant_is_literal_64_hex_with_leading_one(self):
        self.assertEqual(v6.INV_SHA256, '1e8ebc5ee1c5614390c950e903377a6c3664b8d0c2a08f21c0295b2066f4d599')
        self.assertTrue(v6.HEX64.fullmatch(v6.INV_SHA256))

    def test_invalid_pins_fail_before_payload_work(self):
        inv, readout, *_ = self.inventory()
        with mock.patch.object(v6, 'FULL_ALLOWLIST_CANONICAL_SHA256', 'pending'), mock.patch.object(v6, 'ALIGNED_SUBSET_CANONICAL_SHA256', 'pending'):
            with self.assertRaisesRegex(v1.C0CError, 'digest_pins_pending'):
                v6.validate_1927(inv, readout)

    def test_aligned_decodes_exactly_33_bytes_and_ignores_target_bytes(self):
        first, raw = row(0, True, b'abcde'); changed = bytearray(raw)
        for offset in range(8 + 33, len(changed), 38): changed[offset:offset+5] = b'zzzzz'
        second = dict(first, sha256=hashlib.sha256(changed).hexdigest())
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jnnw'; p.write_bytes(raw)
            with mock.patch.object(v1,'canonical_from_position_bytes',wraps=v1.canonical_from_position_bytes) as decoder:
                a, rows, _ = v6._parse_aligned(p, first, first)
            self.assertEqual(rows,1944); self.assertEqual(decoder.call_count,1944); self.assertTrue(all(len(c.args[0]) == 33 for c in decoder.call_args_list))
            p.write_bytes(changed); b, _, _ = v6._parse_aligned(p, second, second)
        self.assertEqual(a,b)

    def test_v5_tail_decoder_remains_the_frozen_helper(self):
        original, raw = row(9, False)
        allow = {(original['job_id'], original['attempt_id'], original['path']): {'sha256':original['sha256'],'size_bytes':original['size_bytes'],'complete':1,'tail':original['partial_tail_bytes_from_size']}}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'v5.jnnw'; p.write_bytes(raw)
            identities, count, recovery = v5._salvage(p, original, original['job_id'], original['attempt_id'], allow)
        self.assertEqual(count, 1); self.assertEqual(recovery['partial_tail_bytes_discarded'], original['partial_tail_bytes_from_size']); self.assertEqual(len(identities), 1)

    def test_every_wrong_aligned_identity_header_geometry_and_empty_rejects(self):
        good, raw = row(0, True)
        variants = [b'', b'XXXX'+raw[4:], b'JNNW'+struct.pack('<I',1)+raw[8:], raw+b'x']
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x'
            for raw_value in variants:
                p.write_bytes(raw_value)
                bad=dict(good, sha256=hashlib.sha256(raw_value).hexdigest(), size_bytes=len(raw_value))
                with self.assertRaises(v1.C0CError): v6._parse_aligned(p,bad,bad)
            p.write_bytes(raw)
            with self.assertRaises(v1.C0CError): v6._parse_aligned(p,{**good,'path':'artefacts/other.jnnw'},good)

    def test_v5_tail_zero_is_not_admitted_and_duplicate_or_invalid_rows_fail(self):
        inv, readout, *_ = self.inventory()
        inv['malformed'][0]['partial_tail_bytes_from_size'] = 0
        with self.assertRaises(v1.C0CError): v6.validate_1927(inv, readout)

    def test_1927_identity_schema_and_counter_guards_fail_closed(self):
        inv, readout, *_ = self.inventory()
        for mutate in (lambda x:x.update(schema='wrong'), lambda x:x.update(target_reads=True)):
            candidate=json.loads(json.dumps(inv)); mutate(candidate)
            with self.assertRaises(v1.C0CError): v6.validate_1927(candidate,readout)
        with mock.patch.object(v6.fetch_result_files,'inspect_result_inventory',return_value={'job_id':v6.INV_JOB,'attempt_id':v6.INV_ATTEMPT,'code_sha':v6.INV_CODE,'result_state':'completed','host':'wrong','exit_code':0}) as inspect, mock.patch.object(v6.fetch_result_files,'fetch_files') as fetch:
            with tempfile.TemporaryDirectory() as td, self.assertRaises(v1.C0CError): v6._load_1927(Path(td))
        self.assertTrue(inspect.called); fetch.assert_not_called()

    def test_frozen_v5_inventory_loader_still_rejects_aligned_tail_zero(self):
        raw=b'JNNW'+struct.pack('<I',0)+record()
        item={'path':v5.INV_PATH,'sha256':'a'*64,'size_bytes':1}
        report={'job_id':v5.INV_JOB,'attempt_id':v5.INV_ATTEMPT,'code_sha':v5.INV_CODE,'result_state':'completed','files':[item]}
        aligned={'schema':'jass.ed4.c0c_v4_full_malformed_inventory.v1','state':'completed','target_fields_decoded':0,'target_reads':0,'wdl_reads':0,'qvalue_reads':0,'alpha_spent':0,'malformed_count':1,'malformed':[{'job_id':'j','attempt_id':'a','path':'artefacts/a.jnnw','kind':'jnnw','state':'invalid','reason':'jnnw_trailing_bytes','declared_count':0,'interrupted_writer_shape':False,'complete_records_from_size':1,'partial_tail_bytes_from_size':0,'sha256':'a'*64,'size_bytes':46}]}
        def fetch(**kwargs):
            (kwargs['out_dir']/'inventory.json').write_text(json.dumps(aligned)); return {'files':[item]}
        with tempfile.TemporaryDirectory() as td, mock.patch.object(v5.fetch_result_files,'inspect_result_inventory',return_value=report), mock.patch.object(v5.fetch_result_files,'fetch_files',side_effect=fetch), self.assertRaisesRegex(v1.C0CError,'v5_new_malformed_class'):
            v5._load_inventory(Path(td))
        inv, readout, *_ = self.inventory(); inv['malformed'].append(dict(inv['malformed'][0]))
        with self.assertRaises(v1.C0CError): v6.validate_1927(inv, readout)
        inv, readout, *_ = self.inventory(); inv['malformed'][0]['sha256'] = 'A' * 64
        with self.assertRaises(v1.C0CError): v6.validate_1927(inv, readout)

    def test_stage_fails_without_sizing_and_cannot_emit_ready(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(stage, 'RUNTIME_MAX_SECONDS', None), mock.patch.object(stage, 'build_union_v6', side_effect=AssertionError('builder must not run')) as builder, mock.patch.dict(os.environ, {'JASS_ARTEFACT_DIR':str(Path(td)/'a'),'JASS_RESULT_DIR':str(Path(td)/'r'),'LAUNCH_MODE':'rehearsal'}):
            self.assertEqual(stage.main(),2)
            summary=json.loads((Path(td)/'a'/'scientific-summary.json').read_text())
        builder.assert_not_called()
        self.assertEqual(summary['state'],'failed'); self.assertFalse(summary['confirmation_authorized']); self.assertEqual(summary['target_reads'],0)
        self.assertEqual(summary['error'], 'v6_runtime_sizing_pending')

    def test_profile_has_required_boundary_suites_and_nonempty_v6_suite(self):
        profile=json.loads((Path(__file__).parents[1]/'launch_profiles/ed4-c0c-exclusion-union-v6-inventory-closed-aligned-count0.json').read_text())
        self.assertTrue({'jobs.tests.test_launch_gate_v2','jobs.tests.test_launch_gate_pipeline_v2','jobs.tests.test_ed4_c0c_exclusion_union','jobs.tests.test_ed4_c0c_exclusion_union_v2','jobs.tests.test_ed4_c0c_exclusion_union_v6'}.issubset(profile['regressions']))

    def test_full_synthetic_union_is_deterministic_and_failures_never_publish(self):
        inv, readout, pairs, full, aligned = self.inventory()
        with tempfile.TemporaryDirectory() as td:
            contexts=self._pipeline(pairs,inv,readout,full,aligned)
            with contexts[0],contexts[1],contexts[2],contexts[3],contexts[4],contexts[5]:
                first=v6.build_union_v6(Path(td)/'w1',Path(td)/'a1')
            contexts=self._pipeline(pairs,inv,readout,full,aligned)
            with contexts[0],contexts[1],contexts[2],contexts[3],contexts[4],contexts[5]:
                second=v6.build_union_v6(Path(td)/'w2',Path(td)/'a2')
            self.assertEqual((Path(td)/'a1/ed4-c0c-structural-exclusion-union.txt').read_bytes(),(Path(td)/'a2/ed4-c0c-structural-exclusion-union.txt').read_bytes())
            self.assertEqual(first['union_sha256'],second['union_sha256']); self.assertEqual(first['aligned_count0_records'],31968)
            for name, kw in [('missing',{'omit':pairs[0][0]['path']}),('duplicate',{'duplicate':True})]:
                contexts=self._pipeline(pairs,inv,readout,full,aligned,**kw)
                out=Path(td)/('bad-'+name)
                with contexts[0],contexts[1],contexts[2],contexts[3],contexts[4],contexts[5], self.assertRaises(v1.C0CError): v6.build_union_v6(Path(td)/('work-'+name),out)
                self.assertFalse((out/'ed4-c0c-structural-exclusion-union.txt').exists())

    def test_unlisted_aligned_and_invalid_position_fail_before_output(self):
        inv, readout, pairs, full, aligned = self.inventory()
        rogue, raw=row(999,True); pairs2=pairs+[(rogue,raw)]
        with tempfile.TemporaryDirectory() as td:
            contexts=self._pipeline(pairs2,inv,readout,full,aligned); out=Path(td)/'rogue'
            with contexts[0],contexts[1],contexts[2],contexts[3],contexts[4],contexts[5], self.assertRaises(v1.C0CError): v6.build_union_v6(Path(td)/'wr',out)
            self.assertFalse((out/'ed4-c0c-structural-exclusion-union.txt').exists())
            inv, readout, pairs, _, _ = self.inventory(); bad_row, _ = pairs[216]; bad_raw=b'JNNW'+struct.pack('<I',0)+record((1,2,4,8,2))*1944
            bad_row['sha256']=hashlib.sha256(bad_raw).hexdigest()
            for item in readout['outside_class']:
                if item['path']==bad_row['path']: item['sha256']=bad_row['sha256']
            pairs[216]=(bad_row,bad_raw); _, full=v6._canonical_rows(inv['malformed']); _, aligned=v6._canonical_rows([r for r in inv['malformed'] if not r['interrupted_writer_shape']])
            contexts=self._pipeline(pairs,inv,readout,full,aligned); out=Path(td)/'invalid'
            with contexts[0],contexts[1],contexts[2],contexts[3],contexts[4],contexts[5], self.assertRaises(v1.C0CError): v6.build_union_v6(Path(td)/'wi',out)
            self.assertFalse((out/'ed4-c0c-structural-exclusion-union.txt').exists())

    def test_checkpoint_records_only_completed_work_on_failure(self):
        inv, readout, pairs, full, aligned = self.inventory(); events=[]
        contexts=self._pipeline(pairs,inv,readout,full,aligned,omit=pairs[0][0]['path'])
        with tempfile.TemporaryDirectory() as td, contexts[0],contexts[1],contexts[2],contexts[3],contexts[4],contexts[5], self.assertRaises(v1.C0CError): v6.build_union_v6(Path(td)/'w',Path(td)/'a',checkpoint=lambda n,e:events.append((n,e)))
        self.assertEqual(events[-1],('download-and-parse-authenticated-candidates','complete'))
        self.assertNotIn(('verify-exact-allowlist-encounters','begin'),events); self.assertNotIn(('publish-union-v6','begin'),events)

if __name__ == '__main__': unittest.main()
