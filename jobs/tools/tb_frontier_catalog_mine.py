#!/usr/bin/env python3
"""Mine exact TB-frontier sibling decisions from a frozen MegaCorpus R2 census.

The catalog is metadata-only.  This tool selects every DIRECT R2 JNNW candidate
whose census disposition is not ``reject``.  Candidate labels/scores are never
used: each payload is passed to the standalone ``jass_tb_frontier`` extractor,
which keeps only K+1-piece parents whose legal capture siblings ALL fall inside
EGDB and have exact, non-homogeneous WLD outcomes.

Results are merged with exact parent-fingerprint de-duplication across sources.
The output groups/children keep the schema expected by tb_frontier_pairwise.py.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any, Iterable, TextIO

JNNW_RECORD_SIZE = 38
GROUP_FIELDS = [
    "row_index", "parent_id", "parent_fingerprint", "parent_stm",
    "from", "to", "num_captures", "promotes", "moving_king",
    "captured_kings", "parent_utility", "child_tb_wdl_stm",
]


def open_text_maybe_gzip(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("rt", encoding="utf-8")


def load_catalog(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open_text_maybe_gzip(path) as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"catalog line {line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"catalog line {line_no}: not an object")
            rows.append(row)
    if not rows:
        raise ValueError("empty catalog")
    return rows


def candidate_payload_key(row: dict[str, Any]) -> str:
    data = row.get("data") or {}
    digest = data.get("declared_sha256")
    if isinstance(digest, str) and len(digest) == 64:
        return f"sha256:{digest}"
    uri = data.get("r2_uri")
    return f"uri:{uri}"


def select_direct_candidates(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    direct: list[dict[str, Any]] = []
    seen_payloads: set[str] = set()
    counts = {
        "catalog_rows": 0,
        "direct_rows": 0,
        "rejected_rows": 0,
        "duplicate_payload_rows": 0,
        "selected_rows": 0,
    }
    ordered = sorted(rows, key=lambda r: (
        str((r.get("data") or {}).get("path") or ""),
        str(r.get("candidate_id") or ""),
    ))
    for row in ordered:
        counts["catalog_rows"] += 1
        data = row.get("data") or {}
        quality = row.get("quality") or {}
        uri = data.get("r2_uri")
        path = data.get("path")
        if not isinstance(uri, str) or not uri or not isinstance(path, str):
            continue
        if not (path.lower().endswith(".jnnw") or path.lower().endswith(".jnnw.gz")):
            continue
        counts["direct_rows"] += 1
        if quality.get("disposition") == "reject":
            counts["rejected_rows"] += 1
            continue
        key = candidate_payload_key(row)
        if key in seen_payloads:
            counts["duplicate_payload_rows"] += 1
            continue
        seen_payloads.add(key)
        direct.append(row)
    counts["selected_rows"] = len(direct)
    return direct, counts


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def materialize_raw_jnnw(download: Path, raw_out: Path, remote_path: str) -> tuple[int, int]:
    """Decompress/validate counted JNNW. Returns (records, raw_bytes)."""
    opener = gzip.open if remote_path.lower().endswith(".gz") else open
    with opener(download, "rb") as src, raw_out.open("wb") as dst:  # type: ignore[arg-type]
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    size = raw_out.stat().st_size
    if size < 8:
        raise ValueError("payload shorter than JNNW header")
    with raw_out.open("rb") as f:
        header = f.read(8)
    if header[:4] != b"JNNW":
        raise ValueError("not counted JNNW")
    n = struct.unpack_from("<I", header, 4)[0]
    expected = 8 + n * JNNW_RECORD_SIZE
    if size != expected:
        raise ValueError(f"count/size drift n={n} size={size} expected={expected}")
    return n, size


def load_child_records(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError("extractor children: bad JNNW header")
    n = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + n * JNNW_RECORD_SIZE:
        raise ValueError("extractor children: count/size drift")
    return [raw[8 + i * JNNW_RECORD_SIZE:8 + (i + 1) * JNNW_RECORD_SIZE] for i in range(n)]


def load_group_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if reader.fieldnames != GROUP_FIELDS:
            raise ValueError(f"unexpected groups fields: {reader.fieldnames!r}")
        rows = list(reader)
    if [int(r["row_index"]) for r in rows] != list(range(len(rows))):
        raise ValueError("source groups row_index is not contiguous")
    return rows


def split_is_holdout(fingerprint: str, seed: int, mod: int) -> bool:
    digest = hashlib.sha256(f"{seed}:{fingerprint}".encode()).digest()
    return int.from_bytes(digest[:8], "little") % mod == 0


def json_dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows = load_catalog(args.catalog)
    candidates, selection_counts = select_direct_candidates(rows)
    if args.max_candidates > 0:
        candidates = candidates[: args.max_candidates]
        selection_counts["selected_rows_after_cap"] = len(candidates)
    if not candidates:
        raise ValueError("catalog contains no usable direct R2 JNNW candidates")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.out_children.parent.mkdir(parents=True, exist_ok=True)
    args.out_groups.parent.mkdir(parents=True, exist_ok=True)
    args.source_report.parent.mkdir(parents=True, exist_ok=True)
    args.parent_provenance.parent.mkdir(parents=True, exist_ok=True)

    seen_parents: set[str] = set()
    next_parent_id = 0
    next_row_index = 0
    total_source_records = 0
    total_informative_occurrences = 0
    duplicate_informative_parents = 0
    valid_sources = 0
    unsupported_sources = 0
    selected_bytes_known = 0
    global_parent_color: dict[str, int] = {}
    source_summaries: list[dict[str, Any]] = []

    with args.out_children.open("wb+") as child_out, \
         args.out_groups.open("w", newline="", encoding="utf-8") as group_out, \
         args.source_report.open("w", encoding="utf-8") as source_out, \
         args.parent_provenance.open("w", encoding="utf-8") as prov_out:
        child_out.write(b"JNNW" + struct.pack("<I", 0))
        writer = csv.DictWriter(group_out, fieldnames=GROUP_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()

        for ordinal, candidate in enumerate(candidates, 1):
            data = candidate["data"]
            uri = data["r2_uri"]
            path = data["path"]
            size_bytes = data.get("size_bytes")
            if isinstance(size_bytes, int):
                selected_bytes_known += size_bytes
            cid = str(candidate.get("candidate_id") or f"candidate-{ordinal}")
            stem = f"src-{ordinal:04d}"
            download = args.work_dir / (stem + (".jnnw.gz" if path.lower().endswith(".gz") else ".jnnw"))
            raw = args.work_dir / f"{stem}.raw.jnnw"
            children = args.work_dir / f"{stem}.children.jnnw"
            groups = args.work_dir / f"{stem}.groups.tsv"
            report = args.work_dir / f"{stem}.frontier.json"
            item: dict[str, Any] = {
                "candidate_id": cid,
                "r2_uri": uri,
                "path": path,
                "declared_sha256": data.get("declared_sha256"),
                "size_bytes": size_bytes,
                "quality": candidate.get("quality"),
                "ordinal": ordinal,
            }
            try:
                subprocess.run(
                    [args.rclone_binary, "copyto", uri, str(download)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=args.copy_timeout_seconds,
                )
                if args.verify_declared_sha and isinstance(data.get("declared_sha256"), str):
                    # Runner inventories hash stored payload bytes, so compare before decompression.
                    item["download_sha256"] = sha256_file(download)
                    item["declared_sha_matches_download"] = item["download_sha256"] == data["declared_sha256"]
                n, raw_bytes = materialize_raw_jnnw(download, raw, path)
                item["records"] = n
                item["raw_bytes"] = raw_bytes
                total_source_records += n
                cmd = [
                    str(args.extractor), str(raw), str(children), str(groups), str(report),
                    str(args.egdb_dir), str(args.cache_mb), str(args.parent_pieces),
                ]
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                item["extractor_stdout"] = proc.stdout[-2000:]
                item["extractor_stderr"] = proc.stderr[-2000:]
                if proc.returncode != 0:
                    raise RuntimeError(f"extractor failed rc={proc.returncode}: {proc.stderr[-1000:]}")
                frep = json.loads(report.read_text(encoding="utf-8"))
                item["frontier"] = frep
                valid_sources += 1
                total_informative_occurrences += int(frep.get("informative_parents", 0))

                child_records = load_child_records(children)
                group_rows = load_group_rows(groups)
                if len(group_rows) != len(child_records):
                    raise ValueError("extractor groups/children row mismatch")
                by_parent: dict[int, list[dict[str, str]]] = {}
                parent_order: list[int] = []
                for row in group_rows:
                    pid = int(row["parent_id"])
                    if pid not in by_parent:
                        by_parent[pid] = []
                        parent_order.append(pid)
                    by_parent[pid].append(row)
                kept_here = 0
                for old_pid in parent_order:
                    prows = by_parent[old_pid]
                    fp = prows[0]["parent_fingerprint"]
                    stm = int(prows[0]["parent_stm"])
                    if any(r["parent_fingerprint"] != fp or int(r["parent_stm"]) != stm for r in prows):
                        raise ValueError("source parent id maps to inconsistent fingerprint/color")
                    if fp in seen_parents:
                        duplicate_informative_parents += 1
                        continue
                    seen_parents.add(fp)
                    global_parent_color[fp] = stm
                    new_pid = next_parent_id
                    next_parent_id += 1
                    for r in prows:
                        old_index = int(r["row_index"])
                        child_out.write(child_records[old_index])
                        out = dict(r)
                        out["row_index"] = str(next_row_index)
                        out["parent_id"] = str(new_pid)
                        writer.writerow(out)
                        next_row_index += 1
                    prov_out.write(json.dumps({
                        "schema": "jass.tb_frontier.parent_provenance.v1",
                        "parent_id": new_pid,
                        "parent_fingerprint": fp,
                        "parent_stm": stm,
                        "candidate_id": cid,
                        "r2_uri": uri,
                        "source_parent_id": old_pid,
                    }, sort_keys=True) + "\n")
                    kept_here += 1
                item["unique_parents_added"] = kept_here
            except (OSError, ValueError, gzip.BadGzipFile) as exc:
                unsupported_sources += 1
                item["status"] = "unsupported_payload"
                item["error"] = str(exc)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"R2 copy timeout for {uri}") from exc
            finally:
                for p in (download, raw, children, groups, report):
                    try:
                        p.unlink()
                    except FileNotFoundError:
                        pass
            item.setdefault("status", "ok")
            source_summaries.append(item)
            source_out.write(json.dumps(item, sort_keys=True) + "\n")
            source_out.flush()
            if args.progress:
                json_dump(args.progress, {
                    "processed": ordinal,
                    "selected": len(candidates),
                    "valid_sources": valid_sources,
                    "unsupported_sources": unsupported_sources,
                    "source_records_scanned": total_source_records,
                    "unique_informative_parents": len(seen_parents),
                    "child_rows": next_row_index,
                })

        child_out.seek(4)
        child_out.write(struct.pack("<I", next_row_index))

    holdout = [fp for fp in seen_parents if split_is_holdout(fp, args.split_seed, args.holdout_mod)]
    holdout_white = sum(global_parent_color[fp] == 0 for fp in holdout)
    holdout_black = sum(global_parent_color[fp] == 1 for fp in holdout)
    train_white = sum(global_parent_color[fp] == 0 and fp not in set(holdout) for fp in seen_parents)
    train_black = sum(global_parent_color[fp] == 1 and fp not in set(holdout) for fp in seen_parents)
    support_established = (
        len(holdout) >= args.min_holdout_parents
        and holdout_white >= args.min_holdout_per_color
        and holdout_black >= args.min_holdout_per_color
        and train_white > 0 and train_black > 0
    )
    report = {
        "schema": "jass.tb_frontier.catalog_mine.v1",
        "catalog_sha256": sha256_file(args.catalog),
        "selection": selection_counts,
        "selected_candidates_effective": len(candidates),
        "selected_candidate_bytes_known": selected_bytes_known,
        "valid_sources": valid_sources,
        "unsupported_sources": unsupported_sources,
        "source_records_scanned": total_source_records,
        "informative_parent_occurrences": total_informative_occurrences,
        "duplicate_informative_parents": duplicate_informative_parents,
        "unique_informative_parents": len(seen_parents),
        "child_rows": next_row_index,
        "split": {"seed": args.split_seed, "holdout_mod": args.holdout_mod},
        "support": {
            "established": support_established,
            "min_holdout_parents": args.min_holdout_parents,
            "min_holdout_per_color": args.min_holdout_per_color,
            "parents_holdout": len(holdout),
            "parents_holdout_by_color": {"white": holdout_white, "black": holdout_black},
            "parents_train_by_color": {"white": train_white, "black": train_black},
        },
        "labels_used_from_sources": False,
        "exact_target": "EGDB_WLD_all_siblings",
        "automatic_training_authorized": support_established,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    json_dump(args.out_report, report)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--extractor", type=Path, required=True)
    ap.add_argument("--egdb-dir", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--out-children", type=Path, required=True)
    ap.add_argument("--out-groups", type=Path, required=True)
    ap.add_argument("--out-report", type=Path, required=True)
    ap.add_argument("--source-report", type=Path, required=True)
    ap.add_argument("--parent-provenance", type=Path, required=True)
    ap.add_argument("--progress", type=Path)
    ap.add_argument("--rclone-binary", default="rclone")
    ap.add_argument("--cache-mb", type=int, default=2048)
    ap.add_argument("--parent-pieces", type=int, default=8)
    ap.add_argument("--copy-timeout-seconds", type=int, default=3600)
    ap.add_argument("--split-seed", type=int, default=2026082801)
    ap.add_argument("--holdout-mod", type=int, default=5)
    ap.add_argument("--min-holdout-parents", type=int, default=800)
    ap.add_argument("--min-holdout-per-color", type=int, default=250)
    ap.add_argument("--max-candidates", type=int, default=0)
    ap.add_argument("--verify-declared-sha", action="store_true")
    args = ap.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"tb_frontier_catalog_mine: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
