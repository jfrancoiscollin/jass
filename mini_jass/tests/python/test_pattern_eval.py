"""Evaluation lineaire valeur-seule sur buckets plies — la couche 3 de l'archi.

Ces tests verrouillent les deux moities de la couche 3, et la seconde compte
autant que la premiere : (a) le modele est une EVALUATION, sans tete de
politique ; (b) sa « reponse » est le coup que la RECHERCHE joue en descendant
d'un pli, pas l'argmax d'une tete auxiliaire. Un banc qui noterait le modele sur
une sortie qu'il n'utilise pas ne mesurerait rien de transposable.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
import torch
from torch import nn

from mini_jass_lab.game_graph import GameGraph
from mini_jass_lab.pattern_eval import PatternEval, greedy_answer, greedy_metrics
from mini_jass_lab.patterns import (
    PLAYABLE,
    SQUARE_ROT180,
    PatternSet,
    bucket_indices,
    folded_class_count,
    square_states,
)


def _raw(pieces: dict[int, int], side: float = 0.0, reversible: float = 0.0):
    row = np.zeros((1, 4 * PLAYABLE + 2), dtype=np.float32)
    for square, plane in pieces.items():
        row[0, plane * PLAYABLE + square] = 1.0
    row[0, 4 * PLAYABLE] = side
    row[0, 4 * PLAYABLE + 1] = reversible
    return row


# --------------------------------------------------------------------------- #
#  (a) LE MODELE EST UNE EVALUATION.
# --------------------------------------------------------------------------- #
def test_the_parameter_count_is_the_folded_one_not_the_bucket_one():
    """Sans renumerotation compacte, le pli n'economiserait AUCUN parametre.

    `fold_map` rend le representant de chaque classe, pas un indice dense : un
    modele qui allouerait un poids par bucket aurait la taille d'avant le pli
    tout en croyant plier.
    """
    pattern_set = PatternSet.from_window(3)
    model = PatternEval(pattern_set)
    assert model.class_count == folded_class_count(pattern_set)
    assert model.class_count < pattern_set.bucket_count
    assert model.parameter_total() == model.class_count + 2 + 1
    assert sum(p.numel() for p in model.parameters()) == model.parameter_total()


def test_the_value_only_model_is_two_orders_below_a_policy_headed_one():
    """La tete policy pesait 98,6 % du modele : c'est ELLE qu'on retire."""
    pattern_set = PatternSet.from_window(3)
    value_only = PatternEval(pattern_set).parameter_total()
    inputs = pattern_set.bucket_count + 2
    with_policy = inputs + 1 + inputs * 72 + 72
    assert with_policy > 100 * value_only


def test_the_model_declares_itself_value_only_and_returns_no_policy():
    """Les consommateurs doivent pouvoir DEMANDER, pas deviner."""
    model = PatternEval(PatternSet.from_window(2))
    value, logits = model(torch.from_numpy(_raw({0: 0, 6: 1})))
    assert model.value_only is True
    assert logits.shape == (1, 72)
    assert torch.count_nonzero(logits) == 0
    assert value.shape == (1,)


def test_the_torch_bucket_indices_match_the_numpy_reference():
    """Le modele recalcule les buckets en torch : il doit rendre EXACTEMENT ce
    que `bucket_indices` rend, sinon les poids sont lus au mauvais endroit."""
    pattern_set = PatternSet.from_window(3)
    model = PatternEval(pattern_set)
    generator = np.random.default_rng(20260809)
    rows = []
    for _ in range(24):
        row = np.zeros((1, 4 * PLAYABLE + 2), dtype=np.float32)
        for square in range(PLAYABLE):
            if generator.random() < 0.6:
                row[0, generator.integers(0, 4) * PLAYABLE + square] = 1.0
        rows.append(row)
    raw = np.concatenate(rows, axis=0)
    planes = raw[:, : 4 * PLAYABLE].reshape(raw.shape[0], 4, PLAYABLE)
    expected = bucket_indices(square_states(planes), pattern_set)
    produced = model._buckets(torch.from_numpy(raw)).numpy()
    assert np.array_equal(produced, expected)


def test_the_value_is_the_sum_of_one_weight_per_pattern_plus_the_extras():
    """Calcul verifiable a la main : la valeur est une SOMME de poids lus."""
    pattern_set = PatternSet.from_window(2)
    model = PatternEval(pattern_set)
    raw = torch.from_numpy(_raw({0: 0, 6: 1}, side=1.0, reversible=0.5))
    with torch.no_grad():
        model.bucket_weight.fill_(0.0)
        buckets = model._buckets(raw)[0]
        classes = model.bucket_class[buckets]
        # Un poids de 1 sur chaque classe active : la somme vaut le nombre de
        # CLASSES DISTINCTES touchees, deux patterns pouvant partager la leur.
        model.bucket_weight[classes] = 1.0
        model.extra_weight[0] = 0.25
        model.extra_weight[1] = 0.5
        model.bias.fill_(-0.125)
        total = float(len(set(classes.tolist()))) + 0.25 * 1.0 + 0.5 * 0.5 - 0.125
        value, _ = model(raw)
    assert float(value[0]) == pytest.approx(np.tanh(total), abs=1e-6)


def test_a_position_and_its_rot180_colour_swap_image_share_their_weights():
    """Le pli exact, VU PAR LE MODELE : les deux positions doivent lire la meme
    somme de poids. C'est ce que +17,1 Elo a achete a L3."""
    pattern_set = PatternSet.from_window(2)
    model = PatternEval(pattern_set)
    pieces = {0: 0, 6: 1, 9: 2, 12: 3}
    # plan p -> etat p+1 -> etat echange -> plan ; (0,1,2,3) -> (1,0,3,2).
    swap = {0: 1, 1: 0, 2: 3, 3: 2}
    image = {SQUARE_ROT180[square]: swap[plane] for square, plane in pieces.items()}
    with torch.no_grad():
        torch.manual_seed(20260809)
        model.bucket_weight.copy_(torch.randn(model.class_count))
        direct, _ = model(torch.from_numpy(_raw(pieces)))
        mirrored, _ = model(torch.from_numpy(_raw(image)))
    assert float(direct[0]) == pytest.approx(float(mirrored[0]), abs=1e-6)


