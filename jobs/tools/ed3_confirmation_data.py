#!/usr/bin/env python3
"""ED3-P2 identity-only cohort/guard selection. No target array is accepted here."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
import numpy as np

CELLS = tuple(f'P{p}_stm{s}' for p in range(4) for s in (0, 1))
GUARD_SEEDS = {'development': 202609090711, 'confirmation': 202609090712}


class SupportOrComputeBlocked(ValueError):
    """Incomplete support/spending gate, not a scientific negative."""


def require(ok, code):
    if not ok:
        if code in ('UNEXPOSED_HISTORICAL_GUARD_SUPPORT_INSUFFICIENT', 'COMPUTE_REVIEW_REQUIRED'):
            raise SupportOrComputeBlocked(code)
        raise ValueError(code)


def zero_record(record):
    require(len(record) == 38, 'record_size')
    return record[:33] + b'\0' * 5


def canonical(record):
    require(len(record) == 38 and record[32] in (0, 1), 'record_format')
    wm, wk, bm, bk = struct.unpack_from('<4Q', record)
    boards = (wm, wk, bm, bk)
    require(not any(x >> 50 for x in boards), 'board_range')
    require(not any(boards[i] & boards[j] for i in range(4) for j in range(i)), 'board_overlap')
    def rotate(b):
        return sum(1 << (49-i) for i in range(50) if b & (1 << i))
    def fp(bs, stm):
        return ':'.join([f'{b:013x}' for b in bs] + [str(stm)])
    return min(fp(boards, record[32]), fp((rotate(bm), rotate(bk), rotate(wm), rotate(wk)), 1-record[32]))


def selected_groups(parents, groups, mode):
    """Original producer roles are remapped prospectively, never from scores.

    The unchanged score-free producer's new `train` block is confirmation512.
    The miniature uses the smoke producer's train16 block. Production must
    exclude ALL miniature parent/child footprints before generation, in addition
    to the old producer outputs. Numeric parent ids are local to each dataset.
    """
    require(mode in ('rehearsal', 'production'), 'mode')
    role = 'train'
    per_cell = 64 if mode == 'production' else 2
    by_parent = {}
    for row in groups:
        by_parent.setdefault(int(row['parent_id']), []).append(row)
    counts = {c: 0 for c in CELLS}
    result = []
    for p in parents:
        if p['split'] != role:
            continue
        cell = p['parent_phase'] + '_stm' + p['parent_stm']
        require(cell in counts, 'unknown_cell')
        if counts[cell] >= per_cell:
            continue
        pid = int(p['parent_id']); siblings = by_parent[pid]
        require(2 <= len(siblings) <= 16, 'sibling_cardinality')
        result.append(dict(id=pid, cell=cell, stm=int(p['parent_stm']),
                           rows=[int(r['row_index']) for r in siblings],
                           terminals=[int(r['row_index']) for r in siblings if int(r['child_rule_terminal'])]))
        counts[cell] += 1
    require(set(counts.values()) == {per_cell} and len(result) == 8*per_cell, 'fixed_cells_missing')
    return result


def select_guard(raw, metadata, old_selection, used, *, lo=1800796, hi=2000000,
                 sizes=(256, 8192), minimum_clusters=32, roles=('development', 'confirmation')):
    """Select two opening-disjoint subsets before indexing any Context30 value.

    `metadata(i)` returns opening id and has no target access. Transporting and
    hashing the historical corpus is allowed, but its WDL bytes are not decoded.
    """
    require(raw[:4] == b'JNNW' and len(raw) == 8+38*hi
            and struct.unpack_from('<I', raw, 4)[0] == hi and 0 <= lo < hi, 'historical_layout')
    blocked = set()
    for subset in old_selection['subsets'].values():
        blocked.update(int(x) for x in subset['opening_ids'])
    used = set(used)
    answer = {}
    require(len(roles) == len(sizes) and set(roles) <= set(GUARD_SEEDS), 'guard_roles')
    for role, size in zip(roles, sizes):
        ids, openings, keys = [], [], []
        role_openings = set()
        for rel in np.random.default_rng(GUARD_SEEDS[role]).permutation(hi-lo):
            i = lo + int(rel)
            opening = int(metadata(i))
            if opening in blocked:
                continue
            record = zero_record(raw[8+38*i:8+38*(i+1)])
            key = canonical(record)
            if key in used:
                continue
            ids.append(i); openings.append(opening); keys.append(key)
            used.add(key); role_openings.add(opening)
            if len(ids) == size:
                break
        require(len(ids) == size and len(role_openings) >= minimum_clusters,
                'UNEXPOSED_HISTORICAL_GUARD_SUPPORT_INSUFFICIENT')
        blocked.update(role_openings)
        answer[role] = dict(indices=ids, opening_ids=openings, canonical_identities=keys,
                            seed=GUARD_SEEDS[role], clusters=len(role_openings))
    if set(answer) == {'development', 'confirmation'}:
        require(not set(answer['development']['opening_ids']) & set(answer['confirmation']['opening_ids']),
                'development_confirmation_opening_leakage')
    return dict(schema='jass.ed3.confirmation_guard_plan.v1', subsets=answer,
                targets_read_at_selection=0, old_selected_opening_overlap=0,
                historical_context30=True, globally_never_exposed_claim=False)


def source_fingerprints(paths):
    from jobs.tools.ed2_preflight import records
    return {canonical(r) for path in paths for r in records(path)}


def write_records(path, rows):
    require(rows and all(len(r) == 38 and r[33:] == b'\0'*5 for r in rows), 'scorefree_output')
    with Path(path).open('xb') as f:
        f.write(b'JNNW' + struct.pack('<I', len(rows)) + b''.join(rows))


def read_json(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()
