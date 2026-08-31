#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2] if len(Path(__file__).resolve().parents) >= 3 else Path.cwd()
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools.t3_f6_r0_select import fen_fingerprint, fen_rows, load_tsv_identities
CANDIDATES=30000; OPENINGS=1350; SELECT_SEED=2026100102; EXEC_SEED=2026100104
CELLS=(('C1',750),('C2',400),('C3',200))
def rank_key(seed:int, canonical:str): return (hashlib.sha256(f"{seed}:{canonical}".encode()).digest(), canonical)
def build(candidates:list[str], excluded:set[str]):
    unique={}; dup=overlap=0
    for fen in candidates:
        canonical,_=fen_fingerprint(fen)
        if canonical in excluded: overlap+=1; continue
        if canonical in unique: dup+=1; unique[canonical]=min(unique[canonical],fen)
        else: unique[canonical]=fen
    ranked=sorted(unique.items(), key=lambda x:rank_key(SELECT_SEED,x[0]))
    selected=ranked[:OPENINGS]
    if len(selected)!=OPENINGS: raise ValueError('E2 fresh support below 1350')
    cells={}; offset=0
    for name,n in CELLS:
        block=selected[offset:offset+n]; offset+=n
        block=sorted(block,key=lambda x:rank_key(EXEC_SEED,x[0]))
        cells[name]=block
    return cells, len(unique), dup, overlap

def main():
    p=argparse.ArgumentParser(); p.add_argument('--candidates',type=Path,required=True); p.add_argument('--exclude-fen',type=Path,action='append',default=[]); p.add_argument('--exclude-tsv',type=Path,action='append',default=[]); p.add_argument('--out-c1',type=Path,required=True); p.add_argument('--out-c2',type=Path,required=True); p.add_argument('--out-c3',type=Path,required=True); p.add_argument('--manifest',type=Path,required=True); p.add_argument('--report',type=Path,required=True); a=p.parse_args()
    candidates=fen_rows(a.candidates)
    if len(candidates)!=CANDIDATES: raise ValueError(f'E2 candidate cardinality {len(candidates)} != {CANDIDATES}')
    excluded=set(); sources={}
    for path in a.exclude_fen:
        ids={fen_fingerprint(f)[0] for f in fen_rows(path)}; excluded.update(ids); sources[str(path)]=len(ids)
    for path in a.exclude_tsv:
        ids=load_tsv_identities(path); excluded.update(ids); sources[str(path)]=len(ids)
    cells,unique_n,dups,overlap=build(candidates,excluded)
    outs={'C1':a.out_c1,'C2':a.out_c2,'C3':a.out_c3}
    seen=set(); manifest=[]; selection_rank={c:i for i,(c,_) in enumerate(sorted([(c,f) for rows in cells.values() for c,f in rows],key=lambda x:rank_key(SELECT_SEED,x[0])))}
    for name,n in CELLS:
        rows=cells[name]; assert len(rows)==n
        ids={c for c,_ in rows}
        if ids & seen: raise ValueError('E2 inter-cell overlap')
        if ids & excluded: raise ValueError('E2 forbidden overlap')
        seen |= ids
        outs[name].write_text('\n'.join(f for _,f in rows)+'\n',encoding='utf-8')
        for exec_index,(canonical,fen) in enumerate(rows): manifest.append({'cell':name,'selection_rank':selection_rank[canonical],'execution_index':exec_index,'canonical_identity':canonical,'fen':fen})
    a.manifest.write_text('\n'.join(json.dumps(r,sort_keys=True) for r in manifest)+'\n',encoding='utf-8')
    report={'schema':'jass.t3_f6_e2_fresh_pool.v1','verdict':'E2_FRESH_POOL_READY','passed':True,'candidate_records':len(candidates),'candidate_sha256':hashlib.sha256(a.candidates.read_bytes()).hexdigest(),'generation_seed':2026100101,'selection_seed':SELECT_SEED,'execution_seed':EXEC_SEED,'selection_order':'SHA256("2026100102:" + canonical_identity)','execution_order':'per-cell SHA256("2026100104:" + canonical_identity)','canonicalization':'exact_plus_rotate180_colour_swap','selected_openings':OPENINGS,'cells':{name:{'openings':n,'games':2*n,'sha256':hashlib.sha256(outs[name].read_bytes()).hexdigest()} for name,n in CELLS},'unique_after_exclusion':unique_n,'duplicates_removed':dups,'excluded_occurrences':overlap,'excluded_unique':len(excluded),'excluded_sources':sources,'forbidden_overlap':0,'inter_cell_overlap':0,'manifest_sha256':hashlib.sha256(a.manifest.read_bytes()).hexdigest(),'score_reads':0,'wdl_reads':0,'deep_label_reads':0}
    a.report.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(report,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
