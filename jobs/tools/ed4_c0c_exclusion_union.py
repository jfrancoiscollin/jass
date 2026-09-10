#!/usr/bin/env python3
"""ED4 C0C: build a conservative canonical exclusion union from C0B candidates.

Only position identity is decoded. For counted JNNW records, the first 33 bytes
(4x u64 bitboards + STM byte) are decoded and the final 5 target/weight bytes
are skipped without interpretation. JSM/JSM.GZ are provenance sidecars and do
not independently encode a board position.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import struct
from pathlib import Path
from typing import BinaryIO, TextIO

from jobs.tools import fetch_result_files
from jobs.tools.adaptive_sibling_b2_exclusions import (
    canonical_fen,
    canonical_fingerprint,
    format_fingerprint,
)

PARENT_JOB = 'cpx62-1897-l3-ed4-c0b-structural-payload-freeze-v2'
PARENT_ATTEMPT = '20260909T210053Z-a3efc988'
PARENT_CODE = 'a3efc988d8ff0b5642ab65fa0bf133897ee2f54c'
PARENT_PREFIX = f'r2:jass-data/runs/{PARENT_JOB}/{PARENT_ATTEMPT}'
C0A_SHA = '0af828dbc84b7103ad2aa54196c2ca18f81b3afab01b4daa6e256ffd87ecb219'
C0B_SHA = 'c04c5ad0a3c6b98d6d3c86575f1ba5607cdad17e92ae5b1ed4108aeb81274bda'
EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()
SCHEMA = 'jass.ed4.c0c_structural_exclusion_union.v1'

# 1909 authenticated the first 1907 parse failure as this exact path and proved
# the envelope is a live-writer snapshot (JNNW count=0 with trailing bytes):
# 1785 created this subtree with `git worktree add --detach ...` under its runner
# scratch while preparing documentary commit S, then failed exit 128.  Therefore
# files below this exact immutable worktree prefix are repository checkout copies,
# not positions produced/consumed by 1785.  C0B was deliberately path-only and
# overinclusive, so the frozen descriptors remain authenticated here but these
# operational copies contribute no *new producer* identities.  The generic JNNW
# parser remains strict; no malformed JNNW is salvaged or accepted.
OPERATIONAL_COPY_JOB = 'cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1'
OPERATIONAL_COPY_ATTEMPT = '20260905T145718Z-d3657332'
OPERATIONAL_COPY_CODE = 'd3657332c3a5609a5501a9ff130f5d5c19488c7f'
OPERATIONAL_COPY_EXIT = 128
OPERATIONAL_COPY_PREFIX = 'b2-preread-schema-compat/documentary-worktree/'
OPERATIONAL_COPY_SEMANTICS = 'authenticated_failed_1785_documentary_git_worktree_copy_no_new_production'


class C0CError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def canonical_from_position_bytes(raw: bytes) -> str:
    if len(raw) != 33:
        raise C0CError('position_identity_width')
    wm, wk, bm, bk, stm = struct.unpack('<QQQQB', raw)
    return canonical_fingerprint(format_fingerprint(wm, wk, bm, bk, stm))


def _bin(path: Path, compressed: bool) -> BinaryIO:
    return gzip.open(path, 'rb') if compressed else path.open('rb')


def parse_jnnw(path: Path, compressed: bool = False) -> tuple[set[str], int]:
    identities: set[str] = set()
    with _bin(path, compressed) as f:
        header = f.read(8)
        if len(header) != 8 or header[:4] != b'JNNW':
            raise C0CError('jnnw_header')
        count = struct.unpack('<I', header[4:])[0]
        for _ in range(count):
            record = f.read(38)
            if len(record) != 38:
                raise C0CError('jnnw_truncated')
            identities.add(canonical_from_position_bytes(record[:33]))
            # record[33:38] is intentionally never unpacked or interpreted.
        if f.read(1):
            raise C0CError('jnnw_trailing_bytes')
    return identities, count


def _text(path: Path, compressed: bool) -> TextIO:
    return (
        gzip.open(path, 'rt', encoding='utf-8', newline='')
        if compressed
        else path.open('r', encoding='utf-8', newline='')
    )


def parse_fen_file(path: Path, compressed: bool = False) -> tuple[set[str], int]:
    out: set[str] = set()
    rows = 0
    with _text(path, compressed) as f:
        for raw in f:
            value = raw.split('#', 1)[0].strip()
            if not value:
                continue
            out.add(canonical_fen(value))
            rows += 1
    if rows == 0:
        raise C0CError('fen_empty')
    return out, rows


def parse_identity_text(path: Path, compressed: bool = False) -> tuple[set[str], int]:
    out: set[str] = set()
    rows = 0
    with _text(path, compressed) as f:
        for raw in f:
            value = raw.strip()
            if not value:
                continue
            out.add(canonical_fingerprint(value))
            rows += 1
    if rows == 0:
        raise C0CError('identity_empty')
    return out, rows


def parse_tsv(path: Path, compressed: bool = False) -> tuple[set[str], int]:
    out: set[str] = set()
    rows = 0
    with _text(path, compressed) as f:
        reader = csv.DictReader(f, delimiter='\t')
        fields = reader.fieldnames or []
        identity_field = next(
            (x for x in ('canonical_identity', 'canonical_fingerprint', 'raw_fingerprint') if x in fields),
            None,
        )
        fen_field = 'fen' if 'fen' in fields else None
        if identity_field is None and fen_field is None:
            raise C0CError('tsv_no_position_field')
        for row in reader:
            if identity_field and row.get(identity_field):
                out.add(canonical_fingerprint(row[identity_field].strip()))
            elif fen_field and row.get(fen_field):
                out.add(canonical_fen(row[fen_field].strip()))
            else:
                raise C0CError('tsv_row_without_position')
            rows += 1
    if rows == 0:
        raise C0CError('tsv_empty')
    return out, rows


def parse_candidate(path: Path, kind: str) -> tuple[set[str], int, str]:
    if kind in {'jsm', 'jsm_gzip'}:
        return set(), 0, 'provenance_sidecar_no_board_position'
    if kind == 'jnnw':
        ids, rows = parse_jnnw(path, False)
    elif kind == 'jnnw_gzip':
        ids, rows = parse_jnnw(path, True)
    elif kind == 'fen':
        ids, rows = parse_fen_file(path, False)
    elif kind == 'fen_gzip':
        ids, rows = parse_fen_file(path, True)
    elif kind == 'identity_text':
        ids, rows = parse_identity_text(path, False)
    elif kind.endswith('_tsv'):
        ids, rows = parse_tsv(path, False)
    else:
        raise C0CError('unsupported_candidate_kind:' + kind)
    return ids, rows, 'position_identity_only'


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise C0CError('json_object_required')
    return value


def fetch_parent(work: Path) -> tuple[dict, dict]:
    out = work / 'parent'
    out.mkdir(parents=True)
    report = fetch_result_files.fetch_files(
        rclone='rclone',
        prefix=PARENT_PREFIX,
        expected_state='completed',
        out_dir=out,
        selections=[
            ('artefacts/ed4-c0a-source-descriptor-inventory.json', 'c0a.json'),
            ('artefacts/ed4-c0b-structural-candidate-manifest.json', 'c0b.json'),
        ],
    )
    if (report.get('job_id'), report.get('attempt_id'), report.get('code_sha')) != (
        PARENT_JOB,
        PARENT_ATTEMPT,
        PARENT_CODE,
    ):
        raise C0CError('parent_identity')
    if sha256_file(out / 'c0a.json') != C0A_SHA or sha256_file(out / 'c0b.json') != C0B_SHA:
        raise C0CError('parent_artifact_hash')
    return _read_json(out / 'c0a.json'), _read_json(out / 'c0b.json')


def _authenticate_candidate_descriptors(
    *,
    prefix: str,
    state: str,
    job_id: str,
    attempt: str,
    candidates: list[dict],
) -> tuple[list[tuple[int, dict]], list[dict]]:
    """Authenticate every descriptor before payload transport.

    A zero-byte object contains no board identity and therefore contributes the
    empty set. It is still accepted only when the authenticated runner inventory
    agrees on path, size=0 and SHA256(empty); it is never parsed as JNNW/text.
    """
    report = fetch_result_files.inspect_result_inventory(
        rclone='rclone', prefix=prefix, expected_state=state
    )
    if report.get('job_id') != job_id or report.get('attempt_id') != attempt:
        raise C0CError('candidate_inventory_identity')
    inventory = {item['path']: item for item in report['files']}
    nonempty: list[tuple[int, dict]] = []
    zero_receipts: list[dict] = []
    for i, desc in enumerate(candidates):
        item = inventory.get(desc['path'])
        if (
            item is None
            or item['sha256'] != desc['sha256']
            or item['size_bytes'] != desc['size_bytes']
        ):
            raise C0CError('descriptor_drift')
        if item['size_bytes'] == 0:
            if item['sha256'] != EMPTY_SHA256:
                raise C0CError('zero_size_hash_mismatch')
            zero_receipts.append({
                'job_id': job_id,
                'attempt_id': attempt,
                'path': desc['path'],
                'kind': desc['kind'],
                'sha256': desc['sha256'],
                'rows': 0,
                'unique_identities': 0,
                'semantics': 'authenticated_zero_size_no_position_bytes',
            })
        else:
            nonempty.append((i, desc))
    return nonempty, zero_receipts


def _operational_copy_semantics(*, source: dict, job_id: str, attempt: str, path: str) -> str | None:
    """Classify only the exact 1785 Git worktree proven by 1909.

    C0B remains byte-identical and every descriptor is authenticated first.  A
    prefix match outside this one immutable failed attempt is never generalized.
    """
    if job_id != OPERATIONAL_COPY_JOB or attempt != OPERATIONAL_COPY_ATTEMPT:
        return None
    if not path.startswith(OPERATIONAL_COPY_PREFIX):
        return None
    if (
        source.get('code_sha') != OPERATIONAL_COPY_CODE
        or source.get('result_state') != 'failed'
        or source.get('exit_code') != OPERATIONAL_COPY_EXIT
    ):
        raise C0CError('operational_copy_source_identity')
    return OPERATIONAL_COPY_SEMANTICS


def build_union(work: Path, artifact: Path) -> dict:
    if work.exists() or work.is_symlink():
        raise C0CError('work_dir_must_not_exist')
    work.mkdir(parents=True)
    artifact.mkdir(parents=True, exist_ok=True)
    c0a, c0b = fetch_parent(work)
    sources = {x['job_id']: x for x in c0a.get('sources', [])}
    all_ids: set[str] = set()
    file_receipts = []
    total_rows = 0
    downloaded = 0
    zero_size_authenticated = 0
    operational_copy_authenticated = 0

    for job in c0b.get('candidate_jobs', []):
        job_id, attempt = job['job_id'], job.get('attempt_id')
        candidates = job.get('candidate_files', [])
        if not candidates:
            continue
        source = sources.get(job_id)
        if not source or source.get('attempt_id') != attempt:
            raise C0CError('c0a_c0b_identity_mismatch')
        state = source.get('result_state')
        if state not in {'completed', 'failed'}:
            raise C0CError('candidate_result_state')
        prefix = f'r2:jass-data/runs/{job_id}/{attempt}'
        local = work / ('job-' + hashlib.sha256(job_id.encode()).hexdigest()[:12])

        nonempty, zero_receipts = _authenticate_candidate_descriptors(
            prefix=prefix,
            state=state,
            job_id=job_id,
            attempt=attempt,
            candidates=candidates,
        )
        file_receipts.extend(zero_receipts)
        zero_size_authenticated += len(zero_receipts)

        parseable: list[tuple[int, dict]] = []
        for i, desc in nonempty:
            copy_semantics = _operational_copy_semantics(
                source=source, job_id=job_id, attempt=attempt, path=desc['path']
            )
            if copy_semantics is None:
                parseable.append((i, desc))
                continue
            operational_copy_authenticated += 1
            file_receipts.append({
                'job_id': job_id,
                'attempt_id': attempt,
                'path': desc['path'],
                'kind': desc['kind'],
                'sha256': desc['sha256'],
                'rows': 0,
                'unique_identities': 0,
                'semantics': copy_semantics,
            })
        if not parseable:
            continue

        selections = [
            (desc['path'], f'{i:04d}-{Path(desc["path"]).name}')
            for i, desc in parseable
        ]
        fetched = fetch_result_files.fetch_files(
            rclone='rclone',
            prefix=prefix,
            expected_state=state,
            selections=selections,
            out_dir=local,
        )
        if fetched.get('job_id') != job_id or fetched.get('attempt_id') != attempt:
            raise C0CError('download_identity')
        fetched_map = {x['path']: x for x in fetched['files']}
        for i, desc in parseable:
            got = fetched_map.get(desc['path'])
            if not got or got['sha256'] != desc['sha256'] or got['size_bytes'] != desc['size_bytes']:
                raise C0CError('descriptor_drift')
            path = local / f'{i:04d}-{Path(desc["path"]).name}'
            ids, rows, semantics = parse_candidate(path, desc['kind'])
            all_ids.update(ids)
            total_rows += rows
            downloaded += 1
            file_receipts.append({
                'job_id': job_id,
                'attempt_id': attempt,
                'path': desc['path'],
                'kind': desc['kind'],
                'sha256': desc['sha256'],
                'rows': rows,
                'unique_identities': len(ids),
                'semantics': semantics,
            })
            path.unlink(missing_ok=True)
        shutil.rmtree(local, ignore_errors=True)

    if not all_ids:
        raise C0CError('empty_exclusion_union')
    union_raw = ('\n'.join(sorted(all_ids)) + '\n').encode('ascii')
    union_path = artifact / 'ed4-c0c-structural-exclusion-union.txt'
    union_path.write_bytes(union_raw)
    manifest = {
        'schema': SCHEMA,
        'state': 'completed',
        'verdict': 'ED4_C0C_STRUCTURAL_EXCLUSION_UNION_READY_V1',
        'parent_job_id': PARENT_JOB,
        'parent_attempt_id': PARENT_ATTEMPT,
        'parent_c0a_sha256': C0A_SHA,
        'parent_c0b_sha256': C0B_SHA,
        'candidate_files_downloaded': downloaded,
        'candidate_zero_size_authenticated': zero_size_authenticated,
        'candidate_operational_copy_authenticated': operational_copy_authenticated,
        'candidate_rows_parsed': total_rows,
        'unique_canonical_identities': len(all_ids),
        'union_sha256': hashlib.sha256(union_raw).hexdigest(),
        'union_size_bytes': len(union_raw),
        'target_fields_decoded': 0,
        'score_reads': 0,
        'wdl_reads': 0,
        'qvalue_reads': 0,
        'model_reads': 0,
        'teacher_calls': 0,
        'search_calls': 0,
        'fits': 0,
        'games': 0,
        'alpha_spent': 0,
        'confirmation_authorized': False,
        'automatic_continuation': False,
        'files': file_receipts,
    }
    (artifact / 'ed4-c0c-structural-exclusion-manifest.json').write_text(
        json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n',
        encoding='utf-8',
    )
    return manifest