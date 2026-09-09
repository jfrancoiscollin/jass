#!/usr/bin/env python3
"""Freeze parseable structural payload candidates from authenticated C0A metadata.

This module never downloads or opens a payload.  It is deliberately
conservative: every file whose *path* identifies a parseable position-bearing
format is retained as a future exclusion candidate.  A candidate is not proof
that the file contains novel positions and it never changes C0A admission.
"""
from __future__ import annotations
from collections import Counter
from pathlib import PurePosixPath

SCHEMA = 'jass.ed4.c0b_structural_candidate_manifest.v1'


def _lower(path: str) -> str:
    return path.lower()


def candidate_kind(path: str) -> str | None:
    """Return a metadata-only parser class for an exact inventory path."""
    value = _lower(path)
    name = PurePosixPath(value).name
    if value.endswith('.jnnw.gz'):
        return 'jnnw_gzip'
    if value.endswith('.jnnw'):
        return 'jnnw'
    if value.endswith('.fen.gz'):
        return 'fen_gzip'
    if value.endswith('.fen'):
        return 'fen'
    if value.endswith('.jsm.gz'):
        return 'jsm_gzip'
    if value.endswith('.jsm'):
        return 'jsm'
    if name in {'parents.tsv', 'children.tsv', 'siblings.tsv', 'groups.tsv'}:
        return name[:-4] + '_tsv'
    if name.endswith('roots.tsv') or name.endswith('root-pool.tsv'):
        return 'roots_tsv'
    if name == 'ordered-identities.txt' or name.endswith('-ordered-identities.txt'):
        return 'identity_text'
    if name.endswith('exclusion-union.txt') or name.endswith('canonical-union.txt'):
        return 'identity_text'
    return None


def build(metadata: dict, report: dict, control_snapshot: str) -> dict:
    """Build an exact, deterministic path manifest from already-authenticated metadata."""
    target_classes = {'unknown', 'structural_payload_unavailable'}
    jobs = []
    kind_counts: Counter[str] = Counter()
    total_bytes = 0
    candidate_count = 0
    no_candidate = []
    for source in sorted(report.get('sources', []), key=lambda row: row['job_id']):
        if source.get('classification') not in target_classes:
            continue
        job = source['job_id']
        attempt = source.get('attempt_id')
        meta = metadata.get((job, attempt)) if attempt else None
        files = []
        if meta is not None:
            for entry in meta.get('files', []):
                path = entry.get('path')
                if not isinstance(path, str):
                    continue
                kind = candidate_kind(path)
                if kind is None:
                    continue
                size = entry.get('size_bytes')
                sha = entry.get('sha256')
                if type(size) is not int or size < 0 or not isinstance(sha, str) or len(sha) != 64:
                    raise ValueError('candidate_descriptor_invalid')
                files.append({'path': path, 'kind': kind, 'size_bytes': size, 'sha256': sha})
        files.sort(key=lambda item: (item['path'], item['kind']))
        if len({item['path'] for item in files}) != len(files):
            raise ValueError('candidate_duplicate_path')
        for item in files:
            kind_counts[item['kind']] += 1
            candidate_count += 1
            total_bytes += item['size_bytes']
        if not files:
            no_candidate.append(job)
        jobs.append({'job_id': job, 'attempt_id': attempt,
                     'classification_at_freeze': source.get('classification'),
                     'candidate_files': files})
    return {
        'schema': SCHEMA,
        'state': 'completed',
        'classification': 'METADATA_ONLY_OVERINCLUSIVE_FREEZE',
        'control_snapshot_commit': control_snapshot,
        'candidate_jobs': jobs,
        'candidate_jobs_count': len(jobs),
        'candidate_files_count': candidate_count,
        'candidate_declared_bytes_total': total_bytes,
        'candidate_kind_counts': dict(sorted(kind_counts.items())),
        'jobs_without_parseable_position_candidate': sorted(no_candidate),
        'payload_downloads': 0,
        'payload_bytes_read': 0,
        'model_reads': 0,
        'target_reads': 0,
        'outcome_reads': 0,
        'qvalue_reads': 0,
        'scientific_verdict': None,
        'confirmation_authorized': False,
        'automatic_continuation': False,
    }
