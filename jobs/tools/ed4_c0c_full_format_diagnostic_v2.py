#!/usr/bin/env python3
"""V2 of the bounded C0C format diagnostic.

V1 remains immutable.  V2 adds only an explicit, finite classification of
position/FEN leaf-validation failures raised by the existing canonicalizer.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path

from jobs.tools import ed4_c0c_full_format_diagnostic as base
from jobs.tools import ed4_c0c_exclusion_union as v1
from jobs.tools import ed4_c0c_exclusion_union_v5 as v5
from jobs.tools import ed4_c0c_exclusion_union_v6 as v6
from jobs.tools import fetch_result_files
from jobs.tools.adaptive_sibling_b2_exclusions import ContractError

SCHEMA = 'jass.ed4.c0c_full_format_diagnostic.v2'
RUNTIME_MAX_SECONDS = 2100
OUTER_BUDGET_SECONDS = 2700
EXPECTED_DESCRIPTORS = 726
EXPECTED_RECOVERY_ROWS = 231
EXPECTED_ZERO_DESCRIPTORS = 6

_EXACT_LEAF_CONTRACT_CODES = {
    'parent fingerprint STM is not 0 or 1': 'position_stm_invalid',
    'parent fingerprint bitboard outside 50 squares': 'position_bitboard_out_of_range',
    'parent fingerprint has overlapping pieces': 'position_overlapping_pieces',
    'FEN must contain exactly one W and one B field': 'fen_colour_fields',
    'FEN must contain one W piece field': 'fen_piece_field',
    'FEN must contain one B piece field': 'fen_piece_field',
    'FEN contains an empty square token': 'fen_empty_square_token',
    'FEN has a square occupied by both colours': 'fen_cross_colour_overlap',
}
_PREFIX_LEAF_CONTRACT_CODES = (
    ('bad parent fingerprint: ', 'position_fingerprint_syntax'),
    ('bad Jass FEN: ', 'fen_syntax'),
    ('bad FEN square token: ', 'fen_square_token'),
    ('bad FEN range: ', 'fen_range'),
    ('FEN square/range outside 1..50: ', 'fen_square_out_of_range'),
)
_DUPLICATE_FEN = re.compile(r'duplicate FEN square (?:[1-9]|[1-4][0-9]|50)\Z')


def _normalize_leaf_contract_error(exc: ContractError) -> str:
    message = str(exc)
    if message in _EXACT_LEAF_CONTRACT_CODES:
        return _EXACT_LEAF_CONTRACT_CODES[message]
    for prefix, code in _PREFIX_LEAF_CONTRACT_CODES:
        if message.startswith(prefix): return code
    if _DUPLICATE_FEN.fullmatch(message): return 'fen_duplicate_square'
    raise exc


def _diagnose_one(path: Path, desc: dict, job_id: str, attempt: str, allow: dict,
                  v5_allow: dict, deadline: float | None) -> dict:
    base._deadline(deadline, 'parse')
    key = (job_id, attempt, desc['path'])
    text = base._text_geometry(path, desc['kind']) if desc['kind'] in base.TEXT_KINDS or desc['kind'].endswith('_tsv') else None
    try:
        frozen = allow.get(key)
        if frozen is not None and frozen['partial_tail_bytes_from_size'] != 0:
            result = v5._salvage(path, desc, job_id, attempt, v5_allow)
            if result is None: base._error('v5_allowlist_identity')
            _ids, rows, _receipt = result
            return base._row(desc, job_id, attempt, 'v5-partial-recovery-pass', rows, geometry=text, recovery='v5')
        if frozen is not None:
            _ids, rows, _receipt = v6._parse_aligned(path, desc, frozen, deadline)
            return base._row(desc, job_id, attempt, 'v6-aligned-recovery-pass', rows, geometry=text, recovery='v6')
        _ids, rows, _semantics = v1.parse_candidate(path, desc['kind'])
        return base._row(desc, job_id, attempt, 'strict-v1-pass', rows, geometry=text)
    except v1.C0CError as exc:
        return base._row(desc, job_id, attempt, base._normalized_error(exc), None, geometry=text)
    except ContractError as exc:
        return base._row(desc, job_id, attempt, _normalize_leaf_contract_error(exc), None, geometry=text)


def build_diagnostic(work: Path, artifact: Path, deadline: float | None = None, checkpoint=None) -> dict:
    if work.exists() or work.is_symlink(): base._error('work_dir_must_not_exist')
    work.mkdir(parents=True); artifact.mkdir(parents=True, exist_ok=True)
    if checkpoint: checkpoint('authenticate-1927-recovery-partition', 'begin')
    inventory, readout, _meta = v6._load_1927(work, deadline)
    allow, _partitions, digests = v6.validate_1927(inventory, readout)
    if len(allow) != EXPECTED_RECOVERY_ROWS: base._error('recovery_partition_cardinality')
    if checkpoint: checkpoint('authenticate-1927-recovery-partition', 'complete')
    v5_allow = {key: {'sha256': row['sha256'], 'size_bytes': row['size_bytes'], 'complete': row['complete_records_from_size'], 'tail': row['partial_tail_bytes_from_size']} for key, row in allow.items() if row['partial_tail_bytes_from_size'] != 0}
    if checkpoint: checkpoint('authenticate-c0a-c0b-descriptor-universe', 'begin')
    c0a, c0b = v1.fetch_parent(work / 'parent')
    if checkpoint: checkpoint('authenticate-c0a-c0b-descriptor-universe', 'complete')
    sources = {x.get('job_id'): x for x in c0a.get('sources', []) if isinstance(x, dict)}
    rows=[]; descriptor_keys=set(); encountered=set(); zero_count=0
    if checkpoint: checkpoint('authenticate-and-classify-every-descriptor', 'begin')
    for job in c0b.get('candidate_jobs', []):
        base._deadline(deadline, 'metadata')
        if not isinstance(job, dict) or not isinstance(job.get('job_id'), str) or not isinstance(job.get('attempt_id'), str): base._error('candidate_job_shape')
        job_id, attempt, candidates = job['job_id'], job['attempt_id'], job.get('candidate_files')
        if not isinstance(candidates, list): base._error('candidate_files_shape')
        source=sources.get(job_id)
        if not source or source.get('attempt_id') != attempt or source.get('result_state') not in {'completed','failed'}: base._error('c0a_c0b_identity')
        for item in candidates:
            desc=base._validate_descriptor(item); key=(job_id,attempt,desc['path'])
            if key in descriptor_keys: base._error('duplicate_descriptor')
            descriptor_keys.add(key)
        nonempty, zeros=v1._authenticate_candidate_descriptors(prefix=f'r2:jass-data/runs/{job_id}/{attempt}',state=source['result_state'],job_id=job_id,attempt=attempt,candidates=candidates)
        for zero in zeros:
            desc=next(d for d in candidates if d['path']==zero['path'])
            if desc['size_bytes'] != 0 or desc['sha256'] != v1.EMPTY_SHA256: base._error('zero_descriptor_identity')
            rows.append(base._row(desc,job_id,attempt,'zero-byte',0)); zero_count += 1
        if not nonempty: continue
        local=work/('job-'+hashlib.sha256((job_id+attempt).encode()).hexdigest()[:16])
        fetched=fetch_result_files.fetch_files(rclone='rclone',prefix=f'r2:jass-data/runs/{job_id}/{attempt}',expected_state=source['result_state'],selections=[(d['path'],f'{i:04d}-{Path(d["path"]).name}') for i,d in nonempty],out_dir=local)
        if (fetched.get('job_id'),fetched.get('attempt_id'),fetched.get('result_state')) != (job_id,attempt,source['result_state']): base._error('fetch_identity')
        if source.get('code_sha') is not None and fetched.get('code_sha') != source['code_sha']: base._error('fetch_code_identity')
        fmap={x.get('path'):x for x in fetched.get('files',[]) if isinstance(x,dict)}
        if len(fetched.get('files',[])) != len(nonempty) or set(fmap) != {d['path'] for _,d in nonempty}: base._error('fetch_descriptor_set')
        for i,desc in nonempty:
            base._deadline(deadline,'source'); got=fmap.get(desc['path'])
            if not got or got.get('sha256') != desc['sha256'] or got.get('size_bytes') != desc['size_bytes']: base._error('descriptor_drift')
            key=(job_id,attempt,desc['path']); rows.append(_diagnose_one(local/f'{i:04d}-{Path(desc["path"]).name}',desc,job_id,attempt,allow,v5_allow,deadline))
            if key in allow: encountered.add(key)
        shutil.rmtree(local,ignore_errors=True)
    if checkpoint: checkpoint('authenticate-and-classify-every-descriptor','complete')
    if len(descriptor_keys) != EXPECTED_DESCRIPTORS or len(rows) != EXPECTED_DESCRIPTORS: base._error('descriptor_universe_cardinality')
    row_keys={(r['job_id'],r['attempt_id'],r['path']) for r in rows}
    if len(row_keys) != len(rows) or row_keys != descriptor_keys: base._error('classification_descriptor_set')
    if zero_count != EXPECTED_ZERO_DESCRIPTORS: base._error('zero_descriptor_cardinality')
    if encountered != set(allow) or len(encountered) != EXPECTED_RECOVERY_ROWS: base._error('recovery_encounter_cardinality')
    if checkpoint: checkpoint('verify-complete-deterministic-classification','begin')
    rows.sort(key=lambda r:(r['job_id'],r['attempt_id'],r['path']))
    canonical=json.dumps(rows,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()+b'\n'; failures=[r for r in rows if not r['outcome'].endswith('pass') and r['outcome']!='zero-byte']; failure_raw=json.dumps(failures,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()+b'\n'
    if checkpoint: checkpoint('verify-complete-deterministic-classification','complete')
    base._deadline(deadline,'publication')
    result={'schema':SCHEMA,'state':'completed','classification':'TECHNICAL_FORMAT_DIAGNOSTIC_ONLY','parent_job_id':v1.PARENT_JOB,'parent_attempt_id':v1.PARENT_ATTEMPT,'parent_c0a_sha256':v1.C0A_SHA,'parent_c0b_sha256':v1.C0B_SHA,**digests,'descriptor_count':len(rows),'recovery_descriptor_count':len(encountered),'classification_sha256':hashlib.sha256(canonical).hexdigest(),'failure_rows_sha256':hashlib.sha256(failure_raw).hexdigest(),'failure_row_count':len(failures),'actual_position_identity_reads':None,'actual_position_identity_reads_measurement':'not_measured','successful_position_rows':sum(r['successful_position_rows'] or 0 for r in rows),'target_fields_decoded':0,'target_reads':0,'score_reads':0,'wdl_reads':0,'qvalue_reads':0,'model_reads':0,'teacher_calls':0,'search_calls':0,'fits':0,'games':0,'alpha_spent':0,'scientific_verdict':None,'confirmation_authorized':False,'automatic_continuation':False,'rows':rows}
    if checkpoint: checkpoint('publish-format-diagnostic','begin')
    (artifact/'ed4-c0c-full-format-diagnostic-v2.json').write_text(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
    if checkpoint: checkpoint('publish-format-diagnostic','complete')
    return result
