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
import json
import sys
from collections import Counter
from pathlib import Path

EVENT_TYPES = ("WIN_TO_DRAW", "WIN_TO_LOSS")


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
    a = ap.parse_args(argv)
    trajs = json.loads(Path(a.trajectories).read_text())
    events = extract_events(trajs, a.probe_tour, a.engine_sha, a.weights_sha, a.cap_per_parent)
    summary = summarize(events, a.games_inspected, a.parents_win)
    Path(a.out_events).write_text(json.dumps(events, indent=2, ensure_ascii=False))
    Path(a.out_summary).write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
