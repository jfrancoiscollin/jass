#!/usr/bin/env python3
"""Materialize JFI-C arms after immutable target-blind row-ID manifests exist."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

from jobs.tools.jfi_candidate_universe import (
    JNNW_DTYPE, JSM1_DTYPE, JSM2_DTYPE, STATE_FIELDS, open_counted, sha256_file,
)


def open_feat(path, count):
    with open(path, "rb") as handle:
        header = handle.read(12)
    if len(header) != 12 or header[:4] != b"FEAT":
        raise ValueError(f"{path}: invalid FEAT")
    rows, width = struct.unpack_from("<II", header, 4)
    if rows != count or Path(path).stat().st_size != 12 + rows * width * 4:
        raise ValueError(f"{path}: FEAT shape drift")
    return np.memmap(path, dtype="<f4", mode="r", offset=12, shape=(rows, width)), width


def verify_selection_file(manifest, label, path):
    expected = manifest["files"][label]["sha256"]
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{label} immutable manifest SHA drift")


def write_jnnw(path, source, source_meta, origin, candidate, candidate_meta,
               candidate_indices, chunk):
    with open(path, "wb") as handle:
        handle.write(b"JNNW" + struct.pack("<I", len(candidate_indices)))
        for start in range(0, len(candidate_indices), chunk):
            selected = np.asarray(candidate_indices[start:start + chunk], dtype=np.int64)
            source_index = np.asarray(origin[selected], dtype=np.int64)
            source_rows = np.asarray(source[source_index])
            source_metadata = np.asarray(source_meta[source_index])
            candidate_rows = np.asarray(candidate[selected])
            candidate_metadata = np.asarray(candidate_meta[selected])
            for field in STATE_FIELDS:
                if not np.array_equal(source_rows[field], candidate_rows[field]):
                    raise ValueError(f"selected source/candidate state drift in {field}")
            for field in JSM1_DTYPE.names:
                if not np.array_equal(source_metadata[field], candidate_metadata[field]):
                    raise ValueError(f"selected source/candidate metadata drift in {field}")
            handle.write(np.ascontiguousarray(source_rows).tobytes())


def write_jsm1(path, meta, indices, chunk):
    with open(path, "wb") as handle:
        handle.write(b"JSM1" + struct.pack("<I", len(indices)))
        for start in range(0, len(indices), chunk):
            selected = np.asarray(meta[indices[start:start + chunk]])
            if selected.dtype != JSM1_DTYPE:
                clean = np.empty(len(selected), dtype=JSM1_DTYPE)
                for field in JSM1_DTYPE.names:
                    clean[field] = selected[field]
                selected = clean
            handle.write(np.ascontiguousarray(selected).tobytes())


def write_feat(path, feat, indices, width, chunk):
    with open(path, "wb") as handle:
        handle.write(b"FEAT" + struct.pack("<II", len(indices), width))
        for start in range(0, len(indices), chunk):
            selected = np.asarray(feat[indices[start:start + chunk]], dtype="<f4")
            handle.write(np.ascontiguousarray(selected).tobytes())


def materialize(args):
    candidate_manifest = json.loads(Path(args.candidate_manifest).read_text())
    if candidate_manifest.get("schema") != "jass.jfi.candidate_universe.v1":
        raise ValueError("unexpected candidate-universe manifest schema")
    selection = json.loads(Path(args.selection_manifest).read_text())
    if selection.get("schema") != "jass.jfi.c_active_uniform_selection.v1":
        raise ValueError("unexpected selection manifest schema")
    if selection.get("guards", {}).get("TARGET_READS_BEFORE_MANIFEST_FREEZE") != 0:
        raise ValueError("selection manifest is not target blind")
    frozen = candidate_manifest.get("files", {})
    candidate_digests = {
        "data": sha256_file(args.candidate_data),
        "meta": sha256_file(args.candidate_meta),
        "origin_indices": sha256_file(args.origin_indices),
    }
    for label, path in (("data", args.candidate_data), ("meta", args.candidate_meta),
                        ("origin_indices", args.origin_indices)):
        if candidate_digests[label] != (frozen.get(label) or {}).get("sha256"):
            raise ValueError(f"candidate-universe {label} SHA drift")
    inputs = selection.get("inputs", {})
    expected_links = {
        "candidate_manifest": (args.candidate_manifest, sha256_file(args.candidate_manifest)),
        "candidate_data": (args.candidate_data, candidate_digests["data"]),
        "origin_indices": (args.origin_indices, candidate_digests["origin_indices"]),
    }
    for label, (_path, digest) in expected_links.items():
        if (inputs.get(label) or {}).get("sha256") != digest:
            raise ValueError(f"selection-to-candidate {label} SHA link drift")
    verify_selection_file(selection, "active_indices", args.active_indices)
    verify_selection_file(selection, "uniform_indices", args.uniform_indices)
    candidate, _ = open_counted(args.candidate_data, {b"JNNW": JNNW_DTYPE})
    candidate_meta, _ = open_counted(
        args.candidate_meta, {b"JSM1": JSM1_DTYPE, b"JSM2": JSM2_DTYPE},
    )
    source, _ = open_counted(args.source_data, {b"JNNW": JNNW_DTYPE})
    source_meta, _ = open_counted(
        args.source_meta, {b"JSM1": JSM1_DTYPE, b"JSM2": JSM2_DTYPE},
    )
    source_frozen = candidate_manifest.get("source", {})
    if (
        sha256_file(args.source_data) != source_frozen.get("data_sha256")
        or sha256_file(args.source_meta) != source_frozen.get("meta_sha256")
    ):
        raise ValueError("authenticated 40M source SHA drift")
    feat, width = open_feat(args.candidate_feat, len(candidate))
    origin = np.load(args.origin_indices, allow_pickle=False, mmap_mode="r")
    active = np.load(args.active_indices, allow_pickle=False)
    uniform = np.load(args.uniform_indices, allow_pickle=False)
    if len(candidate_meta) != len(candidate) or origin.shape != (len(candidate),):
        raise ValueError("candidate alignment drift")
    if len(source_meta) != len(source):
        raise ValueError("source alignment drift")
    if len(active) != len(uniform) or not len(active):
        raise ValueError("ACTIVE/UNIFORM counts must be equal and non-zero")
    if args.production and len(active) != 2_000_000:
        raise ValueError("production JFI-C arms must contain exactly 2,000,000 rows")
    if np.any(active >= args.train_count) or np.any(uniform >= args.train_count):
        raise ValueError("selection includes DEV row")
    if np.intersect1d(active, uniform).size:
        raise ValueError("ACTIVE/UNIFORM selections overlap")
    dev = np.arange(args.train_count, len(candidate), dtype=np.uint32)
    if not len(dev):
        raise ValueError("DEV_EVAL is empty")
    reference = np.concatenate((active, uniform, dev)).astype(np.uint32, copy=False)
    active_arm = np.concatenate((active, dev)).astype(np.uint32, copy=False)
    uniform_arm = np.concatenate((uniform, dev)).astype(np.uint32, copy=False)
    outputs = {
        "reference": (reference, args.reference_data, args.reference_meta, args.reference_feat),
        "active": (active_arm, args.active_data, args.active_meta, args.active_feat),
        "uniform": (uniform_arm, args.uniform_data, args.uniform_meta, args.uniform_feat),
    }
    for _label, (indices, data_path, meta_path, feat_path) in outputs.items():
        write_jnnw(
            data_path, source, source_meta, origin, candidate, candidate_meta,
            indices, args.chunk,
        )
        write_jsm1(meta_path, candidate_meta, indices, args.chunk)
        write_feat(feat_path, feat, indices, width, args.chunk)
    files = {}
    for label, (_indices, data_path, meta_path, feat_path) in outputs.items():
        files[label] = {
            "data": {"path": data_path, "sha256": sha256_file(data_path)},
            "meta": {"path": meta_path, "sha256": sha256_file(meta_path)},
            "feat": {"path": feat_path, "sha256": sha256_file(feat_path)},
        }
    report = {
        "schema": "jass.jfi.c_post_selection_materialization.v1",
        "selection_manifest": {
            "path": args.selection_manifest, "sha256": sha256_file(args.selection_manifest),
        },
        "candidate_manifest": {
            "path": args.candidate_manifest, "sha256": sha256_file(args.candidate_manifest),
        },
        "counts": {
            "active_train": int(len(active)), "uniform_train": int(len(uniform)),
            "dev_eval": int(len(dev)), "reference_train": int(2 * len(active)),
        },
        "ordering": {
            "reference": "ACTIVE,UNIFORM,DEV", "active": "ACTIVE,DEV",
            "uniform": "UNIFORM,DEV", "common_dev_tail": True,
        },
        "files": files,
        "guards": {
            "selection_manifest_verified_before_source_label_access": True,
            "source_terminal_label_rows_read_post_freeze": int(len(reference)),
            "TARGET_READS_BEFORE_MANIFEST_FREEZE": 0, "SCAN_READS": 0,
        },
    }
    Path(args.manifest).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-data", required=True)
    ap.add_argument("--candidate-meta", required=True)
    ap.add_argument("--candidate-feat", required=True)
    ap.add_argument("--candidate-manifest", required=True)
    ap.add_argument("--origin-indices", required=True)
    ap.add_argument("--source-data", required=True)
    ap.add_argument("--source-meta", required=True)
    ap.add_argument("--selection-manifest", required=True)
    ap.add_argument("--active-indices", required=True)
    ap.add_argument("--uniform-indices", required=True)
    ap.add_argument("--train-count", required=True, type=int)
    ap.add_argument("--reference-data", required=True)
    ap.add_argument("--reference-meta", required=True)
    ap.add_argument("--reference-feat", required=True)
    ap.add_argument("--active-data", required=True)
    ap.add_argument("--active-meta", required=True)
    ap.add_argument("--active-feat", required=True)
    ap.add_argument("--uniform-data", required=True)
    ap.add_argument("--uniform-meta", required=True)
    ap.add_argument("--uniform-feat", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--chunk", type=int, default=200_000)
    ap.add_argument("--production", action="store_true")
    args = ap.parse_args(argv)
    materialize(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
