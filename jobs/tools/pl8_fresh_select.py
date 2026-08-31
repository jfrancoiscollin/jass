#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Frozen target-blind selector for the PL8 8000-parent deep confirmation."""
from __future__ import annotations
import argparse, csv, hashlib, json, struct, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools.tb_frontier_symmetry_dedup import canonical_fingerprint
from jobs.tools.t3_f6_r0_select import fen_fingerprint, fen_rows, load_tsv_identities

SEED=2026103120
REC=38
PHASES=(("P0",30,40),("P1",20,29),("P2",12,19),("P3",9,11))
PER_PHASE=2000
TOTAL=8000

def phase(pieces:int)->str:
    for name,lo,hi in PHASES:
        if lo<=pieces<=hi:return name
    raise ValueError(f"pieces outside PL8 phases: {pieces}")

def load_jnnw(path:Path)->list[bytes]:
    raw=path.read_bytes()
    if len(raw)<8 or raw[:4]!=b'JNNW':raise ValueError('bad JNNW header')
    n=struct.unpack_from('<I',raw,4)[0]
    if len(raw)!=8+REC*n:raise ValueError('JNNW count/size drift')
    rows=[raw[8+i*REC:8+(i+1)*REC] for i in range(n)]
    if any(r[33:38]!=b'\0'*5 for r in rows):raise ValueError('filtered source target bytes nonzero')
    return rows

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--jnnw',type=Path,required=True);ap.add_argument('--meta',type=Path,required=True)
    ap.add_argument('--exclude-tsv',type=Path,action='append',default=[]);ap.add_argument('--exclude-fen',type=Path,action='append',default=[])
    ap.add_argument('--out-jnnw',type=Path,required=True);ap.add_argument('--out-tsv',type=Path,required=True);ap.add_argument('--report',type=Path,required=True)
    a=ap.parse_args(); records=load_jnnw(a.jnnw)
    with a.meta.open(newline='',encoding='utf-8') as f:
        meta=list(csv.DictReader(f,delimiter='\t'))
    req={'row_index','source_row_index','parent_fingerprint','parent_stm','pieces','legal_moves'}
    if not meta or not req.issubset(meta[0]):raise ValueError('PL8 filtered metadata drift')
    if len(meta)!=len(records) or [int(r['row_index']) for r in meta]!=list(range(len(meta))):raise ValueError('PL8 source alignment drift')
    excluded=set();sources={}
    for p in a.exclude_tsv:
        ids=load_tsv_identities(p);excluded.update(ids);sources[str(p)]=len(ids)
    for p in a.exclude_fen:
        ids={fen_fingerprint(f)[0] for f in fen_rows(p)};excluded.update(ids);sources[str(p)]=len(ids)
    unique={};excluded_occ=dups=0
    for i,r in enumerate(meta):
        lm=int(r['legal_moves']); pc=int(r['pieces']); stm=int(r['parent_stm'])
        if not 2<=lm<=16 or stm not in (0,1):raise ValueError('filter support drift')
        ph=phase(pc); canon=canonical_fingerprint(r['parent_fingerprint'])
        if canon in excluded:excluded_occ+=1;continue
        rank=hashlib.sha256(f'{SEED}:{canon}'.encode()).digest()
        candidate=(rank,canon,r['parent_fingerprint'],records[i],stm,pc,lm,int(r['source_row_index']))
        old=unique.get(canon)
        if old is None:unique[canon]=candidate
        else:
            dups+=1
            if (rank,r['parent_fingerprint'])<(old[0],old[2]):unique[canon]=candidate
    selected=[]
    support={}
    for name,lo,hi in PHASES:
        pool=sorted((x for x in unique.values() if lo<=x[5]<=hi),key=lambda x:(x[0],x[1]))
        support[name]=len(pool)
        if len(pool)<PER_PHASE:raise ValueError(f'PL8 fresh support insufficient {name}: {len(pool)}')
        selected.extend((name,x) for x in pool[:PER_PHASE])
    if len(selected)!=TOTAL:raise AssertionError(len(selected))
    ids=[x[1][1] for x in selected]
    if len(set(ids))!=TOTAL or set(ids)&excluded:raise ValueError('PL8 selected overlap')
    a.out_jnnw.parent.mkdir(parents=True,exist_ok=True);a.out_tsv.parent.mkdir(parents=True,exist_ok=True)
    with a.out_jnnw.open('wb') as j, a.out_tsv.open('w',newline='',encoding='utf-8') as t:
        j.write(b'JNNW'+struct.pack('<I',TOTAL));fields=['parent_id','canonical_fingerprint','parent_fingerprint','parent_stm','phase','pieces','legal_moves','source_row_index'];w=csv.DictWriter(t,fieldnames=fields,delimiter='\t',lineterminator='\n');w.writeheader()
        for pid,(ph,x) in enumerate(selected):
            _,canon,fp,rec,stm,pc,lm,src=x;j.write(rec);w.writerow({'parent_id':pid,'canonical_fingerprint':canon,'parent_fingerprint':fp,'parent_stm':stm,'phase':ph,'pieces':pc,'legal_moves':lm,'source_row_index':src})
    payload={'schema':'jass.pl8_fresh_selection.v1','verdict':'PL8_FRESH_SELECTION_READY','passed':True,'target_blind':True,'selection_seed':SEED,'selected_parents':TOTAL,'selected_by_phase':{p:PER_PHASE for p,_,_ in PHASES},'eligible_after_exclusion_by_phase':support,'canonicalization':'exact_plus_rotate180_colour_swap','excluded_unique':len(excluded),'excluded_occurrences':excluded_occ,'duplicate_occurrences':dups,'exclusion_sources':sources,'forbidden_overlap':0,'source_score_bytes_read':False,'source_wdl_bytes_read':False,'micro_labels_read':0,'deep_labels_read':0,'fits':0,'strength_games':0,'jnnw_sha256':hashlib.sha256(a.out_jnnw.read_bytes()).hexdigest(),'tsv_sha256':hashlib.sha256(a.out_tsv.read_bytes()).hexdigest()}
    a.report.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(payload,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
