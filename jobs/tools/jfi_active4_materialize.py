#!/usr/bin/env python3
"""Materialize frozen JFI-D ACTIVE_4M plus the common DEV tail post-selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

try:
    from .jfi_active_materialize import open_feat, verify_selection_file, write_feat, write_jnnw, write_jsm1
    from .jfi_candidate_universe import (
        JNNW_DTYPE, JSM1_DTYPE, JSM2_DTYPE, open_counted, sha256_file,
    )
except ImportError:  # direct script execution from jobs/tools
    from jfi_active_materialize import open_feat, verify_selection_file, write_feat, write_jnnw, write_jsm1
    from jfi_candidate_universe import (
        JNNW_DTYPE, JSM1_DTYPE, JSM2_DTYPE, open_counted, sha256_file,
    )


def materialize(args):
    candidate_manifest = json.loads(Path(args.candidate_manifest).read_text())
    selection = json.loads(Path(args.selection_manifest).read_text())
    if candidate_manifest.get("schema") != "jass.jfi.candidate_universe.v1":
        raise ValueError("candidate-universe manifest schema drift")
    if selection.get("schema") != "jass.jfi.d_active_selection.v1":
        raise ValueError("JFI-D selection manifest schema drift")
    if selection.get("guards", {}).get("TARGET_READS_BEFORE_MANIFEST_FREEZE") != 0:
        raise ValueError("JFI-D selection is not target blind")
    candidate_digests = {
        "data": sha256_file(args.candidate_data), "meta": sha256_file(args.candidate_meta),
        "origin_indices": sha256_file(args.origin_indices),
    }
    for label, digest in candidate_digests.items():
        if digest != (candidate_manifest.get("files", {}).get(label) or {}).get("sha256"):
            raise ValueError(f"candidate-universe {label} SHA drift")
    links = selection.get("inputs", {})
    expected = {
        "candidate_manifest": sha256_file(args.candidate_manifest),
        "candidate_data": candidate_digests["data"],
        "candidate_feat": sha256_file(args.candidate_feat),
        "origin_indices": candidate_digests["origin_indices"],
    }
    for label, digest in expected.items():
        if (links.get(label) or {}).get("sha256") != digest:
            raise ValueError(f"JFI-D selection {label} SHA link drift")
    verify_selection_file(selection, "active_indices", args.active_indices)
    candidate, _ = open_counted(args.candidate_data, {b"JNNW": JNNW_DTYPE})
    candidate_meta, _ = open_counted(
        args.candidate_meta, {b"JSM1": JSM1_DTYPE, b"JSM2": JSM2_DTYPE},
    )
    source, _ = open_counted(args.source_data, {b"JNNW": JNNW_DTYPE})
    source_meta, _ = open_counted(
        args.source_meta, {b"JSM1": JSM1_DTYPE, b"JSM2": JSM2_DTYPE},
    )
    frozen_source = candidate_manifest.get("source", {})
    if (
        sha256_file(args.source_data) != frozen_source.get("data_sha256")
        or sha256_file(args.source_meta) != frozen_source.get("meta_sha256")
    ):
        raise ValueError("authenticated 40M source SHA drift")
    feat, width = open_feat(args.candidate_feat, len(candidate))
    origin = np.load(args.origin_indices, allow_pickle=False, mmap_mode="r")
    active = np.load(args.active_indices, allow_pickle=False)
    if (
        len(candidate_meta) != len(candidate) or origin.shape != (len(candidate),)
        or len(source_meta) != len(source) or not len(active)
        or np.any(active >= args.train_count)
    ):
        raise ValueError("JFI-D ACTIVE_4M alignment/count drift")
    if args.production and len(active) != 4_000_000:
        raise ValueError("production JFI-D requires exactly 4,000,000 ACTIVE rows")
    dev = np.arange(args.train_count, len(candidate), dtype=np.uint32)
    if not len(dev):
        raise ValueError("JFI-D DEV tail is empty")
    indices = np.concatenate((active, dev)).astype(np.uint32, copy=False)
    write_jnnw(
        args.out_data, source, source_meta, origin, candidate, candidate_meta,
        indices, args.chunk,
    )
    write_jsm1(args.out_meta, candidate_meta, indices, args.chunk)
    write_feat(args.out_feat, feat, indices, width, args.chunk)
    report = {
        "schema": "jass.jfi.d_post_selection_materialization.v1",
        "counts": {"active_train": int(len(active)), "dev_eval": int(len(dev))},
        "ordering": "ACTIVE_4M,DEV_EVAL",
        "selection_manifest": {
            "path": args.selection_manifest, "sha256": sha256_file(args.selection_manifest),
        },
        "files": {
            "data": {"path": args.out_data, "sha256": sha256_file(args.out_data)},
            "meta": {"path": args.out_meta, "sha256": sha256_file(args.out_meta)},
            "feat": {"path": args.out_feat, "sha256": sha256_file(args.out_feat)},
        },
        "guards": {
            "selection_manifest_verified_before_source_label_access": True,
            "TARGET_READS_BEFORE_MANIFEST_FREEZE": 0, "SCAN_READS": 0,
        },
    }
    Path(args.manifest).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate-data", "candidate-meta", "candidate-feat", "candidate-manifest",
                 "origin-indices", "source-data", "source-meta", "selection-manifest",
                 "active-indices", "out-data", "out-meta", "out-feat", "manifest"):
        ap.add_argument(f"--{name}", required=True)
    ap.add_argument("--train-count", required=True, type=int)
    ap.add_argument("--chunk", type=int, default=200_000)
    ap.add_argument("--production", action="store_true")
    args = ap.parse_args(argv)
    materialize(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
