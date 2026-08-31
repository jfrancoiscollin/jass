#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single-scan target-blind MegaCorpus selector for PL8 anchor and fresh confirmation."""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,sqlite3,struct
from pathlib import Path
from jobs.tools import deep_sibling_catalog_select as base
from jobs.tools.t3_f6_r0_select import fen_fingerprint,fen_rows

ANCHOR_SEED=2026103102
FRESH_SEED=2026103120
PHASES=(('P0',30,40),('P1',20,29),('P2',12,19),('P3',9,11))

def open_text(p:Path):return gzip.open(p,'rt',encoding='utf-8',newline='') if p.suffix=='.gz' else p.open(newline='',encoding='utf-8')
def load_tsv(paths):
    out=set();counts={}
    for p in paths:
        n=0
        with open_text(p) as f:
            rd=csv.DictReader(f,delimiter='\t');fields=rd.fieldnames or []
            key='canonical_fingerprint' if 'canonical_fingerprint' in fields else ('parent_canonical' if 'parent_canonical' in fields else None)
            if key is None:raise ValueError(f'{p}: no canonical identity field')
            for r in rd:
                v=(r.get(key) or '').strip()
                if v:out.add(v);n+=1
        counts[str(p)]=n
    return out,counts
def load_fens(paths):
    out=set();counts={}
    for p in paths:
        ids={fen_fingerprint(f)[0] for f in fen_rows(p)};out.update(ids);counts[str(p)]=len(ids)
    return out,counts
def h(seed:int,canon:str)->str:return hashlib.sha256(f'{seed}:{canon}'.encode()).hexdigest()
def write_jnnw(path,rows):
    with path.open('wb') as f:
        f.write(b'JNNW'+struct.pack('<I',len(rows)))
        for r in rows:f.write(r['record'])
