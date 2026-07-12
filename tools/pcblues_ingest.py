#!/usr/bin/env python3
"""Ingestion du corpus PC Blues raffiné par dilf (exports contractuels).

Source : ``dilf/data/exports/pcblues/`` (tag pcblues-a{2,3}-v1 — cf section
EXPORTS d'INTEROP.md dilf). Produit côté jass :

1. ``data/pcblues_combos.fen``      — canal FEN (format dilf_combinations.fen,
   consommé par les jobs tactiques type 0440/0444/0456) : une ligne par
   combinaison vérifiée, dédupliquée (interne + croisée master-2000/0464),
   commentaire = provenance (deel/page/joueurs/année) + 1er coup publié.
2. ``data/pcblues_thermometre.fen`` — sous-ensemble FIGÉ (instrument de la
   lignée from-scratch, JAMAIS entraînement) : sélection déterministe.
3. ``data/pcblues_prefs_graded.tsv`` — (fen, move_played, grade, source)
   pour les fits rank_finetune (paires construites in-job via la machinerie
   --gen-siblings existante ; les négatives ?/?? s'exploitent en inversant
   la préférence, cf mémo).

Dédup croisée : clé = (stm, wm, wk, bm, bk) bitboards, comparée aux corpus
jnnw existants passés via --dedup-jnnw (master-2000, 0464/combos). Les
positions déjà connues sont ÉCARTÉES du canal .fen (marquées, jamais
silencieuses) mais conservées dans le TSV prefs (une préférence graduée
reste informative même sur une position connue).

⛔ Rappels gravés : Result ≠ label WDL ; aucun artefact PC Blues dans le
corpus d'entraînement from-scratch (thermomètre = instrument).

Usage (local, PAS un job box) ::

    python3 tools/pcblues_ingest.py \
        --exports ../dilf/data/exports/pcblues \
        --dedup-jnnw jobs/results/0014-fetch-master-games/artefacts/master-2000.jnnw \
        --out-dir data
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdn_to_jnnw import fen_to_bitboards  # noqa: E402

REC = 38
_REC_STRUCT = struct.Struct("<QQQQBib")

EXPORT_TAG = "pcblues-a2-v1 / pcblues-a3-v1"


def jnnw_keys(path: Path) -> set[tuple]:
    """Clés (stm, wm, wk, bm, bk) de tous les records d'un fichier JNNW."""
    raw = path.read_bytes()
    assert raw[:4] == b"JNNW", f"{path}: pas un JNNW"
    n = struct.unpack("<I", raw[4:8])[0]
    keys = set()
    for i in range(n):
        wm, wk, bm, bk, stm, _score, _wdl = _REC_STRUCT.unpack_from(raw, 8 + i * REC)
        keys.add((stm, wm, wk, bm, bk))
    return keys


