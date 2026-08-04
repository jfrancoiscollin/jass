#!/usr/bin/env python3
"""Publish one fail-closed signal report for an aligned JNNW/JSM2 corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERN_TOOLS = ROOT / "pattern_jass" / "tools"
JOB_TOOLS = ROOT / "jobs" / "tools"
for search_path in (ROOT, JOB_TOOLS, PATTERN_TOOLS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

import numpy as np  # noqa: E402
import patterns  # noqa: E402
import eval_phase  # noqa: E402
from tools import selfplay_frontier as frontier  # noqa: E402

import l3_bucket_visits  # noqa: E402


JNNW_DTYPE = np.dtype([
    ("wm", "<u8"),
    ("wk", "<u8"),
    ("bm", "<u8"),
    ("bk", "<u8"),
    ("stm", "u1"),
    ("score", "<i4"),
    ("wdl", "i1"),
])
PJTW_HEADER = struct.Struct("<IIIII")
PJTW_MAGIC = 0x57544A50
PJTW_KING_BIT = 0x100
PJTW_KNOWN_BITS = 0xFF | 0x100 | 0x200


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _share(count: int, total: int) -> float:
    return count / total


def _summary(counts: dict[int, int]) -> dict:
    values = list(counts.values())
    return {
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "histogram": {
            str(value): amount
            for value, amount in sorted(Counter(values).items())
        },
    }


def _scan_corpus(data_path: Path, meta_path: Path) -> tuple[dict, np.memmap, int]:
    total = frontier._counted_file_count(data_path, frontier.JNNW_MAGIC, frontier.JNNW_REC)
    meta_schema, meta_count = frontier._meta_file_info(meta_path)
    if total != meta_count:
        raise ValueError(f"data/meta count mismatch: {total} != {meta_count}")
    if total == 0:
        raise ValueError("empty corpus: signal cannot be measured")
    if meta_schema is not frontier.JSM2_SCHEMA:
        raise ValueError("corpus_signal_report requires JSM2 game context; JSM1 is insufficient")

    records = np.memmap(
        data_path,
        dtype=JNNW_DTYPE,
        mode="r",
        offset=8,
        shape=(total,),
    )
    wdl_counts: Counter[int] = Counter()
    piece_counts: Counter[int] = Counter()
    material_balances: Counter[int] = Counter()
    records_by_game: Counter[int] = Counter()
    game_context: dict[int, tuple[int, int, int, int, int]] = {}
    plycap_games: set[int] = set()
    adjudicated_games: set[int] = set()
    contaminated = 0
    plycap_positions = 0
    queen_positions = 0
    sign_checked = 0

    with data_path.open("rb") as data_in, meta_path.open("rb") as meta_in:
        data_in.seek(8)
        meta_in.seek(8)
        for index in range(total):
            record = data_in.read(frontier.JNNW_REC)
            meta_raw = meta_in.read(meta_schema.record.size)
            if len(record) != frontier.JNNW_REC or len(meta_raw) != meta_schema.record.size:
                raise ValueError(f"aligned pair truncated at record {index}")
            row = frontier._decode_meta(
                meta_raw, meta_schema, context=f"{meta_path}: record {index}"
            )
            wm, wk, bm, bk, stm, _score, wdl = struct.unpack("<QQQQBib", record)
            if stm not in (0, 1):
                raise ValueError(f"record {index}: side-to-move {stm} outside {{0,1}}")
            if wdl not in (-1, 0, 1):
                raise ValueError(f"record {index}: WDL {wdl} outside {{-1,0,1}}")
            occupied = wm | wk | bm | bk
            if occupied >> 50:
                raise ValueError(f"record {index}: piece bit outside the 50-square board")
            if occupied.bit_count() != sum(
                board.bit_count() for board in (wm, wk, bm, bk)
            ):
                raise ValueError(f"record {index}: overlapping piece bitboards")
            assert row.ply is not None and row.game_plies is not None
            assert row.last_eps_ply is not None and row.game_result is not None
            assert row.flags is not None

            flags_without_tb = row.flags & ~0x04
            context = (
                row.game_plies,
                row.last_eps_ply,
                row.game_result,
                flags_without_tb,
                row.opening_id,
            )
            previous = game_context.setdefault(row.game_id, context)
            if previous != context:
                raise ValueError(f"record {index}: inconsistent context within game {row.game_id}")
            records_by_game[row.game_id] += 1
            if row.last_eps_ply != 0xFFFF and row.ply <= row.last_eps_ply:
                contaminated += 1
            if row.flags & 0x01:
                plycap_positions += 1
                plycap_games.add(row.game_id)
            if row.flags & 0x02:
                adjudicated_games.add(row.game_id)
            if not row.flags & 0x04:
                # JSM2 result is WHITE POV. JNNW WDL is POV of the side to move.
                expected_wdl = row.game_result * (1 if stm == 0 else -1)
                if wdl != expected_wdl:
                    raise ValueError(
                        f"record {index}: POV mismatch, JNNW WDL={wdl}, "
                        f"JSM2 white result={row.game_result}, stm={stm}"
                    )
                sign_checked += 1

            white_men = wm.bit_count()
            white_kings = wk.bit_count()
            black_men = bm.bit_count()
            black_kings = bk.bit_count()
            pieces = white_men + white_kings + black_men + black_kings
            balance = (white_men + 3 * white_kings) - (black_men + 3 * black_kings)
            wdl_counts[wdl] += 1
            piece_counts[pieces] += 1
            material_balances[balance] += 1
            if wk or bk:
                queen_positions += 1

    games = len(records_by_game)
    if games == 0:
        raise ValueError("no games in non-empty corpus")
    return ({
        "records": total,
        "games": games,
        "positions_par_partie": _summary(records_by_game),
        "wdl": {
            name: {"count": wdl_counts[value], "share": _share(wdl_counts[value], total)}
            for value, name in ((-1, "loss"), (0, "draw"), (1, "win"))
        },
        "contamination": {
            "positions": contaminated,
            "share": _share(contaminated, total),
            "definition": "ply <= last_eps_ply, excluding last_eps_ply=0xFFFF",
        },
        "plycap": {
            "games": len(plycap_games),
            "game_share": _share(len(plycap_games), games),
            "positions": plycap_positions,
            "position_share": _share(plycap_positions, total),
        },
        "adjudicated": {
            "games": len(adjudicated_games),
            "game_share": _share(len(adjudicated_games), games),
        },
        "positions": {
            "piece_count_histogram": {
                str(value): count for value, count in sorted(piece_counts.items())
            },
            "with_queens": queen_positions,
            "with_queens_share": _share(queen_positions, total),
            "material_balance_white_histogram": {
                str(value): count for value, count in sorted(material_balances.items())
            },
            "material_values": {"man": 1, "queen": 3},
        },
        "sign_convention": {
            "jsm2_game_result": "white_pov_-1_0_1",
            "jnnw_wdl": "side_to_move_pov_-1_0_1",
            "records_checked_without_tb_relabel": sign_checked,
        },
        "sidecar_schema": {"magic": meta_schema.name, "record_size": meta_schema.record.size},
    }, records, total)


def _coverage(data_path: Path, chunk: int) -> dict:
    report = l3_bucket_visits.compute([data_path], chunk, top_k=100, fold="exact")
    total_observations = report["corpus"]["total_bucket_visits"]
    free_parameters = report["geometry"]["trained_buckets_total"]
    return {
        "fold": report["fold"],
        "geometry": report["geometry"],
        "visited_buckets": report["coverage"]["visited_buckets"],
        "coverage_fraction": report["coverage"]["coverage_fraction"],
        "buckets_with_at_least": report["coverage"]["buckets_with_at_least"],
        "total_bucket_observations": total_observations,
        "observations_per_free_parameter": total_observations / free_parameters,
        "observations_per_visited_parameter": report["concentration"][
            "mean_visits_per_visited_bucket"
        ],
        "diagnostic_only": True,
    }


def _open_features(path: Path, expected_records: int) -> tuple[np.memmap, int]:
    with path.open("rb") as stream:
        header = stream.read(12)
    if len(header) != 12 or header[:4] != b"FEAT":
        raise ValueError(f"{path}: invalid FEAT header")
    count, width = struct.unpack_from("<II", header, 4)
    if count != expected_records:
        raise ValueError(f"{path}: FEAT count {count} != corpus {expected_records}")
    expected_size = 12 + count * width * 4
    if path.stat().st_size != expected_size:
        raise ValueError(f"{path}: size does not match {count}x{width} FEAT records")
    return np.memmap(path, dtype="<f4", mode="r", offset=12, shape=(count, width)), width


def _load_model(path: Path, feature_width: int) -> tuple[np.ndarray, dict]:
    with path.open("rb") as stream:
        header_raw = stream.read(PJTW_HEADER.size)
    if len(header_raw) != PJTW_HEADER.size:
        raise ValueError(f"{path}: truncated PJTW header")
    magic, version, scale, n_pat, n_ext = PJTW_HEADER.unpack(header_raw)
    if (
        magic != PJTW_MAGIC
        or (version & 0xFF) != 3
        or version & ~PJTW_KNOWN_BITS
        or scale <= 0
    ):
        raise ValueError(f"{path}: unsupported PJTW v3 header")
    if n_pat != patterns.TOTAL_BUCKETS:
        raise ValueError(
            f"{path}: model geometry {n_pat} != active 8cf geometry {patterns.TOTAL_BUCKETS}"
        )
    if n_ext != feature_width:
        raise ValueError(f"{path}: model extras {n_ext} != FEAT width {feature_width}")
    total_weights = 2 * (n_pat + n_ext)
    expected_size = PJTW_HEADER.size + 4 * total_weights
    if path.stat().st_size != expected_size:
        raise ValueError(f"{path}: PJTW size does not match its header")
    weights = np.memmap(
        path,
        dtype="<i4",
        mode="r",
        offset=PJTW_HEADER.size,
        shape=(total_weights,),
    )
    return weights, {
        "scale": scale,
        "n_patterns": n_pat,
        "n_extras": n_ext,
        "king_patterns": bool(version & PJTW_KING_BIT),
        "version": version,
    }


def _fisher(
    records: np.memmap,
    model_path: Path,
    feature_path: Path,
    chunk: int,
    phase_mode: str,
) -> dict:
    features, width = _open_features(feature_path, len(records))
    weights, model = _load_model(model_path, width)
    n_pat = model["n_patterns"]
    n_ext = model["n_extras"]
    scale = float(model["scale"])
    values = np.empty(len(records), dtype=np.float64)
    for start in range(0, len(records), chunk):
        stop = min(start + chunk, len(records))
        batch = records[start:stop]
        wm = np.ascontiguousarray(batch["wm"])
        wk = np.ascontiguousarray(batch["wk"])
        bm = np.ascontiguousarray(batch["bm"])
        bk = np.ascontiguousarray(batch["bk"])
        pattern_black = bm | bk if model["king_patterns"] else bm
        pattern_white = wm | wk if model["king_patterns"] else wm
        indices = patterns.extract_indices(pattern_black, pattern_white)
        columns = patterns.flat_feature_columns(indices)
        pattern_mg = np.asarray(weights[columns], dtype=np.float64).sum(axis=1)
        pattern_eg = np.asarray(weights[n_pat + columns], dtype=np.float64).sum(axis=1)
        extras = np.ascontiguousarray(features[start:stop]).astype(np.float64)
        extra_mg = extras @ np.asarray(
            weights[2 * n_pat:2 * n_pat + n_ext], dtype=np.float64
        )
        extra_eg = extras @ np.asarray(
            weights[2 * n_pat + n_ext:2 * n_pat + 2 * n_ext], dtype=np.float64
        )
        if phase_mode == "tempo":
            wmg = eval_phase.tempo_wmg_bb(wm, bm)
        else:
            pieces = eval_phase.piece_count_bb(wm, wk, bm, bk).astype(np.float64)
            wmg = np.clip(pieces / 40.0, 0.0, 1.0)
        logits = (wmg * (pattern_mg + extra_mg) + (1.0 - wmg) * (
            pattern_eg + extra_eg
        )) / scale
        probabilities = np.empty_like(logits)
        positive = logits >= 0
        probabilities[positive] = 1.0 / (1.0 + np.exp(-logits[positive]))
        exp_logits = np.exp(logits[~positive])
        probabilities[~positive] = exp_logits / (1.0 + exp_logits)
        values[start:stop] = probabilities * (1.0 - probabilities)
    if not np.isfinite(values).all():
        raise ValueError("non-finite Fisher values")
    quantiles = np.quantile(values, np.linspace(0.0, 1.0, 11))
    return {
        "definition": "p*(1-p), p=sigmoid(w*x)",
        "mean": float(values.mean()),
        "deciles": {f"d{index}": float(value) for index, value in enumerate(quantiles)},
        "model": str(model_path),
        "model_sha256": _sha256(model_path),
        "features": str(feature_path),
        "features_sha256": _sha256(feature_path),
        "feature_source": "aligned FEAT dump consumed by train_stream; no extras reimplementation",
        "phase_mode": phase_mode,
        "model_header": model,
    }


def _egdb(data_path: Path, egdb_path: Path, jass_path: Path, cache_mb: int) -> dict:
    if not egdb_path.is_dir():
        raise ValueError(f"EGDB directory does not exist: {egdb_path}")
    if not jass_path.is_file():
        raise ValueError(f"Jass executable does not exist: {jass_path}")
    completed = subprocess.run(
        [str(jass_path), "--egdb-audit", str(data_path), str(egdb_path), str(cache_mb)],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"EGDB audit failed (rc={completed.returncode}): {detail}")
    match = re.search(
        r"^EGDBAUDIT records=(\d+) in_range=(\d+) \([^)]*\)\s+agree=(\d+)"
        r"\s+disagree=(\d+) \(([^%]+)%\)\s+inverted=(\d+) \(([^%]+)%\)$",
        completed.stdout,
        re.MULTILINE,
    )
    if match is None:
        raise ValueError("EGDB audit produced no parseable EGDBAUDIT line")
    records, in_range, agree, disagree, disagree_pct, inverted, inverted_pct = match.groups()
    if int(in_range) == 0:
        raise ValueError("EGDB audit resolved zero records")
    confusion: dict[str, dict[str, int]] = {}
    for label, loss, draw, win in re.findall(
        r"^EGDBCONF label=(\S+)\s+verite_perte=(\d+)\s+verite_nulle=(\d+)"
        r"\s+verite_gain=(\d+)$",
        completed.stdout,
        re.MULTILINE,
    ):
        confusion[label] = {"loss": int(loss), "draw": int(draw), "win": int(win)}
    if set(confusion) != {"perte", "nulle", "gain"}:
        raise ValueError("EGDB audit produced an incomplete confusion matrix")
    return {
        "records": int(records),
        "in_range": int(in_range),
        "agree": int(agree),
        "disagree": int(disagree),
        "disagree_share": float(disagree_pct) / 100.0,
        "inverted": int(inverted),
        "inverted_share": float(inverted_pct) / 100.0,
        "confusion_label_stm_pov_by_truth_stm_pov": confusion,
        "optimistic_noise_bound": True,
    }


def build_report(args: argparse.Namespace) -> dict:
    data_path, meta_path = Path(args.data), Path(args.meta)
    base, records, total = _scan_corpus(data_path, meta_path)
    report = {
        "schema": 1,
        "operation": "corpus_signal_report",
        "diagnostic_candidates_not_optimisation_objectives": True,
        "input": {
            "data": str(data_path),
            "meta": str(meta_path),
            "data_sha256": _sha256(data_path),
            "meta_sha256": _sha256(meta_path),
        },
        **base,
        "couverture": _coverage(data_path, args.chunk),
    }
    if args.model:
        if not args.features:
            raise ValueError("--model requires --features from the same dump used by the fit")
        report["fisher"] = _fisher(
            records,
            Path(args.model),
            Path(args.features),
            args.chunk,
            args.phase_mode,
        )
    elif args.features:
        raise ValueError("--features is meaningless without --model")
    if args.egdb:
        if not args.jass:
            raise ValueError("--egdb requires --jass executable")
        report["egdb"] = _egdb(
            data_path, Path(args.egdb), Path(args.jass), args.egdb_cache_mb
        )
        if report["egdb"]["records"] != total:
            raise ValueError("EGDB audit record count differs from the validated corpus")
    elif args.jass:
        raise ValueError("--jass is meaningless without --egdb")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--model")
    parser.add_argument(
        "--features",
        help="aligned FEAT dump used by the fit; mandatory with --model",
    )
    parser.add_argument("--egdb", help="EGDB directory")
    parser.add_argument("--jass", help="EGDB-enabled Jass executable")
    parser.add_argument("--egdb-cache-mb", type=int, default=1024)
    parser.add_argument("--phase-mode", choices=("tempo", "pieces"), default="tempo")
    parser.add_argument("--chunk", type=int, default=500_000)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.chunk < 1:
        parser.error("--chunk must be positive")
    out_path = Path(args.out)
    if out_path.exists():
        parser.error(f"refusing to overwrite existing output: {out_path}")
    try:
        report = build_report(args)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_name(out_path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(out_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps({
        "records": report["records"],
        "games": report["games"],
        "contamination_share": report["contamination"]["share"],
        "plycap_game_share": report["plycap"]["game_share"],
        "fisher": "fisher" in report,
        "egdb": "egdb" in report,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
