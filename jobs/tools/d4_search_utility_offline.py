#!/usr/bin/env python3
"""Frozen D4 search-utility example selection, single fit, and terminal readout."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.t3_f6_r0_select import fen_fingerprint
from jobs.tools.tb_frontier_symmetry_dedup import format_fingerprint, rotate50

FEATURES = (
    "legacy_rank_norm", "depth_norm", "ply_norm", "legal_count_norm",
    "piece_count_norm", "capture_node", "zero_window", "move_is_capture",
    "capture_count_norm", "promotes", "mover_is_king", "killer0_match",
    "killer1_match", "countermove_match", "history_squash", "conthist_squash",
    "from_row_norm", "from_col_norm", "to_row_norm", "to_col_norm",
    "abs_row_delta_norm", "abs_col_delta_norm", "destination_edge",
    "destination_center",
)
FEATURE_WIDTH = 24
PHASES = ("P0", "P1", "P2", "P3")
WIDTH = 96
EXAMPLE_PREFIX = "D4-EXAMPLE-2026111502:"
EXACT_COUNTS = {"train": 96_000, "valid": 12_000, "test": 12_000}
ROOT_COUNTS = {"train": 3_200, "valid": 400, "test": 400}
L2 = 1e-3
MAX_ITER = 500
MAXCOR = 10
GTOL = 1e-6
BOOTSTRAPS = 200_000
BOOTSTRAP_SEED = 2026111503

EVENT_SCHEMA = "jass.d4.search_utility_teacher_event.v1"
SELECTED_SCHEMA = "jass.d4.search_utility_example.v1"

PASS = "D4_SEARCH_UTILITY_OFFLINE_ESTABLISHED_V1"
FAIL = "D4_SEARCH_UTILITY_OFFLINE_NOT_ESTABLISHED_V1"
INVALID = "D4_SEARCH_UTILITY_OFFLINE_INVALID_V1"


class D4Error(RuntimeError):
    pass


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def canonical_line(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise D4Error(f"JSON object required: {path}")
    return value


def write_json_new(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise D4Error(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" \
        else path.open("r", encoding="utf-8")


def phase_for_pieces(pieces: int) -> int:
    if 33 <= pieces <= 40:
        return 0
    if 25 <= pieces <= 32:
        return 1
    if 17 <= pieces <= 24:
        return 2
    if 9 <= pieces <= 16:
        return 3
    raise D4Error(f"piece count outside D4 support: {pieces}")


def read_roots(path: Path) -> dict[int, tuple[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "root_index\tsplit\tcanonical_identity\tfen\tselection_digest":
        raise D4Error("D4 root manifest header drift")
    out: dict[int, tuple[str, str]] = {}
    counts = {k: 0 for k in ROOT_COUNTS}
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) != 5:
            raise D4Error("D4 root manifest row width drift")
        index = int(fields[0])
        split = fields[1]
        if index in out or split not in counts:
            raise D4Error("D4 root manifest identity/split drift")
        out[index] = (split, fields[2])
        counts[split] += 1
    if len(out) != 4_000 or counts != ROOT_COUNTS:
        raise D4Error(f"D4 root counts drift: roots={len(out)} splits={counts}")
    return out


def move_identity(move: Mapping[str, Any], flip: bool) -> tuple[int, int, int, int, int]:
    frm = int(move["from"])
    to = int(move["to"])
    captures = int(move["captured"])
    ncap = int(move["num_captures"])
    promotes = int(bool(move["promotes"]))
    if not 1 <= frm <= 50 or not 1 <= to <= 50 or captures < 0 or captures >> 50:
        raise D4Error("move identity outside FMJD board")
    if flip:
        frm = 51 - frm
        to = 51 - to
        captures = rotate50(captures)
    return frm, to, ncap, promotes, captures


def canonical_example_key(event: Mapping[str, Any]) -> str:
    fen = event.get("parent_fen")
    if not isinstance(fen, str):
        raise D4Error("event parent_fen missing")
    canonical, values = fen_fingerprint(fen)
    raw = format_fingerprint(*values)
    flip = canonical != raw
    candidates = event.get("candidates")
    if not isinstance(candidates, list) or not 2 <= len(candidates) <= 4:
        raise D4Error("event candidate cardinality drift")
    identities = [move_identity(c["move"], flip) for c in candidates]
    payload = {
        "parent": canonical,
        "remaining_depth": int(event["remaining_depth"]),
        "alpha": int(event["alpha"]),
        "beta": int(event["beta"]),
        "candidates": identities,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def validate_event(event: Mapping[str, Any], roots: Mapping[int, tuple[str, str]]) -> tuple[str, str]:
    if event.get("schema") != EVENT_SCHEMA:
        raise D4Error("teacher event schema drift")
    root_index = int(event["root_index"])
    if root_index not in roots:
        raise D4Error("teacher event unknown root")
    split, root_identity = roots[root_index]
    if event.get("root_split") != split or event.get("root_canonical_identity") != root_identity:
        raise D4Error("teacher event root provenance drift")
    if int(event["search_ply"]) < 1 or int(event["remaining_depth"]) < 3:
        raise D4Error("teacher event search support drift")
    pieces = int(event["parent_piece_count"])
    phase_for_pieces(pieces)
    legal = int(event["legal_move_count"])
    if not 2 <= legal <= 16:
        raise D4Error("teacher event legal move count drift")
    candidates = event["candidates"]
    label = int(event["label_index"])
    if not 0 <= label < len(candidates):
        raise D4Error("teacher event label drift")
    for i, candidate in enumerate(candidates):
        if int(candidate["legacy_rank"]) != i + 1:
            raise D4Error("legacy candidate rank drift")
        features = candidate["features"]
        if not isinstance(features, list) or len(features) != FEATURE_WIDTH:
            raise D4Error("D4 feature width drift")
        arr = np.asarray(features, dtype=np.float64)
        if not np.all(np.isfinite(arr)):
            raise D4Error("non-finite D4 feature")
        expected_rank = i / 3.0
        if abs(float(arr[0]) - expected_rank) > 1e-12:
            raise D4Error("legacy_rank_norm drift")
    return split, canonical_example_key(event)


def iter_events(paths: Sequence[Path]) -> Iterable[tuple[Path, int, dict[str, Any]]]:
    for path in paths:
        with open_text(path) as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    raise D4Error(f"blank teacher event line: {path}:{number}")
                value = json.loads(line)
                if type(value) is not dict:
                    raise D4Error(f"teacher event not object: {path}:{number}")
                yield path, number, value


def invert_digest(digest: bytes) -> bytes:
    return bytes(255 - b for b in digest)


def selected_payload(event: Mapping[str, Any], key: str, split: str) -> dict[str, Any]:
    candidates = event["candidates"]
    return {
        "schema": SELECTED_SCHEMA,
        "split": split,
        "root_index": int(event["root_index"]),
        "event_index": int(event["event_index"]),
        "example_key": key,
        "parent_fen": event["parent_fen"],
        "parent_piece_count": int(event["parent_piece_count"]),
        "search_ply": int(event["search_ply"]),
        "remaining_depth": int(event["remaining_depth"]),
        "alpha": int(event["alpha"]),
        "beta": int(event["beta"]),
        "legal_move_count": int(event["legal_move_count"]),
        "label_index": int(event["label_index"]),
        "candidates": [
            {
                "legacy_rank": int(c["legacy_rank"]),
                "features": [float(v) for v in c["features"]],
            }
            for c in candidates
        ],
    }


def prepare(args: argparse.Namespace) -> int:
    roots = read_roots(args.roots)
    teacher_paths = [Path(p) for p in args.teacher]
    if not teacher_paths:
        raise D4Error("no teacher event shards")

    with tempfile.TemporaryDirectory(prefix="d4-keys-") as tmp:
        db = sqlite3.connect(str(Path(tmp) / "keys.sqlite"))
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("CREATE TABLE keys(k TEXT PRIMARY KEY, mask INTEGER NOT NULL)")
        split_bit = {"train": 1, "valid": 2, "test": 4}
        total_events = 0
        for _, _, event in iter_events(teacher_paths):
            split, key = validate_event(event, roots)
            db.execute(
                "INSERT INTO keys(k,mask) VALUES(?,?) "
                "ON CONFLICT(k) DO UPDATE SET mask=(mask | excluded.mask)",
                (key, split_bit[split]),
            )
            total_events += 1
            if total_events % 10000 == 0:
                db.commit()
        db.commit()
        cross_split_keys = int(db.execute(
            "SELECT COUNT(*) FROM keys WHERE mask NOT IN (1,2,4)"
        ).fetchone()[0])

        heaps: dict[str, list[tuple[bytes, int, int, bytes]]] = {
            split: [] for split in EXACT_COUNTS
        }
        eligible = {split: 0 for split in EXACT_COUNTS}
        dropped_cross = 0
        for _, _, event in iter_events(teacher_paths):
            split, key = validate_event(event, roots)
            mask_row = db.execute("SELECT mask FROM keys WHERE k=?", (key,)).fetchone()
            if mask_row is None:
                raise D4Error("example key database drift")
            if int(mask_row[0]) not in (1, 2, 4):
                dropped_cross += 1
                continue
            eligible[split] += 1
            primary = hashlib.sha256((EXAMPLE_PREFIX + key).encode()).digest()
            root_index = int(event["root_index"])
            event_index = int(event["event_index"])
            payload = canonical_line(selected_payload(event, key, split))
            item = (invert_digest(primary), -root_index, -event_index, payload)
            heap = heaps[split]
            limit = EXACT_COUNTS[split]
            if len(heap) < limit:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)

        support_ok = all(eligible[s] >= EXACT_COUNTS[s] for s in EXACT_COUNTS)
        phase_test = {phase: 0 for phase in PHASES}
        outputs = {"train": args.train, "valid": args.valid, "test": args.test}
        hashes: dict[str, str] = {}
        if support_ok:
            for split, out_path in outputs.items():
                rows = []
                for inv_primary, neg_root, neg_event, payload in heaps[split]:
                    primary = invert_digest(inv_primary)
                    rows.append((primary, -neg_root, -neg_event, payload))
                rows.sort(key=lambda row: (row[0], row[1], row[2]))
                path = Path(out_path)
                if path.exists() or path.is_symlink():
                    raise D4Error(f"refusing existing selected output {path}")
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as out:
                    for _, _, _, payload in rows:
                        out.write(payload)
                        if split == "test":
                            event = json.loads(payload)
                            phase_test[PHASES[phase_for_pieces(
                                int(event["parent_piece_count"]))]] += 1
                hashes[split] = sha_file(path)
            support_ok = all(phase_test[p] >= 500 for p in PHASES)

        report = {
            "schema": "jass.d4.search_utility_prepare.v1",
            "verdict": "D4_SEARCH_UTILITY_EXAMPLES_READY_V1" if support_ok else INVALID,
            "teacher_event_rows": total_events,
            "teacher_shards": len(teacher_paths),
            "root_counts": ROOT_COUNTS,
            "cross_split_keys": cross_split_keys,
            "cross_split_event_occurrences_dropped": dropped_cross,
            "eligible_after_cross_split_filter": eligible,
            "selected_counts": EXACT_COUNTS if support_ok else {},
            "test_phase_counts": phase_test if support_ok else {},
            "selected_sha256": hashes,
            "example_selector_prefix": EXAMPLE_PREFIX,
            "features": list(FEATURES),
            "feature_width": FEATURE_WIDTH,
            "phase_blocks": 4,
            "model_width": WIDTH,
            "fits": 0,
            "strength_games": 0,
            "promotions": 0,
            "bakes": 0,
            "game_outcome_reads": 0,
            "qscore_reads": 0,
            "search_decision_trace_reads": 0,
            "full_ladder_1843_reads": 0,
            "d3_score_reads": 0,
        }
        write_json_new(args.report, report)
        db.close()
        print(json.dumps(report, sort_keys=True))
        return 0 if support_ok else 4


def load_selected(path: Path, expected_split: str) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise D4Error("selected examples must be LF-terminated")
    rows = []
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        value = json.loads(line.decode("ascii"))
        if type(value) is not dict or value.get("schema") != SELECTED_SCHEMA \
                or value.get("split") != expected_split or canonical_line(value) != line:
            raise D4Error(f"selected example canonical/schema drift line {number}")
        rows.append(value)
    if len(rows) != EXACT_COUNTS[expected_split]:
        raise D4Error(f"{expected_split} selected count drift: {len(rows)}")
    return rows


def arrays(rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(rows)
    x = np.zeros((n, 4, FEATURE_WIDTH), dtype=np.float64)
    mask = np.zeros((n, 4), dtype=bool)
    phase = np.empty(n, dtype=np.int8)
    labels = np.empty(n, dtype=np.int8)
    for i, row in enumerate(rows):
        candidates = row["candidates"]
        count = len(candidates)
        if not 2 <= count <= 4:
            raise D4Error("selected candidate count drift")
        labels[i] = int(row["label_index"])
        if not 0 <= labels[i] < count:
            raise D4Error("selected label drift")
        phase[i] = phase_for_pieces(int(row["parent_piece_count"]))
        for j, candidate in enumerate(candidates):
            features = np.asarray(candidate["features"], dtype=np.float64)
            if features.shape != (FEATURE_WIDTH,) or not np.all(np.isfinite(features)):
                raise D4Error("selected feature drift")
            x[i, j] = features
            mask[i, j] = True
    return x, mask, phase, labels


def logits(beta: np.ndarray, x: np.ndarray, mask: np.ndarray, phase: np.ndarray) -> np.ndarray:
    if beta.shape != (WIDTH,):
        raise D4Error("D4 beta width drift")
    blocks = beta.reshape(4, FEATURE_WIDTH)
    score = -np.arange(4, dtype=np.float64)[None, :] + np.einsum(
        "nij,nj->ni", x, blocks[phase], optimize=True
    )
    score = score.copy()
    score[~mask] = -np.inf
    return score


def loss_grad(beta: np.ndarray, x: np.ndarray, mask: np.ndarray,
              phase: np.ndarray, labels: np.ndarray) -> tuple[float, np.ndarray]:
    score = logits(beta, x, mask, phase)
    qmax = np.max(score, axis=1)
    ex = np.exp(score - qmax[:, None])
    ex[~mask] = 0.0
    probs = ex / ex.sum(axis=1, keepdims=True)
    idx = np.arange(len(labels))
    ce = float(np.mean((qmax + np.log(ex.sum(axis=1))) - score[idx, labels]))
    residual = probs
    residual[idx, labels] -= 1.0
    grad = np.zeros((4, FEATURE_WIDTH), dtype=np.float64)
    for p in range(4):
        sel = phase == p
        if np.any(sel):
            grad[p] = np.einsum("ni,nij->j", residual[sel], x[sel], optimize=True)
    grad /= len(labels)
    reg = 0.5 * L2 * float(np.dot(beta, beta))
    return ce + reg, grad.ravel() + L2 * beta


def metrics(beta: np.ndarray, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    x, mask, phase, labels = arrays(rows)
    score = logits(beta, x, mask, phase)
    qmax = np.max(score, axis=1)
    ex = np.exp(score - qmax[:, None])
    ex[~mask] = 0.0
    probs = ex / ex.sum(axis=1, keepdims=True)
    idx = np.arange(len(labels))
    nll = (qmax + np.log(ex.sum(axis=1))) - score[idx, labels]
    order = np.argsort(-score, axis=1, kind="stable")
    ranks = np.empty(len(labels), dtype=np.int8)
    for i in range(len(labels)):
        ranks[i] = int(np.where(order[i] == labels[i])[0][0]) + 1
    return {
        "cross_entropy": float(np.mean(nll)),
        "top1": float(np.mean(np.argmax(score, axis=1) == labels)),
        "mrr": float(np.mean(1.0 / ranks)),
        "nll": nll,
        "phase": phase,
        "labels": labels,
        "ranks": ranks,
        "top_index": np.argmax(score, axis=1),
    }


def seal_model(path: Path, beta: np.ndarray) -> dict[str, Any]:
    if path.exists() or path.is_symlink():
        raise D4Error(f"refusing existing model output {path}")
    if beta.dtype != np.dtype(np.float64) or beta.shape != (WIDTH,) or not np.all(np.isfinite(beta)):
        raise D4Error("D4 model must be finite float64 width 96")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("wb") as out:
            np.save(out, beta, allow_pickle=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    check = np.load(path, allow_pickle=False)
    if check.dtype != np.dtype(np.float64) or check.shape != (WIDTH,) or not np.array_equal(check, beta):
        raise D4Error("D4 model serialization drift")
    return {
        "format": "npy",
        "dtype": "float64",
        "width": WIDTH,
        "sha256": sha_file(path),
        "size_bytes": path.stat().st_size,
    }


def fit(args: argparse.Namespace) -> int:
    rows = load_selected(args.train, "train")
    x, mask, phase, labels = arrays(rows)
    initial = np.zeros(WIDTH, dtype=np.float64)
    baseline_metrics = metrics(initial, rows)
    result = minimize(
        lambda beta: loss_grad(beta, x, mask, phase, labels),
        initial,
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": MAX_ITER, "maxcor": MAXCOR, "gtol": GTOL},
    )
    beta = np.asarray(result.x, dtype=np.float64)
    if beta.shape != (WIDTH,) or not np.all(np.isfinite(beta)):
        raise D4Error("D4 optimizer returned invalid model")
    candidate_metrics = metrics(beta, rows)
    model = seal_model(args.model, beta)
    report = {
        "schema": "jass.d4.search_utility_fit.v1",
        "verdict": "D4_SEARCH_UTILITY_FIT_COMPLETE_V1",
        "train_examples": len(rows),
        "features": list(FEATURES),
        "feature_width": FEATURE_WIDTH,
        "phase_blocks": 4,
        "model_width": WIDTH,
        "baseline_logit": "-(legacy_rank_1_based-1)",
        "l2": L2,
        "optimizer": "L-BFGS-B",
        "max_iter": MAX_ITER,
        "maxcor": MAXCOR,
        "gtol": GTOL,
        "initialization": "zeros",
        "optimizer_success": bool(result.success),
        "optimizer_status": int(result.status),
        "optimizer_message": str(result.message),
        "optimizer_iterations": int(getattr(result, "nit", -1)),
        "optimizer_function_evaluations": int(getattr(result, "nfev", -1)),
        "train": {
            "baseline_cross_entropy": baseline_metrics["cross_entropy"],
            "d4_cross_entropy": candidate_metrics["cross_entropy"],
            "baseline_top1": baseline_metrics["top1"],
            "d4_top1": candidate_metrics["top1"],
            "baseline_mrr": baseline_metrics["mrr"],
            "d4_mrr": candidate_metrics["mrr"],
        },
        "model": model,
        "fits": 1,
        "model_searches": 0,
        "temperature_searches": 0,
        "runtime_scale_searches": 0,
        "valid_reads": 0,
        "test_reads": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
    }
    write_json_new(args.report, report)
    print(json.dumps(report, sort_keys=True))
    return 0


def bootstrap_mean(delta: np.ndarray) -> dict[str, float]:
    n = len(delta)
    if n == 0:
        raise D4Error("empty bootstrap input")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    boot = np.empty(BOOTSTRAPS, dtype=np.float64)
    batch = 256
    dtype = np.uint16 if n <= np.iinfo(np.uint16).max else np.uint32
    for start in range(0, BOOTSTRAPS, batch):
        stop = min(BOOTSTRAPS, start + batch)
        idx = rng.integers(0, n, size=(stop - start, n), dtype=dtype)
        boot[start:stop] = delta[idx].mean(axis=1)
    return {
        "mean": float(np.mean(delta)),
        "ci_low": float(np.quantile(boot, 0.025)),
        "ci_high": float(np.quantile(boot, 0.975)),
        "repetitions": BOOTSTRAPS,
        "seed": BOOTSTRAP_SEED,
    }


def readout(args: argparse.Namespace) -> int:
    prepare_report = read_json(args.prepare_report)
    fit_report = read_json(args.fit_report)
    teacher = read_json(args.teacher_report)
    if prepare_report.get("verdict") != "D4_SEARCH_UTILITY_EXAMPLES_READY_V1":
        raise D4Error("D4 prepare did not establish exact support")
    if fit_report.get("verdict") != "D4_SEARCH_UTILITY_FIT_COMPLETE_V1" \
            or fit_report.get("fits") != 1 or fit_report.get("model_searches") != 0:
        raise D4Error("D4 fit provenance drift")
    if teacher.get("teacher_searches") != 4000 or teacher.get("roots") != 4000 \
            or teacher.get("node_overshoot_mismatches") != 0:
        raise D4Error("D4 teacher aggregate drift")
    for key in ("game_outcome_reads", "qscore_reads", "search_decision_trace_reads",
                "full_ladder_1843_reads", "d3_score_reads"):
        if teacher.get(key) != 0:
            raise D4Error(f"forbidden teacher read counter {key}")

    model = np.load(args.model, allow_pickle=False)
    if model.dtype != np.dtype(np.float64) or model.shape != (WIDTH,) \
            or not np.all(np.isfinite(model)):
        raise D4Error("sealed D4 model drift")
    model_sha = sha_file(args.model)
    if fit_report.get("model", {}).get("sha256") != model_sha:
        raise D4Error("sealed D4 model SHA drift")

    valid_rows = load_selected(args.valid, "valid")
    test_rows = load_selected(args.test, "test")
    zero = np.zeros(WIDTH, dtype=np.float64)
    vb, vd = metrics(zero, valid_rows), metrics(model, valid_rows)
    tb, td = metrics(zero, test_rows), metrics(model, test_rows)
    delta = np.asarray(tb["nll"] - td["nll"], dtype=np.float64)
    bootstrap = bootstrap_mean(delta)

    phase_metrics: dict[str, Any] = {}
    all_phase_nonnegative = True
    for p, name in enumerate(PHASES):
        sel = np.asarray(tb["phase"]) == p
        if int(np.sum(sel)) < 500:
            raise D4Error(f"TEST phase support below 500: {name}")
        gain = float(np.mean(delta[sel]))
        all_phase_nonnegative &= gain >= 0.0
        phase_metrics[name] = {
            "examples": int(np.sum(sel)),
            "baseline_cross_entropy": float(np.mean(np.asarray(tb["nll"])[sel])),
            "d4_cross_entropy": float(np.mean(np.asarray(td["nll"])[sel])),
            "ce_gain": gain,
            "baseline_top1": float(np.mean(np.asarray(tb["ranks"])[sel] == 1)),
            "d4_top1": float(np.mean(np.asarray(td["ranks"])[sel] == 1)),
        }

    passed = (
        bootstrap["mean"] > 0.0
        and bootstrap["ci_low"] > 0.0
        and td["top1"] > tb["top1"]
        and all_phase_nonnegative
    )
    verdict = PASS if passed else FAIL
    report = {
        "schema": "jass.d4.search_utility_offline_terminal.v1",
        "verdict": verdict,
        "science": {
            "target": "observed_beta_cutoff_causing_move_within_legacy_top4_non_tt",
            "model_width": WIDTH,
            "model_sha256": model_sha,
            "value_model_sha256": args.wdl_sha256,
            "fits": 1,
            "model_searches": 0,
        },
        "valid": {
            "examples": len(valid_rows),
            "baseline_cross_entropy": vb["cross_entropy"],
            "d4_cross_entropy": vd["cross_entropy"],
            "ce_gain": vb["cross_entropy"] - vd["cross_entropy"],
            "baseline_top1": vb["top1"],
            "d4_top1": vd["top1"],
            "baseline_mrr": vb["mrr"],
            "d4_mrr": vd["mrr"],
        },
        "test": {
            "examples": len(test_rows),
            "baseline_cross_entropy": tb["cross_entropy"],
            "d4_cross_entropy": td["cross_entropy"],
            "ce_gain": tb["cross_entropy"] - td["cross_entropy"],
            "baseline_top1": tb["top1"],
            "d4_top1": td["top1"],
            "baseline_mrr": tb["mrr"],
            "d4_mrr": td["mrr"],
            "legacy_first_preserved_fraction": float(
                np.mean(np.asarray(td["top_index"]) == 0)
            ),
            "legacy_nonfirst_cutoff_label_promoted_to_rank1_fraction": float(
                np.mean(
                    np.asarray(td["top_index"])[np.asarray(tb["labels"]) > 0]
                    == np.asarray(tb["labels"])[np.asarray(tb["labels"]) > 0]
                )
            ) if np.any(np.asarray(tb["labels"]) > 0) else 0.0,
            "bootstrap_ce_gain": bootstrap,
            "by_phase": phase_metrics,
        },
        "gates": {
            "test_mean_ce_gain_gt_0": bootstrap["mean"] > 0.0,
            "test_bootstrap_95_lcb_ce_gain_gt_0": bootstrap["ci_low"] > 0.0,
            "test_top1_gt_baseline_top1": td["top1"] > tb["top1"],
            "all_four_test_phases_mean_ce_gain_ge_0": all_phase_nonnegative,
            "provenance_and_forbidden_reads_pass": True,
        },
        "teacher_searches": 4000,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        "equal_node_authorized": passed,
        "next_stage": "D4_RUNTIME_IMPLEMENTATION_AND_ZERO_GAME_PREFLIGHT" if passed
                      else "STOP_D4_OFFLINE",
        "game_outcome_reads": 0,
        "qscore_reads": 0,
        "search_decision_trace_reads": 0,
        "full_ladder_1843_reads": 0,
        "d3_score_reads": 0,
    }
    write_json_new(args.report, report)
    print(json.dumps(report, sort_keys=True))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--roots", type=Path, required=True)
    p.add_argument("--teacher", action="append", required=True)
    p.add_argument("--train", type=Path, required=True)
    p.add_argument("--valid", type=Path, required=True)
    p.add_argument("--test", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.set_defaults(func=prepare)

    p = sub.add_parser("fit")
    p.add_argument("--train", type=Path, required=True)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.set_defaults(func=fit)

    p = sub.add_parser("readout")
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--valid", type=Path, required=True)
    p.add_argument("--test", type=Path, required=True)
    p.add_argument("--prepare-report", type=Path, required=True)
    p.add_argument("--fit-report", type=Path, required=True)
    p.add_argument("--teacher-report", type=Path, required=True)
    p.add_argument("--wdl-sha256", required=True)
    p.add_argument("--report", type=Path, required=True)
    p.set_defaults(func=readout)

    args = ap.parse_args()
    try:
        return int(args.func(args))
    except (D4Error, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"d4_search_utility_offline: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
