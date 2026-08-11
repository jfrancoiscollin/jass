"""Evaluation LINEAIRE sur buckets de patterns plies — l'archi de production.

Couche 3 de l'ecart : la production n'a PAS de tete de politique. C'est une
EVALUATION, et les coups sortent de la recherche. Tant qu'un modele porte une
tete policy il ne peut pas avoir la taille d'un modele de patterns — elle
multiplie tout par les 72 actions (mesure : 1 323 344 parametres contre 18 128
en valeur seule, soit 98,6 % du modele).

CE QUE FAIT CE MODULE.
  - `PatternEval` : une valeur, lineaire sur les classes de buckets PLIEES. Le
    joueur au trait fait partie de l'index plie exact ; les plies reversibles
    restent un extra invariant. Aucune couche cachee, aucune non-linearite hors
    du `tanh` final de sortie -- qui borne la valeur dans [-1, 1] et ne cree pas
    de capacite.
  - `greedy_answer` : la « reponse » du modele au sens de la production, c'est
    le coup obtenu en evaluant les ENFANTS et en prenant le meilleur. Pas
    l'argmax d'une tete auxiliaire.

⚠️ POURQUOI CETTE SECONDE PARTIE COMPTE AUTANT QUE LA PREMIERE. Tous les jalons
precedents mesuraient la politique par l'argmax des logits d'une tete entrainee
a part. Une evaluation valeur-seule n'en a pas : sa reponse EST le coup que la
recherche joue. Mesurer autre chose reviendrait a noter un moteur sur une sortie
qu'il n'utilise pas.
"""
from __future__ import annotations

import numpy as np
import torch
from torch import nn

from .game_graph import GameGraph
from .patterns import (
    PLAYABLE,
    PatternSet,
    STATES_PER_SQUARE,
    perspective_fold_map,
)


