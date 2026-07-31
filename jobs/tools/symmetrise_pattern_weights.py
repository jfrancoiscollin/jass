#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Projette un `.pjtw` sur le sous-espace antisymétrique miroir+couleur.

Pourquoi
--------
Le damier international possède une symétrie **exacte** : tourner le plateau de
180° (case `s` → `51-s`) ET échanger les couleurs rend une position
stratégiquement identique, d'évaluation opposée. Ce n'est pas une approximation,
c'est une propriété des règles.

Nos 8 patterns `8cf` sont les 4 colonnes de Scan **dupliquées haut/bas** : elles
s'apparient exactement sous ce miroir (p0↔p7, p1↔p6, p2↔p5, p3↔p4). Scan impose
la relation par construction — index signé et contributions ±1. Nous, on la laisse
s'apprendre, et TURNOVER ne l'a apprise qu'à moitié : corrélation ≈ +0,5 là où
l'exactitude vaut +1, soit **25,8 % de l'énergie des poids qui viole une symétrie
garantie par les règles**.

Cette masse-là ne peut correspondre à aucune évaluation réelle : elle dit qu'une
même configuration vaut différemment selon qu'on la regarde du haut ou du bas du
plateau. Cet outil la retire.

Ce que ça n'est pas
-------------------
Ce n'est PAS le correctif. Le correctif est structurel — lier les deux moitiés
dans l'indexation, ce qui divise par deux les paramètres et double les
observations par bucket. Ici on se contente de projeter un modèle **déjà ajusté**,
dont la partie symétrique a été apprise EN PRÉSENCE de la partie asymétrique.
La projection peut donc dégrader même si la contrainte est juste : ce job mesure,
il ne conclut pas sur l'architecture.

Aucune promotion. Le fichier produit est un candidat à porte, rien de plus.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import struct
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
V3_HEADER = 20


def load_patterns(header: pathlib.Path | None = None) -> list[list[int]]:
    """Cases de chaque pattern, DANS L'ORDRE du header (l'index en dépend)."""
    path = header or (ROOT / "pattern_jass/src/pattern.hpp")
    text = path.read_text()
    m = re.search(r"PATTERNS\s*=\s*\{\{(.*?)\}\};", text, re.S)
    if not m:
        raise ValueError(f"PATTERNS introuvable dans {path}")
    return [[int(x) for x in re.findall(r"\d+", b)]
            for b in re.findall(r"\{\s*\{([^}]*)\}", m.group(1))]


def mirror_partner(pats: list[list[int]], p: int) -> int:
    """Pattern dont les cases sont l'image de `p` par `s → 51-s`."""
    target = {51 - s for s in pats[p]}
    for q, sq in enumerate(pats):
        if set(sq) == target:
            return q
    raise ValueError(f"pattern {p} sans partenaire miroir — géométrie inattendue")


def index_map(pats: list[list[int]], p: int, q: int) -> np.ndarray:
    """σ : index de `p` → index de `q` sous miroir+échange de couleurs.

    La case `i` de `p` (carré `s`) devient la case `j` de `q` telle que
    `pats[q][j] == 51 - s`, et son contenu échange noir↔blanc (1↔2, 0 inchangé).
    """
    size = len(pats[p])
    n = 3 ** size
    perm = [pats[q].index(51 - pats[p][i]) for i in range(size)]
    pow3 = [3 ** i for i in range(size)]
    idx = np.arange(n, dtype=np.int64)
    out = np.zeros(n, dtype=np.int64)
    swap = np.array([0, 2, 1], dtype=np.int64)
    t = idx.copy()
    for i in range(size):
        out += swap[t % 3] * pow3[perm[i]]
        t //= 3
    return out


def read_pjtw(path: pathlib.Path):
    raw = path.read_bytes()
    magic, version, scale, n_pat, n_ext = struct.unpack("<5I", raw[:V3_HEADER])
    w = np.frombuffer(raw[V3_HEADER:], dtype="<i4").copy()
    expected = 2 * (n_pat + n_ext)
    if w.size != expected:
        raise ValueError(f"{path}: {w.size} poids, {expected} attendus")
    return magic, version, scale, n_pat, n_ext, w


def write_pjtw(path: pathlib.Path, magic, version, scale, n_pat, n_ext,
               w: np.ndarray) -> None:
    with path.open("wb") as fh:
        fh.write(struct.pack("<5I", magic, version, scale, n_pat, n_ext))
        fh.write(w.astype("<i4").tobytes())


