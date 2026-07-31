#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Atlas de points aveugles jugé par Scan — où nos décisions coûtent le plus.

`home-1002` a établi que le résidu contre Scan est de la **marge d'évaluation**,
pas de la vitesse : à temps égal on fait mieux qu'à profondeur égale, et donner
dix fois moins de temps à Scan ne rapporte rien. Ce qu'on n'a jamais su, c'est
*sur quelles positions* la marge se perd. Cet outil le mesure.

Méthode, par position rencontrée dans une partie Jass-contre-Scan :

1. Jass choisit un coup à budget fixé ;
2. Scan choisit un coup depuis la MÊME position, au même budget ;
3. s'ils tombent d'accord, le coût est nul — ce n'est pas un point aveugle ;
4. s'ils diffèrent, Scan **juge les deux enfants** à une profondeur de jugement
   fixe, et le coût est `score(enfant de Scan) − score(enfant de Jass)`, du point
   de vue du joueur au trait. Positif = notre coup est moins bon, dans les
   unités de Scan ;
5. la position est rangée dans un bucket, et les coûts sont agrégés.

Ce que cette mesure est, et n'est pas
-------------------------------------
Scan est utilisé comme **juge**, jamais comme source d'entraînement — c'est le
rôle de thermomètre externe que le registre lui reconnaît. Le coût est exprimé
dans les unités d'évaluation de Scan : il **classe** les buckets, il ne se
convertit pas en Elo.

Trois limites à garder en tête en lisant la sortie :

- Scan n'est pas la vérité, c'est l'avis d'un joueur plus fort. Là où Scan se
  trompe, on étiquette à tort ;
- l'accord ne prouve pas la justesse : les deux moteurs peuvent se tromper
  ensemble, et ces positions sortent du décompte avec un coût nul ;
- l'atlas décrit les points aveugles **dans la distribution qu'on lui donne**.
  Changer le pool d'ouvertures change la réponse.

Aucun verdict, aucune promotion, aucune sélection de modèle.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Les lignes `info` de Scan portent le score pendant la réflexion ; `done` ne
# porte que le coup. Le format exact de Scan 3.1 n'a pas pu être vérifié hors
# des box, donc le motif est tolérant ET la sortie du score est OBLIGATOIRE :
# `ScanJudge.self_check()` refuse de démarrer si aucun score ne peut être lu.
# Mieux vaut un abort au préflight qu'un atlas de zéros silencieux.
SCAN_SCORE_RE = re.compile(r"\bscore\s*[=:]\s*([+-]?\d+(?:\.\d+)?)")


class ScanScoreUnreadable(RuntimeError):
    """Scan n'a pas rendu de score lisible — l'atlas serait vide de sens."""


