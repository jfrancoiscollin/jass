"""Complete candidate-building fixture: inputs -> fit -> native reload -> seal.

Pure tests use a deterministic native-I/O stand-in. Dedicated CI separately runs
this same fixture with the real compiled C++ probe; CPX rehearsal uses real R2
inputs and the authenticated CPX binary. None substitutes for another.
"""
from __future__ import annotations
from contextlib import ExitStack
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from jobs.tools import ed4_choice_value_fit as p
from jobs.tools import ed3_label_pressure as audit
from jobs.tools import ed2_value_math as native
from jobs.tools.launch_runtime_v2 import atomic_json


def synthetic_probe(binary,data,model,out):
    rows=p.ep.records(data);n=len(rows)
    raw=np.zeros((n,120));ph=np.empty(n)
    for i,r in enumerate(rows):
        wm,wk,bm,bk,stm=p.ep.values(r)
        raw[i,0]=wk.bit_count();raw[i,49]=bool(wk & (1<<45))
        raw[i,100:106]=[wm.bit_count(),bm.bit_count(),wm%7,bm%7,wm%11,bm%11]
        ph[i]=(wm%5)/4
    x=np.hstack((raw*ph[:,None],raw*(1-ph[:,None])))
    _,_,weights=native.read_model(model)
    z=x@weights;sign=np.array([1 if r[32] else -1 for r in rows])
    cp=np.clip(np.trunc(sign*z*100),-20000,20000).astype(int)
    table=np.column_stack((np.arange(n),z,cp,ph,raw))
    np.savetxt(out,table,delimiter='\t',header='fixture',comments='',fmt='%.17g')
    return native.native_table(out,n)


