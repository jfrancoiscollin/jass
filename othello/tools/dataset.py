# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
#
# Loader for the gen-data binary format (cf. othello/src/gen_data.hpp).

import struct
from pathlib import Path
from typing import NamedTuple

import numpy as np

GEN_DATA_MAGIC = 0x4F544843  # "OTHC" LE
GEN_DATA_VERSION = 1
GEN_DATA_HEADER_SIZE = 16
GEN_DATA_RECORD_SIZE = 18


class Dataset(NamedTuple):
    """Loaded WDL self-play dataset.

    Arrays are aligned : black[i], white[i], stm[i], label[i] form one record.
    Labels are absolute (Black POV) : +1 = Black wins, -1 = White wins, 0 = draw.
    """

    black: np.ndarray  # uint64
    white: np.ndarray  # uint64
    stm:   np.ndarray  # uint8  (0 = Black, 1 = White)
    label: np.ndarray  # int8   (+1, 0, -1)

    @property
    def n_records(self) -> int:
        return len(self.black)


def load(path: str | Path) -> Dataset:
    """Read all records from a gen-data binary file."""
    raw = Path(path).read_bytes()
    if len(raw) < GEN_DATA_HEADER_SIZE:
        raise ValueError(f"file too short : {len(raw)} bytes")
    magic, version, count, _ = struct.unpack_from('<IIII', raw, 0)
    if magic != GEN_DATA_MAGIC:
        raise ValueError(f"bad magic 0x{magic:08X} (expected 0x{GEN_DATA_MAGIC:08X})")
    if version != GEN_DATA_VERSION:
        raise ValueError(f"unsupported version {version}")
    expected = GEN_DATA_HEADER_SIZE + count * GEN_DATA_RECORD_SIZE
    if len(raw) != expected:
        raise ValueError(f"size mismatch : got {len(raw)} expected {expected}")

    body = raw[GEN_DATA_HEADER_SIZE:]
    arr = np.frombuffer(body, dtype=np.dtype([
        ('black', '<u8'),
        ('white', '<u8'),
        ('stm',   'u1'),
        ('label', 'i1'),
    ]))
    return Dataset(
        black=arr['black'].copy(),
        white=arr['white'].copy(),
        stm=arr['stm'].copy(),
        label=arr['label'].copy(),
    )
