#!/usr/bin/env python3
"""Phase 0 / Phase 1 (spec codex_review_v3_2 §7) — mining PASSIF des jets de gain.

STRICTEMENT HORS BOUCLE : inventaire versionné seulement — aucun fit, aucune
injection, aucune influence sur la génération suivante ni sur promotion_gate.
Ce module N'EXPORTE QUE des fonctions d'extraction/inventaire ; il n'importe
NI wdl_finetune NI scan_selfplay_gen NI promotion_gate (garantie hors-boucle
vérifiée par test).

Événements extraits dès la v1 (§7.3) :
    parent WIN → enfant joué DRAW   (WIN_TO_DRAW)
    parent WIN → enfant joué LOSS   (WIN_TO_LOSS)   # jamais reporté

Unité statistique = le PARENT décisionnel (§7.2) ; split futur par parent/game.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path

EVENT_TYPES = ("WIN_TO_DRAW", "WIN_TO_LOSS")
REC = 38


def fen_key_and_pieces(fen: str) -> tuple[bytes, int]:
    """Canonical board+STM key shared by sidecars and JNNW oracle records."""
    parts = fen.strip().split(":")
    if len(parts) != 3 or parts[0] not in {"W", "B"}:
        raise ValueError(f"bad FEN: {fen!r}")
    boards = {"W": [0, 0], "B": [0, 0]}
    for part in parts[1:]:
        color = part[:1]
        if color not in boards:
            raise ValueError(f"bad FEN color list: {fen!r}")
        for token in part[1:].split(","):
            token = token.strip()
            if not token:
                continue
            king = token[:1].upper() == "K"
            if king:
                token = token[1:]
            if "-" in token:
                first, last = map(int, token.split("-", 1))
                squares = range(first, last + 1)
            else:
                squares = (int(token),)
            for square in squares:
                if not 1 <= square <= 50:
                    raise ValueError(f"bad square {square}")
                boards[color][1 if king else 0] |= 1 << (square - 1)
    wm, wk = boards["W"]
    bm, bk = boards["B"]
    key = struct.pack("<4Q", wm, wk, bm, bk) + bytes([0 if parts[0] == "W" else 1])
    return key, sum(value.bit_count() for value in (wm, wk, bm, bk))


def oracle_label_map(path: Path) -> dict[bytes, int]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError(f"not JNNW: {path}")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * REC:
        raise ValueError(f"JNNW size/count mismatch: {path}")
    result: dict[bytes, int] = {}
    for index in range(count):
        record = raw[8 + index * REC:8 + (index + 1) * REC]
        key = record[:33]
        wdl = struct.unpack_from("<b", record, 37)[0]
        previous = result.setdefault(key, wdl)
        if previous != wdl:
            raise ValueError("oracle assigns conflicting labels to one position")
    return result


def load_trajectory_rows(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        text = handle.read()
    stripped = text.lstrip()
    if stripped.startswith("["):
        value = json.loads(text)
        if not isinstance(value, list):
            raise ValueError("trajectory JSON must be a list")
        return value
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def annotate_raw_trajectories(rows: list[dict], labels: dict[bytes, int]) -> list[dict]:
    """Normalize child oracle labels back into the decision parent's POV."""
    annotated: list[dict] = []
    for game_index, row in enumerate(rows):
        fens = list(row.get("fens") or [])
        moves = list(row.get("moves") or [])
        game_id = str(row.get("source_game_id") or f"game-{game_index}")
        for ply in range(min(len(moves), max(0, len(fens) - 1))):
            parent_fen, child_fen = fens[ply], fens[ply + 1]
            parent_key, pieces = fen_key_and_pieces(parent_fen)
            child_key, _ = fen_key_and_pieces(child_fen)
            if parent_key not in labels or child_key not in labels:
                continue
            parent_wdl = labels[parent_key]
            child_parent_pov = -labels[child_key]
            if parent_wdl != 1 or child_parent_pov not in (0, -1):
                continue
            parent_hash = hashlib.sha256(parent_key).hexdigest()
            annotated.append({
                "source_game_id": game_id,
                "parent_id": parent_hash,
                "parent_hash": parent_hash,
                "parent_fen": parent_fen,
                "parent_oracle": "WIN",
                "played_move": str(moves[ply]),
                "played_child_fen": child_fen,
                "played_child_oracle": "DRAW" if child_parent_pov == 0 else "LOSS",
                "siblings": [],
                "oracle_provenance": {"tier": "DEEP_ALIGNED", "pieces": pieces},
                "trajectory_hash": row.get("trajectory_hash"),
            })
    return annotated


def count_win_parents(rows: list[dict], labels: dict[bytes, int]) -> int:
    parents: set[bytes] = set()
    for row in rows:
        fens = list(row.get("fens") or [])
        moves = list(row.get("moves") or [])
        for ply in range(min(len(moves), len(fens))):
            key, _ = fen_key_and_pieces(fens[ply])
            if labels.get(key) == 1:
                parents.add(key)
    return len(parents)


