#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Collecteur de l'atlas : où nos décisions coûtent, jugées par Scan.

Moitié amont de `scan_blind_spot_atlas.py`, qui n'agrège que. Ici on joue, on
compare, on fait juger — et on écrit un JSONL, une ligne par position.

Protocole, à chaque coup où **Jass** est au trait dans une partie Jass-contre-
Scan :

1. Jass choisit son coup à `--play-depth` ;
2. Scan choisit le sien depuis la MÊME position, à la MÊME profondeur ;
3. accord → coût nul, ce n'est pas un point aveugle, on l'enregistre quand même
   (le dénominateur du taux de désaccord en dépend) ;
4. désaccord → Scan **juge les deux enfants** à `--judge-depth`, et le coût est
   la différence de valeur, du point de vue du joueur au trait.

Convention de signe — la seule chose facile à inverser ici
----------------------------------------------------------
Scan rend son score du point de vue du **camp au trait à la position qu'il
regarde**. Après notre coup, c'est l'adversaire qui est au trait dans l'enfant.
La valeur de notre coup POUR NOUS est donc `-s(enfant)`, d'où :

    valeur_de_notre_coup   = -s(enfant après notre coup)
    valeur_du_coup_de_Scan = -s(enfant après le coup de Scan)
    coût                   = valeur_du_coup_de_Scan - valeur_de_notre_coup

Un coût **positif** veut dire que notre coup est moins bon, dans les unités de
Scan. Une erreur de signe donnerait un atlas exactement à l'envers sans rien
casser de visible, donc le collecteur **compte les coûts négatifs** et le rapport
final le dit : Scan préférant son propre coup, une proportion massive de coûts
négatifs ne peut signifier qu'un signe inversé, pas un résultat.

