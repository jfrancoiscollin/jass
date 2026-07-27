#!/usr/bin/env python3
"""Test séquentiel du rapport de vraisemblance (SPRT) pour les gates L3.

Motivation, mesurée sur cette campagne : le coût d'un readout à `n` fixe croît
en `1/effet²`. Établir `+10 Elo` demande ~4 800 parties par cellule, `+5 Elo`
~19 200, `+3 Elo` ~53 000. À ce rythme la validation coûte bientôt plus cher
que l'entraînement.

Le SPRT arrête dès que le résultat est tranché au lieu de payer le pire cas à
chaque fois. À taux d'erreur égaux il consomme typiquement 2 à 3 fois moins de
parties que le `n` fixe, parce que la plupart des expériences sont soit
clairement gagnantes soit clairement nulles et se résolvent tôt.

Deux modèles de variance :

- **trinomial** — compte W/D/L. Utilisable immédiatement sur nos cellules
  actuelles, qui ne publient que ces trois nombres.
- **pentanomial** — compte les résultats par *paire d'ouvertures jouée aux deux
  couleurs*, soit `{0; 0,5; 1; 1,5; 2}` points sur 2. Notre harnais joue déjà
  en paires appariées (`--pairs 1`), donc ce modèle est le bon dès que les
  cellules publieront le détail par paire. Il réduit la variance en éliminant
  la part de bruit due au tirage de la couleur.

Le LLR utilise l'approximation gaussienne standard (GSPRT) :

    LLR ≈ (n / (2·var)) · (µ1 − µ0) · (2·µ̂ − µ0 − µ1)

Bornes de décision : `log(β/(1−α))` et `log((1−β)/α)`.

Aucun verdict produit ici n'autorise de promotion.
"""
from __future__ import annotations

import argparse
import json
import math
from typing import Any

ACCEPT_H1 = "ACCEPT_H1"
ACCEPT_H0 = "ACCEPT_H0"
CONTINUE = "CONTINUE"


def elo_to_score(elo: float) -> float:
    """Score attendu par partie pour un écart de `elo` points."""
    return 1.0 / (1.0 + 10.0 ** (-elo / 400.0))


def score_to_elo(score: float) -> float:
    if not 0.0 < score < 1.0:
        return 0.0
    return -400.0 * math.log10(1.0 / score - 1.0)


def bounds(alpha: float, beta: float) -> tuple[float, float]:
    if not (0 < alpha < 1 and 0 < beta < 1):
        raise ValueError("alpha et beta doivent être dans ]0;1[")
    return math.log(beta / (1 - alpha)), math.log((1 - beta) / alpha)


def trinomial_stats(wins: int, draws: int, losses: int) -> tuple[int, float, float]:
    """Retourne (n, moyenne du score par partie, variance par partie)."""
    n = wins + draws + losses
    if n <= 0:
        raise ValueError("aucune partie")
    if min(wins, draws, losses) < 0:
        raise ValueError("comptes négatifs")
    mu = (wins + 0.5 * draws) / n
    second = (wins + 0.25 * draws) / n
    return n, mu, max(1e-12, second - mu * mu)


def pentanomial_stats(counts: list[int]) -> tuple[int, float, float]:
    """`counts` = effectifs des paires marquant 0, 0.5, 1, 1.5, 2 points sur 2.

    La moyenne et la variance sont ramenées *par partie* pour rester
    comparables au modèle trinomial.
    """
    if len(counts) != 5:
        raise ValueError("le modèle pentanomial attend exactement 5 effectifs")
    if any(c < 0 for c in counts):
        raise ValueError("comptes négatifs")
    pairs = sum(counts)
    if pairs <= 0:
        raise ValueError("aucune paire")
    values = [0.0, 0.25, 0.5, 0.75, 1.0]  # score moyen par partie de la paire
    mu = sum(c * v for c, v in zip(counts, values)) / pairs
    second = sum(c * v * v for c, v in zip(counts, values)) / pairs
    var_pair = max(1e-12, second - mu * mu)
    # une paire vaut deux parties : la variance par partie est deux fois moindre
    return pairs * 2, mu, var_pair / 2.0