def violation_share(pat: np.ndarray, pats: list[list[int]]) -> float:
    """Part de l'énergie des poids qui viole l'antisymétrie (0 = exacte)."""
    ok = bad = 0.0
    for p in range(len(pats)):
        q = mirror_partner(pats, p)
        sigma = index_map(pats, p, q)
        a = pat[p].astype(np.float64)
        b = -pat[q][sigma].astype(np.float64)
        ok += float(np.sum((0.5 * (a + b)) ** 2))
        bad += float(np.sum((0.5 * (a - b)) ** 2))
    return bad / (ok + bad) if (ok + bad) else 0.0


def symmetrise(pat: np.ndarray, pats: list[list[int]]) -> np.ndarray:
    """Projection sur le sous-espace antisymétrique, EXACTE en entiers.

    `v_p = round((w_p - w_q∘σ) / 2)` puis `v_q := -v_p∘σ⁻¹` **posé**, pas
    recalculé. Recalculer donnerait ici le même résultat, parce que `np.rint`
    arrondit au pair le plus proche et vérifie donc `rint(-x) = -rint(x)` ; mais
    l'exactitude reposerait alors sur cette propriété de la fonction d'arrondi.
    En la posant, elle est structurelle et ne dépend plus du mode d'arrondi —
    or c'est précisément l'exactitude qui porte tout l'argument : on projette
    pour supprimer une quantité dont on affirme qu'elle ne peut pas exister.

    σ est une involution, donc σ⁻¹ existe et vaut la permutation inverse.
    """
    out = np.empty_like(pat)
    done: set[int] = set()
    for p in range(len(pats)):
        if p in done:
            continue
        q = mirror_partner(pats, p)
        if q == p:
            raise ValueError(f"pattern {p} est son propre miroir — cas non traité")
        sigma = index_map(pats, p, q)
        a = pat[p].astype(np.int64)
        b = -pat[q][sigma].astype(np.int64)
        v = np.rint((a + b) / 2.0).astype(np.int64)   # composante antisymétrique
        out[p] = v
        inv = np.empty_like(sigma)
        inv[sigma] = np.arange(sigma.size, dtype=np.int64)
        out[q] = -v[inv]
        done.update((p, q))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--header", type=pathlib.Path, default=None,
                    help="pattern.hpp à lire (défaut : celui du dépôt)")
    ap.add_argument("--report", type=pathlib.Path, default=None)
    args = ap.parse_args(argv)

    pats = load_patterns(args.header)
    magic, version, scale, n_pat, n_ext, w = read_pjtw(args.src)
    if n_pat % len(pats):
        print(f"erreur: n_pat={n_pat} n'est pas un multiple de {len(pats)} patterns —"
              " le header ne correspond pas au fichier", file=sys.stderr)
        return 2
    per = n_pat // len(pats)

    out = w.copy()
    before, after = {}, {}
    for name, base in (("mg", 0), ("eg", n_pat)):
        block = w[base:base + n_pat].reshape(len(pats), per)
        before[name] = violation_share(block, pats)
        sym = symmetrise(block, pats)
        after[name] = violation_share(sym, pats)
        out[base:base + n_pat] = sym.reshape(-1)

    # Les extras (dames, mobilité, parité) ne sont PAS touchés : ils n'ont pas la
    # structure appariée des patterns, et les symétriser demanderait de connaître
    # leur géométrie une par une. C'est une limite assumée, pas un oubli.
    write_pjtw(args.out, magic, version, scale, n_pat, n_ext, out)

    report = {
        "schema": "l3_symmetrise_pattern_weights",
        "version": 1,
        "source": str(args.src),
        "output": str(args.out),
        "patterns": len(pats),
        "buckets_per_pattern": per,
        "extras_untouched": int(n_ext),
        "violation_share_before": {k: round(v, 6) for k, v in before.items()},
        "violation_share_after": {k: round(v, 6) for k, v in after.items()},
        "exactly_antisymmetric": all(v < 1e-12 for v in after.values()),
        "diagnostic_only": True,
        "promotion_authorized": False,
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))

    if not report["exactly_antisymmetric"]:
        print("erreur: la projection n'a pas rendu le modèle exactement "
              "antisymétrique — la géométrie du header ne correspond pas",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
