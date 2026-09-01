#!/usr/bin/env python3
"""Publish the frozen JFI-D candidate's common-DEV static metrics."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jass_megacorpus_static_readout import (  # noqa: E402
    JNNW_DTYPE, JSM1_DTYPE, JSM2_DTYPE, metrics, open_counted, open_feat, score_model,
)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True); ap.add_argument("--meta", required=True)
    ap.add_argument("--feat", required=True); ap.add_argument("--targets", required=True)
    ap.add_argument("--model", required=True); ap.add_argument("--identifiability", required=True)
    ap.add_argument("--train-count", type=int, required=True); ap.add_argument("--chunk", type=int, default=20_000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    records, count = open_counted(args.data, {b"JNNW": JNNW_DTYPE})
    metadata, meta_count = open_counted(args.meta, {b"JSM1": JSM1_DTYPE, b"JSM2": JSM2_DTYPE})
    feat = open_feat(args.feat, count)
    target = np.load(args.targets, allow_pickle=False, mmap_mode="r")
    ident = json.loads(Path(args.identifiability).read_text())
    if (
        meta_count != count or target.shape != (count,) or args.train_count != 4_000_000
        or not args.train_count < count or ident.get("records") != args.train_count
    ):
        raise SystemExit("JFI-D input/count/identifiability drift")
    logits = score_model(args.model, records, feat, args.train_count, args.chunk)
    dev_target = np.asarray(target[args.train_count:], dtype=np.float64)
    openings = np.asarray(metadata[args.train_count:]["opening_id"], dtype=np.uint64)
    report = {
        "schema": "jass.jfi.d_candidate_readout.v1",
        "verdict": "JFI_D_JASS_NATIVE_ACTIVE_V1_FROZEN",
        "candidate_name": "JASS_NATIVE_ACTIVE_V1",
        "train_rows": args.train_count, "dev_rows": int(len(dev_target)),
        "dev_unique_openings": int(len(np.unique(openings))),
        "dev_metrics": metrics(logits, dev_target),
        "selected_l2": ident["selected_l2"],
        "identifiability": {
            key: ident[key] for key in (
                "coordinates", "class_counts", "fisher_quantiles",
                "posterior_variance_proxy_quantiles", "effective_df",
            )
        },
        "model": {"path": args.model, "sha256": sha256_file(args.model)},
        "targets": {"path": args.targets, "sha256": sha256_file(args.targets)},
        "markers": {
            "SCAN_READS": 0, "FRESH_OPENINGS": 0, "STRENGTH_GAMES": 0,
            "PROMOTION_AUTHORIZED": False,
        },
        "next_boundary": "BOUNDARY C",
    }
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