Ce que ce collecteur n'est pas
------------------------------
Scan est **juge**, jamais source d'entraînement — le rôle de thermomètre externe
que le registre lui reconnaît. Aucune promotion, aucun gate, aucun modèle
sélectionné ici. On écrit des observations ; l'agrégateur les classe.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    """`jobs/tools` n'est pas un package. Le module doit être enregistré dans
    `sys.modules` AVANT `exec_module` : `@dataclass` résout ses annotations via
    `sys.modules[cls.__module__]` et échoue sur un None."""
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_modules():
    cv = _load("calibrate_vs_scan", "jobs/tools/calibrate_vs_scan.py")
    atlas = _load("scan_blind_spot_atlas", "jobs/tools/scan_blind_spot_atlas.py")
    return cv, atlas


# Part de coûts négatifs au-delà de laquelle on refuse de publier. Quelques
# négatifs sont NORMAUX et sains : le juge est plus profond que le joueur, donc
# il lui arrive de préférer notre coup à celui qu'il avait lui-même choisi moins
# loin. Une majorité de négatifs, elle, ne peut pas être un résultat.
MAX_NEGATIVE_COST_SHARE = 0.25


def sign_convention_ok(negative: int, judged: int) -> bool:
    """Scan préfère son propre coup : trop de coûts négatifs = signe inversé."""
    if judged == 0:
        return True          # rien à conclure ; le garde-fou n=0 est ailleurs
    return negative / judged < MAX_NEGATIVE_COST_SHARE


class Collector:
    def __init__(self, cv, atlas, jass_path: str, scan_path: str,
                 pattern: str | None, play_depth: int, judge_depth: int,
                 max_plies: int):
        self.cv, self.atlas = cv, atlas
        self.play_depth, self.judge_depth = play_depth, judge_depth
        self.max_plies = max_plies
        self.jass = cv.JassEngine(jass_path, pattern_path=pattern, label="Jass")
        self.scan = cv.ScanEngine(scan_path, bb_size=0)
        self.referee = cv.Referee(jass_path)
        self.negative_costs = 0
        self.judged = 0
        self.unjudged = 0

    def close(self) -> None:
        for e in (self.jass, self.scan, self.referee):
            try:
                e.close()
            except Exception:
                pass

    def _judge(self, start: str, history: list[str], move) -> float | None:
        """Valeur du coup POUR LE JOUEUR QUI VIENT DE JOUER (signe déjà retourné)."""
        _, lines = self.scan.go_from_verbose(
            start, history + [move.scan_str()], depth=self.judge_depth)
        s = self.atlas.extract_scan_score(lines)
        return None if s is None else -s

    def play_game(self, opening: str, jass_is_white: bool) -> list[dict]:
        """Une partie ; rend les observations aux coups où Jass est au trait."""
        cv = self.cv
        self.referee.set_position_fen(opening)
        self.scan.new_game()
        out: list[dict] = []
        for _ in range(self.max_plies):
            fen = self.referee.current_fen()
            side_white = fen.split(":", 1)[0].strip() == "W"
            jass_to_move = (side_white == jass_is_white)
            start, history = self.referee.scan_pos()

            if jass_to_move:
                self.jass.set_position_fen(fen)
                our = self.jass.go(depth=self.play_depth)
                if our is None:
                    break
                theirs, _ = self.scan.go_from_verbose(
                    start, history, depth=self.play_depth)
                if theirs is None:
                    break
                agreed = (our.frm, our.to, tuple(sorted(our.captures))) == \
                         (theirs.frm, theirs.to, tuple(sorted(theirs.captures)))
                rec = {"fen": fen, "agreed": agreed,
                       "forced_capture": our.is_capture}
                if not agreed:
                    best = self._judge(start, history, theirs)
                    ours = self._judge(start, history, our)
                    if best is None or ours is None:
                        # Scan a joué mais n'a pas rendu de score lisible. On
                        # garde la position comme désaccord NON jugé plutôt que
                        # d'inventer un coût nul, qui se confondrait avec un
                        # accord.
                        self.unjudged += 1
                    else:
                        rec["scan_score_best"] = best
                        rec["scan_score_ours"] = ours
                        rec["cost"] = best - ours
                        self.judged += 1
                        if best - ours < 0:
                            self.negative_costs += 1
                out.append(rec)
                played = our
            else:
                played, _ = self.scan.go_from_verbose(
                    start, history, depth=self.play_depth)
                if played is None:
                    break

            if not self.referee.apply_move(played):
                break
        return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jass", required=True)
    p.add_argument("--scan", required=True)
    p.add_argument("--pattern", default=None, help="éval (.pjtw) de notre moteur")
    p.add_argument("--games", type=int, default=20)
    p.add_argument("--play-depth", type=int, default=8)
    p.add_argument("--judge-depth", type=int, default=10)
    p.add_argument("--max-plies", type=int, default=160)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--time-budget-s", type=float, default=0.0,
                   help="arrêt propre passé ce budget (0 = illimité) ; le JSONL "
                        "déjà écrit reste exploitable")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--progress", type=Path, default=None)
    p.add_argument("--summary", type=Path, default=None)
    args = p.parse_args(argv)

    cv, atlas = load_modules()
    openings = cv.opening_pool_via_jass(args.jass)
    rng = random.Random(args.seed)

    c = Collector(cv, atlas, args.jass, args.scan, args.pattern,
                  args.play_depth, args.judge_depth, args.max_plies)
    started = time.time()
    positions = disagreements = games_played = 0
    stopped_early = False
    try:
        with args.out.open("w", encoding="utf-8") as fh:
            for g in range(args.games):
                if args.time_budget_s and time.time() - started > args.time_budget_s:
                    stopped_early = True
                    break
                opening = openings[rng.randrange(len(openings))]
                # Les deux couleurs, pour que l'atlas ne décrive pas seulement
                # les positions que Jass rencontre en tant que Blanc.
                recs = c.play_game(opening, jass_is_white=(g % 2 == 0))
                for r in recs:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    positions += 1
                    disagreements += (not r["agreed"])
                fh.flush()
                games_played += 1
                # Progress au fil de l'eau (règle 2) : un job long doit pouvoir
                # sortir une première estimation sans attendre le finalize.
                if args.progress and (g % 5 == 0 or g == args.games - 1):
                    el = time.time() - started
                    rate = games_played / el if el > 0 else 0.0
                    args.progress.write_text(json.dumps({
                        "games_played": games_played, "games_target": args.games,
                        "positions": positions, "disagreements": disagreements,
                        "judged": c.judged, "elapsed_s": round(el, 1),
                        "games_per_min": round(rate * 60, 2),
                        "eta_remaining_min": (round((args.games - games_played)
                                                    / rate / 60, 1)
                                              if rate > 0 else None),
                    }, indent=2) + "\n", encoding="utf-8")
    finally:
        c.close()

    elapsed = time.time() - started
    neg_share = (c.negative_costs / c.judged) if c.judged else None
    summary = {
        "schema": "l3_scan_blind_spot_collector",
        "version": 1,
        "games_played": games_played,
        "positions": positions,
        "disagreements": disagreements,
        "judged": c.judged,
        "unjudged_disagreements": c.unjudged,
        "play_depth": args.play_depth,
        "judge_depth": args.judge_depth,
        "elapsed_s": round(elapsed, 1),
        "positions_per_min": round(positions / elapsed * 60, 1) if elapsed else None,
        "stopped_on_time_budget": stopped_early,
        # Garde-fou de signe. Scan préfère son propre coup : une part massive de
        # coûts négatifs ne peut pas être un résultat, seulement un signe inversé.
        "negative_costs": c.negative_costs,
        "negative_cost_share": (round(neg_share, 4) if neg_share is not None
                                else None),
        "sign_convention_ok": sign_convention_ok(c.negative_costs, c.judged),
        "diagnostic_only": True,
        "promotion_authorized": False,
    }
    if args.summary:
        args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True)
                                + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if positions == 0:
        print("collector: zéro position — échec, pas un corpus vide",
              file=sys.stderr)
        return 2
    if c.judged == 0:
        print("collector: aucun désaccord jugé — soit Scan n'a rendu aucun "
              "score lisible, soit accord partout. Les deux méritent un abort.",
              file=sys.stderr)
        return 3
    if not summary["sign_convention_ok"]:
        print(f"collector: {c.negative_costs}/{c.judged} coûts négatifs — "
              "convention de signe probablement inversée, l'atlas serait à "
              "l'envers. Abort.", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