class PatternEval(nn.Module):
    """Valeur = somme de poids lus dans des tables indexees par conjonctions."""

    def __init__(
        self, pattern_set: PatternSet, include_reversible_plies: bool = True
    ) -> None:
        super().__init__()
        self.pattern_set = pattern_set
        self.include_reversible_plies = bool(include_reversible_plies)
        self.extras = int(self.include_reversible_plies)
        classes = perspective_fold_map(pattern_set)
        # Renumerotation compacte : `perspective_fold_map` rend le representant
        # de chaque classe, pas un indice dense. Sans ca on allouerait un poids
        # par couple (trait, bucket) et le pli n'economiserait aucun parametre.
        unique, compact = np.unique(classes, return_inverse=True)
        self.class_count = int(unique.size)
        self.register_buffer(
            "bucket_class", torch.from_numpy(compact.astype(np.int64))
        )
        sizes = [len(p) for p in pattern_set.patterns]
        self.register_buffer(
            "pattern_squares",
            torch.tensor(
                [list(p) + [0] * (max(sizes) - len(p)) for p in pattern_set.patterns],
                dtype=torch.long,
            ),
        )
        self.register_buffer(
            "pattern_mask",
            torch.tensor(
                [[1] * len(p) + [0] * (max(sizes) - len(p)) for p in pattern_set.patterns],
                dtype=torch.bool,
            ),
        )
        self.register_buffer(
            "pattern_offset",
            torch.tensor(list(pattern_set.offsets), dtype=torch.long),
        )
        self.bucket_count = pattern_set.bucket_count
        self.bucket_weight = nn.Parameter(torch.zeros(self.class_count))
        self.extra_weight = nn.Parameter(torch.zeros(self.extras))
        self.bias = nn.Parameter(torch.zeros(1))
        # Les consommateurs (entrainement, evaluation, recherche) doivent pouvoir
        # DEMANDER si ce modele a une politique, plutot que de le deviner.
        self.value_only = True

    def parameter_total(self) -> int:
        return self.class_count + self.extras + 1

    def _buckets(self, features: torch.Tensor) -> torch.Tensor:
        count = features.shape[0]
        planes = features[:, : 4 * PLAYABLE].reshape(count, 4, PLAYABLE)
        weights = torch.arange(
            1, 5, device=features.device, dtype=features.dtype
        ).reshape(1, 4, 1)
        states = (planes * weights).sum(dim=1).long()          # (N, cases)
        squares = self.pattern_squares                          # (P, kmax)
        picked = states[:, squares]                             # (N, P, kmax)
        picked = torch.where(self.pattern_mask, picked, torch.zeros_like(picked))
        index = torch.zeros(
            count, squares.shape[0], dtype=torch.long, device=features.device
        )
        for position in range(squares.shape[1]):
            live = self.pattern_mask[:, position]
            index = torch.where(
                live.unsqueeze(0),
                index * STATES_PER_SQUARE + picked[:, :, position],
                index,
            )
        return index + self.pattern_offset.unsqueeze(0)

    def raw_score(self, features: torch.Tensor) -> torch.Tensor:
        """Return the additive score before the final bounding ``tanh``.

        Keeping this operation explicit lets training-only experiments split a
        PatternEval into independently optimised additive components, then fold
        those components back into one ordinary production-shaped evaluator.
        """
        buckets = self._buckets(features)
        side = features[:, 4 * PLAYABLE]
        if torch.any((side != 0) & (side != 1)):
            raise ValueError("side-to-move feature must be exactly zero or one")
        augmented = buckets + side.long().unsqueeze(1) * self.bucket_count
        classes = self.bucket_class[augmented]                  # (N, P)
        total = self.bucket_weight[classes].sum(dim=1)
        if self.include_reversible_plies:
            reversible = features[:, 4 * PLAYABLE + 1 : 4 * PLAYABLE + 2]
            total = total + reversible @ self.extra_weight
        total = total + self.bias
        return total

    def forward(self, features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        value = torch.tanh(self.raw_score(features))
        # Les appelants historiques attendent `(value, logits)`. Une evaluation
        # n'a pas de logits : on rend des zeros, ce qui donne une politique
        # UNIFORME sur les coups legaux si quelqu'un s'en sert -- et les
        # consommateurs qui comptent lisent `value_only` pour ne pas s'en servir.
        logits = torch.zeros(
            features.shape[0], 72, device=features.device, dtype=value.dtype
        )
        return value, logits


def greedy_answer(
    model: nn.Module, graph: GameGraph, tensors: dict[str, torch.Tensor],
    state_ids: np.ndarray, batch_size: int = 4096,
) -> np.ndarray:
    """Le coup que joue une evaluation : le meilleur enfant, a un pli.

    C'est la reponse au sens de la production — descendre d'un pli, evaluer les
    enfants, prendre le meilleur — et non l'argmax d'une tete auxiliaire.
    La valeur d'un enfant est vue du camp adverse, donc on la NIE pour la
    ramener au point de vue du joueur au trait.

    ⚠️ UN ENFANT TERMINAL NE SE DEMANDE PAS AU MODELE. `negamax` rend le
    resultat de la REGLE des qu'un noeud est termine (`search.py`), et une
    evaluation apprise qui contredirait la regle sur une position finie
    fabriquerait un ecart qui n'existe pas dans la recherche. On lit donc
    `terminal_value` sur ces enfants-la, exactement comme la recherche.

    Les etats sans coup legal (donc termines) rendent `-1` : ils n'ont pas de
    reponse, et l'appelant les EXCLUT plutot que de les compter comme des
    erreurs.
    """
    model.eval()
    chosen = np.full(state_ids.size, -1, dtype=np.int64)
    with torch.no_grad():
        for start in range(0, state_ids.size, batch_size):
            block = state_ids[start : start + batch_size]
            owners: list[int] = []
            actions: list[int] = []
            children: list[int] = []
            for position, state_id in enumerate(block):
                for action in graph.legal_actions(int(state_id)):
                    owners.append(start + position)
                    actions.append(int(action))
                    children.append(
                        int(graph.action_children[int(state_id), int(action)])
                    )
            if not children:
                continue
            owner = np.asarray(owners, dtype=np.int64)
            action = np.asarray(actions, dtype=np.int64)
            child = np.asarray(children, dtype=np.int64)
            score = np.empty(child.size, dtype=np.float64)
            over = graph.terminal_status[child] != 0
            if np.any(over):
                score[over] = [
                    -graph.terminal_value(int(node)) for node in child[over]
                ]
            if np.any(~over):
                index = torch.from_numpy(child[~over])
                values, _ = model(tensors["features"][index])
                score[~over] = -values.numpy().astype(np.float64)
            # Egalites tranchees par l'ACTION LA PLUS PETITE : sans cet ordre
            # total deterministe, deux runs identiques pourraient repondre
            # differemment et le banc perdrait sa reproductibilite.
            order = np.lexsort((action, -score, owner))
            first = np.ones(order.size, dtype=bool)
            first[1:] = owner[order][1:] != owner[order][:-1]
            chosen[owner[order][first]] = action[order][first]
    return chosen


def greedy_metrics(
    model: nn.Module, graph: GameGraph, oracle, tensors: dict[str, torch.Tensor],
    state_ids: np.ndarray, batch_size: int = 4096,
) -> dict[str, float | int | None]:
    """Note le modele sur le coup qu'il JOUE, contre l'oracle.

    `zero_regret_rate` est la reponse a « le coup choisi perd-il quelque chose ? »
    et c'est la mesure primaire ; `top1_optimal_rate` dit si le coup appartient a
    l'ensemble optimal. Les deux different quand plusieurs coups sont a regret
    nul sans etre tous marques optimaux.
    """
    chosen = greedy_answer(model, graph, tensors, state_ids, batch_size)
    playable = chosen >= 0
    if not np.any(playable):
        return {"count": 0, "zero_regret_rate": None, "top1_optimal_rate": None,
                "mean_regret": None}
    states = state_ids[playable]
    actions = chosen[playable]
    children = oracle.action_children[states, actions]
    regret = oracle.values[states].astype(np.int16) - (
        -oracle.values[children]
    ).astype(np.int16)
    return {
        "count": int(states.size),
        "zero_regret_rate": float((regret == 0).mean()),
        "top1_optimal_rate": float(oracle.optimal_mask[states, actions].mean()),
        "mean_regret": float(regret.mean()),
    }