def inventory_siblings(jass: str, rows: list[dict], work_dir: Path) -> None:
    """Attach legal, explicitly *uncertified* siblings to structured events."""
    if not rows:
        return
    work_dir.mkdir(parents=True, exist_ok=True)
    source = work_dir / "parents.fen"
    target = work_dir / "children.jsonl"
    source.write_text("".join(f"{row['parent_fen']}\n" for row in rows), encoding="utf-8")
    proc = subprocess.run(
        [jass, "--dump-children", str(source), str(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1000:].decode("utf-8", "replace"))
    children = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    if len(children) != len(rows):
        raise RuntimeError("sibling inventory lost line alignment")
    for row, legal in zip(rows, children):
        played_key, _ = fen_key_and_pieces(row["played_child_fen"])
        row["siblings"] = [
            {"move": child["move"], "fen": child["fen"], "certified": False}
            for child in legal
            if fen_key_and_pieces(child["fen"])[0] != played_key
        ]


def extract_events(trajectories: list[dict], probe_tour: str,
                   engine_sha: str = "...", weights_sha: str = "...",
                   cap_per_parent: int | None = None) -> list[dict]:
    """`trajectories` : liste de {source_game_id, parent_id, parent_fen, parent_hash,
    parent_oracle, played_move, played_child_fen, played_child_oracle,
    siblings?, oracle_provenance?, trajectory_hash?}.
    Ne garde que parent_oracle==WIN et enfant DRAW/LOSS. Cap par parent optionnel."""
    out: list[dict] = []
    per_parent: Counter = Counter()
    for t in trajectories:
        if t.get("parent_oracle") != "WIN":
            continue
        child = t.get("played_child_oracle")
        if child == "DRAW":
            ev = "WIN_TO_DRAW"
        elif child == "LOSS":
            ev = "WIN_TO_LOSS"
        else:
            continue
        pid = t.get("parent_id")
        if cap_per_parent is not None and per_parent[pid] >= cap_per_parent:
            continue
        per_parent[pid] += 1
        out.append({
            "probe_tour": probe_tour,
            "source_game_id": t.get("source_game_id"),
            "parent_id": pid,
            "parent_fen": t.get("parent_fen"),
            "parent_hash": t.get("parent_hash"),
            "played_move": t.get("played_move"),
            "played_child_fen": t.get("played_child_fen"),
            "played_child_oracle": child,
            "event_type": ev,
            "siblings": t.get("siblings", []),          # inventoriés, non certifiés (§7.3)
            "oracle_provenance": t.get("oracle_provenance", {}),
            "engine_sha": engine_sha,
            "weights_sha": weights_sha,
            "trajectory_hash": t.get("trajectory_hash"),
        })
    return out


def summarize(events: list[dict], n_games_inspected: int, n_parents_win: int) -> dict:
    """Sorties par tour (§7.5)."""
    by_pieces = Counter(); by_strata = Counter(); by_tier = Counter()
    per_parent = Counter()
    w2d = w2l = 0
    for e in events:
        if e["event_type"] == "WIN_TO_DRAW":
            w2d += 1
        else:
            w2l += 1
        prov = e.get("oracle_provenance", {}) or {}
        if "pieces" in prov:
            by_pieces[prov["pieces"]] += 1
        if "strata" in prov:
            by_strata[prov["strata"]] += 1
        if "tier" in prov:
            by_tier[prov["tier"]] += 1
        per_parent[e["parent_id"]] += 1
    return {
        "games_inspected": n_games_inspected,
        "parents_win": n_parents_win,
        "win_to_draw": w2d,
        "win_to_loss": w2l,
        "unique_parents": len(per_parent),
        "max_events_per_parent": max(per_parent.values()) if per_parent else 0,
        "by_pieces": dict(by_pieces),
        "by_strata": dict(by_strata),
        "by_tier": dict(by_tier),
    }


def _cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trajectories", required=True)
    ap.add_argument("--probe-tour", required=True)
    ap.add_argument("--engine-sha", default="...")
    ap.add_argument("--weights-sha", default="...")
    ap.add_argument("--cap-per-parent", type=int, default=None)
    ap.add_argument("--out-events", required=True)
    ap.add_argument("--out-summary", required=True)
    ap.add_argument("--games-inspected", type=int, default=0)
    ap.add_argument("--parents-win", type=int, default=0)
    ap.add_argument("--oracle-jnnw", type=Path,
                    help="aligned deep labels for a raw replayable trajectory sidecar")
    ap.add_argument("--jass", help="optional sibling inventory via --dump-children")
    ap.add_argument("--work-dir", type=Path)
    a = ap.parse_args(argv)
    raw_rows = load_trajectory_rows(Path(a.trajectories))
    if a.oracle_jnnw:
        labels = oracle_label_map(a.oracle_jnnw)
        trajs = annotate_raw_trajectories(raw_rows, labels)
        if a.jass:
            if not a.work_dir:
                ap.error("--work-dir is required with --jass")
            inventory_siblings(a.jass, trajs, a.work_dir)
        games_inspected = a.games_inspected or len(raw_rows)
        parents_win = a.parents_win or count_win_parents(raw_rows, labels)
    else:
        trajs = raw_rows
        games_inspected = a.games_inspected
        parents_win = a.parents_win
    events = extract_events(trajs, a.probe_tour, a.engine_sha, a.weights_sha, a.cap_per_parent)
    summary = summarize(events, games_inspected, parents_win)
    Path(a.out_events).write_text(json.dumps(events, indent=2, ensure_ascii=False))
    Path(a.out_summary).write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
