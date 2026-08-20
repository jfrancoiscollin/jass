#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Assemble train/holdout corpora for the exploratory four-arm replay DOE.

The caller first applies the existing opening-level ``selfplay_frontier split``
to D1 and D2.  This tool then creates:

* A train: every D2 train row, no holdout rows;
* OLD holdout and NEW holdout as immutable tail-only counted pairs;
* D train: every D1 and D2 train row, source-namespaced, with float32
  sample weights imposing exactly 50/50 effective source loss mass.

B/C are deliberately built by ``tools/contextual_replay_mix.py`` so the primary
replay implementation is exercised directly.  This tool never reads a holdout
row into a training output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import contextual_replay_mix as crm  # noqa: E402
import selfplay_frontier as sf  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_new(*paths: Path) -> None:
    resolved = [p.resolve(strict=False) for p in paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("all output paths must be distinct")
    for path in paths:
        if path.exists():
            raise ValueError(f"refusing to overwrite {path}")
        path.parent.mkdir(parents=True, exist_ok=True)


def _write_range(
    *,
    data: Path,
    meta: Path,
    start: int,
    stop: int,
    out_data: Path,
    out_meta: Path,
) -> dict:
    total = sf._counted_file_count(data, sf.JNNW_MAGIC, sf.JNNW_REC)
    schema, meta_total = sf._meta_file_info(meta)
    if meta_total != total:
        raise ValueError("data/meta count mismatch")
    if not 0 <= start <= stop <= total:
        raise ValueError(f"invalid slice [{start},{stop}) for total={total}")
    count = stop - start
    _require_new(out_data, out_meta)
    data_tmp = out_data.with_name(out_data.name + ".tmp")
    meta_tmp = out_meta.with_name(out_meta.name + ".tmp")
    cursor = 0
    try:
        with data_tmp.open("wb") as data_out, meta_tmp.open("wb") as meta_out:
            data_out.write(sf.JNNW_MAGIC + struct.pack("<I", count))
            meta_out.write(schema.magic + struct.pack("<I", count))
            for index, record, row in sf.iter_pair(data, meta):
                if index < start:
                    continue
                if index >= stop:
                    break
                data_out.write(record)
                meta_out.write(
                    sf._encode_meta(row, schema, context=f"slice record {index}")
                )
                cursor += 1
        if cursor != count:
            raise ValueError(f"slice wrote {cursor} rows, expected {count}")
        data_tmp.replace(out_data)
        meta_tmp.replace(out_meta)
    finally:
        for tmp in (data_tmp, meta_tmp):
            if tmp.exists():
                tmp.unlink()
    return {
        "records": count,
        "metadata_schema": schema.name,
        "data_sha256": _sha256(out_data),
        "meta_sha256": _sha256(out_meta),
    }


def _write_full_history(
    *,
    old_data: Path,
    old_meta: Path,
    old_train: int,
    new_data: Path,
    new_meta: Path,
    new_train: int,
    out_data: Path,
    out_meta: Path,
    out_weights: Path,
) -> dict:
    old_total = sf._counted_file_count(old_data, sf.JNNW_MAGIC, sf.JNNW_REC)
    new_total = sf._counted_file_count(new_data, sf.JNNW_MAGIC, sf.JNNW_REC)
    old_schema, old_meta_total = sf._meta_file_info(old_meta)
    new_schema, new_meta_total = sf._meta_file_info(new_meta)
    if old_meta_total != old_total or new_meta_total != new_total:
        raise ValueError("full-history data/meta count mismatch")
    if old_schema is not new_schema:
        raise ValueError("D1/D2 metadata schemas differ")
    if not (0 < old_train <= old_total and 0 < new_train <= new_total):
        raise ValueError("invalid train counts")
    total = old_train + new_train
    _require_new(out_data, out_meta, out_weights)
    data_tmp = out_data.with_name(out_data.name + ".tmp")
    meta_tmp = out_meta.with_name(out_meta.name + ".tmp")
    weights_tmp = out_weights.with_name(out_weights.name + ".tmp")
    weights = np.lib.format.open_memmap(
        weights_tmp, mode="w+", dtype=np.float32, shape=(total,)
    )
    old_weight = np.float32(0.5 * total / old_train)
    new_weight = np.float32(0.5 * total / new_train)
    weights[:old_train] = old_weight
    weights[old_train:] = new_weight
    weights.flush()
    del weights

    cursor = 0
    source_stats: dict[str, dict[str, int]] = {}
    try:
        with data_tmp.open("wb") as data_out, meta_tmp.open("wb") as meta_out:
            data_out.write(sf.JNNW_MAGIC + struct.pack("<I", total))
            meta_out.write(old_schema.magic + struct.pack("<I", total))
            for label, source_index, data, meta, limit in (
                ("OLD", 1, old_data, old_meta, old_train),
                ("NEW", 2, new_data, new_meta, new_train),
            ):
                games: dict[int, int] = {}
                openings: dict[int, int] = {}
                written = 0
                for index, record, row in sf.iter_pair(data, meta):
                    if index >= limit:
                        break
                    rewritten = crm._namespaced_meta(
                        row,
                        source_index=source_index,
                        game_map=games,
                        opening_map=openings,
                        out_schema=old_schema,
                    )
                    encoded = sf._encode_meta(
                        rewritten, old_schema, context=f"full-history {label} record {index}"
                    )
                    data_out.write(record)
                    meta_out.write(encoded)
                    cursor += 1
                    written += 1
                if written != limit:
                    raise ValueError(f"{label}: wrote {written}, expected {limit}")
                source_stats[label] = {
                    "records": written,
                    "games": len(games),
                    "openings": len(openings),
                }
        if cursor != total:
            raise ValueError(f"full-history wrote {cursor}, expected {total}")
        data_tmp.replace(out_data)
        meta_tmp.replace(out_meta)
        weights_tmp.replace(out_weights)
    finally:
        for tmp in (data_tmp, meta_tmp, weights_tmp):
            if tmp.exists():
                tmp.unlink()

    final_weights = np.load(out_weights, allow_pickle=False, mmap_mode="r")
    old_mass = float(np.sum(final_weights[:old_train], dtype=np.float64))
    new_mass = float(np.sum(final_weights[old_train:], dtype=np.float64))
    share = old_mass / (old_mass + new_mass)
    if not math.isclose(share, 0.5, abs_tol=2e-7):
        raise ValueError(f"full-history effective OLD share drift: {share}")
    return {
        "records": total,
        "metadata_schema": old_schema.name,
        "source_namespaced": True,
        "sources": source_stats,
        "requested_effective_loss_mass": {"OLD": 0.5, "NEW": 0.5},
        "realised_effective_loss_mass": {"OLD": share, "NEW": 1.0 - share},
        "sample_weights": {
            "dtype": "float32",
            "OLD_raw_weight": float(old_weight),
            "NEW_raw_weight": float(new_weight),
            "min": float(min(old_weight, new_weight)),
            "max": float(max(old_weight, new_weight)),
            "sha256": _sha256(out_weights),
        },
        "data_sha256": _sha256(out_data),
        "meta_sha256": _sha256(out_meta),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-data", required=True)
    parser.add_argument("--old-meta", required=True)
    parser.add_argument("--old-split", required=True)
    parser.add_argument("--new-data", required=True)
    parser.add_argument("--new-meta", required=True)
    parser.add_argument("--new-split", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)

    old_data, old_meta, old_split = map(Path, (args.old_data, args.old_meta, args.old_split))
    new_data, new_meta, new_split = map(Path, (args.new_data, args.new_meta, args.new_split))
    out = Path(args.out_dir)
    manifest = Path(args.manifest)
    if manifest.exists():
        raise ValueError(f"refusing to overwrite {manifest}")
    out.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    old_total = sf._counted_file_count(old_data, sf.JNNW_MAGIC, sf.JNNW_REC)
    new_total = sf._counted_file_count(new_data, sf.JNNW_MAGIC, sf.JNNW_REC)
    old_contract, old_train = sf._load_split_manifest(old_split, old_total)
    new_contract, new_train = sf._load_split_manifest(new_split, new_total)
    old_train_openings, old_holdout_openings = sf._split_opening_sets(
        old_split, old_meta, old_total, old_train
    )
    new_train_openings, new_holdout_openings = sf._split_opening_sets(
        new_split, new_meta, new_total, new_train
    )

    a = _write_range(
        data=new_data, meta=new_meta, start=0, stop=new_train,
        out_data=out / "A-current.jnnw", out_meta=out / "A-current.jsm",
    )
    old_holdout = _write_range(
        data=old_data, meta=old_meta, start=old_train, stop=old_total,
        out_data=out / "OLD-holdout.jnnw", out_meta=out / "OLD-holdout.jsm",
    )
    new_holdout = _write_range(
        data=new_data, meta=new_meta, start=new_train, stop=new_total,
        out_data=out / "NEW-holdout.jnnw", out_meta=out / "NEW-holdout.jsm",
    )
    full = _write_full_history(
        old_data=old_data, old_meta=old_meta, old_train=old_train,
        new_data=new_data, new_meta=new_meta, new_train=new_train,
        out_data=out / "D-full-history.jnnw",
        out_meta=out / "D-full-history.jsm",
        out_weights=out / "D-full-history-weights.npy",
    )

    payload = {
        "schema": "jass.l3_exploratory_replay_doe_assembly.v1",
        "split_seed": old_contract.get("seed"),
        "holdout_mod": old_contract.get("holdout_mod"),
        "holdout_rows_read_into_training": 0,
        "OLD": {
            "records": old_total,
            "train_records": old_train,
            "holdout_records": old_total - old_train,
            "train_openings": len(old_train_openings),
            "holdout_openings": len(old_holdout_openings),
            "train_holdout_opening_overlap": 0,
            "source_data_sha256": _sha256(old_data),
            "source_meta_sha256": _sha256(old_meta),
            "split_manifest_sha256": _sha256(old_split),
        },
        "NEW": {
            "records": new_total,
            "train_records": new_train,
            "holdout_records": new_total - new_train,
            "train_openings": len(new_train_openings),
            "holdout_openings": len(new_holdout_openings),
            "train_holdout_opening_overlap": 0,
            "source_data_sha256": _sha256(new_data),
            "source_meta_sha256": _sha256(new_meta),
            "split_manifest_sha256": _sha256(new_split),
        },
        "outputs": {
            "A_CURRENT_train": a,
            "OLD_holdout": old_holdout,
            "NEW_holdout": new_holdout,
            "D_FULL_HISTORY_NO_PRIOR_train": full,
        },
        "target_semantics": "native_JNNW_WDL",
        "promotion_authorized": False,
    }
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
