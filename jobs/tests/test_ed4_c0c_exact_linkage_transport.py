from __future__ import annotations
import os, tempfile, unittest, copy, hashlib, json, time
from pathlib import Path
from unittest import mock
from jobs.tools import ed4_c0c_exact_linkage_diagnostic_stage as stage
from jobs.tools import ed4_c0c_exact_linkage_transport as transport
from jobs.tools import ed4_c0c_exact_linkage_diagnostic as core
from jobs.tests import test_ed4_c0c_exact_linkage_diagnostic as fixtures


def full_fixture():
    manifest,payloads = fixtures.FullSyntheticEvidenceTests().make_fixture()
    original = core.expected_descriptors(manifest)
    new_payloads = {}
    for index,(key,desc) in enumerate(original.items()):
        desc.update(job_id=f'synthetic-{index%14:02d}',attempt_id='attempt',path=f'object-{index:02d}/'+desc['path'])
        desc.setdefault('kind','jnnw')
        desc['metadata_parent']='c0b'
        new_payloads[core.descriptor_key(desc)] = payloads[key]
    for case in manifest['tsv_cases']:
        for row in case['aliases']: row['outcome']='tsv_no_position_field'
        case.update(expected_child_count=1,expected_parent_uncompressed_bytes=46,expected_child_uncompressed_bytes=46)
    for row in manifest['comment_only']['aliases']: row['outcome']='fen_empty'
    for row in manifest['invalid_stm']['aliases']: row['outcome']='position_stm_invalid'
    manifest['invalid_stm']['artifact_causality_proven']=False
    manifest['failure_rows'].sort(key=core.descriptor_key)
    manifest['comment_only']['aliases'].sort(key=core.descriptor_key)
    manifest['invalid_stm']['aliases'].sort(key=core.descriptor_key)
    manifest.update(c0a_sha256=transport.c0c.C0A_SHA,c0b_sha256=transport.c0c.C0B_SHA,
        runtime={'mode':'rehearsal','stage_seconds':2100,'publication_seconds':2700},
        read_policy={'jnnw_source_record_offsets':[0,33],'forbidden_source_record_offsets':[33,38],
                     'alternate_framing_authorized':False})
    descriptors = core.expected_descriptors(manifest)
    diagnostic_rows = copy.deepcopy(manifest['failure_rows'])
    failure_keys = {core.descriptor_key(r) for r in diagnostic_rows}
    diagnostic_rows += [dict(d,outcome='strict-v1-pass') for k,d in descriptors.items() if k not in failure_keys]
    for outcome,n in [('strict-v1-pass',460),('v5-partial-recovery-pass',216),('v6-aligned-recovery-pass',15),('zero-byte',6)]:
        for i in range(n):
            diagnostic_rows.append({'job_id':'synthetic-00','attempt_id':'attempt','path':f'filler/{outcome}/{i}',
                'kind':'jnnw','sha256':hashlib.sha256(b'').hexdigest(),'size_bytes':0,'outcome':outcome})
    diagnostic_rows.sort(key=core.descriptor_key)
    diagnostic = {'schema':'jass.ed4.c0c_full_format_diagnostic.v2','state':'completed','rows':diagnostic_rows,
        'classification_sha256':hashlib.sha256(core._canonical(diagnostic_rows)).hexdigest(),
        'failure_rows_sha256':hashlib.sha256(core._canonical(manifest['failure_rows'])).hexdigest(),
        'scientific_verdict':None,'confirmation_authorized':False,'automatic_continuation':False}
    for name in ('target_fields_decoded','target_reads','score_reads','wdl_reads','qvalue_reads','model_reads',
                 'teacher_calls','search_calls','fits','games','alpha_spent'): diagnostic[name]=0
    manifest['frozen_partition'] = {'descriptor_count':726,'strict-v1-pass':468,'v5-partial-recovery-pass':216,
        'v6-aligned-recovery-pass':15,'zero-byte':6,'fen_empty':3,'position_stm_invalid':3,'tsv_no_position_field':15}
    c0b={'candidate_jobs':[]}; c0a={'sources':[]}; sources=[]; metadata_bytes={}; inventories={}
    for index in range(14):
        job=f'synthetic-{index:02d}'
        source={'job_id':job,'attempt_id':'attempt','prefix':f'r2:synthetic/{job}/attempt','code_sha':'c'*40,
                'result_state':'completed','exit_code':0}
        source['authentication']={}
        for filename,key in [('manifest.json','manifest_sha256'),('inventory.json','inventory_sha256'),('checksums.sha256','checksums_sha256')]:
            raw=core._canonical({'job':job,'file':filename})
            metadata_bytes[source['prefix']+'/'+filename]=raw
            source['authentication'][key]=hashlib.sha256(raw).hexdigest()
        sources.append(source)
        c0a['sources'].append({**source,'classification_evidence':{'authentication':source['authentication']}})
        job_descriptors=[{k:v for k,v in row.items() if k not in ('job_id','attempt_id','outcome')} for row in diagnostic_rows if row['job_id']==job]
        c0b['candidate_jobs'].append({'job_id':job,'attempt_id':'attempt','candidate_files':job_descriptors})
        inventories[source['prefix']]={**source,'files':job_descriptors}
    manifest['sources']=sources
    raw=core._canonical(diagnostic)
    manifest['parent']={'job_id':'diagnostic-parent','attempt_id':'attempt','code_sha':'b'*40,'result_state':'completed',
        'exit_code':0,'path':'artefacts/diagnostic.json','sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),
        'classification_sha256':diagnostic['classification_sha256'],'failure_rows_sha256':diagnostic['failure_rows_sha256']}
    return manifest,new_payloads,c0a,c0b,diagnostic,metadata_bytes,inventories


