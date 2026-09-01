#!/usr/bin/env python3
"""Materialize a bounded zero-label JFI candidate prefix for timing only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

try:
    from .jfi_candidate_universe import JNNW_DTYPE
except ImportError:  # direct script execution from jobs/tools
    from jfi_candidate_universe import JNNW_DTYPE


MAX_RECORDS = 20_000


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def materialize_prefix(data_path, origin_path, records, out_data, out_origin):
    with open(data_path, "rb") as handle:
        header = handle.read(8)
    if len(header) != 8 or header[:4] != b"JNNW":
        raise ValueError("invalid candidate JNNW")
    total = struct.unpack_from("<I", header, 4)[0]
    if Path(data_path).stat().st_size != 8 + total * JNNW_DTYPE.itemsize:
        raise ValueError("candidate JNNW count/size drift")
    origin = np.load(origin_path, allow_pickle=False, mmap_mode="r")
    if origin.shape != (total,) or not 0 < records <= min(MAX_RECORDS, total):
        raise ValueError("candidate origin/prefix count drift")
    source = np.memmap(data_path, dtype=JNNW_DTYPE, mode="r", offset=8, shape=(total,))
    prefix = np.asarray(source[:records])
    if np.any(prefix["score"] != 0) or np.any(prefix["wdl"] != 0):
        raise ValueError("candidate prefix is not target blind")
    with open(out_data, "wb") as handle:
        handle.write(b"JNNW" + struct.pack("<I", records))
        handle.write(np.ascontiguousarray(prefix).tobytes())
    np.save(out_origin, np.asarray(origin[:records], dtype=np.uint32), allow_pickle=False)
    return {
        "schema": "jass.jfi.candidate_prefix.v1",
        "role": "bounded_selector_timing_only",
        "records": records,
        "source": {
            "data_sha256": sha256_file(data_path),
            "origin_indices_sha256": sha256_file(origin_path),
        },
        "outputs": {
            "data_sha256": sha256_file(out_data),
            "origin_indices_sha256": sha256_file(out_origin),
        },
        "guards": {"TARGET_READS": 0, "SCAN_READS": 0},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--origin-indices", required=True)
    ap.add_argument("--records", type=int, default=MAX_RECORDS)
    ap.add_argument("--out-data", required=True)
    ap.add_argument("--out-origin-indices", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    report = materialize_prefix(
        args.data, args.origin_indices, args.records,
        args.out_data, args.out_origin_indices,
    )
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