def fixture_run(result,art,mode='rehearsal',real_probe=None,corrupt=None,prerequisite=None):
    result.mkdir(parents=True,exist_ok=True);art.mkdir(parents=True,exist_ok=True)
    store=result/'fixture-inputs';store.mkdir()
    roots={k:store/k for k in ('p0','n1','base','target')}
    for root in roots.values():root.mkdir()
    p0,n1,base,target=(roots[k] for k in ('p0','n1','base','target'))
    (p0/'source').mkdir();(n1/'native').mkdir();(n1/'build-outputs').mkdir()
    if real_probe is not None:
        import subprocess
        npat,ne=map(int,subprocess.check_output([str(real_probe),'--layout'],text=True).split())
        assert ne==120
        binary_bytes=Path(real_probe).read_bytes();probe=p.run_probe
    else:npat=5;binary_bytes=b'fixture-native-io';probe=synthetic_probe
    model=struct.pack('<5I',0x57544a50,3,1000,npat,120)+np.zeros(2*(npat+120),dtype='<i4').tobytes()
    bh=hashlib.sha256(model).hexdigest()
    (base/'WDL_CONTROL.pjtw.gz').write_bytes(gzip.compress(model,mtime=0))
    model_path=store/'base.pjtw';model_path.write_bytes(model)
    records=[]
    for i in range(96):
        wm=sum(1<<s for s in (30,32,37,40,44))
        bm=sum(1<<s for s in (1,3,7,10,13))
        # Legal-format board states; synthetic group ownership is not claimed
        # to be a real move trajectory. Real CPX uses authenticated source bytes.
        wk=1<<(45+(i//2)%2);bk=1<<(18+i%3)
        records.append(struct.pack('<QQQQBiB',wm,wk,bm,bk,i%2,0,0))
    p.write_records(p0/'source/children.jnnw',records)
    groups=[]
    for i in range(48):
        pid=i//2;groups.append(dict(row_index=2*i,parent_id=pid,parent_phase='P'+str(pid//6),
            parent_stm=pid%2,split='train',child_rule_terminal=0))
    with (p0/'source/groups.tsv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(groups[0]),delimiter='\t');writer.writeheader();writer.writerows(groups)
    atomic_json(p0/'ed2-source-seal.json',dict(files={name:audit.sha(p0/'source'/name)
            for name in ('groups.tsv','children.jnnw')}))
    source_hash=audit.sha(p0/'ed2-source-seal.json')
    for shard in range(8):
        with (n1/f'train-{shard}.jsonl').open('w') as out:
            for rid in range(shard,96,8):
                if rid%2: continue
                for budget in (5000,50000):out.write(json.dumps(dict(row=rid,budget=budget,
                    score=10 if ((rid%4==0)==bool((rid//4)%2)) else 0,terminal=False))+'\n')
    atomic_json(n1/'train-labels-sealed.json',dict(source_seal=source_hash,test_teacher_calls=0,
        teacher_files={name:audit.sha(n1/name) for name in audit.TRAIN_NAMES}))
    atomic_json(n1/'label-support.json',dict(fixture=True))
    p.write_records(n1/'replay.jnnw',records[:64])
    p.write_records(store/'selected-train.jnnw',[records[2*i] for i in range(48)])
    for name,data in [('train',store/'selected-train.jnnw'),('replay',n1/'replay.jnnw')]:
        plain=store/(name+'.tsv');probe(real_probe,data,model_path,plain)
        (n1/f'native/{name}-native.tsv.gz').write_bytes(gzip.compress(plain.read_bytes(),mtime=0))
    atomic_json(n1/'wdl-selection.json',dict(subsets={
        'replay':dict(indices=list(range(64)),data_sha256=audit.sha(n1/'replay.jnnw')),
        'wdl_holdout':dict(indices=[1800796,1800797])}))
    atomic_json(n1/'wdl-selection.seal.json',dict(sha256=audit.sha(n1/'wdl-selection.json')))
    yy=np.full(2000000,np.nan,dtype=np.float32);yy[:64]=.5
    tmp=store/'y.npy';np.save(tmp,yy,allow_pickle=False)
    (target/'current_2m-context30.npy.gz').write_bytes(gzip.compress(tmp.read_bytes(),mtime=0))
    archived=n1/'build-outputs/jass_ed2_value_probe.gz';archived.write_bytes(gzip.compress(binary_bytes,mtime=0))
    atomic_json(n1/'scratch-cleanup.json',dict(retained_binaries={'jass_ed2_value_probe':dict(
        sha256=hashlib.sha256(binary_bytes).hexdigest(),archive_sha256=audit.sha(archived))}))
    if corrupt is not None:corrupt(roots)
    identity_roots={audit.P0:p0,audit.N1:n1,audit.BASE:base,audit.TARGET:target}
    def downloader(identity,names,root,report):
        for name in names:
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(identity_roots[identity]/name,dest)
        atomic_json(report,dict(fixture_transport=True,names=names))
    with ExitStack() as stack:
        for key,value in dict(TRAIN_PARENTS=24,TRAIN_ROWS=48,TRAIN_PAIRS=24,REPLAY_N=64,
                              CELL_QUOTA=3,
                              MODEL_HASH=dict(BASE=bh,PARTIAL=p.MODEL_HASH['PARTIAL'],SOFT=p.MODEL_HASH['SOFT'])).items():
            stack.enter_context(patch.object(p,key,value))
        stack.enter_context(patch.object(audit,'SOURCE_SEAL',source_hash))
        if prerequisite is not None:
            dest=result/'launch-prerequisite';dest.mkdir()
            for name in p.OUTPUTS:shutil.copyfile(prerequisite/name,dest/name)
            atomic_json(result/'launch-prerequisite.json',dict(verdict='FULL_PIPELINE_REHEARSAL_PASS',published_roundtrip=True))
        return p.run(result,art,mode,downloader=downloader,probe=probe)


class CompleteFitTests(unittest.TestCase):
    def test_complete_rehearsal_fit_native_io_and_candidate_role(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);art=root/'artefacts';r=fixture_run(root,art)
            self.assertEqual(r['fits'],1);self.assertFalse(r['heldout_evaluation_performed'])
            self.assertEqual(r['actual_side_effects']['test_target_reads'],0)
            evidence=audit.load_json(art/'execution-evidence.json')
            self.assertEqual(evidence['completed_phases'],p.PHASES)
            self.assertEqual(evidence['actual_side_effects']['fits'],1)
            seal=audit.load_json(art/'candidate-seal.json')
            self.assertEqual(seal['role'],'development_only')
            self.assertFalse(seal['runtime_authorized'])
            self.assertEqual(seal['model_sha256'],audit.sha(art/'ED4_CHOICE.pjtw'))
            self.assertLessEqual(r['gradient_l2'],1e-6)
            self.assertGreater(audit.load_json(art/'fit-report.json')['quantization']['changed_extra_coefficients'],0)
            contract=audit.load_json(art/'train-contract.json')
            self.assertEqual(contract['ordered_original_row_ids'],list(range(0,96,2)))
            self.assertEqual(contract['target_values_dereferenced'],64)

    def test_bad_train_bytes_stop_before_optimizer_with_original_phase(self):
        def corrupt(roots):
            with (roots['n1']/'train-0.jsonl').open('a') as f:f.write('{}\n')
        with tempfile.TemporaryDirectory() as td,patch.object(p.math,'fit',side_effect=AssertionError('forbidden fit')):
            root=Path(td);art=root/'artefacts'
            with self.assertRaisesRegex(ValueError,'teacher_hash'):fixture_run(root,art,corrupt=corrupt)
            evidence=audit.load_json(art/'execution-evidence.json')
            self.assertEqual(evidence['phase'],'verify-inputs');self.assertEqual(evidence['state'],'failed')
            self.assertEqual(evidence['actual_side_effects']['fits'],0)
            self.assertFalse((art/'ED4_CHOICE.pjtw').exists())

    def test_teacher_allowlist_contains_no_test_or_holdout_values(self):
        self.assertFalse(any('test-' in p or 'holdout-native' in p or 'scientific-summary' in p for p in p.N1_NAMES))
        self.assertNotIn('wdl_holdout.jnnw',p.N1_NAMES)

    def test_both_modes_use_all_parents(self):
        groups=[dict(id=i,cell=str(i%8)) for i in range(512)]
        chosen=p.select_groups(groups,'rehearsal')
        self.assertIs(chosen,groups)
        self.assertIs(p.select_groups(groups,'production'),groups)

    def test_production_matches_authenticated_development_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);first=root/'first';second=root/'second'
            fixture_run(first,first/'artefacts')
            report=fixture_run(second,second/'artefacts',mode='production',prerequisite=first/'artefacts')
            self.assertEqual(report['verdict'],'ED4_CHOICE_SET_REAL_CANDIDATE_SEALED_V1')
            self.assertEqual((first/'artefacts/ED4_CHOICE.pjtw').read_bytes(),(second/'artefacts/ED4_CHOICE.pjtw').read_bytes())

    def test_production_without_rehearsal_fails_before_fit(self):
        with tempfile.TemporaryDirectory() as td,patch.object(p.math,'fit',side_effect=AssertionError('forbidden fit')):
            root=Path(td)
            with self.assertRaises(FileNotFoundError):fixture_run(root,root/'artefacts',mode='production')
            self.assertEqual(audit.load_json(root/'artefacts/execution-evidence.json')['actual_side_effects']['fits'],0)

    def test_replay_cannot_reference_holdout(self):
        def corrupt(roots):
            path=roots['n1']/'wdl-selection.json';value=audit.load_json(path)
            value['subsets']['replay']['indices'][0]=1800796
            atomic_json(path,value)
            atomic_json(roots['n1']/'wdl-selection.seal.json',{'sha256':audit.sha(path)})
        with tempfile.TemporaryDirectory() as td,patch.object(p.math,'fit',side_effect=AssertionError('forbidden fit')):
            root=Path(td)
            with self.assertRaisesRegex(ValueError,'replay_indices'):fixture_run(root,root/'artefacts',corrupt=corrupt)

if __name__=='__main__':unittest.main()