class CompleteTransportTests(unittest.TestCase):
    def run_fixture(self, mutation=None, stage_mode=False):
        manifest,payloads,c0a,c0b,diagnostic,metadata,inventory=full_fixture()
        if mutation: mutation(manifest,c0a,c0b,diagnostic,metadata,inventory)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); artifact=root/'art'; source_calls=[]; phases=[]
            def fetch_files(**kwargs):
                out=kwargs['out_dir']; out.mkdir(parents=True,exist_ok=True)
                if kwargs['prefix'].endswith('/diagnostic-parent/attempt'):
                    raw=core._canonical(diagnostic); (out/'diagnostic.json').write_bytes(raw)
                    return {**manifest['parent'],'files':[{'path':manifest['parent']['path'],'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)}]}
                policy=json.loads((artifact/transport.POLICY_NAME).read_bytes())
                self.assertFalse(policy['semantic_payload_reads_started'])
                self.assertEqual(policy['manifest'],manifest)
                source_calls.append(kwargs['prefix'])
                report=copy.deepcopy(inventory[kwargs['prefix']]); files=[]
                for remote,local in kwargs['selections']:
                    raw=payloads[(report['job_id'],report['attempt_id'],remote)]
                    (out/local).write_bytes(raw)
                    files.append({'path':remote,'local_name':local,'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)})
                return {**report,'files':files}
            with mock.patch.object(transport.c0c,'fetch_parent',return_value=(c0a,c0b)), \
                 mock.patch.object(transport.fetch,'fetch_files',side_effect=fetch_files), \
                 mock.patch.object(transport.fetch,'inspect_result_inventory',side_effect=lambda **kw:copy.deepcopy(inventory[kw['prefix']])), \
                 mock.patch.object(transport.fetch.base,'remote_bytes',side_effect=lambda _bin,path:metadata[path]):
                if mutation:
                    with self.assertRaises(core.ExactLinkageError):
                        transport.build_diagnostic(manifest,'a'*64,root/'work',artifact,time.monotonic()+30)
                    self.assertEqual(source_calls,[])
                    return
                if stage_mode:
                    control=root/'control'; (control/'specs').mkdir(parents=True)
                    manifest_path=control/'specs/frozen.json'; raw=core._canonical(manifest); manifest_path.write_bytes(raw)
                    env={'JASS_ARTEFACT_DIR':str(artifact),'JASS_RESULT_DIR':str(root/'result'),
                         'JASS_STAGE_SPEC':str(control/'specs/stage.json'),'LAUNCH_MODE':'rehearsal',
                         'EXACT_LINKAGE_MANIFEST_REL':'specs/frozen.json','EXPECTED_EXACT_LINKAGE_MANIFEST_SHA256':hashlib.sha256(raw).hexdigest()}
                    with mock.patch.dict(os.environ,env,clear=True): self.assertEqual(stage.main(),0)
                    result=json.loads((artifact/(core.OUTPUT_NAME+'.json')).read_bytes())
                    evidence=json.loads((artifact/'execution-evidence.json').read_bytes())
                    self.assertEqual(evidence['state'],'completed')
                    self.assertEqual(len(evidence['completed_phases']),5)
                    self.assertEqual(json.loads((artifact/'scientific-summary.json').read_bytes()),{k:result[k] for k in transport.SUMMARY_FIELDS})
                else:
                    result=transport.build_diagnostic(manifest,'a'*64,root/'work',artifact,time.monotonic()+30,
                        checkpoint=lambda name,event:phases.append((name,event)))
                    self.assertEqual(len(phases),8)
                self.assertEqual(len(source_calls),14)
                self.assertEqual(result['terminal'],'ED4_C0C_V7_BLOCKED_BY_INCOMPLETE_STRUCTURAL_COVERAGE')
                self.assertEqual(result['resolved_descriptor_count'],18)
                self.assertEqual(result['unresolved_descriptor_count'],3)
                self.assertEqual(result['read_ledger']['position_identity_records_read'],9)
                self.assertEqual(result['read_ledger']['position_identity_records_validated'],8)
                self.assertEqual(result['read_ledger']['forbidden_field_values_read'],0)
                self.assertNotIn('FORBIDDEN-TARGET-POISON',json.dumps(result))

    def test_full_726_metadata_21_aliases_four_cases_real_adapter(self): self.run_fixture()
    def test_complete_stage_with_runner_sanitized_environment(self): self.run_fixture(stage_mode=True)
    def test_changed_metadata_hash_blocks_before_source_transport(self):
        self.run_fixture(lambda m,a,b,d,raw,inv:raw.update({next(iter(raw)):b'drift'}))
    def test_missing_inventory_descriptor_blocks_before_source_transport(self):
        self.run_fixture(lambda m,a,b,d,raw,inv:inv[m['sources'][0]['prefix']].update(files=[]))
    def test_changed_alias_map_blocks_before_source_transport(self):
        self.run_fixture(lambda m,a,b,d,raw,inv:m['tsv_cases'][0]['aliases'].pop())

class TransportAdmissionTests(unittest.TestCase):
    def test_metadata_pin_failure_precedes_transport(self):
        with mock.patch.object(transport.c0c,"fetch_parent",side_effect=AssertionError("forbidden")), mock.patch.object(transport.fetch,"fetch_files",side_effect=AssertionError("forbidden")):
            with self.assertRaisesRegex(Exception,"metadata_parent_pins"):
                transport.validate_metadata({"parent":{},"c0a_sha256":"x","c0b_sha256":"y"},{},{},{})
    def test_deadline_precedes_transport(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(transport.c0c,"fetch_parent",side_effect=AssertionError("forbidden")), mock.patch.object(transport.fetch,"fetch_files",side_effect=AssertionError("forbidden")):
            with self.assertRaisesRegex(Exception,"deadline"):
                transport.build_diagnostic({},"0"*64,Path(td)/"work",Path(td)/"art",0.0)
    def test_production_stage_never_builds(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(stage,"build_diagnostic",side_effect=AssertionError("forbidden")) as build, mock.patch.dict(os.environ,{"JASS_ARTEFACT_DIR":str(Path(td)/"a"),"JASS_RESULT_DIR":str(Path(td)/"r"),"LAUNCH_MODE":"production"},clear=False):
            self.assertEqual(stage.main(),2)
        build.assert_not_called()

if __name__ == "__main__": unittest.main()
