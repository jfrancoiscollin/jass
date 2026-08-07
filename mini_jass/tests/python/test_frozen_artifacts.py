from __future__ import annotations

import json
from pathlib import Path

from mini_jass_lab.experiment import _package_sha256

def test_frozen_m3_artifacts_are_internally_consistent() -> None:
    root = Path(__file__).resolve().parents[2]
    split = json.loads((root / "artefacts/split_manifest.v1.json").read_text(encoding="utf-8"))
    baseline = json.loads((root / "artefacts/m3_baseline.v1.json").read_text(encoding="utf-8"))
    assert split["schema"] == "mini_jass.split_manifest.v1"
    assert split["canonical_state_count"] == 218305
    assert split["raw_state_count"] == 263829
    assert baseline["split_manifest_hash"] == split["manifest_hash"]
    assert baseline["split_assignment_hash"] == split["assignment_hash"]
    assert baseline["model"]["parameter_count"] == 5225
    assert baseline["exact_supervised"]["gate"] == "PASS"
    assert baseline["all_state_fit"]["gate"] == "PASS"
    assert baseline["all_state_fit"]["failed_runs"][0]["gate"] == "FAIL"


def test_m6_artifact_preserves_m5_provenance_and_transfer_gate() -> None:
    root = Path(__file__).resolve().parents[2]
    m5 = json.loads((root / "artefacts/m5_experiment_pack.v1.json").read_text(encoding="utf-8"))
    m6 = json.loads((root / "artefacts/m6_learning_gate.v1.json").read_text(encoding="utf-8"))
    assert m6["schema"] == "mini_jass.m6_learning_gate.v1"
    assert m6["status"] == "PASS"
    assert m6["m5_result_hash"] == m5["result_hash"]
    assert m6["pack"]["run_count"] == 55
    assert m6["pack"]["successful_run_count"] == 55
    assert m6["gate"]["train_split_start_contract"] is True
    assert len(m6["contracts"]["python_package_sha256"]) == 64
    assert m6["scientific_gate"]["status"] == "FAIL"
    assert m6["recommendation"]["decision"] == "continue_L1_policy_gate"
    assert m6["recommendation"]["l2_transfer_authorized"] is False
    assert m6["recommendation"]["direct_10x10_transfer_authorized"] is False


def test_m7_artifact_closes_policy_gate_without_authorizing_transfer() -> None:
    root = Path(__file__).resolve().parents[2]
    m6 = json.loads((root / "artefacts/m6_learning_gate.v1.json").read_text(encoding="utf-8"))
    m7 = json.loads((root / "artefacts/m7_policy_target_gate.v1.json").read_text(encoding="utf-8"))
    assert m7["schema"] == "mini_jass.m7_policy_target_gate.v1"
    assert m7["status"] == "PASS"
    assert m7["m6_result_hash"] == m6["result_hash"]
    assert m7["pack"]["run_count"] == 15
    assert m7["pack"]["successful_run_count"] == 15
    assert m7["gate"]["target_only_causal_contrast"] is True
    assert m7["gate"]["complete_root_action_coverage"] is True
    assert m7["contracts"]["python_package_sha256"] == _package_sha256()
    assert m7["scientific_gate"]["status"] == "PASS"
    assert m7["recommendation"]["decision"] == "rerun_frozen_M6_gate_before_L2"
    assert m7["recommendation"]["l2_transfer_authorized"] is False
    assert m7["recommendation"]["direct_10x10_transfer_authorized"] is False