def fen_key(fen: str) -> tuple:
    stm, wm, wk, bm, bk = fen_to_bitboards(fen)
    return (stm, wm, wk, bm, bk)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", required=True, help="dilf data/exports/pcblues")
    ap.add_argument("--dedup-jnnw", nargs="*", default=[])
    ap.add_argument("--out-dir", default="data")
    ap.add_argument("--thermometre-size", type=int, default=400)
    args = ap.parse_args()

    exports = Path(args.exports)
    out_dir = Path(args.out_dir)
    combos = [
        json.loads(l)
        for l in (exports / "pcblues_combos.jsonl").open(encoding="utf-8")
    ]
    prefs = [
        json.loads(l)
        for l in (exports / "pcblues_prefs_graded.jsonl").open(encoding="utf-8")
    ]

    known: set[tuple] = set()
    for p in args.dedup_jnnw:
        k = jnnw_keys(Path(p))
        print(f"dédup croisée : {p} -> {len(k)} positions connues")
        known |= k

    # ---- 1. canal FEN ----
    lines: list[str] = []
    seen: set[tuple] = set()
    n_dup_internal = n_dup_cross = n_bad = 0
    for c in combos:
        if c.get("dup_of"):
            n_dup_internal += 1
            continue
        try:
            key = fen_key(c["fen_start"])
        except ValueError:
            n_bad += 1
            continue
        if key in seen:
            n_dup_internal += 1
            continue
        seen.add(key)
        if key in known:
            n_dup_cross += 1
            continue
        prov = (
            f"deel {c['deel']} p{c['page']}"
            + (f" {c['players']}" if c.get("players") else "")
            + (f" {c['year']}" if c.get("year") else "")
        )
        # players peut contenir sauts de ligne / '#' (extraction de prose)
        prov = " ".join(prov.replace("#", " ").split())
        first = c["seq_moves"][0] if c["seq_moves"] else "?"
        lines.append(f"{c['fen_start']}  # {c['id']} | {prov} | 1er coup {first}")

    combos_fen = out_dir / "pcblues_combos.fen"
    with combos_fen.open("w", encoding="utf-8") as fh:
        fh.write(
            f"# {len(lines)} combinaisons certifiées-jouées PC Blues "
            f"(export dilf {EXPORT_TAG}, verified=true par re-jeu FMJD).\n"
            f"# Dédup : {n_dup_internal} internes, {n_dup_cross} déjà dans les "
            f"corpus jnnw, {n_bad} FEN invalides. Trait au camp indiqué "
            f"(celui qui a la combinaison).\n"
            f"# © Piens Christiaan — usage interne entraînement/QA.\n"
        )
        fh.write("\n".join(lines) + "\n")
    print(f"1. {combos_fen} : {len(lines)} positions "
          f"({n_dup_internal} dup internes, {n_dup_cross} dup croisées écartées)")

    # ---- 2. thermomètre FIGÉ ----
    # Sélection déterministe : mainlines (non-variantes) avec provenance
    # complète (joueurs+année), 4-10 plies, triées par (deel, page, id),
    # au plus 8 par volume — puis cap global. FIGÉ : ne JAMAIS regénérer
    # avec d'autres critères sous le même nom de fichier (bump _v2 sinon).
    cands = [
        c
        for c in combos
        if not c.get("dup_of")
        and not c.get("variation")
        and c.get("players")
        and c.get("year")
        and 4 <= len(c["seq_moves"]) <= 10
        and not c.get("dropped_tokens")
    ]
    cands.sort(key=lambda c: (c["deel"], c["page"], c["id"]))
    per_deel: dict[int, int] = {}
    thermo: list[dict] = []
    for c in cands:
        if per_deel.get(c["deel"], 0) >= 8 or len(thermo) >= args.thermometre_size:
            continue
        per_deel[c["deel"]] = per_deel.get(c["deel"], 0) + 1
        thermo.append(c)
    thermo_fen = out_dir / "pcblues_thermometre.fen"
    with thermo_fen.open("w", encoding="utf-8") as fh:
        fh.write(
            f"# THERMOMETRE pcblues-thermo-v1 — {len(thermo)} positions FIGÉES "
            f"(instrument lignée from-scratch, JAMAIS entraînement).\n"
            f"# Sélection déterministe : mainlines vérifiées, provenance "
            f"complète, 4-10 plies, <=8/volume, tri (deel,page,id).\n"
        )
        for c in thermo:
            prov = " ".join(f"{c['players']} {c['year']}".replace("#", " ").split())
            fh.write(
                f"{c['fen_start']}  # {c['id']} | deel {c['deel']} | "
                f"{prov} | sol {' '.join(c['seq_moves'][:3])}…\n"
            )
    print(f"2. {thermo_fen} : {len(thermo)} positions figées (pcblues-thermo-v1)")

    # ---- 3. prefs TSV ----
    prefs_tsv = out_dir / "pcblues_prefs_graded.tsv"
    n_pos = n_neg = 0
    with prefs_tsv.open("w", encoding="utf-8") as fh:
        fh.write("# fen\tmove_played\tgrade\tsource\n")
        for p in prefs:
            g = p["grade"]
            if g in ("!", "!!"):
                n_pos += 1
            elif g in ("?", "??"):
                n_neg += 1
            src = " ".join(f"deel{p['deel']}:p{p['page']}".split())
            fh.write(f"{p['fen']}\t{p['move_played']}\t{g}\t{src}\n")
    print(
        f"3. {prefs_tsv} : {len(prefs)} prefs ({n_pos} positives !/!!, "
        f"{n_neg} négatives ?/?? — préférence à inverser in-job, cf mémo)"
    )

    # Round-trip write -> read (règle smoke-test des formats).
    reread = [
        l for l in combos_fen.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    ]
    assert len(reread) == len(lines)
    for l in reread[:50]:
        fen_to_bitboards(l.split("#", 1)[0].strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