# --------------------------------------------------------------------------- #
#  (b) LA REPONSE EST LE COUP QUE JOUE LA RECHERCHE.
# --------------------------------------------------------------------------- #
class _Scored(nn.Module):
    """Evaluation dont la valeur d'un etat est donnee a la main."""

    def __init__(self, values: dict[int, float], features: np.ndarray) -> None:
        super().__init__()
        self.value_only = True
        self.table = values
        # Chaque etat est identifie par sa premiere feature, mise a son id.
        self.features = features

    def forward(self, features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        ids = features[:, 0].to(torch.int64).tolist()
        values = torch.tensor([self.table[i] for i in ids], dtype=torch.float32)
        return values, torch.zeros((features.shape[0], 72))


def _graph(edges: dict[int, dict[int, int]], status: dict[int, int], count: int):
    """Petit graphe conforme aux regles, sans encombrer chaque test.

    `GameGraph.validate` exige qu'un etat sans coup legal soit declare termine :
    tout etat NON declare tel recoit donc une sortie vers un puits terminal.
    C'est ce qui permet a un enfant d'etre EN COURS -- et donc evalue par le
    modele -- au lieu d'etre lu dans les regles.
    """
    edges = {parent: dict(moves) for parent, moves in edges.items()}
    sink = count
    terminal = dict(status)
    terminal[sink] = 1
    for state in range(sink):
        if state not in terminal and not edges.get(state):
            edges[state] = {0: sink}
    total = sink + 1
    features = np.zeros((total, 54), dtype=np.float32)
    features[:, 0] = np.arange(total)
    legal = np.zeros((total, 72), dtype=np.bool_)
    children = np.full((total, 72), -1, dtype=np.int32)
    for parent, moves in edges.items():
        for action, child in moves.items():
            legal[parent, action] = True
            children[parent, action] = child
    terminal_status = np.zeros(total, dtype=np.uint8)
    for state, value in terminal.items():
        terminal_status[state] = value
    graph = GameGraph(features, legal, children, terminal_status)
    graph.validate()
    return graph, {"features": torch.from_numpy(features)}


def test_the_answer_is_the_best_child_with_the_child_value_negated():
    """La valeur d'un enfant est vue du camp adverse : sans la negation, le
    modele choisirait systematiquement le coup qui l'arrange le MOINS."""
    graph, tensors = _graph({0: {5: 1, 9: 2}}, {}, 3)
    # L'enfant 1 est bon POUR L'ADVERSAIRE, l'enfant 2 est mauvais pour lui.
    model = _Scored({1: 0.9, 2: -0.9}, graph.features)
    chosen = greedy_answer(model, graph, tensors, np.asarray([0]))
    assert chosen.tolist() == [9]


def test_a_terminal_child_is_read_from_the_rules_not_from_the_model():
    """`negamax` rend le resultat de la REGLE des qu'un noeud est termine. Une
    evaluation qui contredirait la regle sur une position finie fabriquerait un
    ecart que la recherche ne connait pas."""
    # L'enfant 1 est une DEFAITE pour celui qui doit y jouer, donc un GAIN pour
    # nous ; le modele, lui, le declare desastreux. La regle doit gagner.
    graph, tensors = _graph({0: {3: 1, 7: 2}}, {1: 1}, 3)
    model = _Scored({1: 1.0, 2: -0.5}, graph.features)
    chosen = greedy_answer(model, graph, tensors, np.asarray([0]))
    assert chosen.tolist() == [3]


def test_ties_are_broken_by_the_smallest_action_so_two_runs_agree():
    graph, tensors = _graph({0: {11: 1, 4: 2, 30: 3}}, {}, 4)
    model = _Scored({1: 0.25, 2: 0.25, 3: 0.25}, graph.features)
    first = greedy_answer(model, graph, tensors, np.asarray([0]))
    second = greedy_answer(model, graph, tensors, np.asarray([0]))
    assert first.tolist() == [4]
    assert np.array_equal(first, second)


def test_batching_never_changes_the_answer():
    """Le decoupage en lots est une optimisation, pas une decision."""
    edges = {state: {2: 4, 5: 5} for state in range(4)}
    graph, tensors = _graph(edges, {}, 6)
    model = _Scored({4: -0.5, 5: 0.5}, graph.features)
    states = np.asarray([0, 1, 2, 3])
    whole = greedy_answer(model, graph, tensors, states, batch_size=64)
    split = greedy_answer(model, graph, tensors, states, batch_size=1)
    assert np.array_equal(whole, split)
    assert whole.tolist() == [2, 2, 2, 2]


def test_a_state_with_no_legal_move_has_no_answer_and_is_excluded():
    """Un etat termine n'a pas de reponse : le compter comme une erreur
    gonflerait artificiellement le regret."""
    graph, tensors = _graph({0: {1: 2}}, {1: 2}, 3)
    model = _Scored({2: 0.0}, graph.features)
    chosen = greedy_answer(model, graph, tensors, np.asarray([1, 0]))
    assert chosen[0] == -1
    assert chosen[1] == 1


@dataclass
class _Oracle:
    values: np.ndarray
    optimal_mask: np.ndarray
    action_children: np.ndarray


def test_the_metrics_score_the_move_the_model_actually_plays():
    """`zero_regret_rate` est la mesure primaire : le coup joue perd-il quelque
    chose ? Elle se calcule sur le coup CHOISI, contre l'oracle."""
    graph, tensors = _graph({0: {3: 1, 8: 2}}, {}, 3)
    model = _Scored({1: -1.0, 2: 1.0}, graph.features)      # choisit l'action 3
    optimal = np.zeros(graph.legal_mask.shape, dtype=np.bool_)
    optimal[0, 3] = True
    oracle = _Oracle(
        values=np.asarray([1, -1, 0, 0], dtype=np.int8),
        optimal_mask=optimal,
        action_children=graph.action_children,
    )
    metrics = greedy_metrics(model, graph, oracle, tensors, np.asarray([0]))
    assert metrics["count"] == 1
    assert metrics["zero_regret_rate"] == pytest.approx(1.0)
    assert metrics["top1_optimal_rate"] == pytest.approx(1.0)
    assert metrics["mean_regret"] == pytest.approx(0.0)


def test_a_losing_choice_is_charged_its_full_regret():
    graph, tensors = _graph({0: {3: 1, 8: 2}}, {}, 3)
    model = _Scored({1: 1.0, 2: -1.0}, graph.features)      # choisit l'action 8
    optimal = np.zeros(graph.legal_mask.shape, dtype=np.bool_)
    optimal[0, 3] = True
    oracle = _Oracle(
        values=np.asarray([1, -1, 1, 0], dtype=np.int8),
        optimal_mask=optimal,
        action_children=graph.action_children,
    )
    metrics = greedy_metrics(model, graph, oracle, tensors, np.asarray([0]))
    assert metrics["zero_regret_rate"] == pytest.approx(0.0)
    assert metrics["top1_optimal_rate"] == pytest.approx(0.0)
    assert metrics["mean_regret"] == pytest.approx(2.0)


def test_metrics_on_a_cohort_without_any_playable_state_report_none_not_zero():
    """Aucune mesure n'est preferable a une mesure fausse a 0,0."""
    graph, tensors = _graph({0: {1: 1}}, {1: 1}, 2)
    model = _Scored({}, graph.features)
    oracle = _Oracle(
        values=np.zeros(graph.state_count, dtype=np.int8),
        optimal_mask=np.zeros(graph.legal_mask.shape, dtype=np.bool_),
        action_children=graph.action_children,
    )
    metrics = greedy_metrics(model, graph, oracle, tensors, np.asarray([1]))
    assert metrics["count"] == 0
    assert metrics["zero_regret_rate"] is None
    assert metrics["mean_regret"] is None
