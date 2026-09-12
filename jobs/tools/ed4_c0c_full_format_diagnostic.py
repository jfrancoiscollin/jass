#!/usr/bin/env python3
"""Bounded, target-free format classification for the frozen ED4 C0C universe.

This is deliberately a diagnostic, not an exclusion-union builder.  It uses the
existing V1 parsers and the frozen V5/V6 recovery partitions, but does not
retain identities between files or publish decoded identities.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

from jobs.tools import ed4_c0c_exclusion_union as v1
from jobs.tools import ed4_c0c_exclusion_union_v5 as v5
from jobs.tools import ed4_c0c_exclusion_union_v6 as v6
from jobs.tools import fetch_result_files

SCHEMA = 'jass.ed4.c0c_full_format_diagnostic.v1'
RUNTIME_MAX_SECONDS = 2100
OUTER_BUDGET_SECONDS = 2700
EXPECTED_DESCRIPTORS = 726
EXPECTED_RECOVERY_ROWS = 231
EXPECTED_ZERO_DESCRIPTORS = 6
TEXT_KINDS = {'fen', 'fen_gzip', 'identity_text', 'identity_text_gzip', 'tsv', 'fen_tsv', 'identity_tsv'}
KNOWN_PARSER_CODES = {'position_identity_width', 'jnnw_header', 'jnnw_truncated',
                      'jnnw_trailing_bytes', 'fen_empty', 'identity_empty',
                      'tsv_no_position_field', 'tsv_row_without_position', 'tsv_empty'}


def _error(code: str) -> None:
    raise v1.C0CError(code)


def _deadline(deadline: float | None, phase: str) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        _error('format_diagnostic_deadline_exceeded:' + phase)


def _normalized_error(exc: v1.C0CError) -> str:
    """Keep only the stable code portion; never publish input text or offsets."""
    message = str(exc)
    raw = message.split(':', 1)[0]
    if raw in KNOWN_PARSER_CODES:
        return raw
    if raw == 'unsupported_candidate_kind' and message.startswith('unsupported_candidate_kind:'):
        return raw
    raise exc


def _text_geometry(path: Path, kind: str) -> dict:
    compressed = kind.endswith('_gzip')
    opener = __import__('gzip').open if compressed else open
    physical = blank = comment = payload = 0
    try:
        with opener(path, 'rt', encoding='utf-8', newline='') as source:
            for raw in source:
                physical += 1
                stripped = raw.strip()
                if not stripped:
                    blank += 1
                elif stripped.startswith('#'):
                    comment += 1
                if raw.split('#', 1)[0].strip():
                    payload += 1
    except UnicodeDecodeError:
        return {'utf8_valid': False, 'physical_lines': None, 'blank_lines': None,
                'comment_lines': None, 'payload_lines_after_v1_comment_stripping': None}
    return {'utf8_valid': True, 'physical_lines': physical, 'blank_lines': blank,
            'comment_lines': comment, 'payload_lines_after_v1_comment_stripping': payload}


def _row(desc: dict, job_id: str, attempt: str, outcome: str, rows: int | None,
         *, geometry: dict | None = None, recovery: str | None = None) -> dict:
    value = {k: desc[k] for k in ('path', 'kind', 'sha256', 'size_bytes')}
    value.update({'job_id': job_id, 'attempt_id': attempt, 'parser_kind': desc['kind'],
                  'outcome': outcome, 'rows': rows,
                  'successful_position_rows': rows if outcome.endswith('pass') and rows is not None else None})
    if geometry is not None:
        value['text_geometry'] = geometry
    if recovery is not None:
        value['recovery_policy'] = recovery
    return value


def _validate_descriptor(desc: object) -> dict:
    if not isinstance(desc, dict): _error('descriptor_shape')
    for key in ('path', 'kind', 'sha256'):
        if not isinstance(desc.get(key), str) or not desc[key]: _error('descriptor_' + key)
    if not isinstance(desc.get('size_bytes'), int) or isinstance(desc['size_bytes'], bool) or desc['size_bytes'] < 0:
        _error('descriptor_size')
    return desc


def _diagnose_one(path: Path, desc: dict, job_id: str, attempt: str, allow: dict,
                  v5_allow: dict, deadline: float | None) -> dict:
    _deadline(deadline, 'parse')
    key = (job_id, attempt, desc['path'])
    text = _text_geometry(path, desc['kind']) if desc['kind'] in TEXT_KINDS or desc['kind'].endswith('_tsv') else None
    try:
        frozen = allow.get(key)
        if frozen is not None and frozen['partial_tail_bytes_from_size'] != 0:
            result = v5._salvage(path, desc, job_id, attempt, v5_allow)
            if result is None: _error('v5_allowlist_identity')
            _ids, rows, _receipt = result
            return _row(desc, job_id, attempt, 'v5-partial-recovery-pass', rows,
                        geometry=text, recovery='v5')
        if frozen is not None:
            _ids, rows, _receipt = v6._parse_aligned(path, desc, frozen, deadline)
            return _row(desc, job_id, attempt, 'v6-aligned-recovery-pass', rows,
                        geometry=text, recovery='v6')
        _ids, rows, _semantics = v1.parse_candidate(path, desc['kind'])
        return _row(desc, job_id, attempt, 'strict-v1-pass', rows, geometry=text)
    except v1.C0CError as exc:
        return _row(desc, job_id, attempt, _normalized_error(exc), None, geometry=text)


def build_diagnostic(work: Path, artifact: Path, deadline: float | None = None, checkpoint=None) -> dict:
    if work.exists() or work.is_symlink(): _error('work_dir_must_not_exist')
    work.mkdir(parents=True); artifact.mkdir(parents=True, exist_ok=True)
    if checkpoint: checkpoint('authenticate-1927-recovery-partition', 'begin')
    inventory, readout, _meta = v6._load_1927(work, deadline)
    allow, partitions, digests = v6.validate_1927(inventory, readout)
    if len(allow) != EXPECTED_RECOVERY_ROWS: _error('recovery_partition_cardinality')
    if checkpoint: checkpoint('authenticate-1927-recovery-partition', 'complete')
    v5_allow = {key: {'sha256': row['sha256'], 'size_bytes': row['size_bytes'],
                      'complete': row['complete_records_from_size'], 'tail': row['partial_tail_bytes_from_size']}
                for key, row in allow.items() if row['partial_tail_bytes_from_size'] != 0}
    if checkpoint: checkpoint('authenticate-c0a-c0b-descriptor-universe', 'begin')
    c0a, c0b = v1.fetch_parent(work / 'parent')
    if checkpoint: checkpoint('authenticate-c0a-c0b-descriptor-universe', 'complete')
    sources = {x.get('job_id'): x for x in c0a.get('sources', []) if isinstance(x, dict)}
    rows: list[dict] = []; descriptor_keys: set[tuple[str, str, str]] = set(); encountered: set[tuple[str, str, str]] = set(); zero_count = 0
    if checkpoint: checkpoint('authenticate-and-classify-every-descriptor', 'begin')
    for job in c0b.get('candidate_jobs', []):
        _deadline(deadline, 'metadata')
        if not isinstance(job, dict) or not isinstance(job.get('job_id'), str) or not isinstance(job.get('attempt_id'), str): _error('candidate_job_shape')
        job_id, attempt = job['job_id'], job['attempt_id']; candidates = job.get('candidate_files')
        if not isinstance(candidates, list): _error('candidate_files_shape')
        source = sources.get(job_id)
        if not source or source.get('attempt_id') != attempt or source.get('result_state') not in {'completed', 'failed'}: _error('c0a_c0b_identity')
        for item in candidates:
            desc = _validate_descriptor(item); key = (job_id, attempt, desc['path'])
            if key in descriptor_keys: _error('duplicate_descriptor')
            descriptor_keys.add(key)
        nonempty, zeros = v1._authenticate_candidate_descriptors(prefix=f'r2:jass-data/runs/{job_id}/{attempt}', state=source['result_state'], job_id=job_id, attempt=attempt, candidates=candidates)
        for zero in zeros:
            desc = next(d for d in candidates if d['path'] == zero['path'])
            if desc['size_bytes'] != 0 or desc['sha256'] != v1.EMPTY_SHA256: _error('zero_descriptor_identity')
            rows.append(_row(desc, job_id, attempt, 'zero-byte', 0))
            zero_count += 1
        if not nonempty: continue
        local = work / ('job-' + hashlib.sha256((job_id + attempt).encode()).hexdigest()[:16])
        selected = [(d['path'], f'{i:04d}-{Path(d["path"]).name}') for i, d in nonempty]
        fetched = fetch_result_files.fetch_files(rclone='rclone', prefix=f'r2:jass-data/runs/{job_id}/{attempt}', expected_state=source['result_state'], selections=selected, out_dir=local)
        if (fetched.get('job_id'), fetched.get('attempt_id'), fetched.get('result_state')) != (job_id, attempt, source['result_state']): _error('fetch_identity')
        if source.get('code_sha') is not None and fetched.get('code_sha') != source['code_sha']: _error('fetch_code_identity')
        fmap = {x.get('path'): x for x in fetched.get('files', []) if isinstance(x, dict)}
        if len(fetched.get('files', [])) != len(nonempty) or set(fmap) != {d['path'] for _, d in nonempty}: _error('fetch_descriptor_set')
        for i, desc in nonempty:
            _deadline(deadline, 'source')
            got = fmap.get(desc['path'])
            if not got or got.get('sha256') != desc['sha256'] or got.get('size_bytes') != desc['size_bytes']: _error('descriptor_drift')
            key = (job_id, attempt, desc['path']); row = _diagnose_one(local / f'{i:04d}-{Path(desc["path"]).name}', desc, job_id, attempt, allow, v5_allow, deadline)
            rows.append(row)
            if key in allow: encountered.add(key)
        shutil.rmtree(local, ignore_errors=True)
    if checkpoint: checkpoint('authenticate-and-classify-every-descriptor', 'complete')
    if len(descriptor_keys) != EXPECTED_DESCRIPTORS or len(rows) != EXPECTED_DESCRIPTORS: _error('descriptor_universe_cardinality')
    row_keys = [(r['job_id'], r['attempt_id'], r['path']) for r in rows]
    if len(set(row_keys)) != len(row_keys) or set(row_keys) != descriptor_keys: _error('classification_descriptor_set')
    if zero_count != EXPECTED_ZERO_DESCRIPTORS: _error('zero_descriptor_cardinality')
    if encountered != set(allow) or len(encountered) != EXPECTED_RECOVERY_ROWS: _error('recovery_encounter_cardinality')
    if checkpoint: checkpoint('verify-complete-deterministic-classification', 'begin')
    rows.sort(key=lambda r: (r['job_id'], r['attempt_id'], r['path']))
    canonical = json.dumps(rows, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8') + b'\n'
    failures = [r for r in rows if not r['outcome'].endswith('pass') and r['outcome'] != 'zero-byte']
    failure_raw = json.dumps(failures, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8') + b'\n'
    if checkpoint: checkpoint('verify-complete-deterministic-classification', 'complete')
    _deadline(deadline, 'publication')
    result = {'schema': SCHEMA, 'state': 'completed', 'classification': 'TECHNICAL_FORMAT_DIAGNOSTIC_ONLY',
              'parent_job_id': v1.PARENT_JOB, 'parent_attempt_id': v1.PARENT_ATTEMPT,
              'parent_c0a_sha256': v1.C0A_SHA, 'parent_c0b_sha256': v1.C0B_SHA,
              **digests, 'descriptor_count': len(rows), 'recovery_descriptor_count': len(encountered),
              'classification_sha256': hashlib.sha256(canonical).hexdigest(),
              'failure_rows_sha256': hashlib.sha256(failure_raw).hexdigest(), 'failure_row_count': len(failures),
              'actual_position_identity_reads': None, 'actual_position_identity_reads_measurement': 'not_measured',
              'successful_position_rows': sum(r['successful_position_rows'] or 0 for r in rows),
              'target_fields_decoded': 0, 'target_reads': 0, 'score_reads': 0, 'wdl_reads': 0,
              'qvalue_reads': 0, 'model_reads': 0, 'teacher_calls': 0, 'search_calls': 0, 'fits': 0,
              'games': 0, 'alpha_spent': 0, 'scientific_verdict': None,
              'confirmation_authorized': False, 'automatic_continuation': False, 'rows': rows}
    if checkpoint: checkpoint('publish-format-diagnostic', 'begin')
    (artifact / 'ed4-c0c-full-format-diagnostic.json').write_text(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    if checkpoint: checkpoint('publish-format-diagnostic', 'complete')
    return result
