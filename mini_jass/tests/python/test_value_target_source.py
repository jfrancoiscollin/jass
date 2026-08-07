"""`value_target_source` : l'ablation à étiquettes d'oracle, et ses garde-fous.

Motivation. M13 (20 graines appariées) laisse la tête de VALEUR sans progrès à
L2 (`mean_development_value_sign_delta = -0,0051`) pendant que la POLITIQUE
progresse des deux côtés (`+0,0222` / `+0,0219`). Or la qualité des deux cibles
n'a pas chuté de la même façon entre L1 et L2 :

    cible valeur     86,29 % (L1, M8)  ->  70,98 % (L2, M13)   -15,31 pts
    cible politique  91,94 % (L1, M8)  ->  88,99 % (L2, M13)    -2,95 pts

À nombre d'échantillons identique pour les deux têtes, ce n'est donc pas de la
famine de données mais un défaut propre à la cible de valeur. L'ablation
remplace cette cible par le label EXACT du solveur, tout le reste gelé, et
tranche entre « bruit d'étiquetage » et « ce n'est pas la donnée ».

⚠️ Un bras `exact_oracle` n'est JAMAIS promouvable : il consomme des labels
qu'aucune boucle de self-play ne peut produire. Ces tests verrouillent surtout
les frontières -- défaut inchangé, aucune fuite hors cohorte d'entraînement,
générateur laissé aveugle, et cible de politique intacte.
"""
import numpy as np
import pytest

from mini_jass_lab.loop import VALUE_TARGET_SOURCES
from mini_jass_lab.replay import ReplaySample


def _relabel(samples, exact_values):
    """Reproduit la transformation telle qu'elle est écrite dans execute_loop."""
    from dataclasses import replace

    rebuilt, changed = [], 0
    for sample in samples:
        exact = float(exact_values[sample.state_id])
        if exact != sample.value_target:
            changed += 1
        rebuilt.append(replace(sample, value_target=exact))
    return rebuilt, changed


def _sample(state_id, value_target, policy=None):
    return ReplaySample(
        state_id=state_id,
        value_target=value_target,
        policy_target=np.zeros(3, dtype=np.float32) if policy is None else policy,
        generation=1,
        game_id=0,
        ply=0,
    )


def test_only_two_sources_are_accepted():
    assert VALUE_TARGET_SOURCES == ("selfplay_outcome", "exact_oracle")


def test_unknown_source_is_refused():
    """Fail-closed : un nom mal orthographié ne doit pas retomber sur un défaut."""
    from mini_jass_lab import loop

    with pytest.raises(ValueError, match="unknown value-target source"):
        loop.execute_loop({}, None, np.array([]), value_target_source="oracle")


def test_relabel_makes_the_exact_rate_one_by_construction():
    """Le contrôle de bout en bout : c'est la définition de value_exact_rate."""
    exact = np.array([1.0, -1.0, 0.0, 1.0], dtype=np.float32)
    samples = [_sample(0, -1.0), _sample(1, -1.0), _sample(2, 1.0), _sample(3, 1.0)]
    rebuilt, changed = _relabel(samples, exact)

    state_ids = np.asarray([s.state_id for s in rebuilt], dtype=np.int64)
    targets = np.asarray([s.value_target for s in rebuilt], dtype=np.float32)
    assert float(np.mean(targets == exact[state_ids])) == 1.0
    # 2 des 4 étaient déjà justes : le compteur mesure le bruit, pas le volume
    assert changed == 2


def test_relabel_leaves_the_policy_target_untouched():
    """Le facteur isolé est la VALEUR ; toucher la politique en ferait deux."""
    policy = np.array([0.2, 0.5, 0.3], dtype=np.float32)
    exact = np.array([1.0], dtype=np.float32)
    rebuilt, _ = _relabel([_sample(0, -1.0, policy)], exact)
    np.testing.assert_array_equal(rebuilt[0].policy_target, policy)


def test_relabel_preserves_every_other_field():
    exact = np.array([0.0, 0.0], dtype=np.float32)
    original = ReplaySample(
        state_id=1, value_target=1.0, policy_target=np.zeros(3, dtype=np.float32),
        generation=7, game_id=42, ply=13,
    )
    rebuilt, _ = _relabel([original], exact)
    assert (rebuilt[0].generation, rebuilt[0].game_id, rebuilt[0].ply) == (7, 42, 13)
    assert rebuilt[0].state_id == 1


def test_relabel_does_not_mutate_the_source_samples():
    """ReplaySample est frozen : all_samples doit garder les labels du GÉNÉRATEUR.

    Sinon le diagnostic de qualité de cible rapporterait 100 % dans le bras
    oracle et le contraste perdrait son contrôle.
    """
    exact = np.array([1.0], dtype=np.float32)
    original = _sample(0, -1.0)
    rebuilt, _ = _relabel([original], exact)
    assert original.value_target == -1.0
    assert rebuilt[0].value_target == 1.0
    assert rebuilt[0] is not original


def test_changed_count_is_zero_when_targets_already_exact():
    """Un corpus parfait rend l'ablation inerte : c'est le témoin de non-effet."""
    exact = np.array([1.0, -1.0], dtype=np.float32)
    samples = [_sample(0, 1.0), _sample(1, -1.0)]
    rebuilt, changed = _relabel(samples, exact)
    assert changed == 0
    assert [s.value_target for s in rebuilt] == [1.0, -1.0]


def test_default_core_is_untouched_so_historical_hashes_survive():
    """`execution_hash = _digest(core)` couvre TOUT le dict.

    Ajouter les champs de l'ablation inconditionnellement changerait le hash de
    chaque run historique, et `expected_m12_result_hash` -- que la config M13
    verifie -- cesserait d'etre reproductible. Sous le defaut, `core` ne doit
    donc contenir AUCUN champ nouveau.
    """
    import inspect

    from mini_jass_lab import loop

    source = inspect.getsource(loop.execute_loop)
    guard = source.index('if value_target_source != "selfplay_outcome":')
    digest = source.index('core["execution_hash"] = _digest(core)')
    # les champs ne sont ecrits qu'entre la garde et le digest
    assert guard < digest
    for field in ('"value_target_source"', '"value_target_relabel"',
                  '"exact_oracle_wdl"',
                  '"development_promotion_gate_and_value_target_relabel"'):
        assert source.count(field) == 1, field
        assert guard < source.index(field) < digest, field


def test_exact_oracle_arm_is_marked_non_promotable():
    """Un bras qui lit le solveur ne doit jamais pouvoir etre pris pour un champion."""
    import inspect

    from mini_jass_lab import loop

    source = inspect.getsource(loop.execute_loop)
    assert '"promotable": False' in source

