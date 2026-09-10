#!/usr/bin/env python3
"""ED4 C0C V2: prospective recovery of one authenticated interrupted JNNW.

V1 remains unchanged and fail-closed. V2 differs only for the exact immutable
producer-1785 object identified by diagnostic 1909. That object has a zero
count placeholder, 3023 complete 38-byte records, and a 32-byte partial tail.
V2 authenticates path/job/attempt/SHA/size, decodes position identity from the
3023 complete records only, skips the final 5 target bytes of each record as
before, and discards the 32-byte incomplete tail. No other malformed JNNW is
salvaged.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import struct
from pathlib import Path

from jobs.tools import fetch_result_files
from jobs.tools import ed4_c0c_exclusion_union as v1

SCHEMA = 'jass.ed4.c0c_structural_exclusion_union.v2'
VERDICT = 'ED4_C0C_STRUCTURAL_EXCLUSION_UNION_READY_V2'
REC = 38
SALVAGE_JOB = 'cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1'
SALVAGE_ATTEMPT = '20260905T145718Z-d3657332'
SALVAGE_PATH = 'b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-1.jnnw'
SALVAGE_SHA256 = '730ee719a651e371c782afd1c1f29a4a95a2c81b2bfdf7f9748aab4d6d7cd576'
SALVAGE_SIZE = 114914
SALVAGE_COMPLETE_RECORDS = 3023
SALVAGE_PARTIAL_TAIL_BYTES = 32


def _parse_exact_interrupted_jnnw(path: Path) -> tuple[set[str], int, dict]:
    raw = path.read_bytes()
    if len(raw) != SALVAGE_SIZE or hashlib.sha256(raw).hexdigest() != SALVAGE_SHA256:
        raise v1.C0CError('v2_salvage_object_identity')
    if raw[:4] != b'JNNW' or len(raw) < 8:
        raise v1.C0CError('v2_salvage_header')
    declared = struct.unpack('<I', raw[4:8])[0]
    if declared != 0:
        raise v1.C0CError('v2_salvage_expected_zero_placeholder')
    body = raw[8:]
    complete, tail = divmod(len(body), REC)
    if complete != SALVAGE_COMPLETE_RECORDS or tail != SALVAGE_PARTIAL_TAIL_BYTES:
        raise v1.C0CError('v2_salvage_shape_mismatch')
    identities: set[str] = set()
    for i in range(complete):
        record = body[i * REC:(i + 1) * REC]
        identities.add(v1.canonical_from_position_bytes(record[:33]))
        # record[33:38] remains intentionally uninterpreted, exactly as V1.
    return identities, complete, {
        'declared_count': declared,
        'complete_records_recovered': complete,
        'partial_tail_bytes_discarded': tail,
        'policy': 'exact_authenticated_interrupted_jnnw_complete_prefix_v2',
    }


def _parse_candidate_v2(local_path: Path, desc: dict, job_id: str, attempt: str):
    exact = (
        job_id == SALVAGE_JOB and attempt == SALVAGE_ATTEMPT
        and desc.get('path') == SALVAGE_PATH
        and desc.get('sha256') == SALVAGE_SHA256
        and desc.get('size_bytes') == SALVAGE_SIZE
        and desc.get('kind') == 'jnnw'
    )
    if exact:
        ids, rows, recovery = _parse_exact_interrupted_jnnw(local_path)
        return ids, rows, 'position_identity_only_v2_salvaged_complete_prefix', recovery
    ids, rows, semantics = v1.parse_candidate(local_path, desc['kind'])
    return ids, rows, semantics, None


def build_union_v2(work: Path, artifact: Path) -> dict:
    if work.exists() or work.is_symlink():
        raise v1.C0CError('work_dir_must_not_exist')
    work.mkdir(parents=True)
    artifact.mkdir(parents=True, exist_ok=True)
    c0a, c0b = v1.fetch_parent(work)
    sources = {x['job_id']: x for x in c0a.get('sources', [])}
    all_ids: set[str] = set()
    file_receipts: list[dict] = []
    total_rows = 0
    downloaded = 0
    zero_size_authenticated = 0
    salvage_count = 0

    for job in c0b.get('candidate_jobs', []):
        job_id, attempt = job['job_id'], job.get('attempt_id')
        candidates = job.get('candidate_files', [])
        if not candidates:
            continue
        source = sources.get(job_id)
        if not source or source.get('attempt_id') != attempt:
            raise v1.C0CError('c0a_c0b_identity_mismatch')
        state = source.get('result_state')
        if state not in {'completed', 'failed'}:
            raise v1.C0CError('candidate_result_state')
        prefix = f'r2:jass-data/runs/{job_id}/{attempt}'
        local = work / ('job-' + hashlib.sha256(job_id.encode()).hexdigest()[:12])

        nonempty, zero_receipts = v1._authenticate_candidate_descriptors(
            prefix=prefix, state=state, job_id=job_id, attempt=attempt, candidates=candidates,
        )
        file_receipts.extend(zero_receipts)
        zero_size_authenticated += len(zero_receipts)
        if not nonempty:
            continue

        selections = [(desc['path'], f'{i:04d}-{Path(desc["path"]).name}') for i, desc in nonempty]
        fetched = fetch_result_files.fetch_files(
            rclone='rclone', prefix=prefix, expected_state=state,
            selections=selections, out_dir=local,
        )
        if fetched.get('job_id') != job_id or fetched.get('attempt_id') != attempt:
            raise v1.C0CError('download_identity')
        fetched_map = {x['path']: x for x in fetched['files']}
        for i, desc in nonempty:
            got = fetched_map.get(desc['path'])
            if not got or got['sha256'] != desc['sha256'] or got['size_bytes'] != desc['size_bytes']:
                raise v1.C0CError('descriptor_drift')
            path = local / f'{i:04d}-{Path(desc["path"]).name}'
            ids, rows, semantics, recovery = _parse_candidate_v2(path, desc, job_id, attempt)
            all_ids.update(ids)
            total_rows += rows
            downloaded += 1
            receipt = {
                'job_id': job_id, 'attempt_id': attempt, 'path': desc['path'],
                'kind': desc['kind'], 'sha256': desc['sha256'], 'rows': rows,
                'unique_identities': len(ids), 'semantics': semantics,
            }
            if recovery is not None:
                receipt['recovery'] = recovery
                salvage_count += 1
            file_receipts.append(receipt)
            path.unlink(missing_ok=True)
        shutil.rmtree(local, ignore_errors=True)

    if salvage_count != 1:
        raise v1.C0CError('v2_exact_salvage_count')
    if not all_ids:
        raise v1.C0CError('empty_exclusion_union')
    union_raw = ('\n'.join(sorted(all_ids)) + '\n').encode('ascii')
    union_path = artifact / 'ed4-c0c-structural-exclusion-union.txt'
    union_path.write_bytes(union_raw)
    manifest = {
        'schema': SCHEMA, 'state': 'completed', 'verdict': VERDICT,
        'protocol_change': 'prospective_v2_exact_complete_record_salvage_authorized_2026-09-10',
        'parent_job_id': v1.PARENT_JOB, 'parent_attempt_id': v1.PARENT_ATTEMPT,
        'parent_c0a_sha256': v1.C0A_SHA, 'parent_c0b_sha256': v1.C0B_SHA,
        'candidate_files_downloaded': downloaded,
        'candidate_zero_size_authenticated': zero_size_authenticated,
        'candidate_rows_parsed': total_rows,
        'salvaged_files': salvage_count,
        'salvaged_complete_records': SALVAGE_COMPLETE_RECORDS,
        'discarded_partial_tail_bytes': SALVAGE_PARTIAL_TAIL_BYTES,
        'unique_canonical_identities': len(all_ids),
        'union_sha256': hashlib.sha256(union_raw).hexdigest(),
        'union_size_bytes': len(union_raw),
        'target_fields_decoded': 0, 'score_reads': 0, 'wdl_reads': 0,
        'qvalue_reads': 0, 'model_reads': 0, 'teacher_calls': 0,
        'search_calls': 0, 'fits': 0, 'games': 0, 'alpha_spent': 0,
        'confirmation_authorized': False, 'automatic_continuation': False,
        'files': file_receipts,
    }
    (artifact / 'ed4-c0c-structural-exclusion-manifest.json').write_text(
        json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8'
    )
    return manifest
