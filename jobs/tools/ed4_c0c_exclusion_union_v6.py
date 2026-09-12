#!/usr/bin/env python3
"""Frozen V6 technical recovery of the ED4 C0C structural source union.

This module remains deliberately unusable for a remote run until the runtime
sizing cap is measured and set.  Its two canonical row-set digests are frozen
from the authenticated 1927 readout. It never reads target bytes: JNNW records
are passed to the V1 position decoder as exactly 33-byte prefixes.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import time
from pathlib import Path

from jobs.tools import ed4_c0c_exclusion_union as v1
from jobs.tools import ed4_c0c_exclusion_union_v5 as v5
from jobs.tools import fetch_result_files

SCHEMA = 'jass.ed4.c0c_structural_exclusion_union.v6'
VERDICT = 'ED4_C0C_STRUCTURAL_EXCLUSION_UNION_READY_V6_INVENTORY_CLOSED_ALIGNED_COUNT0'
CLASSIFICATION = 'TECHNICAL_STRUCTURAL_SOURCE_RECOVERY_ONLY'
REC = 38
INV_JOB = 'cpx62-1927-l3-ed4-c0c-v5-inventory-class-readout-v1'
INV_ATTEMPT = '20260912T111000Z-26d79792'
INV_CODE = '26d79792d207018982f482bbb8a96520a845c659'
INV_PATH = 'inventory/inventory.json'
READOUT_PATH = 'artefacts/ed4-c0c-v5-inventory-class-readout.json'
INV_SHA256 = '1e8ebc5ee1c5614390c950e903377a6c3664b8d0c2a08f21c0295b2066f4d599'
INV_SIZE = 171848
READOUT_SHA256 = 'e93bb11a3783077955bc2393ca55e219be8e93df92260c42c35484684d4135e1'
READOUT_SIZE = 9083

# Frozen from the authenticated 1927 inventory/readout pair.
FULL_ALLOWLIST_CANONICAL_SHA256 = 'f56fda00c0ce815eaeac924ede0ce78840bed60f68360b57de9b801fb8885f95'
ALIGNED_SUBSET_CANONICAL_SHA256 = '7721b29bcbb65a0dc070def901bdb03b9738ca399bf146d2a5a156338dd4fb47'
# Runtime sizing is not inferred.  The stage refuses launch until the measured
# CPX rehearsal supplies this explicit cap.
RUNTIME_MAX_SECONDS: int | None = None
HEX64 = re.compile(r'^[0-9a-f]{64}$')
CANONICAL_FIELDS = ('job_id','attempt_id','path','kind','sha256','size_bytes','reason','declared_count','complete_records_from_size','partial_tail_bytes_from_size')


def _error(code: str) -> None:
    raise v1.C0CError(code)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _deadline_check(deadline: float | None, phase: str) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        _error('v6_deadline_exceeded:' + phase)


def _canonical_rows(rows: list[dict]) -> tuple[bytes, str]:
    values = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict): _error('v6_row_not_object')
        value = {key: row.get(key) for key in CANONICAL_FIELDS}
        key = tuple(value[k] for k in ('job_id','attempt_id','path'))
        if key in seen: _error('v6_duplicate_allowlist_key')
        seen.add(key)
        values.append(value)
    values.sort(key=lambda r: (r['job_id'], r['attempt_id'], r['path']))
    raw = json.dumps(values, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8') + b'\n'
    return raw, hashlib.sha256(raw).hexdigest()


def _validate_row(row: dict) -> str:
    for key in ('job_id','attempt_id','path','kind','sha256','reason'):
        if not isinstance(row.get(key), str) or not row[key]: _error('v6_row_string:' + key)
    if not HEX64.fullmatch(row['sha256']): _error('v6_row_sha256')
    path = row['path']
    if path.startswith('/') or '\\' in path or any(piece in ('', '.', '..') for piece in path.split('/')):
        _error('v6_row_path')
    for key in ('size_bytes','declared_count','complete_records_from_size','partial_tail_bytes_from_size'):
        if not _is_int(row.get(key)): _error('v6_row_integer:' + key)
    if row['kind'] != 'jnnw' or row['reason'] != 'jnnw_trailing_bytes' or row.get('state') != 'invalid' or row['declared_count'] != 0:
        _error('v6_unknown_malformed_class')
    complete, tail = divmod(row['size_bytes'] - 8, REC)
    if row['size_bytes'] < 8 or (complete, tail) != (row['complete_records_from_size'], row['partial_tail_bytes_from_size']) or complete < 1:
        _error('v6_row_geometry')
    interrupted = row.get('interrupted_writer_shape')
    if not isinstance(interrupted, bool): _error('v6_row_interrupted_bool')
    if tail == 0:
        if interrupted or complete not in (1944, 2160) or row['size_bytes'] not in (73880, 82088): _error('v6_aligned_shape')
        return 'aligned'
    if not interrupted or not 1 <= tail <= 37: _error('v6_v5_shape')
    return 'v5'


def _require_pins(full_digest: str, aligned_digest: str) -> None:
    if not HEX64.fullmatch(FULL_ALLOWLIST_CANONICAL_SHA256) or not HEX64.fullmatch(ALIGNED_SUBSET_CANONICAL_SHA256):
        _error('v6_canonical_digest_pins_pending')
    if full_digest != FULL_ALLOWLIST_CANONICAL_SHA256 or aligned_digest != ALIGNED_SUBSET_CANONICAL_SHA256:
        _error('v6_canonical_digest_mismatch')


def _load_1927(work: Path, deadline: float | None = None) -> tuple[dict, dict, dict]:
    _deadline_check(deadline, 'metadata')
    prefix = f'r2:jass-data/runs/{INV_JOB}/{INV_ATTEMPT}'
    inventory = fetch_result_files.inspect_result_inventory(rclone='rclone', prefix=prefix, expected_state='completed')
    if (inventory.get('job_id'), inventory.get('attempt_id'), inventory.get('code_sha'), inventory.get('result_state'), inventory.get('host'), inventory.get('exit_code')) != (INV_JOB, INV_ATTEMPT, INV_CODE, 'completed', 'cpx62', 0):
        _error('v6_1927_identity')
    expected = {INV_PATH: (INV_SHA256, INV_SIZE), READOUT_PATH: (READOUT_SHA256, READOUT_SIZE)}
    actual = {x.get('path'): (x.get('sha256'), x.get('size_bytes')) for x in inventory.get('files', []) if isinstance(x, dict)}
    if any(actual.get(path) != identity for path, identity in expected.items()): _error('v6_1927_artifact_identity')
    _deadline_check(deadline, 'source')
    out = work / '1927'; out.mkdir(parents=True, exist_ok=True)
    fetched = fetch_result_files.fetch_files(rclone='rclone', prefix=prefix, expected_state='completed', selections=[(INV_PATH, 'inventory.json'), (READOUT_PATH, 'readout.json')], out_dir=out)
    files = {x.get('path'): (x.get('sha256'), x.get('size_bytes')) for x in fetched.get('files', []) if isinstance(x, dict)}
    if files != expected or (fetched.get('job_id'), fetched.get('attempt_id'), fetched.get('code_sha'), fetched.get('host'), fetched.get('exit_code')) != (INV_JOB, INV_ATTEMPT, INV_CODE, 'cpx62', 0): _error('v6_1927_fetch_identity')
    raws = {'inventory': (out / 'inventory.json').read_bytes(), 'readout': (out / 'readout.json').read_bytes()}
    if (hashlib.sha256(raws['inventory']).hexdigest(), len(raws['inventory'])) != expected[INV_PATH] or (hashlib.sha256(raws['readout']).hexdigest(), len(raws['readout'])) != expected[READOUT_PATH]: _error('v6_1927_download_identity')
    try: return json.loads(raws['inventory']), json.loads(raws['readout']), {'inventory_sha256': INV_SHA256, 'inventory_size_bytes': INV_SIZE, 'readout_sha256': READOUT_SHA256, 'readout_size_bytes': READOUT_SIZE}
    except json.JSONDecodeError: _error('v6_1927_json')


def validate_1927(inventory: dict, readout: dict) -> tuple[dict, dict, dict]:
    if not isinstance(inventory, dict) or inventory.get('schema') != 'jass.ed4.c0c_v4_full_malformed_inventory.v1' or inventory.get('state') != 'completed': _error('v6_inventory_schema')
    for key in ('record_fields_decoded','position_identity_reads','target_fields_decoded','target_reads','score_reads','wdl_reads','qvalue_reads','model_reads','teacher_calls','search_calls','fits','games','alpha_spent'):
        if not _is_int(inventory.get(key)) or inventory[key] != 0: _error('v6_inventory_contamination:' + key)
    rows = inventory.get('malformed')
    if not isinstance(rows, list) or len(rows) != 231 or inventory.get('malformed_count') != 231: _error('v6_partition_count')
    v5_rows, aligned_rows = [], []
    for row in rows:
        bucket = _validate_row(row)
        (v5_rows if bucket == 'v5' else aligned_rows).append(row)
    if len(v5_rows) != 216 or len(aligned_rows) != 15 or sum(r['complete_records_from_size'] for r in aligned_rows) != 31968: _error('v6_partition_membership')
    if sum(r['size_bytes'] == 73880 and r['complete_records_from_size'] == 1944 for r in aligned_rows) != 2 or sum(r['size_bytes'] == 82088 and r['complete_records_from_size'] == 2160 for r in aligned_rows) != 13: _error('v6_aligned_counts')
    full_raw, full_digest = _canonical_rows(rows); aligned_raw, aligned_digest = _canonical_rows(aligned_rows)
    _require_pins(full_digest, aligned_digest)
    if not isinstance(readout, dict) or readout.get('schema') != 'jass.ed4.c0c_v5_inventory_class_readout.v1' or readout.get('state') != 'completed' or readout.get('inventory_job_id') != v5.INV_JOB: _error('v6_readout_schema')
    for key in ('record_fields_decoded','position_identity_reads','target_fields_decoded','target_reads','wdl_reads','qvalue_reads','alpha_spent'):
        if not _is_int(readout.get(key)) or readout[key] != 0: _error('v6_readout_contamination:' + key)
    if readout.get('scientific_verdict') is not None or readout.get('confirmation_authorized') is not False: _error('v6_readout_scientific_state')
    outside = readout.get('outside_class')
    if readout.get('malformed_count') != 231 or readout.get('interrupted_writer_count') != 216 or readout.get('outside_class_count') != 15 or not isinstance(outside, list) or len(outside) != 15: _error('v6_readout_partition')
    if _canonical_rows(outside)[0] != aligned_raw: _error('v6_readout_aligned_identity')
    allow = {tuple(row[k] for k in ('job_id','attempt_id','path')): row for row in rows}
    return allow, {'v5': v5_rows, 'aligned': aligned_rows}, {'allowlist_canonical_sha256': full_digest, 'aligned_subset_canonical_sha256': aligned_digest, 'allowlist_canonical_size_bytes': len(full_raw), 'aligned_subset_canonical_size_bytes': len(aligned_raw)}


def _parse_aligned(path: Path, desc: dict, row: dict, deadline: float | None = None) -> tuple[set[str], int, dict]:
    if any(desc.get(k) != row.get(k) for k in ('path','kind','sha256','size_bytes')): _error('v6_aligned_descriptor_identity')
    raw = path.read_bytes()
    if len(raw) != row['size_bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']: _error('v6_aligned_download_identity')
    if raw[:4] != b'JNNW' or len(raw) < 8 or struct.unpack('<I', raw[4:8])[0] != 0: _error('v6_aligned_header')
    complete, tail = divmod(len(raw) - 8, REC)
    if tail != 0 or complete < 1 or complete != row['complete_records_from_size']: _error('v6_aligned_geometry')
    ids = set()
    for i in range(complete):
        _deadline_check(deadline, 'parse')
        rec = raw[8 + i * REC:8 + (i + 1) * REC]
        try:
            ids.add(v1.canonical_from_position_bytes(rec[:33]))
        except Exception as exc:
            raise v1.C0CError('v6_aligned_invalid_position') from exc
        # The last five bytes are never unpacked; their only use was whole-file SHA-256 above.
    return ids, complete, {'declared_count': 0, 'complete_records_recovered': complete, 'partial_tail_bytes_discarded': 0, 'policy': 'exact_authenticated_aligned_count0_v6'}


def build_union_v6(work: Path, artifact: Path, deadline: float | None = None, checkpoint=None) -> dict:
    if work.exists() or work.is_symlink(): _error('work_dir_must_not_exist')
    work.mkdir(parents=True); artifact.mkdir(parents=True, exist_ok=True)
    if checkpoint: checkpoint('authenticate-1927-inventory-and-class-readout', 'begin')
    inv, readout, source_meta = _load_1927(work, deadline)
    if checkpoint: checkpoint('authenticate-1927-inventory-and-class-readout', 'complete')
    if checkpoint: checkpoint('validate-pinned-231-row-partition', 'begin')
    allow, partitions, digests = validate_1927(inv, readout)
    if checkpoint: checkpoint('validate-pinned-231-row-partition', 'complete')
    v5_allow = {key: {'sha256': row['sha256'], 'size_bytes': row['size_bytes'], 'complete': row['complete_records_from_size'], 'tail': row['partial_tail_bytes_from_size']} for key, row in allow.items() if row['partial_tail_bytes_from_size'] != 0}
    if checkpoint: checkpoint('authenticate-c0a-c0b-descriptor-universe', 'begin')
    c0a, c0b = v1.fetch_parent(work / 'parent')
    if checkpoint: checkpoint('authenticate-c0a-c0b-descriptor-universe', 'complete')
    sources = {x.get('job_id'): x for x in c0a.get('sources', []) if isinstance(x, dict)}
    ids, receipts, encountered = set(), [], []
    total = downloaded = zero = v5_files = v5_records = aligned_files = aligned_records = discarded = 0
    descriptor_keys = set()
    if checkpoint: checkpoint('download-and-parse-authenticated-candidates', 'begin')
    for job in c0b.get('candidate_jobs', []):
        _deadline_check(deadline, 'metadata')
        if not isinstance(job, dict) or not isinstance(job.get('job_id'), str) or not isinstance(job.get('attempt_id'), str): _error('v6_candidate_job_shape')
        job_id, attempt, candidates = job['job_id'], job['attempt_id'], job.get('candidate_files', [])
        if not isinstance(candidates, list): _error('v6_candidate_files_shape')
        source = sources.get(job_id)
        if not source or source.get('attempt_id') != attempt or source.get('result_state') not in {'completed','failed'}: _error('v6_c0a_c0b_identity')
        for desc in candidates:
            if not isinstance(desc, dict) or not isinstance(desc.get('path'), str): _error('v6_descriptor_shape')
            key = (job_id, attempt, desc['path'])
            if key in descriptor_keys: _error('v6_duplicate_descriptor_encounter')
            descriptor_keys.add(key)
        nonempty, zero_receipts = v1._authenticate_candidate_descriptors(prefix=f'r2:jass-data/runs/{job_id}/{attempt}', state=source['result_state'], job_id=job_id, attempt=attempt, candidates=candidates)
        receipts.extend(zero_receipts); zero += len(zero_receipts)
        if not nonempty: continue
        local = work / ('job-' + hashlib.sha256((job_id + attempt).encode()).hexdigest()[:16])
        fetched = fetch_result_files.fetch_files(rclone='rclone', prefix=f'r2:jass-data/runs/{job_id}/{attempt}', expected_state=source['result_state'], selections=[(d['path'], f'{i:04d}-{Path(d["path"]).name}') for i, d in nonempty], out_dir=local)
        fmap = {x.get('path'): x for x in fetched.get('files', []) if isinstance(x, dict)}
        for i, desc in nonempty:
            _deadline_check(deadline, 'source')
            key = (job_id, attempt, desc['path']); got = fmap.get(desc['path'])
            if not got or got.get('sha256') != desc.get('sha256') or got.get('size_bytes') != desc.get('size_bytes'): _error('v6_descriptor_drift')
            path = local / f'{i:04d}-{Path(desc["path"]).name}'
            row = allow.get(key)
            if row is None:
                try: parsed, rows, semantics = v1.parse_candidate(path, desc.get('kind')); recovery = None
                except v1.C0CError: _error('v6_unlisted_malformed')
            elif row['partial_tail_bytes_from_size'] == 0:
                parsed, rows, recovery = _parse_aligned(path, desc, row, deadline); semantics = 'position_identity_only_v6_aligned_count0'
                aligned_files += 1; aligned_records += rows
            else:
                recovered = v5._salvage(path, desc, job_id, attempt, v5_allow)
                if recovered is None: _error('v6_v5_allowlist_identity')
                parsed, rows, recovery = recovered; semantics = 'position_identity_only_v5_inventory_salvage'; v5_files += 1; v5_records += rows; discarded += recovery['partial_tail_bytes_discarded']
            _deadline_check(deadline, 'parse')
            if row is not None: encountered.append(key)
            ids.update(parsed); total += rows; downloaded += 1
            receipts.append({'job_id': job_id, 'attempt_id': attempt, 'path': desc['path'], 'kind': desc.get('kind'), 'sha256': desc.get('sha256'), 'size_bytes': desc.get('size_bytes'), 'rows': rows, 'unique_identities': len(parsed), 'semantics': semantics, **({'recovery': recovery} if recovery else {})})
            path.unlink(missing_ok=True)
        shutil.rmtree(local, ignore_errors=True)
    if checkpoint: checkpoint('download-and-parse-authenticated-candidates', 'complete')
    if v5_files != 216 or aligned_files != 15 or aligned_records != 31968: _error('v6_recovery_partition_runtime')
    if len(encountered) != len(set(encountered)) or set(encountered) != set(allow) or len(encountered) != 231: _error('v6_allowlist_encounter_cardinality')
    if checkpoint: checkpoint('verify-exact-allowlist-encounters', 'begin'); checkpoint('verify-exact-allowlist-encounters', 'complete')
    if not ids: _error('empty_exclusion_union')
    _deadline_check(deadline, 'publication')
    union = ('\n'.join(sorted(ids)) + '\n').encode('ascii'); (artifact / 'ed4-c0c-structural-exclusion-union.txt').write_bytes(union)
    _deadline_check(deadline, 'publication')
    manifest = {'schema': SCHEMA, 'state': 'completed', 'verdict': VERDICT, 'classification': CLASSIFICATION, 'protocol_change': 'immutable_v6_exact_1927_inventory_class_recovery', 'inventory_job_id': INV_JOB, 'inventory_attempt_id': INV_ATTEMPT, 'inventory_code_sha': INV_CODE, **source_meta, **digests, 'parent_job_id': v1.PARENT_JOB, 'parent_attempt_id': v1.PARENT_ATTEMPT, 'parent_c0a_sha256': v1.C0A_SHA, 'parent_c0b_sha256': v1.C0B_SHA, 'candidate_files_downloaded': downloaded, 'candidate_zero_size_authenticated': zero, 'candidate_rows_parsed': total, 'v5_salvaged_files': v5_files, 'v5_salvaged_complete_records': v5_records, 'aligned_count0_files': aligned_files, 'aligned_count0_records': aligned_records, 'discarded_partial_tail_bytes': discarded, 'unique_canonical_identities': len(ids), 'union_sha256': hashlib.sha256(union).hexdigest(), 'union_size_bytes': len(union), 'target_fields_decoded': 0, 'target_reads': 0, 'score_reads': 0, 'wdl_reads': 0, 'qvalue_reads': 0, 'model_reads': 0, 'teacher_calls': 0, 'search_calls': 0, 'fits': 0, 'games': 0, 'alpha_spent': 0, 'scientific_verdict': None, 'confirmation_authorized': False, 'automatic_continuation': False, 'files': receipts}
    if checkpoint: checkpoint('publish-union-v6', 'begin')
    _deadline_check(deadline, 'publication')
    (artifact / 'ed4-c0c-structural-exclusion-manifest.json').write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    if checkpoint: checkpoint('publish-union-v6', 'complete')
    return manifest