def extract_scan_score(lines: list[str]) -> float | None:
    """Dernier score annoncé par Scan avant `done`, ou None."""
    for line in reversed(lines):
        m = SCAN_SCORE_RE.search(line)
        if m:
            return float(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Buckets — volontairement peu nombreux et explicables. Un atlas qu'on ne sait
# pas lire ne sert à rien, et des buckets fins sur peu de positions rendent du
# bruit.
# ---------------------------------------------------------------------------
def piece_band(total: int) -> str:
    if total <= 6:
        return "finale_tres_courte_<=6"
    if total <= 12:
        return "finale_7_12"
    if total <= 24:
        return "milieu_13_24"
    return "ouverture_25+"


def king_band(wk: int, bk: int) -> str:
    if wk == 0 and bk == 0:
        return "sans_dame"
    if wk > 0 and bk > 0:
        return "dames_des_deux_cotes"
    return "dames_d_un_seul_cote"


def balance_band(mover_material: int, other_material: int) -> str:
    d = mover_material - other_material
    if d <= -3:
        return "en_retard_3+"
    if d <= -1:
        return "en_retard_1_2"
    if d == 0:
        return "materiel_egal"
    if d <= 2:
        return "en_avance_1_2"
    return "en_avance_3+"


def bucket_of(pos: dict) -> str:
    """`pos` porte les compteurs déjà extraits d'une FEN : men/kings par couleur
    et le trait. Le matériel compte une dame pour trois, comme l'éval."""
    wm, wk, bm, bk = pos["wm"], pos["wk"], pos["bm"], pos["bk"]
    total = wm + wk + bm + bk
    white_mat = wm + 3 * wk
    black_mat = bm + 3 * bk
    mover_mat, other_mat = ((white_mat, black_mat) if pos["stm_white"]
                            else (black_mat, white_mat))
    return "|".join((piece_band(total), king_band(wk, bk),
                     balance_band(mover_mat, other_mat),
                     "capture_forcee" if pos["forced_capture"] else "calme"))


FEN_RE = re.compile(r"^([WB]):(W[^:]*):(B.*)$")


def parse_fen_counts(fen: str) -> dict:
    """Compte men et dames par couleur depuis une FEN FMJD."""
    m = FEN_RE.match(fen.strip())
    if not m:
        raise ValueError(f"FEN illisible : {fen!r}")
    stm, white, black = m.group(1), m.group(2)[1:], m.group(3)[1:]

    def count(side: str) -> tuple[int, int]:
        men = kings = 0
        for tok in (t for t in side.split(",") if t):
            if tok.startswith("K"):
                kings += 1
            else:
                men += 1
        return men, kings

    wm, wk = count(white)
    bm, bk = count(black)
    return {"wm": wm, "wk": wk, "bm": bm, "bk": bk, "stm_white": stm == "W"}


# ---------------------------------------------------------------------------
# Agrégation
# ---------------------------------------------------------------------------
class Atlas:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = defaultdict(
            lambda: {"positions": 0, "disagreements": 0, "cost_sum": 0.0,
                     "cost_max": 0.0, "worst_fen": None})
        self.judged = 0
        self.agreed = 0

    def add(self, bucket: str, fen: str, agreed: bool,
            cost: float | None) -> None:
        row = self.rows[bucket]
        row["positions"] += 1
        if agreed:
            self.agreed += 1
            return
        row["disagreements"] += 1
        if cost is None:
            return
        self.judged += 1
        row["cost_sum"] += cost
        if cost > row["cost_max"]:
            row["cost_max"] = cost
            row["worst_fen"] = fen

    def report(self, min_positions: int) -> dict:
        out = []
        for bucket, r in self.rows.items():
            n = r["positions"]
            out.append({
                "bucket": bucket,
                "positions": n,
                "disagreements": r["disagreements"],
                "disagreement_rate": round(r["disagreements"] / n, 4) if n else None,
                "cost_sum": round(r["cost_sum"], 2),
                # Coût MOYEN PAR POSITION du bucket, pas par désaccord : c'est
                # ce qui classe les points aveugles. Un bucket où l'on est
                # rarement en désaccord mais très cher compte autant qu'un
                # bucket où l'on diverge souvent pour rien.
                "cost_per_position": round(r["cost_sum"] / n, 3) if n else None,
                "cost_max": round(r["cost_max"], 2),
                "worst_fen": r["worst_fen"],
                # En dessous du plancher, on publie la ligne mais on refuse de
                # la classer : trop peu de positions pour signifier quoi que ce
                # soit. La rendre invisible serait pire — on croirait le bucket
                # inexistant.
                "ranked": n >= min_positions,
            })
        ranked = [r for r in out if r["ranked"]]
        ranked.sort(key=lambda r: -r["cost_per_position"])
        return {
            "schema": "l3_scan_blind_spot_atlas",
            "version": 1,
            "positions_seen": sum(r["positions"] for r in self.rows.values()),
            "moves_agreed": self.agreed,
            "disagreements_judged": self.judged,
            "min_positions_to_rank": min_positions,
            "buckets_ranked": ranked,
            "buckets_below_floor": [r for r in out if not r["ranked"]],
            "units": "scan_eval_units_not_elo",
            "scan_is_a_judge_not_ground_truth": True,
            "diagnostic_only": True,
            "gate_authorized": False,
            "promotion_authorized": False,
        }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--samples", required=True, type=Path,
                   help="JSONL produit par le collecteur : une ligne par "
                        "position avec fen, agreed, cost")
    p.add_argument("--min-positions", type=int, default=200,
                   help="plancher pour qu'un bucket soit classé (défaut 200)")
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)

    atlas = Atlas()
    with args.samples.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            counts = parse_fen_counts(rec["fen"])
            counts["forced_capture"] = bool(rec.get("forced_capture"))
            atlas.add(bucket_of(counts), rec["fen"],
                      bool(rec["agreed"]), rec.get("cost"))

    report = atlas.report(args.min_positions)
    if report["positions_seen"] == 0:
        print("scan_blind_spot_atlas: zéro position — échec, pas un atlas vide",
              file=sys.stderr)
        return 2
    if report["disagreements_judged"] == 0:
        print("scan_blind_spot_atlas: aucun désaccord jugé — soit Scan n'a rendu "
              "aucun score lisible, soit les deux moteurs sont d'accord partout. "
              "Les deux méritent un abort plutôt qu'un atlas de zéros.",
              file=sys.stderr)
        return 3
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True,
                                   ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k != "buckets_below_floor"}, ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
