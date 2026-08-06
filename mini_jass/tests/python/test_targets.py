from __future__ import annotations

import numpy as np

from mini_jass_lab.oracle import encode_features, uniform_optimal_targets


def test_feature_encoding_is_normative(synthetic_oracle) -> None:
    features = encode_features(synthetic_oracle)
    assert features.shape == (synthetic_oracle.state_count, 54)
    assert features[0, 6] == 1.0
    assert features[0, 13 + 7] == 1.0
    assert features[1, 52] == 1.0
    assert features[20, 53] == 1.0


def test_policy_target_is_uniform_over_all_optimal_actions(synthetic_oracle) -> None:
    mask = synthetic_oracle.optimal_mask.copy()
    mask[0] = False
    mask[0, [4, 9]] = True
    targets = uniform_optimal_targets(mask)
    assert targets[0, 4] == 0.5
    assert targets[0, 9] == 0.5
    assert np.isclose(targets[0].sum(), 1.0)
