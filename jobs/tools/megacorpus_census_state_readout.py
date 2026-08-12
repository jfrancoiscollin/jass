#!/usr/bin/env python3
"""Lit la QUEUE RESTANTE d'un census MegaCorpus, sans relancer le census.

⛔ POURQUOI CET OUTIL EXISTE. `cpx62-1264` a ete tue apres 8 h : son debit etait
tombe a ~15 min par shard, soit EXACTEMENT `SHARD_TIMEOUT_SECONDS=900`. Chaque
prefixe restant consommait son timeout complet avant de se subdiviser, et les
enfants faisaient de meme jusqu'a la profondeur maximale.

⚠️ ET CE TIMEOUT N'ACHETE RIEN. Quand un listing recursif expire, `rclone_json`
leve et le listing PARTIEL EST JETE : les 900 s ne produisent aucun objet, elles
ne financent que la DECISION de subdiviser. Cette decision est disponible bien
plus tot. Le cout d'une branche pathologique est donc
`900 s x (nombre de noeuds du sous-arbre)`, ce qui explose.

Recalibrer le timeout suppose de savoir CE QUI RESTE. Cet outil rend ce compte,
et rien d'autre : aucune ecriture, aucun listing R2, aucune reprise.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import PurePosixPath
from typing import Any


def depth_of(prefix: str) -> int:
    return 0 if not prefix else len(PurePosixPath(prefix).parts)


def pending_frontier(state: dict[str, Any]) -> list[str]:
    """Prefixes que le census DEVRAIT encore traiter, par le meme parcours.

    On rejoue la file d'attente de `census()` : depuis la racine, un prefixe
    `done` s'arrete, un prefixe `split` empile ses enfants, et tout prefixe
    inconnu de l'etat est un travail RESTANT. C'est le seul moyen honnete
    d'obtenir un denominateur -- le compter autrement inventerait un total.
    """
    prefixes = state.get("prefixes", {})
    queue: list[str] = [""]
    seen: set[str] = set()
    pending: list[str] = []
    while queue:
        prefix = queue.pop(0)
        if prefix in seen:
            continue
        seen.add(prefix)
        entry = prefixes.get(prefix)
        if entry is None:
            pending.append(prefix)
            continue
        if entry.get("state") == "split":
            queue.extend(entry.get("children", []))
    return pending


def summarize(state: dict[str, Any]) -> dict[str, Any]:
    prefixes = state.get("prefixes", {})
    done = [p for p, e in prefixes.items() if e.get("state") == "done"]
    split = [p for p, e in prefixes.items() if e.get("state") == "split"]
    pending = pending_frontier(state)

    objects = sum(
        int(e.get("shard", {}).get("object_count", 0)) for e in prefixes.values()
    )
    # ⚠️ Un prefixe traite en `direct` APRES echec du recursif est la trace d'un
    # timeout paye. C'est le compteur qui dit combien le reglage courant coute.
    split_by_depth = Counter(depth_of(p) for p in split)
    pending_by_depth = Counter(depth_of(p) for p in pending)
    return {
        "schema": "jass.megacorpus_census_state_readout.v1",
        "remote": state.get("remote"),
        "split_depth": state.get("split_depth"),
        "max_depth": state.get("max_depth"),
        "prefix_records": len(prefixes),
        "done_count": len(done),
        "split_count": len(split),
        "pending_count": len(pending),
        "objects_indexed": objects,
        "split_by_depth": dict(sorted(split_by_depth.items())),
        "pending_by_depth": dict(sorted(pending_by_depth.items())),
        "deepest_split_depth": max(split_by_depth, default=0),
        # Les prefixes en attente les moins profonds sont les plus chers : ce
        # sont eux qui vont se subdiviser en cascade.
        "shallowest_pending": sorted(pending, key=lambda p: (depth_of(p), p))[:40],
        "pending_total_is_a_FRONTIER_not_a_tree_size": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    with open(args.state, encoding="utf-8") as handle:
        state = json.load(handle)
    summary = summarize(state)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    for key in ("done_count", "split_count", "pending_count", "objects_indexed",
                "deepest_split_depth"):
        print(f"{key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