def write_meta(path,rows):
    fields=['parent_id','canonical_fingerprint','parent_fingerprint','parent_stm','phase','pieces','legal_moves','source_identity','source_path','source_row_index']
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter='\t',lineterminator='\n');w.writeheader()
        for i,r in enumerate(rows):w.writerow({'parent_id':i,'canonical_fingerprint':r['canonical'],'parent_fingerprint':r['raw_fp'],'parent_stm':r['stm'],'phase':r['phase'],'pieces':r['pieces'],'legal_moves':r['legal_moves'],'source_identity':r['source_identity'],'source_path':r['source_path'],'source_row_index':r['source_row_index']})

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--catalog',type=Path,required=True);ap.add_argument('--parent-filter',type=Path,required=True);ap.add_argument('--work-dir',type=Path,required=True);ap.add_argument('--db',type=Path,required=True);ap.add_argument('--exclude-tsv',type=Path,action='append',default=[]);ap.add_argument('--exclude-fen',type=Path,action='append',default=[]);ap.add_argument('--anchor-jnnw',type=Path,required=True);ap.add_argument('--anchor-tsv',type=Path,required=True);ap.add_argument('--fresh-jnnw',type=Path,required=True);ap.add_argument('--fresh-tsv',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--source-report',type=Path,required=True);ap.add_argument('--progress',type=Path);ap.add_argument('--rclone-binary',default='rclone');a=ap.parse_args()
    blocked,tc=load_tsv(a.exclude_tsv);bf,fc=load_fens(a.exclude_fen);blocked.update(bf)
    orig=base.merge_occurrence;stats={'excluded_occurrences':0,'accepted_occurrences':0}
    def guarded(db,**kw):
        if kw['canonical'] in blocked:stats['excluded_occurrences']+=1;return False,False
        stats['accepted_occurrences']+=1;return orig(db,**kw)
    base.merge_occurrence=guarded;base.PHASES={p:(lo,hi,0) for p,lo,hi in PHASES}
    a.anchor_jnnw.parent.mkdir(parents=True,exist_ok=True);a.fresh_jnnw.parent.mkdir(parents=True,exist_ok=True)
    tmpj=a.work_dir/'unused.jnnw';tmpt=a.work_dir/'unused.tsv';tmpr=a.work_dir/'base-report.json'
    ns=argparse.Namespace(catalog=a.catalog,parent_filter=a.parent_filter,work_dir=a.work_dir/'scan',db=a.db,output_jnnw=tmpj,output_tsv=tmpt,report=tmpr,source_report=a.source_report,progress=a.progress,sample_seed=ANCHOR_SEED,split_seed=2026083102,rclone_binary=a.rclone_binary,copy_timeout_seconds=3600,verify_declared_sha=True)
    base.run(ns)
    db=sqlite3.connect(a.db);db.row_factory=sqlite3.Row;db.execute('ALTER TABLE parents ADD COLUMN anchor_hash TEXT');db.execute('ALTER TABLE parents ADD COLUMN fresh_hash TEXT')
    cur=db.execute('SELECT canonical FROM parents');batch=[]
    for (canon,) in cur:
        batch.append((h(ANCHOR_SEED,canon),h(FRESH_SEED,canon),canon))
        if len(batch)>=10000:db.executemany('UPDATE parents SET anchor_hash=?,fresh_hash=? WHERE canonical=?',batch);db.commit();batch=[]
    if batch:db.executemany('UPDATE parents SET anchor_hash=?,fresh_hash=? WHERE canonical=?',batch);db.commit()
    anchor=list(db.execute('SELECT * FROM parents ORDER BY anchor_hash,canonical LIMIT 500000'))
    if len(anchor)!=500000:raise ValueError(f'PL8 anchor support {len(anchor)} !=500000')
    fresh=[];available={}
    for ph,lo,hi in PHASES:
        available[ph]=db.execute('SELECT COUNT(*) FROM parents WHERE phase=?',(ph,)).fetchone()[0]
        rows=list(db.execute('SELECT * FROM parents WHERE phase=? ORDER BY fresh_hash,canonical LIMIT 2000',(ph,)))
        if len(rows)!=2000:raise ValueError(f'PL8 fresh support {ph}={len(rows)}')
        fresh.extend(rows)
    write_jnnw(a.anchor_jnnw,anchor);write_meta(a.anchor_tsv,anchor);write_jnnw(a.fresh_jnnw,fresh);write_meta(a.fresh_tsv,fresh)
    aid={r['canonical'] for r in anchor};fid={r['canonical'] for r in fresh}
    payload={'schema':'jass.pl8_catalog_selection.v1','verdict':'PL8_TARGET_BLIND_SELECTION_READY','passed':True,'catalog_sha256':hashlib.sha256(a.catalog.read_bytes()).hexdigest(),'anchor_seed':ANCHOR_SEED,'anchor_states':500000,'fresh_seed':FRESH_SEED,'fresh_parents':8000,'fresh_by_phase':{p:2000 for p,_,_ in PHASES},'eligible_by_phase':available,'canonicalization':'exact_plus_rotate180_colour_swap','excluded_unique':len(blocked),'excluded_occurrences':stats['excluded_occurrences'],'exclusion_tsv_rows':tc,'exclusion_fen_unique':fc,'anchor_fresh_overlap_target_blind':len(aid&fid),'source_score_bytes_read':False,'source_wdl_bytes_read':False,'teacher_scores_read':0,'deep_labels_read':0,'fits':0,'strength_games':0,'promotion_authorized':False,'anchor_jnnw_sha256':hashlib.sha256(a.anchor_jnnw.read_bytes()).hexdigest(),'fresh_jnnw_sha256':hashlib.sha256(a.fresh_jnnw.read_bytes()).hexdigest(),'fresh_tsv_sha256':hashlib.sha256(a.fresh_tsv.read_bytes()).hexdigest()}
    a.report.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');db.close();print(json.dumps(payload,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
