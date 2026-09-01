#!/usr/bin/env python3
"""Split one common post-freeze Context30 target into JFI-C arm sidecars."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def split_targets(source, arm_count, dev_count):
    values = np.asarray(source)
    expected = 2 * arm_count + dev_count
    if values.shape != (expected,) or not np.all(np.isfinite(values)):
        raise ValueError("reference target shape/finite drift")
    if np.any(values < 0) or np.any(values > 1):
        raise ValueError("reference targets outside [0,1]")
    dev = values[2*arm_count:]
    active = np.concatenate((values[:arm_count], dev)).astype(np.float32)
    uniform = np.concatenate((values[arm_count:2*arm_count], dev)).astype(np.float32)
    return active, uniform


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference-targets", required=True)
    ap.add_argument("--arm-count", type=int, required=True)
    ap.add_argument("--dev-count", type=int, required=True)
    ap.add_argument("--active-out", required=True)
    ap.add_argument("--uniform-out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    source = np.load(args.reference_targets, allow_pickle=False, mmap_mode="r")
    active, uniform = split_targets(source, args.arm_count, args.dev_count)
    np.save(args.active_out, active, allow_pickle=False)
    np.save(args.uniform_out, uniform, allow_pickle=False)
    if not np.array_equal(active[-args.dev_count:], uniform[-args.dev_count:]):
        raise AssertionError("common DEV targets drift")
    report = {
        "schema": "jass.jfi.c_common_target_split.v1",
        "reference": {"path": args.reference_targets, "sha256": sha256_file(args.reference_targets)},
        "active": {"path": args.active_out, "sha256": sha256_file(args.active_out)},
        "uniform": {"path": args.uniform_out, "sha256": sha256_file(args.uniform_out)},
        "arm_train_rows": args.arm_count, "common_dev_rows": args.dev_count,
        "common_dev_targets_exact": True,
        "guards": {"selection_frozen_before_target_read": True, "SCAN_READS": 0},
    }
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
