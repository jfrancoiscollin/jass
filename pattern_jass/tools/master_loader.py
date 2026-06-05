# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
#
# Loader for the JNNW dataset format (jass core).
# Header  : 4B magic "JNNW" + 4B uint32 count
# Record  : 38B = 4×uint64 bitboards (wm, wk, bm, bk) + uint8 stm
#                + int32 score (cp, STM-POV) + int8 wdl (STM-POV)
# Cf src/main.cpp:220 in the jass core.

import struct
from pathlib import Path
from typing import NamedTuple

import numpy as np

JNNW_MAGIC = b'JNNW'
JNNW_HEADER_SIZE = 8
JNNW_RECORD_SIZE = 38


class MasterDataset(NamedTuple):
    """Loaded JNNW dataset.

    All arrays are aligned : index i refers to record i.
    Bitboards are uint64, bit j = FMJD square (j+1).
    Score is centipawn, STM-POV. WDL is {-1, 0, +1}, STM-POV.
    """

    white_men:   np.ndarray  # uint64
    white_kings: np.ndarray  # uint64
    black_men:   np.ndarray  # uint64
    black_kings: np.ndarray  # uint64
    stm:         np.ndarray  # uint8  (0 = white-to-move, 1 = black-to-move)
    score:       np.ndarray  # int32  (centipawn, STM POV)
    wdl:         np.ndarray  # int8   ({-1, 0, +1}, STM POV)

    @property
    def n_records(self) -> int:
        return len(self.white_men)


def load(path: str | Path, max_records: int | None = None) -> MasterDataset:
    """Read records from a JNNW binary file. If `max_records` is given,
    only the first N records are loaded (useful for smoke tests)."""
    raw = Path(path).read_bytes()
    if len(raw) < JNNW_HEADER_SIZE:
        raise ValueError(f"file too short : {len(raw)} bytes")
    magic = raw[:4]
    if magic != JNNW_MAGIC:
        raise ValueError(f"bad magic {magic!r}")
    count = struct.unpack_from('<I', raw, 4)[0]
    body_bytes = len(raw) - JNNW_HEADER_SIZE
    if body_bytes % JNNW_RECORD_SIZE != 0:
        raise ValueError(f"body size {body_bytes} not a multiple of "
                         f"{JNNW_RECORD_SIZE}")
    expected = body_bytes // JNNW_RECORD_SIZE
    if count != expected:
        raise ValueError(f"header count {count} != file-derived {expected}")

    if max_records is not None and max_records < count:
        count = max_records
        body_bytes = count * JNNW_RECORD_SIZE

    body = raw[JNNW_HEADER_SIZE:JNNW_HEADER_SIZE + body_bytes]
    arr = np.frombuffer(body, dtype=np.dtype([
        ('wm',    '<u8'),
        ('wk',    '<u8'),
        ('bm',    '<u8'),
        ('bk',    '<u8'),
        ('stm',   'u1'),
        ('score', '<i4'),
        ('wdl',   'i1'),
    ]))
    return MasterDataset(
        white_men=arr['wm'].copy(),
        white_kings=arr['wk'].copy(),
        black_men=arr['bm'].copy(),
        black_kings=arr['bk'].copy(),
        stm=arr['stm'].copy(),
        score=arr['score'].copy(),
        wdl=arr['wdl'].copy(),
    )