def llr(
    *,
    n: int,
    mu: float,
    var: float,
    elo0: float,
    elo1: float,
) -> float:
    """Log-rapport de vraisemblance généralisé (approximation gaussienne)."""
    mu0, mu1 = elo_to_score(elo0), elo_to_score(elo1)
    if mu1 == mu0:
        raise ValueError("elo0 et elo1 doivent différer")
    return (n / (2.0 * var)) * (mu1 - mu0) * (2.0 * mu - mu0 - mu1)


def verdict(value: float, lower: float, upper: float) -> str:
    if value >= upper:
        return ACCEPT_H1
    if value <= lower:
        return ACCEPT_H0
    return CONTINUE


def evaluate(
    *,
    wins: int | None = None,
    draws: int | None = None,
    losses: int | None = None,
    pentanomial: list[int] | None = None,
    elo0: float = 0.0,
    elo1: float = 5.0,
    alpha: float = 0.05,
    beta: float = 0.05,
) -> dict[str, Any]:
    if pentanomial is not None:
        n, mu, var = pentanomial_stats(pentanomial)
        model = "pentanomial"
    else:
        if wins is None or draws is None or losses is None:
            raise ValueError("fournir W/D/L ou un vecteur pentanomial")
        n, mu, var = trinomial_stats(wins, draws, losses)
        model = "trinomial"
    lower, upper = bounds(alpha, beta)
    value = llr(n=n, mu=mu, var=var, elo0=elo0, elo1=elo1)
    return {
        "schema": 1,
        "model": model,
        "hypotheses": {"elo0": elo0, "elo1": elo1, "alpha": alpha, "beta": beta},
        "n": n,
        "score": round(mu, 6),
        "elo": round(score_to_elo(mu), 2),
        "variance_per_game": round(var, 9),
        "llr": round(value, 4),
        "bounds": {"lower": round(lower, 4), "upper": round(upper, 4)},
        "verdict": verdict(value, lower, upper),
    }


def expected_games(
    *,
    true_elo: float,
    elo0: float,
    elo1: float,
    alpha: float,
    beta: float,
    draw_rate: float = 0.02,
) -> int:
    """Ordre de grandeur du nombre de parties attendu sous `true_elo`.

    Approximation de Wald : `E[n] ≈ E[LLR_final] / E[LLR par partie]`.
    Sert au dimensionnement, pas à la décision.
    """
    lower, upper = bounds(alpha, beta)
    mu = elo_to_score(true_elo)
    var = max(1e-12, mu * (1 - mu) - draw_rate / 4.0)
    per_game = llr(n=1, mu=mu, var=var, elo0=elo0, elo1=elo1)
    if abs(per_game) < 1e-12:
        return 0
    target = upper if per_game > 0 else lower
    return max(1, int(abs(target / per_game)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wins", type=int)
    parser.add_argument("--draws", type=int)
    parser.add_argument("--losses", type=int)
    parser.add_argument(
        "--pentanomial",
        help="cinq effectifs séparés par des virgules : 0,0.5,1,1.5,2 point(s)",
    )
    parser.add_argument("--elo0", type=float, default=0.0)
    parser.add_argument("--elo1", type=float, default=5.0)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--beta", type=float, default=0.05)
    parser.add_argument("--out")
    args = parser.parse_args()

    penta = None
    if args.pentanomial:
        penta = [int(x) for x in args.pentanomial.split(",")]
    report = evaluate(
        wins=args.wins,
        draws=args.draws,
        losses=args.losses,
        pentanomial=penta,
        elo0=args.elo0,
        elo1=args.elo1,
        alpha=args.alpha,
        beta=args.beta,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
